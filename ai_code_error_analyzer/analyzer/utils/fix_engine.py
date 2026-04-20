import ast
import builtins
import difflib
import keyword
import re


PYTHON_BLOCK_STARTERS = {
    'if', 'elif', 'else', 'for', 'while', 'def', 'class',
    'try', 'except', 'finally', 'with', 'match', 'case'
}

COMMON_NAME_TYPOS = {
    'pritn': 'print',
    'imput': 'input',
    'lnet': 'len',
    'apend': 'append',
    'rnage': 'range',
    'flase': 'False',
    'ture': 'True',
    'fase': 'False',
    'retrun': 'return',
}


def _safe_lines(code):
    return code.splitlines()


def _preserve_join(original, lines):
    return '\n'.join(lines) + ('\n' if original.endswith('\n') else '')


def _can_parse_python(code):
    try:
        ast.parse(code)
        return True
    except Exception:
        return False


def _extract_known_python_names(code):
    names = set(dir(builtins)) | set(keyword.kwlist)

    for m in re.finditer(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=.*$', code, flags=re.M):
        names.add(m.group(1))

    for m in re.finditer(r'^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', code, flags=re.M):
        names.add(m.group(1))

    for m in re.finditer(r'^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b', code, flags=re.M):
        names.add(m.group(1))

    for m in re.finditer(r'^\s*from\s+\S+\s+import\s+(.+)$', code, flags=re.M):
        for item in m.group(1).split(','):
            names.add(item.strip().split(' as ')[-1].strip())

    for m in re.finditer(r'^\s*import\s+(.+)$', code, flags=re.M):
        for item in m.group(1).split(','):
            mod = item.strip().split(' as ')[-1].strip().split('.')[0]
            if mod:
                names.add(mod)

    return {n for n in names if n}


def _find_defined_variables(code):
    return re.findall(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=.*$', code, flags=re.M)


def _find_last_assigned_name(code):
    vars_found = _find_defined_variables(code)
    return vars_found[-1] if vars_found else None


def _infer_placeholder_for_name(name):
    lowered = name.lower()
    if lowered in {'name', 'text', 'msg', 'message', 'word', 's', 'title'}:
        return '""'
    if lowered in {'items', 'arr', 'nums', 'values', 'lst', 'list1', 'list2'}:
        return '[]'
    if lowered in {'data', 'obj', 'mapping', 'config', 'dct', 'dict1'}:
        return '{}'
    if lowered in {'flag', 'done', 'valid', 'found'}:
        return 'False'
    return '0'


def _fix_missing_colon(code, raw_error):
    m = re.search(r'line (\d+)', raw_error or '')
    if not m:
        return code

    line_no = int(m.group(1))
    lines = _safe_lines(code)

    if not (1 <= line_no <= len(lines)):
        return code

    line = lines[line_no - 1]
    stripped = line.strip()

    if not stripped or stripped.endswith(':'):
        return code

    first = stripped.split()[0].rstrip(':')
    if first in PYTHON_BLOCK_STARTERS and not stripped.startswith('#'):
        lines[line_no - 1] = line.rstrip() + ':'
        return _preserve_join(code, lines)

    return code


def _fix_unclosed_brackets(code):
    pairs = {'(': ')', '[': ']', '{': '}'}
    closing_stack = []
    in_single = False
    in_double = False
    escaped = False

    for ch in code:
        if escaped:
            escaped = False
            continue

        if ch == '\\':
            escaped = True
            continue

        if ch == "'" and not in_double:
            in_single = not in_single
            continue

        if ch == '"' and not in_single:
            in_double = not in_double
            continue

        if in_single or in_double:
            continue

        if ch in pairs:
            closing_stack.append(pairs[ch])
        elif ch in ')]}':
            if closing_stack and closing_stack[-1] == ch:
                closing_stack.pop()

    if closing_stack:
        return code + ''.join(reversed(closing_stack))

    return code


def _fix_unterminated_string(code):
    single_quotes = 0
    double_quotes = 0
    escaped = False

    for ch in code:
        if escaped:
            escaped = False
            continue
        if ch == '\\':
            escaped = True
            continue
        if ch == "'":
            single_quotes += 1
        elif ch == '"':
            double_quotes += 1

    if single_quotes % 2 != 0:
        return code + "'"
    if double_quotes % 2 != 0:
        return code + '"'

    return code


def _fix_typo_tokens(code):
    fixed = code
    for bad, good in COMMON_NAME_TYPOS.items():
        fixed = re.sub(rf'\b{re.escape(bad)}\b', good, fixed)
    return fixed


def _smart_print_fix(code):
    lines = code.splitlines()
    if not lines:
        return code

    assigned_name = _find_last_assigned_name(code)
    new_lines = []

    for line in lines:
        fixed_line = re.sub(r'\bpritn\s*\(', 'print(', line)
        indent = re.match(r'^\s*', line).group(0)

        if re.search(r'^\s*print\(\s*["\'][^"\']*$', fixed_line):
            quote_match = re.search(r'^\s*print\(\s*(["\'])(.*)$', fixed_line)
            if quote_match:
                quote = quote_match.group(1)
                msg = quote_match.group(2)
                if assigned_name:
                    fixed_line = f'{indent}print({quote}{msg}{quote}, {assigned_name})'
                else:
                    fixed_line = f'{indent}print({quote}{msg}{quote})'

        elif re.search(r'^\s*print\(\s*["\'][^"\']*["\']\s*$', fixed_line):
            text_match = re.search(r'^\s*print\(\s*(["\'])(.*?)\1\s*$', fixed_line)
            if text_match:
                quote = text_match.group(1)
                msg = text_match.group(2)
                if assigned_name:
                    fixed_line = f'{indent}print({quote}{msg}{quote}, {assigned_name})'
                else:
                    fixed_line = fixed_line + ')'

        new_lines.append(fixed_line)

    return '\n'.join(new_lines) + ('\n' if code.endswith('\n') else '')


def _fix_indentation_error(code, raw_error):
    lines = code.splitlines()
    fixed_lines = [line.replace('\t', '    ') for line in lines]

    m = re.search(r'line (\d+)', raw_error or '')
    line_no = int(m.group(1)) if m else None

    if line_no and 1 < line_no <= len(fixed_lines):
        prev = fixed_lines[line_no - 2].rstrip()
        curr = fixed_lines[line_no - 1]

        if prev.strip().endswith(':') and not curr.startswith((' ', '\t')):
            fixed_lines[line_no - 1] = '    ' + curr.lstrip()

    fixed = _preserve_join(code, fixed_lines)
    return fixed if _can_parse_python(fixed) else code.replace('\t', '    ')


def _fix_python_name_error(code, raw_error):
    missing = re.search(r"name '([^']+)' is not defined", raw_error or '')
    if not missing:
        return code

    bad_name = missing.group(1)
    defined_vars = _find_defined_variables(code)
    known = _extract_known_python_names(code)

    matches = difflib.get_close_matches(bad_name, list(known), n=1, cutoff=0.8)
    if not matches and bad_name in COMMON_NAME_TYPOS:
        matches = [COMMON_NAME_TYPOS[bad_name]]

    if matches:
        good_name = matches[0]
        fixed = re.sub(rf'\b{re.escape(bad_name)}\b', good_name, code)
        return fixed if _can_parse_python(fixed) else code

    if defined_vars:
        closest_var = difflib.get_close_matches(bad_name, defined_vars, n=1, cutoff=0.1)
        target = closest_var[0] if closest_var else defined_vars[-1]
        fixed = re.sub(rf'\b{re.escape(bad_name)}\b', target, code)
        return fixed if _can_parse_python(fixed) else code

    placeholder = _infer_placeholder_for_name(bad_name)
    lines = code.splitlines()
    insert_at = 0
    while insert_at < len(lines):
        stripped = lines[insert_at].strip()
        if not stripped or stripped.startswith('#'):
            insert_at += 1
            continue
        break

    injected = f"{bad_name} = {placeholder}"
    new_lines = lines[:insert_at] + [injected] + lines[insert_at:]
    fixed = '\n'.join(new_lines) + ('\n' if code.endswith('\n') else '')
    return fixed if _can_parse_python(fixed) else code


def _fix_unbound_local_error(code, raw_error):
    m = re.search(r"local variable '([^']+)' referenced before assignment", raw_error or '')
    if not m:
        m = re.search(r"cannot access local variable '([^']+)' where it is not associated with a value", raw_error or '')
    if not m:
        return code

    var_name = m.group(1)
    placeholder = _infer_placeholder_for_name(var_name)
    lines = code.splitlines()

    for i, line in enumerate(lines):
        if re.match(r'^\s*def\s+\w+\s*\(', line):
            indent = re.match(r'^\s*', line).group(0) + '    '
            lines.insert(i + 1, f'{indent}{var_name} = {placeholder}')
            fixed = _preserve_join(code, lines)
            return fixed if _can_parse_python(fixed) else code

    return code


def _fix_type_error(code, raw_error):
    fixed = code

    if 'can only concatenate str' in (raw_error or ''):
        fixed = re.sub(
            r'print\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)',
            r'print(str(\1) + str(\2))',
            fixed
        )
        if _can_parse_python(fixed):
            return fixed

    if 'unsupported operand type(s) for +' in (raw_error or ''):
        fixed = re.sub(
            r'print\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\+\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)',
            r'print(str(\1) + str(\2))',
            code
        )
        if _can_parse_python(fixed):
            return fixed

    if "'>' not supported between instances of 'str' and 'int'" in (raw_error or ''):
        fixed = re.sub(r'(\w+)\s*=\s*input\(\)', r'\1 = int(input())', code)
        if _can_parse_python(fixed):
            return fixed

    if "unsupported operand type(s) for -: 'str' and" in (raw_error or '') or \
       "unsupported operand type(s) for *: 'str' and" in (raw_error or '') or \
       "unsupported operand type(s) for /: 'str' and" in (raw_error or ''):
        fixed = re.sub(r'(\w+)\s*=\s*input\(\)', r'\1 = int(input())', code)
        if _can_parse_python(fixed):
            return fixed

    if "'NoneType' object is not callable" in (raw_error or ''):
        return code

    return code


def _fix_value_error(code, raw_error):
    if "invalid literal for int()" in (raw_error or ''):
        fixed = code.replace('int(input())', 'int(input().strip() or 0)')
        if _can_parse_python(fixed):
            return fixed

    if "could not convert string to float" in (raw_error or ''):
        fixed = code.replace('float(input())', 'float(input().strip() or 0)')
        if _can_parse_python(fixed):
            return fixed

    return code


def _fix_zero_division_error(code, raw_error):
    lines = code.splitlines()
    new_lines = []

    for line in lines:
        if re.search(r'/\s*0\b', line):
            new_lines.append(re.sub(r'/\s*0\b', '/ 1', line))
        elif re.search(r'%\s*0\b', line):
            new_lines.append(re.sub(r'%\s*0\b', '% 1', line))
        else:
            new_lines.append(line)

    fixed = _preserve_join(code, new_lines)
    return fixed if _can_parse_python(fixed) else code


def _fix_index_error(code, raw_error):
    fixed = re.sub(
        r'print\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*([A-Za-z_][A-Za-z0-9_]*|\d+)\s*\]\s*\)',
        r'print(\1[\2] if len(\1) > int(\2) else None)',
        code
    )
    return fixed if fixed != code and _can_parse_python(fixed) else code


def _fix_key_error(code, raw_error):
    m = re.search(r"KeyError: ['\"]?([^'\"]+)['\"]?", raw_error or '')
    if not m:
        return code

    key = m.group(1)

    fixed = re.sub(
        rf'([A-Za-z_][A-Za-z0-9_]*)\s*\[\s*[\'"]{re.escape(key)}[\'"]\s*\]',
        rf'\1.get("{key}")',
        code
    )
    return fixed if fixed != code and _can_parse_python(fixed) else code


def _fix_attribute_error(code, raw_error):
    m = re.search(r"'(\w+)' object has no attribute '([^']+)'", raw_error or '')
    if not m:
        return code

    obj_type = m.group(1)
    bad_attr = m.group(2)
    valid_attrs = dir(str) if obj_type == 'str' else dir(list) if obj_type == 'list' else dir(dict) if obj_type == 'dict' else []

    matches = difflib.get_close_matches(bad_attr, valid_attrs, n=1, cutoff=0.75)
    if not matches:
        return code

    good_attr = matches[0]
    fixed = re.sub(rf'\.{re.escape(bad_attr)}\b', f'.{good_attr}', code)
    return fixed if _can_parse_python(fixed) else code


def _fix_import_error(code, raw_error):
    if 'No module named' in (raw_error or ''):
        return code
    if 'cannot import name' in (raw_error or ''):
        return code
    return code


def _fix_file_error(code, raw_error):
    m = re.search(r"No such file or directory: ['\"]([^'\"]+)['\"]", raw_error or '')
    if not m:
        return code

    missing_path = m.group(1)
    fixed = code.replace(f'open("{missing_path}"', f'open("{missing_path}", "w+")')
    return fixed if _can_parse_python(fixed) else code


def _fix_eof_error(code, raw_error):
    fixed = code.replace('input()', 'input() or ""')
    return fixed if _can_parse_python(fixed) else code


def _fix_recursion_error(code, raw_error):
    return code


def _fix_python_syntax_error(code, raw_error):
    fixed = code.replace('\t', '    ')

    candidate = _fix_missing_colon(fixed, raw_error)
    if candidate != fixed and _can_parse_python(candidate):
        return candidate

    candidate = _fix_typo_tokens(fixed)
    if candidate != fixed and _can_parse_python(candidate):
        return candidate

    candidate = _smart_print_fix(fixed)
    if candidate != fixed and _can_parse_python(candidate):
        return candidate

    candidate = _fix_unclosed_brackets(fixed)
    if candidate != fixed and _can_parse_python(candidate):
        return candidate

    candidate = _fix_unterminated_string(candidate)
    if candidate != fixed and _can_parse_python(candidate):
        return candidate

    m = re.search(r'line (\d+)', raw_error or '')
    line_no = int(m.group(1)) if m else None
    if line_no:
        lines = fixed.splitlines()
        if 1 <= line_no <= len(lines):
            line = lines[line_no - 1]
            updated = re.sub(r'\bpritn\s*\(', 'print(', line)
            if updated != line:
                lines[line_no - 1] = updated
                candidate = _preserve_join(fixed, lines)
                if _can_parse_python(candidate):
                    return candidate

    return code


def _python_fix(code, err_type, raw_error):
    fixed = code

    handlers = {
        'SyntaxError': _fix_python_syntax_error,
        'IndentationError': _fix_indentation_error,
        'TabError': _fix_indentation_error,
        'NameError': _fix_python_name_error,
        'UnboundLocalError': _fix_unbound_local_error,
        'TypeError': _fix_type_error,
        'ValueError': _fix_value_error,
        'ZeroDivisionError': _fix_zero_division_error,
        'IndexError': _fix_index_error,
        'KeyError': _fix_key_error,
        'AttributeError': _fix_attribute_error,
        'ImportError': _fix_import_error,
        'ModuleNotFoundError': _fix_import_error,
        'FileNotFoundError': _fix_file_error,
        'EOFError': _fix_eof_error,
        'RecursionError': _fix_recursion_error,
    }

    handler = handlers.get(err_type)
    if handler:
        fixed = handler(code, raw_error)

    try:
        ast.parse(fixed)
        return fixed
    except Exception:
        return code


def suggest_fix(language, code, parsed, raw_error):
    err_type = parsed.get('type', '')
    if not err_type and not raw_error:
        return code

    if language == 'python':
        return _python_fix(code, err_type, raw_error)

    return code


def sanitize_ai_python_fix(ai_fix):
    if not ai_fix:
        return ''

    text = str(ai_fix).strip()
    fence_match = re.search(r'```(?:python)?\s*([\s\S]*?)```', text, flags=re.I)
    if fence_match:
        return fence_match.group(1).strip()

    return text


def is_valid_python_fix(original_code, fixed_code):
    if not fixed_code or not str(fixed_code).strip():
        return False, 'empty'

    fixed = str(fixed_code).strip()

    if '```' in fixed:
        return False, 'markdown_fence'

    bad_phrases = [
        'here is the corrected code',
        'this code fixes',
        'explanation:',
        'corrected code:',
        'the fix is',
        'should have been:',
        'it should be:',
        'use this:',
        'change this to:',
    ]
    lower = fixed.lower()
    if any(p in lower for p in bad_phrases):
        return False, 'contains_explanation'

    if 'exit()' in fixed and 'exit()' not in original_code:
        return False, 'unsafe_exit'

    try:
        ast.parse(fixed)
    except Exception:
        return False, 'not_parseable'

    if not re.search(r'\b(print|input|def|class|if|for|while|import|from|return|try|except)\b', fixed) and '\n' not in fixed:
        return False, 'does_not_look_like_code'

    return True, 'ok'


def estimate_complexity(code):
    loops = len(re.findall(r'\bfor\b|\bwhile\b', code))
    nested_hint = len(re.findall(r'\bfor\b[\s\S]{0,120}\bfor\b|\bwhile\b[\s\S]{0,120}\bwhile\b', code))

    if loops == 0:
        return 'O(1)', 'O(1)'
    if loops == 1:
        return 'O(n)', 'O(1)'
    if loops >= 2 and nested_hint:
        return 'O(n^2)', 'O(n)'
    if loops == 2:
        return 'O(n)', 'O(n)'
    return 'O(n^2)', 'O(n)'


def concept_tags(code, language, parsed):
    tags = []

    if 'for' in code:
        tags.append('For Loops')
    if 'while' in code:
        tags.append('While Loops')
    if 'if' in code:
        tags.append('Conditionals')
    if language == 'python' and 'def ' in code:
        tags.append('Functions')
    if '[' in code:
        tags.append('Arrays / Indexing')
    if 'input(' in code:
        tags.append('User Input')
    if parsed.get('type'):
        tags.append(parsed['type'])

    return tags or ['Program Structure']


def code_improvements(code, language, parsed):
    tips = []

    if language == 'python' and 'print(' in code and '+' in code:
        tips.append('Consider using f-strings or explicit type conversion for safer string formatting.')
    if language == 'python' and 'append(' in code and 'for ' in code:
        tips.append('A list comprehension may make this code shorter and easier to read.')
    if language == 'python' and 'except:' in code:
        tips.append('Use specific exception types instead of a bare except block.')
    if language == 'python' and 'open(' in code and '.close()' not in code and 'with open(' not in code:
        tips.append('Use a with statement while opening files to close them safely.')

    if not tips:
        tips.append('Test this code with multiple normal and edge-case inputs to improve reliability.')

    return tips


def line_from_error(raw_error, language):
    if not raw_error:
        return None

    for pat in [
        r'line (\d+)',
        r'File ".*?", line (\d+)',
    ]:
        m = re.search(pat, raw_error)
        if m:
            return int(m.group(1))

    return None