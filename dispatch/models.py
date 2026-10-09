"""
DispatchAI Models

These models are completely separate from the existing app/ models.
- They do NOT modify any existing tables.
- They reference app.User via FK but never write to app.* models.
- All AI-specific state lives here.
"""

import uuid

from django.contrib.auth.models import User
from django.db import models


# ── Conversation Models ───────────────────────────────────────────────────────

class ConversationSession(models.Model):
    """
    Represents a single AI chat session between a B2B distributor and DispatchAI.
    Scoped per user. Multiple sessions per user are allowed (like chat history tabs).
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='dispatch_sessions',
    )
    session_id = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    title = models.CharField(
        max_length=200,
        blank=True,
        help_text='Auto-generated from first user message.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Conversation Session'
        verbose_name_plural = 'Conversation Sessions'

    def __str__(self):
        title = self.title or f'Session {str(self.session_id)[:8]}'
        return f'{self.user.email} — {title}'

    def get_recent_messages(self, limit=20):
        """Return the most recent messages for building LLM context window."""
        return list(self.messages.order_by('-created_at', '-id')[:limit])[::-1]  # Reverse to chronological


class ConversationMessage(models.Model):
    """
    A single message turn in a DispatchAI conversation.
    Stores both user messages and AI responses.
    """
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
        ('system', 'System'),
    ]

    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    # Stores references, tool calls, error flags, token counts
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        verbose_name = 'Conversation Message'
        verbose_name_plural = 'Conversation Messages'

    def __str__(self):
        preview = self.content[:60].replace('\n', ' ')
        return f'[{self.role}] {preview}...'


# ── Audit / Decision Trail ────────────────────────────────────────────────────

class DispatchDecision(models.Model):
    """
    Immutable audit trail for every AI decision or action.
    Enables admin review and compliance reporting.
    """
    DECISION_TYPES = [
        ('quote_price', 'Quote Price Suggestion'),
        ('delivery_estimate', 'Delivery Estimate'),
        ('product_recommendation', 'Product Recommendation'),
        ('stock_check', 'Stock Availability Check'),
        ('rule_correction', 'Business Rule Correction Applied'),
        ('escalation', 'Escalated to Admin'),
        ('general_response', 'General Conversational Response'),
    ]

    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.CASCADE,
        related_name='decisions',
    )
    message = models.ForeignKey(
        ConversationMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='decisions',
    )
    decision_type = models.CharField(max_length=30, choices=DECISION_TYPES)
    input_data = models.JSONField(
        help_text='What the AI received (user message, DB context, memories).',
    )
    output_data = models.JSONField(
        help_text='What the AI decided (response, suggested price, etc.).',
    )
    rule_applied = models.CharField(
        max_length=200,
        blank=True,
        help_text='Name of BusinessRule that was validated against.',
    )
    was_overridden = models.BooleanField(
        default=False,
        help_text='True if admin manually corrected this AI decision.',
    )
    groq_model = models.CharField(max_length=100, blank=True)
    tokens_used = models.PositiveIntegerField(default=0)
    latency_ms = models.PositiveIntegerField(
        default=0,
        help_text='Groq response latency in milliseconds.',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Dispatch Decision'
        verbose_name_plural = 'Dispatch Decisions'

    def __str__(self):
        return f'{self.decision_type} — {self.session.user.email} ({self.created_at:%Y-%m-%d})'


# ── Business Rules ────────────────────────────────────────────────────────────

class BusinessRule(models.Model):
    """
    Admin-configurable business rules that constrain DispatchAI responses.
    These are injected into every system prompt so the AI always respects them.
    """
    RULE_TYPES = [
        ('moq', 'Minimum Order Quantity'),
        ('price_floor', 'Price Floor (₹/unit)'),
        ('price_ceiling', 'Price Ceiling (₹/unit)'),
        ('max_discount_pct', 'Maximum Discount %'),
        ('delivery_zone', 'Delivery Zone Restriction'),
        ('inventory_threshold', 'Inventory Threshold Before Quoting'),
        ('custom', 'Custom Rule (free-form instruction)'),
    ]

    name = models.CharField(max_length=200)
    rule_type = models.CharField(max_length=30, choices=RULE_TYPES)
    description = models.TextField(
        help_text='Plain English description. Injected verbatim into Groq system prompt.',
    )
    parameters = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            'Structured rule parameters. Examples:\n'
            '  moq: {"min_qty": 100}\n'
            '  price_floor: {"min_price": 3.00, "product_category": "all"}\n'
            '  max_discount_pct: {"max_pct": 15}\n'
            '  delivery_zone: {"allowed_states": ["Telangana", "AP", "Karnataka"]}\n'
            '  inventory_threshold: {"min_stock_pct": 10}'
        ),
    )
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(
        default=0,
        help_text='Higher number = evaluated first. Rules are injected in priority order.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-priority', 'name']
        verbose_name = 'Business Rule'
        verbose_name_plural = 'Business Rules'

    def __str__(self):
        status = '✓' if self.is_active else '✗'
        return f'[{status}] {self.name} ({self.get_rule_type_display()})'


# ── Agent Action Audit Log ───────────────────────────────────────────────────

class AgentActionLog(models.Model):
    """
    Immutable audit log for controlled business workflow actions executed
    or proposed by DispatchAI.
    """
    ACTION_TYPES = [
        ('search_product', 'Search Product Catalog'),
        ('get_current_price', 'Get Current Price'),
        ('get_order_history', 'Get Order History'),
        ('get_quote_status', 'Get Quote Status'),
        ('get_payment_status', 'Get Payment Status'),
        ('create_quote_request', 'Create Quote Request'),
        ('prepare_order_request', 'Prepare Order Request'),
        ('check_delivery_preference', 'Check Delivery Preference'),
        ('summarize_requirements', 'Summarize Customer Requirements'),
        ('apply_discount', 'Apply Discount Proposal'),
        ('confirm_payment', 'Confirm Payment Verification'),
        ('change_terms', 'Contractual Terms Modification'),
    ]

    STATUS_CHOICES = [
        ('proposed', 'Action Proposed (Pending Confirmation)'),
        ('confirmed', 'Action Confirmed by User'),
        ('executed', 'Action Executed Successfully'),
        ('rejected', 'Action Rejected / Cancelled'),
        ('failed', 'Action Execution Failed'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='agent_action_logs',
    )
    buyer_id = models.CharField(max_length=50, blank=True)
    session = models.ForeignKey(
        ConversationSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='action_logs',
    )
    action_type = models.CharField(max_length=40, choices=ACTION_TYPES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='executed')
    is_sensitive = models.BooleanField(default=False)
    requires_confirmation = models.BooleanField(default=False)
    proposal_explanation = models.TextField(blank=True)
    action_data = models.JSONField(default=dict, blank=True)
    result_data = models.JSONField(default=dict, blank=True)
    confirmed_by_user = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Agent Action Log'
        verbose_name_plural = 'Agent Action Logs'

    def __str__(self):
        return f"[{self.status.upper()}] {self.get_action_type_display()} for {self.buyer_id or self.user.username} ({self.created_at:%Y-%m-%d %H:%M})"

