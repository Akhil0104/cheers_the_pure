"""
DispatchAI API Views.

All endpoints are under /api/dispatch/ and require session authentication.
B2B distributors and staff/admin can access the chat endpoints.
B2C-only customers are blocked with 403.

Endpoints:
    POST /api/dispatch/sessions/                  Create new session
    GET  /api/dispatch/sessions/                  List user's sessions
    GET  /api/dispatch/sessions/<session_id>/     Get session + messages
    POST /api/dispatch/chat/                      Send message to agent
    GET  /api/dispatch/chat/stream/<session_id>/  SSE stream (last AI response)
    GET  /api/dispatch/decisions/                 Audit trail (admin only)
    GET  /api/dispatch/rules/                     List business rules (admin)
    POST /api/dispatch/rules/                     Create rule (admin)
    PUT  /api/dispatch/rules/<pk>/                Update rule (admin)
"""

import json
import logging
import time
import uuid

from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from . import agent as dispatch_agent
from . import groq_client
from .models import BusinessRule, ConversationMessage, ConversationSession, DispatchDecision
from .services import process_dispatch_chat, validate_buyer_identity

logger = logging.getLogger(__name__)


def is_rate_limited(key: str, limit: int = 30, window_seconds: int = 60) -> bool:
    """
    Standard sliding/fixed window rate limiter using Django's cache backend.
    Returns True if rate limit is exceeded.
    """
    cache_key = f"dispatch_ratelimit:{key}"
    try:
        current_count = cache.get(cache_key, 0)
        if current_count >= limit:
            return True
        cache.set(cache_key, current_count + 1, timeout=window_seconds)
    except Exception:
        pass  # Fail open if cache is unavailable
    return False


# ── Auth Helpers ──────────────────────────────────────────────────────────────

def _is_b2b_or_admin(user) -> bool:
    """Allow B2B distributors and staff/admin. Block B2C-only customers."""
    if not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    if profile:
        return profile.account_type == 'b2b'
    # Fallback: check email domain
    from app.account_utils import detect_account_type
    return detect_account_type(user.email) == 'b2b'


def _json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({'ok': False, 'error': message}, status=status)


def _require_dispatch_access(request):
    """Returns None if access is granted, else a JsonResponse error."""
    if not request.user.is_authenticated:
        return _json_error('Authentication required.', 401)
    if not _is_b2b_or_admin(request.user):
        return _json_error('B2B account required to use DispatchAI.', 403)
    return None


# ── Session Views ─────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET', 'POST'])
def sessions(request):
    """
    GET  — List the current user's conversation sessions (most recent first).
    POST — Create a new conversation session.
    """
    auth_error = _require_dispatch_access(request)
    if auth_error:
        return auth_error

    if request.method == 'GET':
        user_sessions = (
            ConversationSession.objects
            .filter(user=request.user, is_active=True)
            .order_by('-updated_at')[:50]
        )
        data = [
            {
                'session_id': str(s.session_id),
                'title': s.title or 'New Conversation',
                'message_count': s.messages.count(),
                'updated_at': s.updated_at.isoformat(),
                'created_at': s.created_at.isoformat(),
            }
            for s in user_sessions
        ]
        return JsonResponse({'ok': True, 'sessions': data})

    # POST — create new session
    session = ConversationSession.objects.create(user=request.user)
    return JsonResponse({
        'ok': True,
        'session_id': str(session.session_id),
        'title': '',
        'created_at': session.created_at.isoformat(),
    }, status=201)


@login_required
@require_http_methods(['GET'])
def session_detail(request, session_id):
    """
    GET — Retrieve a specific session with its full message history.
    """
    auth_error = _require_dispatch_access(request)
    if auth_error:
        return auth_error

    try:
        if request.user.is_staff:
            session = ConversationSession.objects.get(session_id=session_id)
        else:
            session = ConversationSession.objects.get(
                session_id=session_id, user=request.user
            )
    except ConversationSession.DoesNotExist:
        return _json_error('Session not found.', 404)

    messages = session.messages.order_by('created_at')
    return JsonResponse({
        'ok': True,
        'session': {
            'session_id': str(session.session_id),
            'title': session.title or 'Conversation',
            'user_email': session.user.email,
            'is_active': session.is_active,
            'created_at': session.created_at.isoformat(),
            'updated_at': session.updated_at.isoformat(),
        },
        'messages': [
            {
                'id': m.id,
                'role': m.role,
                'content': m.content,
                'metadata': m.metadata,
                'created_at': m.created_at.isoformat(),
            }
            for m in messages
        ],
    })


