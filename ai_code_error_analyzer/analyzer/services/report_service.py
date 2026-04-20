def build_text_report(record):
    complexity = record.complexity if isinstance(record.complexity, dict) else {}
    suggestions = record.suggestions if isinstance(record.suggestions, dict) else {'general': record.suggestions or [], 'optimizations': []}
    insights = record.insights if isinstance(record.insights, dict) else {'highlights': record.insights or [], 'steps': [], 'viva_answer': '', 'root_cause': ''}

    time_cx = complexity.get('time', 'N/A')
    space_cx = complexity.get('space', 'N/A')
    complexity_expl = complexity.get('explanation', 'N/A')
    debug_steps = '\n'.join(f'- {x}' for x in insights.get('steps', [])) or 'N/A'
    general_suggestions = '\n'.join(f'- {x}' for x in suggestions.get('general', [])) or 'N/A'
    optimization_ideas = '\n'.join(f'- {x}' for x in suggestions.get('optimizations', [])) or 'N/A'

    lines = [
        'CODESAGE DEBUG REPORT',
        f'Generated: {record.created_at.strftime("%Y-%m-%d %H:%M:%S")}',
        f'Language: {record.language.upper()}',
        f'Status: {record.status}',
        f'Error Type: {record.error_type or "None"}',
        f'Line Number: {record.line_number or "N/A"}',
        '=' * 60,
        'ORIGINAL CODE:',
        record.code,
        '=' * 60,
        'RAW ERROR:',
        record.raw_error or 'None',
        '=' * 60,
        'EXPLANATION:',
        record.explanation or 'N/A',
        '=' * 60,
        'ROOT CAUSE:',
        insights.get('root_cause') or 'N/A',
        '=' * 60,
        'SUGGESTED CODE:',
        record.corrected_code or 'N/A',
        '=' * 60,
        'OUTPUT:',
        record.output or 'None',
        '=' * 60,
        'DEBUG STEPS:',
        debug_steps,
        '=' * 60,
        'GENERAL SUGGESTIONS:',
        general_suggestions,
        '=' * 60,
        'OPTIMIZATION IDEAS:',
        optimization_ideas,
        '=' * 60,
        'VIVA ANSWER:',
        insights.get('viva_answer') or 'N/A',
        '=' * 60,
        'CONCEPTS: ' + ', '.join(record.concepts or []),
        'INSIGHTS: ' + ', '.join(insights.get('highlights', [])),
        f'COMPLEXITY: time={time_cx}, space={space_cx}',
        'COMPLEXITY EXPLANATION: ' + complexity_expl,
    ]
    return '\n'.join(lines)
