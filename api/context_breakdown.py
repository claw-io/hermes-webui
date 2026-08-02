"""Bounded, data-minimized context composition diagnostics."""

from __future__ import annotations

import math
import re
import time

_MAX_CATEGORIES = 32
_MAX_ID = 64
_MAX_LABEL = 96
_MAX_MODEL = 128
_SAFE_ID = re.compile(r"^[a-zA-Z0-9_.-]+$")


def _bounded_text(value, maximum):
    if not isinstance(value, str):
        return ""
    return value.strip()[:maximum]


def _nonnegative_int(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0:
        return None
    return int(number)


def normalize_context_breakdown(raw, *, session_id, source, as_of=None):
    """Reduce an Agent/Gateway payload to the numeric browser wire contract."""
    if not isinstance(raw, dict):
        return None
    categories = []
    for item in raw.get("categories", []):
        if len(categories) >= _MAX_CATEGORIES or not isinstance(item, dict):
            break
        category_id = _bounded_text(item.get("id"), _MAX_ID)
        label = _bounded_text(item.get("label"), _MAX_LABEL)
        tokens = _nonnegative_int(item.get("tokens"))
        if not category_id or not _SAFE_ID.fullmatch(category_id) or not label or tokens is None:
            continue
        categories.append({"id": category_id, "label": label, "tokens": tokens})
    if not categories:
        return None
    result = {
        "status": "available",
        "source": source,
        "estimate": "rough_chars_per_4",
        "as_of": float(as_of if as_of is not None else time.time()),
        "session_id": str(session_id),
        "categories": categories,
        "estimated_total": sum(row["tokens"] for row in categories),
    }
    model = _bounded_text(raw.get("model"), _MAX_MODEL)
    if model:
        result["model"] = model
    return result


def context_breakdown_for_session(session):
    """Read a matching cached Agent without constructing or mutating one."""
    snapshot = getattr(session, "last_context_breakdown", None)
    if getattr(session, "active_stream_id", None):
        if isinstance(snapshot, dict):
            return dict(snapshot, source="settled_snapshot", updates_after_turn=True)
        return {"status": "busy", "reason": "turn_in_progress"}

    from api.config import SESSION_AGENT_CACHE, SESSION_AGENT_CACHE_LOCK

    with SESSION_AGENT_CACHE_LOCK:
        entry = SESSION_AGENT_CACHE.get(str(session.session_id))
    if entry is None:
        if isinstance(snapshot, dict):
            return dict(snapshot, source="settled_snapshot")
        return {"status": "unavailable", "reason": "no_live_agent"}
    agent = entry[0] if isinstance(entry, tuple) else entry
    from api.streaming import _cached_agent_matches_session

    if not _cached_agent_matches_session(agent, session.session_id):
        return {"status": "unavailable", "reason": "agent_identity_mismatch"}
    try:
        from agent.context_breakdown import compute_session_context_breakdown
    except (ImportError, AttributeError):
        return {"status": "unsupported", "reason": "agent_helper_unavailable"}
    history = getattr(session, "context_messages", None) or getattr(session, "messages", None) or []
    normalized = normalize_context_breakdown(
        compute_session_context_breakdown(agent, history),
        session_id=session.session_id,
        source="live_agent",
    )
    return normalized or {"status": "unavailable", "reason": "no_category_data"}


def normalized_snapshot(raw, session):
    """Normalize and stamp optional settled local/Gateway data for persistence."""
    return normalize_context_breakdown(
        raw,
        session_id=session.session_id,
        source="settled_snapshot",
    )