# ── Chat Endpoint ─────────────────────────────────────────────────────────────

@login_required
@require_http_methods(['POST'])
def chat(request):
    """
    POST — Send a message to DispatchAI and receive a response.

    Request body (JSON):
    {
        "session_id": "uuid-string or null",   // null → creates new session
        "message": "I need 500 units of 500ml bottles for Bangalore"
    }

    Response:
    {
        "ok": true,
        "session_id": "uuid-string",
        "message": {
            "id": 42,
            "role": "assistant",
            "content": "Based on your order history...",
            "metadata": { "model": "...", "tokens_used": 123, ... }
        },
        "agent_meta": {
            "memories_count": 3,
            "rules_applied": ["Minimum Order Quantity"],
            "decision_type": "quote_price",
            "latency_ms": 1842,
            "error": false
        }
    }
    """
    auth_error = _require_dispatch_access(request)
    if auth_error:
        return auth_error

    # Parse body
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return _json_error('Invalid JSON body.')

    user_message = (body.get('message') or '').strip()
    if not user_message:
        return _json_error('message is required.')

    if len(user_message) > 2000:
        return _json_error('Message too long (max 2000 characters).')

    session_id = body.get('session_id')

    # Get or create session
    session = None
    if session_id:
        try:
            session = ConversationSession.objects.get(
                session_id=session_id, user=request.user
            )
        except ConversationSession.DoesNotExist:
            pass  # Create new one below

    if not session:
        session = ConversationSession.objects.create(user=request.user)

    # Save user message
    user_msg = ConversationMessage.objects.create(
        session=session,
        role='user',
        content=user_message,
    )

    # Update session timestamp
    session.save(update_fields=['updated_at'])

    # Run agent
    try:
        result = dispatch_agent.process_message(
            user=request.user,
            session=session,
            user_message_text=user_message,
        )
    except Exception as exc:
        logger.error('Agent process_message crashed: %s', exc, exc_info=True)
        result = {
            'content': (
                'I encountered an unexpected issue. Please try again, or contact '
                'cheersthepure@gmail.com for assistance.'
            ),
            'model': '',
            'tokens_used': 0,
            'latency_ms': 0,
            'rules_applied': [],
            'decision_type': 'general_response',
            'memories_count': 0,
            'error': True,
        }

    # Get the saved assistant message
    assistant_msg = (
        session.messages
        .filter(role='assistant')
        .order_by('-created_at')
        .first()
    )

    return JsonResponse({
        'ok': True,
        'session_id': str(session.session_id),
        'message': {
            'id': assistant_msg.id if assistant_msg else None,
            'role': 'assistant',
            'content': result['content'],
            'metadata': assistant_msg.metadata if assistant_msg else {},
            'created_at': assistant_msg.created_at.isoformat() if assistant_msg else None,
        },
        'agent_meta': {
            'memories_count': result['memories_count'],
            'rules_applied': result['rules_applied'],
            'decision_type': result['decision_type'],
            'latency_ms': result['latency_ms'],
            'error': result['error'],
        },
    })


