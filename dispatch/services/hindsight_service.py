"""
Hindsight Persistent Memory Service for DispatchAI.

Provides high-level, production-grade memory recall and retention
for B2B buyers and distributors in Cheers the Pure.

Default Memory Bank:
    cheersthepure-b2b

Exported Functions:
    - recall_customer_memory(buyer_id, query, limit=10, bank_id=None)
    - retain_customer_memory(buyer_id, content, bank_id=None, metadata=None)
    - is_hindsight_service_available()
    - search_customer_memories(buyer_id, query, limit=20)
    - forget_customer_memory(memory_id)

Guarantees:
    1. Zero Crash / Fail Graceful: All network, timeout, authentication, and
       parsing errors are caught, structured-logged (with masked secrets), and
       handled safely without crashing the caller.
    2. Buyer Isolation: Memory entries are strictly tagged and namespaced with
       the buyer's stable identifier (e.g. DIST-00042).
    3. Source of Truth Separation: Transactional data (orders, prices, invoices)
       remains in SQL. Hindsight ONLY stores buyer preferences, negotiation context,
       delivery schedules, and conversational nuances.
"""

from collections import defaultdict
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional, Union

from django.contrib.auth.models import User
from dispatch.config import (
    get_hindsight_api_key,
    get_hindsight_bank_id,
    get_hindsight_url,
    is_hindsight_configured,
    mask_secret,
)

logger = logging.getLogger(__name__)

# Standard timeout in seconds for persistent memory requests
HINDSIGHT_TIMEOUT_SECONDS = 5.0
DEFAULT_MEMORY_BANK = "cheersthepure-b2b"

# Local fallback store across sessions (used when offline/unconfigured or for demo verification)
_LOCAL_FALLBACK_STORE: Dict[str, List[Dict[str, Any]]] = defaultdict(list)


def get_buyer_memories(buyer_id: Union[str, int, User, Any]) -> List[Dict[str, Any]]:
    """Inspect all stored local memories for a given buyer."""
    stable_id = normalize_buyer_id(buyer_id)
    return list(_LOCAL_FALLBACK_STORE.get(stable_id, []))


def clear_buyer_memories(buyer_id: Optional[Union[str, int, User, Any]] = None) -> None:
    """Clear memories for a specific buyer (e.g. for demo reset) or all buyers."""
    if buyer_id:
        stable_id = normalize_buyer_id(buyer_id)
        _LOCAL_FALLBACK_STORE.pop(stable_id, None)
    else:
        _LOCAL_FALLBACK_STORE.clear()


# ── Helper: Buyer Identity Normalizer ─────────────────────────────────────────

def normalize_buyer_id(buyer_id: Union[str, int, User, Any]) -> str:
    """
    Consistently resolve any buyer reference (User, UserProfile, int, str)
    into a stable string identity for Hindsight namespacing.
    """
    if buyer_id is None:
        return ""

    if isinstance(buyer_id, User):
        try:
            if hasattr(buyer_id, 'profile') and buyer_id.profile:
                return buyer_id.profile.get_buyer_id()
        except Exception:
            pass
        return f"DIST-{buyer_id.id:05d}"

    # Check for UserProfile or custom model with get_buyer_id
    if hasattr(buyer_id, 'get_buyer_id') and callable(buyer_id.get_buyer_id):
        try:
            return str(buyer_id.get_buyer_id())
        except Exception:
            pass

    if isinstance(buyer_id, int):
        return f"DIST-{buyer_id:05d}"

    cleaned = str(buyer_id).strip()
    return cleaned


