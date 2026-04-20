import json
from asgiref.sync import sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .models import ExecutionRecord
from .process_manager import send_input, start_execution, stop_execution


class ExecutionConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = None
        self.group_name = None

        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.close()
            return

        self.group_name = f'user_{user.id}_execution'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self.send(text_data=json.dumps({
            'type': 'status',
            'message': 'WebSocket connected successfully'
        }))

    async def disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON data'
            }))
            return

        action = data.get('action')
        if action == 'start':
            await self.handle_start(data)
        elif action == 'input':
            await self.handle_input(data)
        elif action == 'stop':
            await self.handle_stop()
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Unknown action'
            }))

    async def handle_start(self, data):
        user = self.scope.get('user')
        if not user or user.is_anonymous:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Authentication required'
            }))
            return

        code = data.get('code', '')
        language = data.get('language', 'python')

        if not code.strip():
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Code cannot be empty'
            }))
            return

        if len(code) > getattr(settings, 'MAX_CODE_SIZE', 50000):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Code is too large for one run'
            }))
            return

        if language not in ['python', 'java', 'c']:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Unsupported language'
            }))
            return

        if language in ['java', 'c']:
            await self.send(text_data=json.dumps({
                'event': 'complete',
                'status': 'coming_soon',
                'record_id': None,
                'analysis': {
                    'hasError': False,
                    'is_code_correct': True,
                    'type': '',
                    'line': None,
                    'raw': '',
                    'error': '',
                    'output': '',
                    'explain': f'{language.upper()} execution support is coming soon.',
                    'root_cause': '',
                    'fix': '',
                    'corrected_code': '',
                    'tips': [f'{language.upper()} execution will be available in a future update.'],
                    'optimizations': [],
                    'time': 'N/A',
                    'space': 'N/A',
                    'complexity_explanation': '',
                    'concepts': [f'{language.upper()} Support Coming Soon'],
                    'insights': [f'{language.upper()} execution is not enabled yet.'],
                    'steps': [],
                    'viva_answer': '',
                    'confidence': 'high',
                    'source': 'system'
                }
            }))
            return

        if self.session_id:
            await sync_to_async(stop_execution)(self.session_id)
            self.session_id = None

        record = await sync_to_async(ExecutionRecord.objects.create)(
            user=user,
            language=language,
            code=code,
            status='running'
        )

        self.session_id = await sync_to_async(start_execution)(
            user_id=user.id,
            group_name=self.group_name,
            language=language,
            code=code,
            record=record
        )

        await self.send(text_data=json.dumps({
            'event': 'started',
            'record_id': record.id,
            'session_id': self.session_id
        }))

    async def handle_input(self, data):
        if not self.session_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'No active execution session'
            }))
            return

        text = data.get('text', '')
        ok = await sync_to_async(send_input)(self.session_id, text)
        if not ok:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to send input'
            }))

    async def handle_stop(self):
        if not self.session_id:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'No active execution session'
            }))
            return

        ok = await sync_to_async(stop_execution)(self.session_id)
        if ok:
            await self.send(text_data=json.dumps({
                'type': 'status',
                'message': 'Execution stopped'
            }))
            self.session_id = None
        else:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to stop execution'
            }))

    async def stream_message(self, event):
        payload = event['payload']
        await self.send(text_data=json.dumps(payload))
        if payload.get('event') == 'complete':
            self.session_id = None