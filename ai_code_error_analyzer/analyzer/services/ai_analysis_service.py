import ast
import json
import logging
import re
from json import JSONDecodeError
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def ai_is_configured() -> bool:
    base = str(getattr(settings, "OLLAMA_BASE_URL", "") or "").strip()
    model = str(getattr(settings, "OLLAMA_MODEL", "") or "").strip()
    return bool(base and model)


def _ollama_base() -> str:
    return str(
        getattr(settings, "OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def _ollama_model() -> str:
    return str(
        getattr(settings, "OLLAMA_MODEL", "deepseek-coder:latest")
        or "deepseek-coder:latest"
    ).strip()


def _timeout() -> int:
    return int(getattr(settings, "OLLAMA_TIMEOUT", 90) or 90)


def ai_status() -> dict:
    base = _ollama_base()
    model = _ollama_model()
    status = {
        "configured": ai_is_configured(),
        "reachable": False,
        "model_available": False,
        "base_url": base,
        "model": model,
    }
    if not status["configured"]:
        return status

    try:
        response = requests.get(f"{base}/api/tags", timeout=5)
        response.raise_for_status()
        status["reachable"] = True
        data = response.json()
        names = [
            str(m.get("name", "")).strip().lower()
            for m in data.get("models", [])
            if isinstance(m, dict)
        ]
        requested = model.strip().lower()
        requested_base = requested.split(":")[0]
        status["model_available"] = any(
            name == requested or name.split(":")[0] == requested_base for name in names
        )
    except Exception:
        logger.exception("Unable to fetch Ollama status")

    return status


def _safe_json_loads(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except JSONDecodeError:
        return None


def _safe_text(text: Any, limit: int = 12000) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _clean_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    cleaned: List[str] = []
    for item in value:
        s = str(item or "").strip()
        if s:
            cleaned.append(s)
    return cleaned


def _strip_markdown_fences(text: str) -> str:
    s = str(text or "").strip()
    s = s.replace("```python", "").replace("```json", "").replace("```", "").strip()
    return s


def _extract_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        raise ValueError("Empty AI response")

    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        raw,
        flags=re.IGNORECASE | re.MULTILINE,
    ).strip()

    direct = _safe_json_loads(cleaned)
    if direct:
        return direct

    starts = [m.start() for m in re.finditer(r"\{", cleaned)]
    for start in starts:
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start: i + 1]
                    parsed = _safe_json_loads(candidate)
                    if parsed:
                        return parsed
                    break

    raise ValueError("Could not parse AI response as JSON")


def _python_compile_check(code: str) -> Dict[str, Any]:
    try:
        compile(code, "<user_code>", "exec")
        return {
            "is_valid": True,
            "error_type": "",
            "error_message": "",
            "line_number": None,
            "offset": None,
        }
    except SyntaxError as e:
        return {
            "is_valid": False,
            "error_type": "SyntaxError",
            "error_message": str(e.msg or "Invalid Python syntax"),
            "line_number": e.lineno,
            "offset": e.offset,
        }
    except Exception as e:
        return {
            "is_valid": False,
            "error_type": type(e).__name__,
            "error_message": str(e),
            "line_number": None,
            "offset": None,
        }


def _verify_python_fix(code: str) -> bool:
    try:
        compile(code, "<fixed_code>", "exec")
        return True
    except Exception:
        return False


def _extract_error_line(stderr: str) -> Optional[int]:
    if not stderr:
        return None

    patterns = [
        r'line\s+(\d+)',
        r'File ".*?", line (\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, stderr, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except Exception:
                return None
    return None


def _extract_python_name_error(stderr: str) -> Optional[str]:
    match = re.search(r"name '([^']+)' is not defined", stderr or "")
    return match.group(1) if match else None


def _fallback_name_error_fix(code: str, missing_name: str) -> str:
    placeholder = "0"
    lowered = missing_name.lower()

    if lowered in {"name", "text", "word", "s", "msg"}:
        placeholder = '""'
    elif lowered in {"items", "arr", "nums", "values", "lst"}:
        placeholder = "[]"
    elif lowered in {"data", "obj", "mapping", "config"}:
        placeholder = "{}"

    lines = code.splitlines()
    insert_at = 0
    while insert_at < len(lines):
        stripped = lines[insert_at].strip()
        if not stripped or stripped.startswith("#"):
            insert_at += 1
            continue
        break

    injected = f"{missing_name} = {placeholder}  # added fallback definition"
    new_lines = lines[:insert_at] + [injected] + lines[insert_at:]
    fixed = "\n".join(new_lines)

    try:
        ast.parse(fixed)
        return fixed
    except Exception:
        return code


def sanitize_ai_python_fix(ai_fix: str) -> str:
    if not ai_fix:
        return ""

    text = str(ai_fix).strip()

    fence_match = re.search(r"```(?:python)?\s*([\s\S]*?)```", text, flags=re.I)
    if fence_match:
        text = fence_match.group(1).strip()

    text = re.sub(
        r"^(corrected code|fixed code|here is the corrected code|here's the corrected code)\s*:?\s*",
        "",
        text,
        flags=re.I,
    ).strip()

    return text


def is_valid_python_fix(original_code: str, fixed_code: str) -> (bool, str):
    if not fixed_code or not str(fixed_code).strip():
        return False, "empty"

    fixed = str(fixed_code).strip()

    if "```" in fixed:
        return False, "markdown_fence"

    bad_phrases = [
        "here is the corrected code",
        "this code fixes",
        "explanation:",
        "corrected code:",
        "the fix is",
        "should have been:",
        "it should be:",
        "use this:",
        "change this to:",
    ]
    lower = fixed.lower()
    if any(p in lower for p in bad_phrases):
        return False, "contains_explanation"

    if "exit()" in fixed and "exit()" not in original_code:
        return False, "unsafe_exit"

    try:
        ast.parse(fixed)
    except Exception:
        return False, "not_parseable"

    looks_like_code = re.search(
        r"\b(print|input|def|class|if|for|while|import|from|return|try|except)\b",
        fixed,
    )
    if not looks_like_code and "\n" not in fixed:
        return False, "does_not_look_like_code"

    return True, "ok"


def _looks_like_real_code(text: str, language: str) -> bool:
    s = str(text or "").strip()
    if not s:
        return False

    bad_prefixes = [
        "should have been:",
        "it should be:",
        "use this:",
        "change this to:",
        "here is the corrected code",
        "corrected code:",
    ]
    lowered = s.lower()
    if any(lowered.startswith(p) for p in bad_prefixes):
        return False

    if language.lower() == "python":
        try:
            compile(s, "<candidate_fix>", "exec")
            return True
        except Exception:
            return False

    if language.lower() == "java":
        return any(token in s for token in ["class ", "public static void main", ";", "{", "}"])

    if language.lower() == "c":
        return any(token in s for token in ["#include", "int main", ";", "{", "}"])

    return len(s.splitlines()) >= 2


def _text_fallback_analysis(
    *,
    language: str,
    code: str,
    stdout: str,
    stderr: str,
    status: str,
    raw_ai_text: str = "",
) -> Dict[str, Any]:
    line_focus = _extract_error_line(stderr)
    err = str(stderr or "").strip()

    result: Dict[str, Any] = {
        "is_code_correct": status == "success" and not err,
        "title": "Code analysis",
        "explain": "",
        "root_cause": "",
        "fix": "",
        "tips": [],
        "optimizations": [],
        "concepts": [],
        "steps": [],
        "viva_answer": "",
        "complexity": {"time": "", "space": "", "explanation": ""},
        "line_focus": line_focus,
        "confidence": "medium",
        "model": _ollama_model(),
        "source": "fallback",
    }

    if language.lower() == "python":
        compile_result = _python_compile_check(code)
        if compile_result["is_valid"] and status == "success" and not err:
            result.update(
                {
                    "is_code_correct": True,
                    "title": "Code is correct",
                    "explain": "The Python code ran without syntax or runtime errors.",
                    "root_cause": "No error was detected.",
                    "fix": "",
                    "tips": [
                        "Add comments only where they improve clarity.",
                        "Consider edge-case handling if user input is expected.",
                    ],
                    "optimizations": [],
                    "concepts": ["Python execution flow"],
                    "steps": ["Run additional test cases to verify behavior."],
                    "viva_answer": "The code is correct because it executes without syntax or runtime errors. I would still test multiple inputs to confirm expected behavior.",
                    "confidence": "high",
                }
            )
            return result

        if not compile_result["is_valid"]:
            result.update(
                {
                    "is_code_correct": False,
                    "title": "Python syntax issue",
                    "explain": "The code has a syntax problem, so Python cannot even start execution.",
                    "root_cause": compile_result["error_message"] or "Invalid Python syntax.",
                    "line_focus": compile_result.get("line_number"),
                    "tips": [
                        "Check colons, brackets, indentation, and quotes.",
                        "Fix syntax first before debugging logic.",
                    ],
                    "steps": [
                        "Go to the reported line.",
                        "Check the statement structure carefully.",
                        "Run the code again after correcting the syntax.",
                    ],
                    "viva_answer": "This is a syntax error, which means Python cannot parse the program structure. The code must be syntactically valid before runtime debugging can begin.",
                    "confidence": "high",
                }
            )
            return result

    missing_name = _extract_python_name_error(err) if language.lower() == "python" else None
    if missing_name:
        fixed = _fallback_name_error_fix(code, missing_name)
        result.update(
            {
                "is_code_correct": False,
                "title": "Undefined variable error",
                "explain": f"The variable '{missing_name}' is used before it is defined.",
                "root_cause": f"Python raised NameError because '{missing_name}' does not have any assigned value before it is referenced.",
                "fix": fixed if fixed != code else "",
                "tips": [
                    "Define variables before using them.",
                    "Check for spelling mistakes in variable names.",
                ],
                "optimizations": [],
                "concepts": ["variables", "scope", "NameError"],
                "steps": [
                    f"Find where '{missing_name}' is first used.",
                    f"Define '{missing_name}' before that line.",
                    "Run the code again and check for any remaining undefined variables.",
                ],
                "viva_answer": f"A NameError occurs when Python sees a variable name that has not been defined yet. The fix is to assign a value before using that variable.",
                "confidence": "high",
            }
        )
        return result

    if err:
        result.update(
            {
                "is_code_correct": False,
                "title": "Runtime or execution issue",
                "explain": "The program failed during execution. Check the exact error message and the failing line.",
                "root_cause": err.splitlines()[-1] if err.splitlines() else "Execution failed.",
                "tips": [
                    "Read the last error line first.",
                    "Check variables, input values, and control flow near the failing line.",
                ],
                "concepts": ["runtime error"],
                "steps": [
                    "Identify the line where execution failed.",
                    "Inspect the variables used on that line.",
                    "Correct the issue and run the code again.",
                ],
                "viva_answer": "A runtime error happens after the program starts executing. It usually occurs because of invalid operations, missing values, or bad logic at runtime.",
                "confidence": "medium",
            }
        )
        return result

    result.update(
        {
            "title": "Analysis unavailable",
            "explain": raw_ai_text.strip() or "The AI response could not be parsed, and no specific error details were available.",
            "root_cause": "Unstructured AI output or insufficient error data.",
            "confidence": "low",
        }
    )
    return result


def _normalize_analysis(data: Dict[str, Any], *, code: str, status: str, stderr: str) -> Dict[str, Any]:
    confidence = str(data.get("confidence") or "medium").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    complexity = data.get("complexity") or {}
    if not isinstance(complexity, dict):
        complexity = {}

    line_focus = data.get("line_focus")
    try:
        line_focus = int(line_focus) if line_focus not in (None, "") else None
    except Exception:
        line_focus = None

    is_code_correct = data.get("is_code_correct")
    if isinstance(is_code_correct, str):
        is_code_correct = is_code_correct.strip().lower() == "true"
    elif not isinstance(is_code_correct, bool):
        is_code_correct = status == "success" and not str(stderr or "").strip()

    corrected_code = str(
        data.get("corrected_code")
        or data.get("fixed_code")
        or data.get("fix")
        or ""
    ).strip()

    corrected_code = sanitize_ai_python_fix(corrected_code) if corrected_code else ""

    title = str(data.get("title") or "").strip()
    explanation = str(data.get("explanation") or data.get("explain") or "").strip()
    root_cause = str(data.get("root_cause") or "").strip()

    result = {
        "is_code_correct": is_code_correct,
        "title": title or "Code analysis",
        "explain": explanation,
        "root_cause": root_cause,
        "fix": corrected_code,
        "tips": _clean_list(data.get("suggestions") or data.get("tips")),
        "optimizations": _clean_list(data.get("optimizations")),
        "concepts": _clean_list(data.get("concepts")),
        "steps": _clean_list(data.get("fix_steps") or data.get("debug_steps") or data.get("steps")),
        "viva_answer": str(data.get("viva_answer") or "").strip(),
        "complexity": {
            "time": str(complexity.get("time") or "").strip(),
            "space": str(complexity.get("space") or "").strip(),
            "explanation": str(complexity.get("explanation") or "").strip(),
        },
        "line_focus": line_focus,
        "confidence": confidence,
        "model": _ollama_model(),
        "source": "ollama",
    }

    if result["is_code_correct"]:
        result["fix"] = ""

    return result


def _build_analysis_prompt(*, language: str, code: str, stdout: str, stderr: str, status: str) -> str:
    compile_result = _python_compile_check(code) if language.lower() == "python" else None

    return f"""
If you do not return valid JSON, your response will be discarded.
You are an expert programming debugger and mentor.

You MUST analyze the provided code and execution result ONLY.
Do not ask follow-up questions.
Do not invent bugs that are not present.
Do not praise the code.
Do not give vague advice.
If enough context exists, produce a corrected version of the code.
Prefer a minimal correct fix over a rewrite.

Important rules:
1. Use the exact compiler/runtime error to identify the real root cause.
2. If the code is correct, set "is_code_correct" to true and keep "corrected_code" empty.
3. If the code is wrong, set "is_code_correct" to false and provide corrected_code.
4. corrected_code MUST be the full corrected source code only.
5. corrected_code must not contain explanation text, labels, markdown fences, or phrases like "should have been".
6. If you cannot confidently provide a full corrected program, set corrected_code to an empty string.
7. Mention undefined variables explicitly by name.
8. If the issue is caused by logic flow, explain that clearly.
9. Output STRICT JSON only.
10. Do not wrap JSON in markdown.
11. Every field must be present.
12. Never add exit() unless it already exists in the original code.
13. Preserve the original intent of the program.
14. For beginner input/output programs, keep variables logically connected in corrected_code.

Required JSON schema:
{{
  "is_code_correct": false,
  "title": "short title",
  "root_cause": "clear exact root cause",
  "explanation": "beginner-friendly explanation tied to this exact code",
  "fix_steps": [
    "step 1",
    "step 2",
    "step 3"
  ],
  "corrected_code": "full corrected code or empty string",
  "suggestions": [
    "short practical tip 1",
    "short practical tip 2"
  ],
  "optimizations": [
    "optimization 1"
  ],
  "concepts": [
    "concept 1",
    "concept 2"
  ],
  "viva_answer": "2 to 4 sentence viva-ready answer",
  "complexity": {{
    "time": "O(...) or empty string",
    "space": "O(...) or empty string",
    "explanation": "short explanation"
  }},
  "line_focus": 1,
  "confidence": "high"
}}

corrected_code must be valid source code only. No commentary. No markdown. No labels.

Language: {language}
Execution status: {status}

Python pre-check:
{json.dumps(compile_result, ensure_ascii=False) if compile_result is not None else "not_applicable"}

Code:
{_safe_text(code, 12000)}

Program output:
{_safe_text(stdout, 5000)}

Program error:
{_safe_text(stderr, 5000)}
""".strip()


def analyze_with_ollama(*, language: str, code: str, stdout: str, stderr: str, status: str) -> Dict[str, Any]:
    prompt = _build_analysis_prompt(
        language=language,
        code=code,
        stdout=stdout,
        stderr=stderr,
        status=status,
    )

    payload = {
        "model": _ollama_model(),
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {
            "temperature": getattr(settings, "OLLAMA_TEMPERATURE", 0.15)
        },
    }

    try:
        response = None
        for attempt in range(2):
            try:
                response = requests.post(
                    f"{_ollama_base()}/api/generate",
                    json=payload,
                    timeout=_timeout(),
                )
                response.raise_for_status()
                break
            except Exception:
                if attempt == 1:
                    raise

        data = response.json()

        raw = data.get("response", "")
        if not isinstance(raw, str):
            raw = str(raw)

        raw = raw.strip()

        if not raw:
            logger.warning("Ollama returned empty response")
            result = _text_fallback_analysis(
                language=language,
                code=code,
                stdout=stdout,
                stderr=stderr,
                status=status,
                raw_ai_text="",
            )
        else:
            try:
                parsed = _extract_json(raw)
                result = _normalize_analysis(parsed, code=code, status=status, stderr=stderr)
            except Exception:
                logger.exception("Could not parse Ollama JSON response")
                result = _text_fallback_analysis(
                    language=language,
                    code=code,
                    stdout=stdout,
                    stderr=stderr,
                    status=status,
                    raw_ai_text=raw,
                )

    except requests.exceptions.ConnectionError:
        logger.exception("Could not connect to Ollama")
        result = _text_fallback_analysis(
            language=language,
            code=code,
            stdout=stdout,
            stderr=stderr,
            status=status,
            raw_ai_text="Ollama connection failed",
        )
    except requests.exceptions.Timeout:
        logger.exception("Ollama request timed out")
        result = _text_fallback_analysis(
            language=language,
            code=code,
            stdout=stdout,
            stderr=stderr,
            status=status,
            raw_ai_text="Ollama timeout",
        )
    except Exception:
        logger.exception("Ollama analysis request failed")
        result = _text_fallback_analysis(
            language=language,
            code=code,
            stdout=stdout,
            stderr=stderr,
            status=status,
            raw_ai_text="",
        )

    raw_fix = result.get("fix", "")

    if language.lower() == "python" and raw_fix:
        cleaned_fix = sanitize_ai_python_fix(raw_fix)
        ok, reason = is_valid_python_fix(code, cleaned_fix)

        if ok:
            result["fix"] = cleaned_fix
        else:
            logger.warning("Rejected invalid AI Python fix: %s", reason)
            result["fix"] = ""
            result["confidence"] = "low"
            existing_steps = result.get("steps") or []
            if isinstance(existing_steps, list):
                result["steps"] = existing_steps
            else:
                result["steps"] = []
    elif raw_fix and not _looks_like_real_code(raw_fix, language):
        logger.warning("Rejected non-code AI fix: %r", raw_fix[:200])
        result["fix"] = ""
        result["confidence"] = "low"

    if language.lower() == "python":
        compile_result = _python_compile_check(code)

        if compile_result["is_valid"] and status == "success" and not str(stderr or "").strip():
            result["is_code_correct"] = True
            result["fix"] = ""
            if not result.get("explain"):
                result["explain"] = "The code appears correct. It ran without syntax or runtime errors."
            if not result.get("root_cause"):
                result["root_cause"] = "No error was detected."
            if not result.get("title"):
                result["title"] = "Code is correct"
        elif not compile_result["is_valid"]:
            result["is_code_correct"] = False
            if not result.get("line_focus"):
                result["line_focus"] = compile_result.get("line_number")
            if not result.get("root_cause"):
                result["root_cause"] = compile_result.get("error_message") or "The code has a syntax issue."
            if result.get("fix") and not _verify_python_fix(result["fix"]):
                result["confidence"] = "low"
                result["fix"] = ""

    if result.get("is_code_correct"):
        result["fix"] = ""

    return result


def _build_mentor_prompt(
    *,
    language: str,
    code: str,
    question: str,
    latest_analysis: Dict[str, Any],
    output: str,
    error: str,
    chat_history: List[Dict[str, str]],
) -> str:
    history_lines = []
    for item in chat_history[-8:]:
        role = "Student" if str(item.get("role")) == "user" else "Mentor"
        text = _safe_text(item.get("text", ""), 1200)
        if text:
            history_lines.append(f"{role}: {text}")
    history_blob = "\n".join(history_lines) or "No prior chat history."

    return f"""
You are an expert programming mentor.

STRICT RULES:
- Be concise and structured.
- Do NOT write long paragraphs.
- Use short bullet points.
- Give code only if it is useful.
- Do NOT use markdown fences like ```python or ```.
- Keep the response clean and readable.
- Base the answer only on the provided code, analysis, output, and error.
- Do not ask vague follow-up questions.

Respond in EXACTLY this format:

Answer:
- one or two bullet points

Explanation:
- short point 1
- short point 2
- short point 3

Improved Code:
NONE
or
<plain code only, no markdown fences>

Tips:
- short tip 1
- short tip 2

Context:
Language: {language}

Current code:
{_safe_text(code, 12000)}

Latest analysis:
Title: {_safe_text(latest_analysis.get('title', ''))}
Explanation: {_safe_text(latest_analysis.get('explain', ''))}
Root cause: {_safe_text(latest_analysis.get('root_cause', ''))}
Suggested fix: {_safe_text(latest_analysis.get('fix', ''))}
Debug steps: {_safe_text(latest_analysis.get('steps', ''))}
Viva answer: {_safe_text(latest_analysis.get('viva_answer', ''))}

Latest output:
{_safe_text(output, 3000)}

Latest error:
{_safe_text(error, 3000)}

Recent conversation:
{history_blob}

Student question:
{_safe_text(question, 2000)}
""".strip()


def mentor_reply_with_ollama(
    *,
    language: str,
    code: str,
    question: str,
    latest_analysis=None,
    output: str = "",
    error: str = "",
    chat_history=None,
) -> str:
    latest_analysis = latest_analysis or {}
    chat_history = chat_history or []

    has_analysis = any(
        [
            str(latest_analysis.get("explain", "")).strip(),
            str(latest_analysis.get("root_cause", "")).strip(),
            str(latest_analysis.get("fix", "")).strip(),
            str(output or "").strip(),
            str(error or "").strip(),
        ]
    )

    if not has_analysis:
        return (
            "Answer:\n"
            "- Please run Run & Analyze first.\n\n"
            "Explanation:\n"
            "- I need the latest code result, error, or analysis.\n"
            "- Then I can give a grounded mentor answer.\n\n"
            "Improved Code:\n"
            "NONE\n\n"
            "Tips:\n"
            "- Run the program once before asking mentor questions.\n"
            "- Then ask about error, fix, optimization, or viva."
        )

    prompt = _build_mentor_prompt(
        language=language,
        code=code,
        question=question,
        latest_analysis=latest_analysis,
        output=output,
        error=error,
        chat_history=chat_history,
    )

    payload = {
        "model": _ollama_model(),
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": getattr(settings, "OLLAMA_TEMPERATURE", 0.2)
        },
    }

    try:
        response = requests.post(
            f"{_ollama_base()}/api/generate",
            json=payload,
            timeout=_timeout(),
        )
        response.raise_for_status()
        data = response.json()
        text = _strip_markdown_fences(str(data.get("response") or "").strip())

        if not text:
            return (
                "Answer:\n"
                "- I could not generate a mentor reply.\n\n"
                "Explanation:\n"
                "- The AI returned an empty response.\n\n"
                "Improved Code:\n"
                "NONE\n\n"
                "Tips:\n"
                "- Run the code again.\n"
                "- Try asking a more specific question."
            )

        return text

    except Exception:
        logger.exception("Ollama mentor reply failed")
        return (
            "Answer:\n"
            "- Ollama request failed.\n\n"
            "Explanation:\n"
            "- The AI mentor could not be reached.\n"
            "- Check whether the Ollama server is running.\n"
            "- Check whether the configured model is available.\n\n"
            "Improved Code:\n"
            "NONE\n\n"
            "Tips:\n"
            "- Verify OLLAMA_BASE_URL and OLLAMA_MODEL in Django settings.\n"
            "- Confirm the model exists with ollama list."
        )