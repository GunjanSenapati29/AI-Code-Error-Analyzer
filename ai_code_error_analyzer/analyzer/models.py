from django.conf import settings
from django.db import models

class ExecutionRecord(models.Model):
    LANGUAGE_CHOICES = [('python', 'Python'), ('java', 'Java'), ('c', 'C')]
    STATUS_CHOICES = [('success', 'Success'), ('error', 'Error'), ('blocked', 'Blocked'), ('timeout', 'Timeout'), ('running', 'Running')]
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='executions')
    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES)
    code = models.TextField()
    output = models.TextField(blank=True, default='')
    raw_error = models.TextField(blank=True, default='')
    error_type = models.CharField(max_length=120, blank=True, default='')
    explanation = models.TextField(blank=True, default='')
    corrected_code = models.TextField(blank=True, default='')
    line_number = models.IntegerField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='running')
    concepts = models.JSONField(default=list, blank=True)
    suggestions = models.JSONField(default=list, blank=True)
    insights = models.JSONField(default=list, blank=True)
    complexity = models.JSONField(default=dict, blank=True)
    modules = models.JSONField(default=list, blank=True)
    blocked_modules = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def code_preview(self):
        return (self.code or '').strip().replace('\n', ' ')[:80]
