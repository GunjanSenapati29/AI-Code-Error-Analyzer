import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings

from .services.analysis_service import build_analysis
from .utils.module_scanner import scan_modules, detect_insights
from .utils.security_checker import check_security
from .utils.python_runner import python_command
from .utils.java_runner import java_commands
from .utils.c_runner import c_commands

SESSIONS = {}

MAX_EXECUTION_SECONDS = getattr(settings, "EXECUTION_TIMEOUT", 3600)


class ExecutionSession:
    def __init__(self, *, user_id, group_name, language, code, record):
        self.session_id = str(uuid.uuid4())
        self.user_id = user_id
        self.group_name = group_name
        self.language = language
        self.code = code
        self.record = record
        self.channel_layer = get_channel_layer()

        self.workspace = Path(settings.TEMP_CODE_DIR) / f"user_{user_id}_{self.session_id}"
        self.workspace.mkdir(parents=True, exist_ok=True)

        self.process = None
        self.output_buffer = []
        self.error_buffer = []

        self.start_ts = time.time()
        self.stdin_lock = threading.Lock()
        self.buffer_lock = threading.Lock()
        self.finished = False

        self.stdout_done = threading.Event()
        self.stderr_done = threading.Event()

        self.needs_input = any(flag in self.code for flag in ["input(", "Scanner", "scanf("])

    def send(self, payload):
        async_to_sync(self.channel_layer.group_send)(
            self.group_name,
            {
                "type": "stream.message",
                "payload": payload,
            },
        )

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()
        return self.session_id

    def _emit_terminal(self, text, kind):
        if text is None:
            return
        clean = str(text).replace("\r", "")
        if clean == "":
            return
        self.send({
            "event": "terminal",
            "stream": kind,
            "text": clean,
        })

    def _run(self):
        modules = scan_modules(self.code, self.language)
        blocked = check_security(modules, self.language)
        insights = detect_insights(self.code, self.language)

        self.record.modules = modules
        self.record.blocked_modules = blocked
        self.record.insights = insights
        self.record.save(update_fields=["modules", "blocked_modules", "insights", "updated_at"])

        self.send({
            "event": "modules",
            "modules": modules,
            "blocked_modules": blocked,
            "insights": insights,
        })

        if blocked:
            self._finish_with_analysis("", f'Blocked module(s): {", ".join(blocked)}', "blocked")
            return

        try:
            if self.language == "python":
                self._launch(python_command(self.workspace, self.code))

            elif self.language == "java":
                compile_cmd, run_cmd = java_commands(self.workspace, self.code)
                ok, compile_err = self._compile_step(compile_cmd)
                if not ok:
                    self._finish_with_analysis("", compile_err, "error")
                    return
                self._launch(run_cmd)

            elif self.language == "c":
                compile_cmd, run_cmd = c_commands(self.workspace, self.code)
                ok, compile_err = self._compile_step(compile_cmd)
                if not ok:
                    self._finish_with_analysis("", compile_err, "error")
                    return
                self._launch(run_cmd)

            else:
                self._finish_with_analysis("", f"Unsupported language: {self.language}", "error")

        except FileNotFoundError as exc:
            self._finish_with_analysis("", f"Missing compiler/runtime: {exc}", "error")
        except Exception as exc:
            self._finish_with_analysis("", f"Execution setup failed: {exc}", "error")

    def _compile_step(self, cmd):
        self.send({
            "event": "terminal",
            "stream": "cmd",
            "text": "$ " + " ".join(cmd),
        })

        try:
            proc = subprocess.run(
                cmd,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            return False, "Compilation timed out."

        combined = (proc.stdout or "") + (proc.stderr or "")

        if proc.returncode != 0:
            for line in combined.splitlines() or ["Compilation failed."]:
                self._emit_terminal(line, "error")
            return False, combined

        self._emit_terminal("Compilation successful.", "ok")
        return True, ""

    def _launch(self, cmd):
        self.send({
            "event": "terminal",
            "stream": "cmd",
            "text": "$ " + " ".join(cmd),
        })

        popen_kwargs = {
            "cwd": self.workspace,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 0,
        }

        if os.name != "nt":
            popen_kwargs["preexec_fn"] = os.setsid

        self.process = subprocess.Popen(cmd, **popen_kwargs)
        SESSIONS[self.session_id] = self

        threading.Thread(
            target=self._read_stream,
            args=(self.process.stdout, "out", self.stdout_done),
            daemon=True
        ).start()

        threading.Thread(
            target=self._read_stream,
            args=(self.process.stderr, "error", self.stderr_done),
            daemon=True
        ).start()

        if self.needs_input:
            self.send({"event": "waiting_input", "value": True})
            self._emit_terminal("Program waiting for input...", "info")

        while self.process.poll() is None:
            if time.time() - self.start_ts > MAX_EXECUTION_SECONDS:
                self._terminate()
                self.stdout_done.wait(timeout=1.5)
                self.stderr_done.wait(timeout=1.5)

                with self.buffer_lock:
                    stdout = "".join(self.output_buffer)
                    stderr = "".join(self.error_buffer)

                self._finish_with_analysis(
                    stdout,
                    stderr + f"\nExecution timed out after {MAX_EXECUTION_SECONDS} seconds.",
                    "timeout",
                )
                return

            time.sleep(0.1)

        self.stdout_done.wait(timeout=1.5)
        self.stderr_done.wait(timeout=1.5)

        with self.buffer_lock:
            stdout = "".join(self.output_buffer)
            stderr = "".join(self.error_buffer)

        status = "success" if self.process.returncode == 0 and not stderr.strip() else "error"
        self._finish_with_analysis(stdout, stderr, status)

    def _read_stream(self, stream, kind, done_event):
        try:
            partial = ""
            while True:
                chunk = stream.read(1)
                if not chunk:
                    break

                partial += chunk

                with self.buffer_lock:
                    if kind == "out":
                        self.output_buffer.append(chunk)
                    else:
                        self.error_buffer.append(chunk)

                if chunk == "\n":
                    self._emit_terminal(partial.rstrip("\n"), kind)
                    partial = ""

                    if self.needs_input and kind == "out" and self.process and self.process.poll() is None:
                        self.send({"event": "waiting_input", "value": True})

                elif partial.endswith(": ") or partial.endswith("? ") or partial.endswith("> "):
                    self._emit_terminal(partial, kind)
                    partial = ""

                    if self.needs_input and kind == "out" and self.process and self.process.poll() is None:
                        self.send({"event": "waiting_input", "value": True})

            if partial:
                self._emit_terminal(partial, kind)

                if self.needs_input and kind == "out" and self.process and self.process.poll() is None:
                    self.send({"event": "waiting_input", "value": True})

        finally:
            try:
                stream.close()
            except Exception:
                pass
            done_event.set()

    def provide_input(self, text):
        if not self.process or self.process.poll() is not None or not self.process.stdin:
            return False

        try:
            with self.stdin_lock:
                self.process.stdin.write(text + "\n")
                self.process.stdin.flush()

            self.start_ts = time.time()

            if self.needs_input and self.process.poll() is None:
                self.send({"event": "waiting_input", "value": True})

            return True
        except Exception:
            return False

    def _terminate(self):
        if not self.process or self.process.poll() is not None:
            return

        try:
            if os.name != "nt":
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
            else:
                self.process.terminate()
        except Exception:
            pass

    def _finish_with_analysis(self, stdout, stderr, status):
        if self.finished:
            return

        self.finished = True

        analysis = build_analysis(self.code, self.language, stdout, stderr, status)

        self.record.output = stdout
        self.record.raw_error = stderr
        self.record.error_type = analysis.get("type") or ""
        self.record.explanation = analysis.get("explain", "")
        self.record.corrected_code = analysis.get("fix", self.code)
        self.record.line_number = analysis.get("line")
        self.record.status = status
        self.record.concepts = analysis.get("concepts", [])
        self.record.suggestions = {
            "general": analysis.get("tips", []),
            "optimizations": analysis.get("optimizations", []),
        }
        self.record.insights = {
            "highlights": analysis.get("insights", []),
            "steps": analysis.get("steps", []),
            "viva_answer": analysis.get("viva_answer", ""),
            "root_cause": analysis.get("root_cause", ""),
            "confidence": analysis.get("confidence", "low"),
            "source": analysis.get("source", "rules"),
            "summary": analysis.get("summary", ""),
        }
        self.record.complexity = {
            "time": analysis.get("time"),
            "space": analysis.get("space"),
            "explanation": analysis.get("complexity_explanation", ""),
        }
        self.record.save()

        self.send({
            "event": "complete",
            "record_id": self.record.id,
            "analysis": analysis,
            "status": status,
        })

        self.cleanup()

    def cleanup(self):
        SESSIONS.pop(self.session_id, None)
        shutil.rmtree(self.workspace, ignore_errors=True)


def start_execution(*, user_id, group_name, language, code, record):
    return ExecutionSession(
        user_id=user_id,
        group_name=group_name,
        language=language,
        code=code,
        record=record,
    ).start()


def send_input(session_id, text):
    session = SESSIONS.get(session_id)
    return session.provide_input(text) if session else False


def stop_execution(session_id):
    session = SESSIONS.get(session_id)
    if session:
        session._terminate()
        return True
    return False