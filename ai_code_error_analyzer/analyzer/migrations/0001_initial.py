from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion

class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name='ExecutionRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('language', models.CharField(choices=[('python', 'Python'), ('java', 'Java'), ('c', 'C')], max_length=10)),
                ('code', models.TextField()), ('output', models.TextField(blank=True, default='')), ('raw_error', models.TextField(blank=True, default='')),
                ('error_type', models.CharField(blank=True, default='', max_length=120)), ('explanation', models.TextField(blank=True, default='')),
                ('corrected_code', models.TextField(blank=True, default='')), ('line_number', models.IntegerField(blank=True, null=True)),
                ('status', models.CharField(choices=[('success', 'Success'), ('error', 'Error'), ('blocked', 'Blocked'), ('timeout', 'Timeout'), ('running', 'Running')], default='running', max_length=10)),
                ('concepts', models.JSONField(blank=True, default=list)), ('suggestions', models.JSONField(blank=True, default=list)), ('insights', models.JSONField(blank=True, default=list)),
                ('complexity', models.JSONField(blank=True, default=dict)), ('modules', models.JSONField(blank=True, default=list)), ('blocked_modules', models.JSONField(blank=True, default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)), ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executions', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
