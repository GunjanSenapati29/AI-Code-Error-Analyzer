import io
import json
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET, require_POST
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from .models import ExecutionRecord
from .services.ai_analysis_service import ai_is_configured, ai_status, mentor_reply_with_ollama
from .services.dashboard_service import dashboard_payload
from .services.history_service import history_payload, record_payload
from .services.report_service import build_text_report


def index(request):
    return render(request, 'analyzer/base.html')


@require_GET
def session_view(request):
    if request.user.is_authenticated:
        return JsonResponse({
            'authenticated': True,
            'user': {
                'id': request.user.id,
                'name': request.user.first_name or request.user.username,
                'email': request.user.email,
                'username': request.user.username,
            },
            'ai_configured': ai_status().get('reachable', False),
            'ai_ready': ai_status(),
        })
    return JsonResponse({'authenticated': False, 'ai_configured': ai_status().get('reachable', False), 'ai_ready': ai_status()})


@require_POST
def signup_view(request):
    data = json.loads(request.body.decode('utf-8'))
    name = data.get('name', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    if not name or not email or not password:
        return JsonResponse({'ok': False, 'message': 'All fields are required.'}, status=400)
    if User.objects.filter(email=email).exists():
        return JsonResponse({'ok': False, 'message': 'Email already registered.'}, status=400)
    username = email.split('@')[0]
    base = username
    idx = 1
    while User.objects.filter(username=username).exists():
        idx += 1
        username = f'{base}{idx}'
    user = User.objects.create_user(username=username, email=email, password=password, first_name=name)
    login(request, user)
    return JsonResponse({'ok': True, 'user': {'id': user.id, 'name': user.first_name or user.username, 'email': user.email}})


@require_POST
def login_view(request):
    data = json.loads(request.body.decode('utf-8'))
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    user = None
    if email:
        try:
            username = User.objects.get(email=email).username
            user = authenticate(request, username=username, password=password)
        except User.DoesNotExist:
            pass
    if not user:
        return JsonResponse({'ok': False, 'message': 'Invalid credentials.'}, status=400)
    login(request, user)
    return JsonResponse({'ok': True, 'user': {'id': user.id, 'name': user.first_name or user.username, 'email': user.email}})


@require_POST
def logout_view(request):
    logout(request)
    return JsonResponse({'ok': True})


@login_required
@require_GET
def dashboard_api(request):
    return JsonResponse(dashboard_payload(request.user))


@login_required
@require_GET
def history_api(request):
    return JsonResponse({'items': history_payload(request.user)})


@login_required
@require_POST
def clear_history_api(request):
    deleted, _ = ExecutionRecord.objects.filter(user=request.user).delete()
    return JsonResponse({'ok': True, 'deleted': deleted})


@login_required
@require_GET
def history_detail_api(request, record_id):
    record = get_object_or_404(ExecutionRecord, id=record_id, user=request.user)
    return JsonResponse(record_payload(record))


@login_required
@require_POST
def mentor_chat_api(request):
    data = json.loads(request.body.decode('utf-8'))
    question = (data.get('question') or '').strip()
    code = data.get('code') or ''
    language = data.get('language') or 'python'
    latest_analysis = data.get('analysis') or {}
    output = data.get('output') or ''
    error = data.get('error') or ''

    if not question:
        return JsonResponse({'ok': False, 'message': 'Question is required.'}, status=400)

    status = ai_status()
    if not status.get('configured') or not status.get('reachable') or not status.get('model_available'):
        return JsonResponse({
            'ok': True,
            'reply': 'Ollama is not ready yet. Start Ollama, run `ollama pull ' + (status.get('model') or 'deepseek-coder') + '`, then keep your .env values in sync.'
        })

    try:
        reply = mentor_reply_with_ollama(
            language=language,
            code=code,
            question=question,
            latest_analysis=latest_analysis,
            output=output,
            error=error,
        )
        return JsonResponse({'ok': True, 'reply': reply})
    except Exception as exc:
        return JsonResponse({'ok': False, 'message': f'AI request failed: {exc}'}, status=500)


@login_required
@require_GET
def ai_status_api(request):
    return JsonResponse(ai_status())


@login_required
@require_GET
def report_txt(request, record_id):
    record = get_object_or_404(ExecutionRecord, id=record_id, user=request.user)
    text = build_text_report(record)
    response = HttpResponse(text, content_type='text/plain; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename=report-{record.id}.txt'
    return response


@login_required
@require_GET
def report_pdf(request, record_id):
    record = get_object_or_404(ExecutionRecord, id=record_id, user=request.user)
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 40
    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(40, y, 'CodeSage Debug Report')
    y -= 24
    pdf.setFont('Helvetica', 9)
    for line in build_text_report(record).splitlines():
        if y < 40:
            pdf.showPage()
            pdf.setFont('Helvetica', 9)
            y = height - 40
        pdf.drawString(40, y, line[:120])
        y -= 12
    pdf.save()
    buffer.seek(0)
    return FileResponse(buffer, as_attachment=True, filename=f'report-{record.id}.pdf')
