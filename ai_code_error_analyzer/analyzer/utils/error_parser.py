import re


PYTHON_ERROR_PATTERNS = [
    r'([A-Za-z_][A-Za-z0-9_]*Error):',
    r'([A-Za-z_][A-Za-z0-9_]*Exception):',
    r'^\s*Traceback.*?\n.*?([A-Za-z_][A-Za-z0-9_]*Error):',
]

JAVA_ERROR_PATTERNS = [
    r'([A-Za-z_][A-Za-z0-9_]*Exception)',
    r'([A-Za-z_][A-Za-z0-9_]*Error)',
    r'\berror\b',
]

C_ERROR_PATTERNS = [
    r'Segmentation fault',
    r'Floating point exception',
    r'Compilation Error',
    r'error:',
]


def _extract_line(patterns, raw_error):
    for pat in patterns:
        m = re.search(pat, raw_error, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
    return None


def _extract_first_match(patterns, raw_error, flags=0):
    for pat in patterns:
        m = re.search(pat, raw_error, flags)
        if m:
            return m.group(1)
    return ''


def _category_for_python(err_type, raw_error):
    syntax_errors = {'SyntaxError', 'IndentationError', 'TabError'}
    runtime_errors = {
        'NameError', 'UnboundLocalError', 'TypeError', 'ValueError',
        'ZeroDivisionError', 'IndexError', 'KeyError', 'AttributeError',
        'ImportError', 'ModuleNotFoundError', 'FileNotFoundError',
        'EOFError', 'RecursionError', 'MemoryError', 'OverflowError',
        'AssertionError'
    }

    if err_type in syntax_errors:
        return 'syntax'
    if err_type in runtime_errors:
        return 'runtime'
    if err_type.endswith('Error') or err_type.endswith('Exception'):
        return 'runtime'

    if 'syntax' in raw_error.lower() or 'invalid syntax' in raw_error.lower():
        return 'syntax'

    return 'unknown'


def _severity_for_python(err_type, category):
    if err_type in {'SyntaxError', 'IndentationError', 'TabError'}:
        return 'high'
    if err_type in {'NameError', 'TypeError', 'ValueError', 'ZeroDivisionError'}:
        return 'high'
    if category == 'runtime':
        return 'medium'
    return 'low'


def _category_for_java(err_type, raw_error):
    lowered = raw_error.lower()

    if 'compilation' in lowered or err_type == 'error':
        return 'compile_time'
    if err_type.endswith('Exception') or err_type.endswith('Error'):
        return 'runtime'
    return 'unknown'


def _category_for_c(err_type, raw_error):
    lowered = raw_error.lower()

    if 'error:' in lowered or err_type == 'Compilation Error':
        return 'compile_time'
    if 'segmentation fault' in lowered or 'floating point exception' in lowered:
        return 'runtime'
    return 'unknown'


def parse_error(language, raw_error):
    raw_error = str(raw_error or '').strip()

    data = {
        'type': '',
        'line': None,
        'message': raw_error,
        'category': 'unknown',
        'severity': 'low',
    }

    if not raw_error:
        return data

    language = str(language or '').lower()

    if language == 'python':
        err_type = _extract_first_match(PYTHON_ERROR_PATTERNS, raw_error, flags=re.M | re.S)
        line = _extract_line(
            [
                r'File ".*?", line (\d+)',
                r'line (\d+)',
            ],
            raw_error
        )

        data['type'] = err_type
        data['line'] = line
        data['category'] = _category_for_python(err_type, raw_error)
        data['severity'] = _severity_for_python(err_type, data['category'])

        special_cases = [
            ('SyntaxError', r'invalid syntax|was never closed|unexpected EOF|unterminated string', re.I),
            ('IndentationError', r'expected an indented block|unexpected indent|unindent does not match', re.I),
            ('TabError', r'inconsistent use of tabs and spaces', re.I),
            ('NameError', r"name '.*' is not defined", 0),
            ('UnboundLocalError', r'local variable .* referenced before assignment|cannot access local variable', re.I),
            ('TypeError', r'TypeError:', 0),
            ('ValueError', r'ValueError:', 0),
            ('ZeroDivisionError', r'ZeroDivisionError:', 0),
            ('IndexError', r'IndexError:', 0),
            ('KeyError', r'KeyError:', 0),
            ('AttributeError', r'AttributeError:', 0),
            ('ModuleNotFoundError', r'ModuleNotFoundError:', 0),
            ('ImportError', r'ImportError:', 0),
            ('FileNotFoundError', r'FileNotFoundError:', 0),
            ('EOFError', r'EOFError:', 0),
            ('RecursionError', r'RecursionError:', 0),
        ]

        if not data['type']:
            for name, pattern, flags in special_cases:
                if re.search(pattern, raw_error, flags):
                    data['type'] = name
                    data['category'] = _category_for_python(name, raw_error)
                    data['severity'] = _severity_for_python(name, data['category'])
                    break

    elif language == 'java':
        err_type = _extract_first_match(JAVA_ERROR_PATTERNS, raw_error, flags=re.I)
        line = _extract_line(
            [
                r'Main\.java:(\d+)',
                r'line[:\s]+(\d+)',
            ],
            raw_error
        )

        if err_type.lower() == 'error':
            if 'exception' in raw_error.lower():
                exc = re.search(r'([A-Za-z_][A-Za-z0-9_]*Exception)', raw_error)
                err_type = exc.group(1) if exc else 'error'
            elif 'error' in raw_error.lower():
                err_type = 'Compilation Error'

        data['type'] = err_type
        data['line'] = line
        data['category'] = _category_for_java(err_type, raw_error)
        data['severity'] = 'high' if data['category'] in {'compile_time', 'runtime'} else 'low'

    else:
        line = _extract_line(
            [
                r'program\.c:(\d+)',
                r'line[:\s]+(\d+)',
            ],
            raw_error
        )

        lowered = raw_error.lower()
        if 'segmentation fault' in lowered:
            err_type = 'Segmentation Fault'
        elif 'floating point exception' in lowered:
            err_type = 'Floating Point Exception'
        elif 'error:' in lowered:
            err_type = 'Compilation Error'
        else:
            err_type = 'Runtime Error'

        data['type'] = err_type
        data['line'] = line
        data['category'] = _category_for_c(err_type, raw_error)
        data['severity'] = 'high' if data['category'] in {'compile_time', 'runtime'} else 'low'

    return data