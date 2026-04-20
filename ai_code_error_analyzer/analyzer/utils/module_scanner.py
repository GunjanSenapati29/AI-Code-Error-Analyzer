import re
PATS = {
    'python': re.compile(r'^\s*(?:import|from)\s+([\w.]+)', re.M),
    'java': re.compile(r'^\s*import\s+([\w.*]+);', re.M),
    'c': re.compile(r'^\s*#include\s*[<\"]([\w./]+)[>\"]', re.M),
}

def scan_modules(code, language):
    return sorted(set(PATS[language].findall(code)))

def detect_insights(code, language):
    insights = []
    if any(x in code for x in ['input(', 'Scanner', 'scanf(']): insights.append('Requires User Input')
    if any(x in code for x in ['random', 'rand(', 'Math.random']): insights.append('Uses Randomness')
    if 'while True' in code or 'for(;;)' in code or 'while(1)' in code: insights.append('Potential Infinite Loop')
    if not insights: insights.append('Static Analysis Complete')
    return insights
