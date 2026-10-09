# dispatch/urls.py
from django.urls import path

from . import views

app_name = 'dispatch'

urlpatterns = [
    # Session management
    path('sessions/', views.sessions, name='sessions'),
    path('sessions/<uuid:session_id>/', views.session_detail, name='session_detail'),

    # Production Agent API
    path('agent/chat/', views.agent_chat_api, name='agent_chat'),

    # Chat (AJAX — synchronous, full response)
    path('chat/', views.chat, name='chat'),

    # Chat (SSE — streaming, token-by-token)
    # session_id can be an existing UUID or "new" (creates new session)
    path('chat/stream/<str:session_id>/', views.chat_stream, name='chat_stream'),

    # Admin-only: audit trail
    path('decisions/', views.decisions, name='decisions'),

    # Admin-only: business rules CRUD
    path('rules/', views.rules, name='rules'),
    path('rules/<int:pk>/', views.rule_detail, name='rule_detail'),
]
