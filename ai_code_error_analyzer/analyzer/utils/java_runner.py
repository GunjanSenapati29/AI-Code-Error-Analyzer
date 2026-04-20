from pathlib import Path

def java_commands(workspace, code):
    Path(workspace, 'Main.java').write_text(code, encoding='utf-8')
    return ['javac', 'Main.java'], ['java', 'Main']
