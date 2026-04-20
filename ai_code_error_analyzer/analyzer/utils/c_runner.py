from pathlib import Path

def c_commands(workspace, code):
    Path(workspace, 'program.c').write_text(code, encoding='utf-8')
    return ['gcc', 'program.c', '-o', 'program'], ['./program']
