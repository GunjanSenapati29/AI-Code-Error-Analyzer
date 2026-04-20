BLOCKED = {
    'python': ['subprocess', 'socket', 'pty', 'pickle', 'ctypes', 'os.system'],
    'java': ['java.net', 'Runtime', 'ProcessBuilder'],
    'c': ['sys/socket', 'unistd.h', 'signal.h', 'pthread.h'],
}

def check_security(modules, language):
    blocked = []
    for mod in modules:
        for bad in BLOCKED.get(language, []):
            if bad.lower() in mod.lower():
                blocked.append(mod)
                break
    return blocked
