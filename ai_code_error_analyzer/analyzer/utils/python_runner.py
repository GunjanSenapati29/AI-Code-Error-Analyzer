# from pathlib import Path


# def python_command(workspace: Path, code: str):
#     file_path = workspace / "main.py"
#     file_path.write_text(code, encoding="utf-8")
#     return ["python", "-u", "main.py"]

from pathlib import Path


def python_command(workspace: Path, code: str):
    file_path = workspace / "main.py"
    file_path.write_text(code, encoding="utf-8")
    return ["python", "-u", "main.py"]