@login_required
@require_http_methods(['GET'])
def chat_stream(request, session_id):
    """
    GET — Server-Sent Events (SSE) stream for DispatchAI responses.

    Query params:
        message — The user's message to send to the agent.

    Streams:
        data: {"type": "token", "content": "Based"}
        data: {"type": "token", "content": " on"}
        ...
        data: {"type": "done", "session_id": "...", "full_content": "..."}
        data: {"type": "error", "content": "Error message"}
    """
    auth_error = _require_dispatch_access(request)
    if auth_error:
        # Can't return JsonResponse for SSE — just close
        return _json_error('Access denied.', 403)

    user_message = request.GET.get('message', '').strip()
    if not user_message:
        return _json_error('message query param required.')

    # Get or create session
    session = None
    if session_id:
        try:
            session = ConversationSession.objects.get(
                session_id=session_id, user=request.user
            )
        except ConversationSession.DoesNotExist:
            pass

    if not session:
        session = ConversationSession.objects.create(user=request.user)

    # Save user message upfront
    ConversationMessage.objects.create(
        session=session,
        role='user',
        content=user_message,
    )
    session.save(update_fields=['updated_at'])

    def event_stream():
        """Generator yielding SSE-formatted chunks."""
        try:
            # Build context + prompt (same as non-streaming chat)
            from .context_builder import build as build_context, get_active_business_rules
            from .prompts.system import build_system_prompt

            context = build_context(user=request.user, user_message=user_message)
            business_rules = get_active_business_rules()
            system_prompt = build_system_prompt(context=context, business_rules=business_rules)

            recent_messages = session.get_recent_messages(limit=20)
            groq_messages = [{'role': 'system', 'content': system_prompt}]
            for msg in recent_messages:
                if msg.role in ('user', 'assistant'):
                    groq_messages.append({'role': msg.role, 'content': msg.content})
            groq_messages.append({'role': 'user', 'content': user_message})

            # Stream from Groq
            full_response = ''
            for token in groq_client.chat_stream(messages=groq_messages):
                if token == '__GROQ_STREAM_ERROR__':
                    yield f'data: {json.dumps({"type": "error", "content": "Groq stream error. Please try again."})}\n\n'
                    return

                full_response += token
                yield f'data: {json.dumps({"type": "token", "content": token})}\n\n'

            # Validate response
            from .rules_engine import validate_response
            final_response, rules_applied = validate_response(full_response, context)

            # If rules added corrections, stream the correction too
            if final_response != full_response:
                correction = final_response[len(full_response):]
                yield f'data: {json.dumps({"type": "token", "content": correction})}\n\n'

            # Save complete assistant message
            asst_msg = ConversationMessage.objects.create(
                session=session,
                role='assistant',
                content=final_response,
                metadata={
                    'rules_applied': rules_applied,
                    'stream': True,
                    'memories_recalled': len(context.get('memories', [])),
                },
            )

            # Retain memories
            dispatch_agent._retain_memories_async(
                user=request.user,
                user_message=user_message,
                ai_response=final_response,
            )

            # Auto-title session
            if not session.title:
                session.title = user_message[:60]
                session.save(update_fields=['title', 'updated_at'])

            yield f'data: {json.dumps({"type": "done", "session_id": str(session.session_id), "message_id": asst_msg.id, "rules_applied": rules_applied})}\n\n'

        except Exception as exc:
            logger.error('SSE stream error: %s', exc, exc_info=True)
            yield f'data: {json.dumps({"type": "error", "content": "An unexpected error occurred. Please try again."})}\n\n'

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'  # Disable Nginx buffering for SSE
    return response


# ── Admin-Only Endpoints ──────────────────────────────────────────────────────

@login_required
@require_http_methods(['GET'])
def decisions(request):
    """
    GET — List DispatchDecision audit trail (admin/staff only).

    Query params:
        limit (int)    — Max records to return (default 50)
        session_id     — Filter by session UUID
    """
    if not (request.user.is_staff or request.user.is_superuser):
        return _json_error('Admin access required.', 403)

    limit = min(int(request.GET.get('limit', 50)), 200)
    qs = DispatchDecision.objects.select_related('session__user').order_by('-created_at')

    session_id = request.GET.get('session_id')
    if session_id:
        qs = qs.filter(session__session_id=session_id)

    data = [
        {
            'id': d.id,
            'session_id': str(d.session.session_id),
            'user_email': d.session.user.email,
            'decision_type': d.decision_type,
            'rule_applied': d.rule_applied,
            'was_overridden': d.was_overridden,
            'groq_model': d.groq_model,
            'tokens_used': d.tokens_used,
            'latency_ms': d.latency_ms,
            'output_preview': str(d.output_data.get('response_preview', ''))[:100],
            'created_at': d.created_at.isoformat(),
        }
        for d in qs[:limit]
    ]
    return JsonResponse({'ok': True, 'decisions': data, 'count': len(data)})


