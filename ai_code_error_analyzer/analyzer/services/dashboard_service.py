from collections import Counter

def dashboard_payload(user):
    records = list(user.executions.order_by('-created_at'))
    total = len(records)
    errors = sum(1 for r in records if r.error_type)
    fixes = sum(1 for r in records if (r.corrected_code or '').strip() and (r.corrected_code or '').strip() != (r.code or '').strip())
    cnt = Counter(r.language for r in records)
    base = total or 1
    return {
        'stats': {'executions': total, 'errors': errors, 'fixes': fixes, 'languages_used': len(cnt)},
        'language_breakdown': {'python': round(cnt.get('python', 0) * 100 / base), 'java': round(cnt.get('java', 0) * 100 / base), 'c': round(cnt.get('c', 0) * 100 / base)},
        'recent_activity': [
            {'id': r.id, 'language': r.language, 'error_type': r.error_type or 'No error', 'status': r.status, 'created_at': r.created_at.strftime('%Y-%m-%d %H:%M')}
            for r in records[:5]
        ]
    }