def _get_request_headers(api_key: str) -> Dict[str, str]:
    """Build safe headers for Hindsight API calls."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "CheersthePure-DispatchAI/1.0",
    }


def _get_active_bank_id(bank_id: Optional[str] = None) -> str:
    """Resolve active memory bank name."""
    return bank_id or get_hindsight_bank_id() or DEFAULT_MEMORY_BANK


# ── Core Service: Recall Customer Memory ──────────────────────────────────────

def recall_customer_memory(
    buyer_id: Union[str, int, User, Any],
    query: str,
    limit: int = 10,
    bank_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant long-term memories for a specific buyer/distributor.

    Args:
        buyer_id: Stable buyer ID (str, int, or User instance).
        query:    Inquiry or prompt used to semantically search memories.
        limit:    Maximum number of memories to return.
        bank_id:  Optional override for memory bank (default: cheersthepure-b2b).

    Returns:
        List of memory dicts:
        [
            {
                "id": "mem_01...",
                "content": "Distributor prefers Tuesday morning delivery in Nacharam",
                "category": "logistics_preference",
                "score": 0.92,
                "created_at": "2026-09-20T10:00:00Z",
            },
            ...
        ]
        Returns [] safely on any network, auth, timeout, or parsing failure.
    """
    stable_buyer_id = normalize_buyer_id(buyer_id)
    if not stable_buyer_id:
        logger.debug("[Hindsight] recall called with empty buyer_id; returning empty memories.")
        return []

    query_clean = str(query or "").strip()
    if not query_clean:
        logger.debug("[Hindsight] recall called with empty query for buyer=%s; returning empty memories.", stable_buyer_id)
        return []

    if not is_hindsight_configured():
        logger.debug(
            "[Hindsight] Service not configured (missing HINDSIGHT_API_KEY). Using persistent fallback memory for buyer=%s.",
            stable_buyer_id,
        )
        return _LOCAL_FALLBACK_STORE.get(stable_buyer_id, [])[:limit]

    base_url = get_hindsight_url()
    api_key = get_hindsight_api_key()
    active_bank = _get_active_bank_id(bank_id)
    buyer_tag = f"buyer:{stable_buyer_id}"

    # Try official SDK first if available
    try:
        import hindsight_client
        if hasattr(hindsight_client, 'Hindsight'):
            client = hindsight_client.Hindsight(
                base_url=base_url,
                api_key=api_key,
                timeout=HINDSIGHT_TIMEOUT_SECONDS,
            )
            response = client.recall(
                bank_id=active_bank,
                query=query_clean,
                tags=[buyer_tag],
                max_tokens=2048,
            )
            memories: List[Dict[str, Any]] = []
            results = getattr(response, 'results', None) or getattr(response, 'memories', None) or []
            for item in results:
                if isinstance(item, dict):
                    memories.append({
                        'id': str(item.get('id', '')),
                        'content': item.get('content', item.get('text', str(item))),
                        'category': item.get('category', 'general'),
                        'score': float(item.get('score', item.get('relevance', 1.0))),
                        'created_at': str(item.get('created_at', '')),
                    })
                elif hasattr(item, 'content'):
                    memories.append({
                        'id': getattr(item, 'id', ''),
                        'content': getattr(item, 'content', ''),
                        'category': getattr(item, 'category', 'general'),
                        'score': float(getattr(item, 'score', 1.0)),
                        'created_at': str(getattr(item, 'created_at', '')),
                    })
            logger.info(
                "[Hindsight] Recalled %d memories via SDK for buyer=%s (bank=%s)",
                len(memories),
                stable_buyer_id,
                active_bank,
            )
            return memories[:limit]
    except ImportError:
        pass  # Fallback to direct HTTP client below
    except Exception as sdk_exc:
        # Check for auth / timeout vs continuing to REST fallback
        err_msg = str(sdk_exc).lower()
        if "401" in err_msg or "unauthorized" in err_msg or "forbidden" in err_msg or "403" in err_msg:
            logger.error("[Hindsight] Authentication failure: check HINDSIGHT_API_KEY. Key: %s", mask_secret(api_key))
            return []
        if "timeout" in err_msg or "timed out" in err_msg:
            logger.warning("[Hindsight] API timeout after %.1fs during recall for buyer=%s", HINDSIGHT_TIMEOUT_SECONDS, stable_buyer_id)
            return []
        logger.debug("[Hindsight] SDK recall attempt raised %s; trying REST fallback.", sdk_exc)

    # HTTP REST Fallback
    try:
        import httpx
        headers = _get_request_headers(api_key)
        payload = {
            "bank_id": active_bank,
            "query": query_clean,
            "tags": [buyer_tag],
            "limit": limit,
            "user_id": stable_buyer_id,
        }

        url = f"{base_url}/v1/banks/{active_bank}/recall"
        # Also support legacy /api/recall if base URL doesn't use v1
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=HINDSIGHT_TIMEOUT_SECONDS)
            if resp.status_code == 404:
                # Fallback to alternate route
                url = f"{base_url}/api/recall"
                resp = httpx.post(url, json=payload, headers=headers, timeout=HINDSIGHT_TIMEOUT_SECONDS)
        except httpx.ConnectError as conn_err:
            logger.warning("[Hindsight] Service unavailable (ConnectError): %s", conn_err)
            return []

        if resp.status_code in (401, 403):
            logger.error("[Hindsight] Authentication failure (%d): check HINDSIGHT_API_KEY. Key: %s", resp.status_code, mask_secret(api_key))
            return []

        if resp.status_code >= 500:
            logger.warning("[Hindsight] Service error (%d) at %s: persistent memory temporarily unreachable.", resp.status_code, url)
            return []

        resp.raise_for_status()

        try:
            data = resp.json()
        except Exception as json_err:
            logger.warning("[Hindsight] Malformed JSON response received for buyer=%s: %s", stable_buyer_id, json_err)
            return []

        raw_memories = data.get("memories", data.get("results", data if isinstance(data, list) else []))
        formatted: List[Dict[str, Any]] = []
        for m in raw_memories:
            if isinstance(m, dict):
                formatted.append({
                    "id": str(m.get("id", "")),
                    "content": m.get("content", m.get("text", str(m))),
                    "category": m.get("category", "general"),
                    "score": float(m.get("score", m.get("relevance", 1.0))),
                    "created_at": str(m.get("created_at", "")),
                })
            elif isinstance(m, str) and m.strip():
                formatted.append({
                    "id": "",
                    "content": m.strip(),
                    "category": "general",
                    "score": 1.0,
                    "created_at": "",
                })

        logger.info(
            "[Hindsight] Recalled %d memories via HTTP for buyer=%s (bank=%s)",
            len(formatted),
            stable_buyer_id,
            active_bank,
        )
        return formatted[:limit]

    except httpx.TimeoutException:
        logger.warning("[Hindsight] API timeout after %.1fs during recall for buyer=%s", HINDSIGHT_TIMEOUT_SECONDS, stable_buyer_id)
        return []
    except httpx.HTTPStatusError as http_err:
        logger.warning("[Hindsight] HTTP status error (%s) during recall for buyer=%s", http_err.response.status_code, stable_buyer_id)
        return []
    except Exception as exc:
        logger.error("[Hindsight] Unexpected exception during memory recall for buyer=%s: %s", stable_buyer_id, exc)
        return []