@login_required
@require_http_methods(['GET', 'POST'])
def rules(request):
    """
    GET  — List all BusinessRules (admin only).
    POST — Create a new BusinessRule (admin only).
    """
    if not (request.user.is_staff or request.user.is_superuser):
        return _json_error('Admin access required.', 403)

    if request.method == 'GET':
        all_rules = BusinessRule.objects.all().order_by('-priority', 'name')
        data = [
            {
                'id': r.id,
                'name': r.name,
                'rule_type': r.rule_type,
                'description': r.description,
                'parameters': r.parameters,
                'is_active': r.is_active,
                'priority': r.priority,
                'updated_at': r.updated_at.isoformat(),
            }
            for r in all_rules
        ]
        return JsonResponse({'ok': True, 'rules': data})

    # POST
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return _json_error('Invalid JSON body.')

    required = ['name', 'rule_type', 'description']
    for field in required:
        if not body.get(field):
            return _json_error(f'{field} is required.')

    valid_types = [choice[0] for choice in BusinessRule.RULE_TYPES]
    if body['rule_type'] not in valid_types:
        return _json_error(f'Invalid rule_type. Choose from: {valid_types}')

    rule = BusinessRule.objects.create(
        name=body['name'],
        rule_type=body['rule_type'],
        description=body['description'],
        parameters=body.get('parameters', {}),
        is_active=body.get('is_active', True),
        priority=body.get('priority', 0),
    )
    return JsonResponse({
        'ok': True,
        'id': rule.id,
        'name': rule.name,
    }, status=201)


@login_required
@require_http_methods(['PUT', 'PATCH'])
def rule_detail(request, pk):
    """PUT/PATCH — Update a BusinessRule (admin only)."""
    if not (request.user.is_staff or request.user.is_superuser):
        return _json_error('Admin access required.', 403)

    try:
        rule = BusinessRule.objects.get(pk=pk)
    except BusinessRule.DoesNotExist:
        return _json_error('Rule not found.', 404)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return _json_error('Invalid JSON body.')

    updatable = ['name', 'description', 'parameters', 'is_active', 'priority']
    for field in updatable:
        if field in body:
            setattr(rule, field, body[field])
    rule.save()

    return JsonResponse({'ok': True, 'id': rule.id, 'name': rule.name})


# ── Production Endpoint: POST /api/agent/chat ─────────────────────────────────

