from django.contrib import admin
from .models import ExecutionRecord

@admin.register(ExecutionRecord)
class ExecutionRecordAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'language', 'status', 'error_type', 'created_at')