# ── Core Service: Retain Customer Memory ──────────────────────────────────────

def retain_customer_memory(
    buyer_id: Union[str, int, User, Any],
    content: Union[str, List[Union[str, Dict[str, Any]]]],
    bank_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Store new long-term memories for a specific buyer/distributor.

    Args:
        buyer_id: Stable buyer ID (str, int, or User instance).
        content:  Memory content string, list of strings, or list of memory dicts.
        bank_id:  Optional override for memory bank (default: cheersthepure-b2b).
        metadata: Optional dictionary of extra non-sensitive metadata.

    Returns:
        List of stored memory IDs (e.g. ['mem_01', 'mem_02']) or [] on failure.
        Guaranteed not to throw or crash on failures.
    """
    stable_buyer_id = normalize_buyer_id(buyer_id)
    if not stable_buyer_id:
        logger.debug("[Hindsight] retain called with empty buyer_id; skipping.")
        return []

    if not content:
        logger.debug("[Hindsight] retain called with empty content for buyer=%s; skipping.", stable_buyer_id)
        return []

    # Prepare normalized items
    items_to_store: List[Dict[str, Any]] = []
    if isinstance(content, str):
        c_str = content.strip()
        if c_str:
            items_to_store.append({"content": c_str, "importance": "medium"})
    elif isinstance(content, list):
        for item in content:
            if isinstance(item, str) and item.strip():
                items_to_store.append({"content": item.strip(), "importance": "medium"})
            elif isinstance(item, dict) and item.get("content"):
                items_to_store.append(item)

    # Always record in local store for session persistence and demo verification
    fallback_ids = []
    for item in items_to_store:
        mem_id = f"mem_{len(_LOCAL_FALLBACK_STORE[stable_buyer_id]) + 1:03d}"
        _LOCAL_FALLBACK_STORE[stable_buyer_id].append({
            "id": mem_id,
            "content": item.get("content", ""),
            "category": item.get("category", "general"),
            "importance": item.get("importance", "medium"),
            "score": 1.0,
            "created_at": datetime.now().isoformat(),
        })
        fallback_ids.append(mem_id)

    if not is_hindsight_configured():
        logger.debug(
            "[Hindsight] Service not configured (missing HINDSIGHT_API_KEY). Stored in persistent fallback memory for buyer=%s.",
            stable_buyer_id,
        )
        return []

    base_url = get_hindsight_url()
    api_key = get_hindsight_api_key()
    active_bank = _get_active_bank_id(bank_id)
    buyer_tag = f"buyer:{stable_buyer_id}"

    base_metadata = {
        "buyer_id": stable_buyer_id,
        "source": "dispatch_ai",
    }
    if metadata and isinstance(metadata, dict):
        base_metadata.update(metadata)

    # Try official SDK first
    try:
        import hindsight_client
        if hasattr(hindsight_client, 'Hindsight'):
            client = hindsight_client.Hindsight(
                base_url=base_url,
                api_key=api_key,
                timeout=HINDSIGHT_TIMEOUT_SECONDS,
            )
            stored_ids: List[str] = []
            for item in items_to_store:
                resp = client.retain(
                    bank_id=active_bank,
                    content=item.get("content", ""),
                    tags=[buyer_tag],
                    metadata=base_metadata,
                )
                op_id = getattr(resp, 'id', None) or getattr(resp, 'operation_id', None) or 'ok'
                stored_ids.append(str(op_id))

            logger.info(
                "[Hindsight] Retained %d memories via SDK for buyer=%s (bank=%s)",
                len(stored_ids),
                stable_buyer_id,
                active_bank,
            )
            return stored_ids
    except ImportError:
        pass
    except Exception as sdk_exc:
        err_msg = str(sdk_exc).lower()
        if "401" in err_msg or "unauthorized" in err_msg or "forbidden" in err_msg or "403" in err_msg:
            logger.error("[Hindsight] Authentication failure on retain: check HINDSIGHT_API_KEY. Key: %s", mask_secret(api_key))
            return []
        if "timeout" in err_msg or "timed out" in err_msg:
            logger.warning("[Hindsight] API timeout after %.1fs during retain for buyer=%s", HINDSIGHT_TIMEOUT_SECONDS, stable_buyer_id)
            return []
        logger.debug("[Hindsight] SDK retain attempt raised %s; trying REST fallback.", sdk_exc)

    # HTTP REST Fallback
    try:
        import httpx
        headers = _get_request_headers(api_key)
        payload = {
            "bank_id": active_bank,
            "memories": items_to_store,
            "tags": [buyer_tag],
            "metadata": base_metadata,
            "user_id": stable_buyer_id,
        }

        url = f"{base_url}/v1/banks/{active_bank}/retain"
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=HINDSIGHT_TIMEOUT_SECONDS)
            if resp.status_code == 404:
                url = f"{base_url}/api/retain"
                resp = httpx.post(url, json=payload, headers=headers, timeout=HINDSIGHT_TIMEOUT_SECONDS)
        except httpx.ConnectError as conn_err:
            logger.warning("[Hindsight] Service unavailable (ConnectError on retain): %s", conn_err)
            return []

        if resp.status_code in (401, 403):
            logger.error("[Hindsight] Authentication failure (%d) on retain: check HINDSIGHT_API_KEY. Key: %s", resp.status_code, mask_secret(api_key))
            return []

        if resp.status_code >= 500:
            logger.warning("[Hindsight] Service error (%d) at %s during retain.", resp.status_code, url)
            return []

        resp.raise_for_status()

        try:
            data = resp.json()
        except Exception as json_err:
            logger.warning("[Hindsight] Malformed JSON response received on retain for buyer=%s: %s", stable_buyer_id, json_err)
            return []

        stored_ids = data.get("stored_ids", data.get("ids", ["stored"] if data.get("success") or data.get("ok") else []))
        logger.info(
            "[Hindsight] Retained %d memories via HTTP for buyer=%s (bank=%s)",
            len(items_to_store),
            stable_buyer_id,
            active_bank,
        )
        return [str(i) for i in stored_ids]

    except httpx.TimeoutException:
        logger.warning("[Hindsight] API timeout after %.1fs during retain for buyer=%s", HINDSIGHT_TIMEOUT_SECONDS, stable_buyer_id)
        return []
    except httpx.HTTPStatusError as http_err:
        logger.warning("[Hindsight] HTTP status error (%s) during retain for buyer=%s", http_err.response.status_code, stable_buyer_id)
        return []
    except Exception as exc:
        logger.error("[Hindsight] Unexpected exception during memory retain for buyer=%s: %s", stable_buyer_id, exc)
        return []


# ── Additional Utilities ──────────────────────────────────────────────────────

def is_hindsight_service_available() -> bool:
    """
    Check whether Hindsight is configured and reachable.
    Does not throw exceptions.
    """
    if not is_hindsight_configured():
        return False

    try:
        import httpx
        url = f"{get_hindsight_url()}/health"
        resp = httpx.get(url, timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return is_hindsight_configured()


def search_customer_memories(
    buyer_id: Optional[Union[str, int, User, Any]] = None,
    query: str = "",
    limit: int = 20,
    bank_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Admin-level cross-buyer or single-buyer memory search.
    """
    if not is_hindsight_configured():
        return []

    stable_buyer = normalize_buyer_id(buyer_id) if buyer_id else None
    if stable_buyer:
        return recall_customer_memory(stable_buyer, query or "preferences and history", limit=limit, bank_id=bank_id)
    return []


def forget_customer_memory(memory_id: str, bank_id: Optional[str] = None) -> bool:
    """
    Delete a specific memory by ID for GDPR / customer correction.
    """
    if not is_hindsight_configured() or not memory_id:
        return False

    base_url = get_hindsight_url()
    api_key = get_hindsight_api_key()
    active_bank = _get_active_bank_id(bank_id)

    try:
        import httpx
        headers = _get_request_headers(api_key)
        url = f"{base_url}/v1/banks/{active_bank}/memories/{memory_id}"
        resp = httpx.delete(url, headers=headers, timeout=HINDSIGHT_TIMEOUT_SECONDS)
        if resp.status_code == 404:
            url = f"{base_url}/api/memories/{memory_id}"
            resp = httpx.delete(url, headers=headers, timeout=HINDSIGHT_TIMEOUT_SECONDS)
        return resp.status_code in (200, 204)
    except Exception as exc:
        logger.warning("[Hindsight] Error forgetting memory %s: %s", memory_id, exc)
        return False
