# core/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from dispatch import views as dispatch_views

urlpatterns = [
    path('portal-hq-access/', admin.site.urls),
    path('demo/memory/', dispatch_views.memory_demo_view, name='memory_demo'),
    path('demo/memory', dispatch_views.memory_demo_view, name='memory_demo_noslash'),
    path('api/demo/memory/chat/', dispatch_views.api_demo_memory_chat, name='api_demo_memory_chat'),
    path('api/demo/memory/reset/', dispatch_views.api_demo_memory_reset, name='api_demo_memory_reset'),
    path('api/agent/chat', dispatch_views.agent_chat_api, name='agent_chat_api'),
    path('api/agent/chat/', dispatch_views.agent_chat_api, name='agent_chat_api_slash'),
    path('', include('app.urls')),
    path('api/dispatch/', include('dispatch.urls', namespace='dispatch')),  # DispatchAI
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
