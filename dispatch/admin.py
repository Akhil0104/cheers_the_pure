from django.contrib import admin

from .models import BusinessRule, ConversationMessage, ConversationSession, DispatchDecision


@admin.register(ConversationSession)
class ConversationSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'is_active', 'message_count', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user__email', 'user__username', 'title')
    readonly_fields = ('session_id', 'created_at', 'updated_at')
    ordering = ('-updated_at',)

    def message_count(self, obj):
        return obj.messages.count()
    message_count.short_description = 'Messages'


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'role', 'content_preview', 'created_at')
    list_filter = ('role', 'created_at')
    search_fields = ('session__user__email', 'content')
    readonly_fields = ('created_at',)
    ordering = ('-created_at',)

    def content_preview(self, obj):
        return obj.content[:80]
    content_preview.short_description = 'Content'


@admin.register(DispatchDecision)
class DispatchDecisionAdmin(admin.ModelAdmin):
    list_display = (
        'decision_type', 'session_user', 'rule_applied',
        'was_overridden', 'groq_model', 'tokens_used', 'latency_ms', 'created_at',
    )
    list_filter = ('decision_type', 'was_overridden', 'groq_model', 'created_at')
    search_fields = ('session__user__email', 'rule_applied')
    readonly_fields = ('created_at', 'input_data', 'output_data')
    ordering = ('-created_at',)

    def session_user(self, obj):
        return obj.session.user.email
    session_user.short_description = 'User'

    def has_add_permission(self, request):
        """Audit trail is immutable — no manual creation."""
        return False


@admin.register(BusinessRule)
class BusinessRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'rule_type', 'is_active', 'priority', 'updated_at')
    list_filter = ('rule_type', 'is_active')
    search_fields = ('name', 'description')
    ordering = ('-priority', 'name')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Rule Identity', {
            'fields': ('name', 'rule_type', 'is_active', 'priority'),
        }),
        ('Rule Content', {
            'fields': ('description', 'parameters'),
            'description': (
                'The "description" field is injected verbatim into every Groq system prompt. '
                'Write it in plain English as an instruction to the AI.'
            ),
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