@csrf_exempt
@require_http_methods(['POST'])
def agent_chat_api(request):
    """
    Production API endpoint: POST /api/agent/chat

    Request Payload (JSON):
    {
        "buyer_id": "DIST-00042",   # Optional; derived securely from session if omitted
        "message": "...",          # Required
        "session_id": "..."        # Optional UUID string
    }

    Response Format (JSON):
    {
        "success": true,
        "reply": "...",
        "memory_used": true,
        "memory_summary": "...",
        "sources": [...],
        "actions": [...],
        "session_id": "...",
        "buyer_id": "..."
    }
    """
    # 1. Authenticate user
    if not request.user.is_authenticated:
        return JsonResponse({
            "success": False,
            "error": "Authentication required. Please sign in to access DispatchAI.",
            "reply": "",
        }, status=401)

    # 2. Validate B2B authorization
    if not _is_b2b_or_admin(request.user):
        return JsonResponse({
            "success": False,
            "error": "Access restricted: DispatchAI is exclusively for verified B2B wholesale buyers and distributors.",
            "reply": "",
        }, status=403)

    # Rate limiting: 30 requests per minute per authenticated user
    rate_limit_key = f"user_{request.user.id}"
    if is_rate_limited(rate_limit_key, limit=30, window_seconds=60):
        return JsonResponse({
            "success": False,
            "error": "Rate limit exceeded (maximum 30 requests/minute). Please wait a moment before sending another message.",
            "reply": "",
        }, status=429)

    # 3. Parse & Validate request JSON body
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError, UnicodeDecodeError):
        return JsonResponse({
            "success": False,
            "error": "Invalid JSON body in request.",
            "reply": "",
        }, status=400)

    if not isinstance(data, dict):
        return JsonResponse({
            "success": False,
            "error": "Request body must be a valid JSON object.",
            "reply": "",
        }, status=400)

    raw_message = data.get("message")
    if raw_message is None or not str(raw_message).strip():
        return JsonResponse({
            "success": False,
            "error": "The 'message' field is required and cannot be empty.",
            "reply": "",
        }, status=400)

    message = str(raw_message).strip()
    if len(message) > 4000:
        return JsonResponse({
            "success": False,
            "error": "Message exceeds maximum allowed length of 4,000 characters.",
            "reply": "",
        }, status=400)

    # Resolve buyer identity securely from session (prevents IDOR / unauthorized impersonation)
    authenticated_profile = getattr(request.user, 'profile', None)
    authenticated_buyer_id = authenticated_profile.get_buyer_id() if authenticated_profile else f"DIST-{request.user.id:05d}"

    requested_buyer_id = data.get("buyer_id")
    # Staff users may inspect specific buyer accounts; non-staff users are locked to their own identity
    if requested_buyer_id and request.user.is_staff:
        effective_buyer = requested_buyer_id
    else:
        effective_buyer = request.user

    session_id = data.get("session_id")

    # 4-8. Execute 9-step DispatchAI cognitive pipeline
    try:
        result = process_dispatch_chat(
            buyer=effective_buyer,
            user_message=message,
            session_id=session_id,
        )
    except Exception as exc:
        logger.error("[DispatchAI API] Unexpected execution failure: %s", exc)
        return JsonResponse({
            "success": False,
            "error": "An internal error occurred while processing your request. Please try again.",
            "reply": "I encountered an error processing your request. Please try again shortly.",
        }, status=500)

    # 9. Format structured production response
    mem_count = result.get("memories_count", 0)
    memory_used = mem_count > 0
    memory_summary = f"Recalled {mem_count} customer preference{'s' if mem_count > 1 else ''} from previous conversations." if memory_used else ""

    sources = [
        "Cheers the Pure Authoritative Database Catalog",
        "Active B2B Business Rules",
    ]
    if memory_used:
        sources.append("Hindsight Persistent Memory (cheersthepure-b2b)")

    actions = []
    if any(term in message.lower() for term in ['quote', 'bulk', 'wholesale', 'order', 'pricing', 'buy']):
        actions.append({
            "type": "request_quote",
            "label": "Submit Formal Quote Request",
            "url": "/orders/request/",
        })
    if any(term in message.lower() for term in ['track', 'status', 'delivery', 'where is']):
        actions.append({
            "type": "view_orders",
            "label": "View Order History & Logistics",
            "url": "/dashboard/",
        })

    return JsonResponse({
        "success": result.get("ok", True),
        "reply": result.get("content", ""),
        "memory_used": memory_used,
        "memory_summary": memory_summary,
        "sources": sources,
        "actions": actions,
        "session_id": result.get("session_id", ""),
        "buyer_id": result.get("buyer_id", authenticated_buyer_id),
    })


# ── Memory Demonstration Views & APIs ─────────────────────────────────────────

from dispatch.demo_service import (
    DEMO_BUYER_ID,
    DEMO_COMPANY,
    execute_demo_turn,
    get_or_create_demo_customer,
    reset_demo_data,
)
from dispatch.services.hindsight_service import get_buyer_memories


def memory_demo_view(request):
    """
    Dedicated Memory Demonstration View.
    Showcases multi-session persistent memory recall and retention using Hindsight.
    Customer: Sri Balaji Supermarket (DIST-BALAJI-01)
    """
    demo_user = get_or_create_demo_customer()
    existing_memories = get_buyer_memories(DEMO_BUYER_ID)

    context = {
        "demo_buyer_id": DEMO_BUYER_ID,
        "demo_company": DEMO_COMPANY,
        "demo_user": demo_user,
        "existing_memories": existing_memories,
        "initial_session_id": f"sess_balaji_{uuid.uuid4().hex[:8]}",
    }
    return render(request, "app/memory_demo.html", context)


@require_POST
def api_demo_memory_chat(request):
    """
    Interactive API for the Memory Demonstration.
    Processes turns for Sri Balaji Supermarket and returns detailed evaluation telemetry.
    """
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)

    message = (data.get("message") or "").strip()
    if not message:
        return JsonResponse({"success": False, "error": "Message is required"}, status=400)

    session_id = data.get("session_id")
    session_number = int(data.get("session_number", 1))

    telemetry = execute_demo_turn(
        message=message,
        session_id=session_id,
        session_number=session_number,
    )
    return JsonResponse(telemetry)


@require_POST
def api_demo_memory_reset(request):
    """
    Resets memories and sessions for Sri Balaji Supermarket for fresh evaluator testing.
    """
    result = reset_demo_data()
    return JsonResponse(result)


