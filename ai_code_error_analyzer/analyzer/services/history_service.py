def _ensure_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return []
    return [value]


def history_payload(user):
    return [
        {'id': r.id, 'date': r.created_at.strftime('%Y-%m-%d %H:%M'), 'language': r.language, 'code_preview': r.code_preview, 'error_type': r.error_type or '—', 'status': r.status}
        for r in user.executions.order_by('-created_at')[:100]
    ]


def record_payload(r):
    suggestions = r.suggestions if isinstance(r.suggestions, dict) else {'general': _ensure_list(r.suggestions), 'optimizations': []}
    insights = r.insights if isinstance(r.insights, dict) else {'highlights': _ensure_list(r.insights), 'steps': [], 'viva_answer': '', 'root_cause': '', 'confidence': 'medium', 'source': 'rules'}
    complexity = r.complexity if isinstance(r.complexity, dict) else {'time': 'O(1)', 'space': 'O(1)', 'explanation': ''}
    return {
        'id': r.id,
        'language': r.language,
        'code': r.code,
        'output': r.output,
        'raw_error': r.raw_error,
        'error_type': r.error_type,
        'explanation': r.explanation,
        'corrected_code': r.corrected_code,
        'line_number': r.line_number,
        'status': r.status,
        'concepts': r.concepts,
        'suggestions': suggestions.get('general', []),
        'optimizations': suggestions.get('optimizations', []),
        'insights': insights.get('highlights', []),
        'steps': insights.get('steps', []),
        'viva_answer': insights.get('viva_answer', ''),
        'root_cause': insights.get('root_cause', ''),
        'confidence': insights.get('confidence', 'medium'),
        'source': insights.get('source', 'rules'),
        'complexity': complexity,
        'modules': r.modules,
        'blocked_modules': r.blocked_modules,
        'created_at': r.created_at.strftime('%Y-%m-%d %H:%M')
    }
