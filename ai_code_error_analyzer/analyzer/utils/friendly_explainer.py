from django.conf import settings


def explain_error(language, parsed, raw_error, code, status):
    et = str(parsed.get('type', '') or '').strip()
    category = str(parsed.get('category', '') or '').strip().lower()
    timeout_seconds = getattr(settings, 'EXECUTION_TIMEOUT', 20)
    raw_error = str(raw_error or '')
    language = str(language or '').lower()

    if status == 'success':
        return 'Your program ran successfully. You can still review the concepts and improvement suggestions below.'

    if status == 'timeout':
        return f'Your program took too long and was stopped after {timeout_seconds} seconds. This often happens because of an infinite loop, deep recursion, or very slow logic.'

    if status == 'blocked':
        return 'The code uses blocked or unsafe modules, so execution was stopped before running.'

    python_map = {
        'SyntaxError': 'There is a syntax mistake, so Python could not understand your code structure.',
        'IndentationError': 'Indentation is inconsistent. Python blocks must align properly after statements like if, for, while, and def.',
        'TabError': 'Tabs and spaces were mixed in indentation. Python requires consistent indentation formatting.',
        'NameError': 'You used a variable or function name before defining it, or there is a spelling mistake in the name.',
        'UnboundLocalError': 'A local variable is being used before it gets a value inside the function.',
        'TypeError': 'A value was used with an incompatible data type for that operation.',
        'ValueError': 'The operation received the right type of value, but the value itself is not valid.',
        'ZeroDivisionError': 'The code tried to divide or take modulo by zero, which is not allowed.',
        'IndexError': 'The code tried to access a list or sequence position that does not exist.',
        'KeyError': 'The code tried to access a dictionary key that is not present.',
        'AttributeError': 'The code tried to use a method or property that does not exist for that object.',
        'ImportError': 'Python could not import the required name or object.',
        'ModuleNotFoundError': 'Python could not find the required module.',
        'FileNotFoundError': 'The program tried to open a file that does not exist at the given path.',
        'EOFError': 'The program asked for input but did not receive enough data.',
        'RecursionError': 'The function called itself too many times without reaching a stopping condition.',
        'MemoryError': 'The program tried to use more memory than Python could allocate.',
        'AssertionError': 'An assert condition failed, which means an expected condition was not true.',
        'OverflowError': 'A numeric operation exceeded the allowed limit for that calculation.',
    }

    java_map = {
        'NullPointerException': 'A Java object reference is null, so a method or field cannot be used on it.',
        'ArrayIndexOutOfBoundsException': 'The code accessed an array index outside the valid range.',
        'InputMismatchException': 'The Java program expected a different input type than the one provided.',
        'Compilation Error': 'The Java compiler found syntax or build errors and could not compile the program.',
        'NumberFormatException': 'The program tried to convert text into a number, but the text was not a valid number.',
        'ArithmeticException': 'An invalid arithmetic operation happened, such as division by zero.',
    }

    c_map = {
        'Compilation Error': 'The C compiler found syntax or build errors and could not compile the program.',
        'Segmentation Fault': 'The C program likely accessed invalid memory.',
        'Floating Point Exception': 'The C program performed an invalid arithmetic operation, such as division by zero.',
        'Runtime Error': 'The C program failed during execution.',
    }

    if language == 'python':
        if et in python_map:
            return python_map[et]

        lowered = raw_error.lower()
        if 'invalid syntax' in lowered or 'was never closed' in lowered or 'unterminated string' in lowered:
            return python_map['SyntaxError']
        if 'unexpected indent' in lowered or 'expected an indented block' in lowered or 'unindent does not match' in lowered:
            return python_map['IndentationError']
        if "is not defined" in lowered:
            return python_map['NameError']
        if 'unsupported operand type' in lowered or 'can only concatenate str' in lowered:
            return python_map['TypeError']
        if 'invalid literal for int()' in lowered or 'could not convert string to float' in lowered:
            return python_map['ValueError']

    if language == 'java':
        if et in java_map:
            return java_map[et]

    if language == 'c':
        if et in c_map:
            return c_map[et]

    if category == 'syntax':
        return 'There is a syntax problem in the code, so the program cannot be parsed correctly.'
    if category == 'runtime':
        return 'The program started running but failed during execution because of an invalid operation or unexpected value.'
    if category == 'compile_time':
        return 'The compiler found errors before execution, so the program could not be built.'

    return 'The program failed. Read the raw error and suggested fix for more detail.'