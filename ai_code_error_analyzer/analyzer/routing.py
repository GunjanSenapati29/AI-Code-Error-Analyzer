from django.urls import re_path
from .consumers import ExecutionConsumer

websocket_urlpatterns = [
    re_path(r'^ws/execute/$', ExecutionConsumer.as_asgi()),
]