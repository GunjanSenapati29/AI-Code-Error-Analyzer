from ..utils.error_parser import parse_error
from ..utils.friendly_explainer import explain_error
from ..utils.fix_engine import (
    suggest_fix,
    estimate_complexity,
    concept_tags,
    code_improvements,
    line_from_error,
)
from ..utils.module_scanner import detect_insights
from .ai_analysis_service import ai_is_configured, ai_status, analyze_with_ollama


def build_analysis(code, language, stdout, stderr, status):
    parsed = parse_error(language, stderr)
    time_cx, space_cx = estimate_complexity(code)

    has_error = bool(stderr) or status in {'error', 'blocked', 'timeout'}
    suggested_fix = suggest_fix(language, code, parsed, stderr)

    analysis = {
        'hasError': has_error,
        'is_code_correct': not has_error,
        'type': parsed.get('type', ''),
        'line': line_from_error(stderr, language) or parsed.get('line'),
        'raw': stderr,
        'error': stderr,
        'explain': explain_error(language, parsed, stderr, code, status),
        'summary': explain_error(language, parsed, stderr, code, status),
        'root_cause': '',
        'fix': suggested_fix if has_error else '',
        'corrected_code': suggested_fix if has_error else '',
        'tips': code_improvements(code, language, parsed),
        'optimizations': [],
        'time': time_cx,
        'space': space_cx,
        'complexity_explanation': 'Estimated from loops, recursion, and major data structures in the current code.',
        'concepts': concept_tags(code, language, parsed),
        'insights': detect_insights(code, language),
        'steps': [],
        'viva_answer': '',
        'output': stdout,
        'confidence': 'low',
        'source': 'rules',
    }

    if analysis['line']:
        analysis['insights'] = list(dict.fromkeys(
            (analysis.get('insights') or []) + [f'Check line {analysis["line"]} first.']
        ))

    # Fast path: if code ran successfully, do not call AI analysis
    if not has_error:
        analysis['confidence'] = 'high'
        analysis['source'] = 'rules'
        return analysis

    # Skip AI on very large outputs to avoid slowdown
    if len(stdout or '') > 4000 or len(stderr or '') > 4000:
        analysis['insights'] = list(dict.fromkeys(
            (analysis.get('insights') or []) + ['AI analysis skipped because execution output was large.']
        ))
        return analysis

    status_info = ai_status()
    if ai_is_configured() and status_info.get('reachable') and status_info.get('model_available'):
        try:
            ai = analyze_with_ollama(
                language=language,
                code=code,
                stdout=(stdout or '')[:4000],
                stderr=(stderr or '')[:4000],
                status=status
            )

            if ai.get('explain'):
                analysis['explain'] = ai['explain']
                analysis['summary'] = ai['explain']

            if ai.get('fix'):
                analysis['fix'] = ai['fix']
                analysis['corrected_code'] = ai['fix']

            if ai.get('tips'):
                analysis['tips'] = ai['tips']

            if ai.get('optimizations'):
                analysis['optimizations'] = ai['optimizations']

            if ai.get('concepts'):
                analysis['concepts'] = ai['concepts']

            if ai.get('steps'):
                analysis['steps'] = ai['steps']

            if ai.get('viva_answer'):
                analysis['viva_answer'] = ai['viva_answer']

            if ai.get('root_cause'):
                analysis['root_cause'] = ai['root_cause']

            if ai.get('complexity'):
                complexity = ai['complexity']
                analysis['time'] = complexity.get('time') or analysis['time']
                analysis['space'] = complexity.get('space') or analysis['space']
                analysis['complexity_explanation'] = complexity.get('explanation') or analysis['complexity_explanation']

            if ai.get('line_focus') and not analysis.get('line'):
                analysis['line'] = ai['line_focus']

            analysis['confidence'] = ai.get('confidence', 'medium')
            analysis['model'] = ai.get('model', '')
            analysis['source'] = 'ollama'

            model = ai.get('model')
            if model:
                analysis['insights'] = list(dict.fromkeys(
                    (analysis.get('insights') or []) + [
                        f'AI model: {model}',
                        f"AI confidence: {analysis['confidence']}"
                    ]
                ))

        except Exception as exc:
            analysis['insights'] = list(dict.fromkeys(
                (analysis.get('insights') or []) + [f'AI fallback used: {exc}']
            ))

    return analysis