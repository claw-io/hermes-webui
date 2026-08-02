import io
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from urllib.parse import urlparse

import api.config as config
import api.routes as routes
from api.context_breakdown import (
    context_breakdown_for_session,
    normalize_context_breakdown,
)


class _Handler:
    def __init__(self):
        self.status = None
        self.headers = {}
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, key, value):
        self.headers[key] = value

    def end_headers(self):
        pass

    def json_body(self):
        return json.loads(self.wfile.getvalue().decode())


def test_normalization_minimizes_and_bounds_untrusted_agent_payload():
    raw = {
        "categories": [
            {"id": "rules", "label": "Rules", "tokens": 12.9, "color": "red", "content": "SECRET"},
            {"id": "bad id!", "label": "X", "tokens": 2},
            {"id": "memory", "label": "M" * 200, "tokens": -1},
            {"id": "future", "label": "Future", "tokens": "7"},
        ],
        "estimated_total": 999,
        "model": "m" * 300,
        "prompt": "SECRET",
    }

    got = normalize_context_breakdown(raw, session_id="s1", source="live_agent", as_of=123)

    assert got == {
        "status": "available",
        "source": "live_agent",
        "estimate": "rough_chars_per_4",
        "as_of": 123.0,
        "session_id": "s1",
        "categories": [
            {"id": "rules", "label": "Rules", "tokens": 12},
            {"id": "future", "label": "Future", "tokens": 7},
        ],
        "estimated_total": 19,
        "model": "m" * 128,
    }
    assert "SECRET" not in json.dumps(got)


def test_cached_agent_tuple_uses_model_facing_context_messages(monkeypatch):
    captured = {}
    helper_module = ModuleType("agent.context_breakdown")

    def compute(agent, messages):
        captured["agent"] = agent
        captured["messages"] = messages
        return {"categories": [{"id": "conversation", "label": "Conversation", "tokens": 4}], "model": "x"}

    helper_module.compute_session_context_breakdown = compute
    monkeypatch.setitem(sys.modules, "agent.context_breakdown", helper_module)
    agent = SimpleNamespace(session_id="s1")
    session = SimpleNamespace(
        session_id="s1",
        context_messages=[{"role": "user", "content": "model-facing"}],
        messages=[{"role": "user", "content": "visible secret"}],
        active_stream_id=None,
        last_context_breakdown=None,
    )
    monkeypatch.setitem(config.SESSION_AGENT_CACHE, "s1", (agent, "signature"))

    got = context_breakdown_for_session(session)

    assert got["status"] == "available"
    assert captured == {"agent": agent, "messages": session.context_messages}


def test_active_turn_is_typed_http_200_busy(monkeypatch):
    session = SimpleNamespace(
        session_id="s1", profile="default", active_stream_id="stream", last_context_breakdown=None
    )
    monkeypatch.setattr(routes, "get_session", lambda sid, metadata_only=False: session)
    monkeypatch.setattr(routes, "_session_visible_to_active_profile", lambda profile, handler: True)
    handler = _Handler()

    routes.handle_get(handler, urlparse("http://example/api/session/context-breakdown?session_id=s1"))

    assert handler.status == 200
    assert handler.json_body() == {"breakdown": {"status": "busy", "reason": "turn_in_progress"}}


def test_session_model_update_clears_stale_context_breakdown():
    """Covered by the existing #1436 update regression fixture."""
    source = (Path(__file__).resolve().parent / "test_issue1436_context_indicator_load_path.py").read_text()
    assert "assert s.last_context_breakdown is None" in source


def test_local_settlement_persists_snapshot_before_save():
    source = (Path(__file__).resolve().parents[1] / "api" / "streaming.py").read_text()
    snapshot = source.index("s.last_context_breakdown = normalized_snapshot(raw_breakdown, s)")
    save = source.index("s.save()", snapshot)
    assert snapshot < save
    assert "result.get('messages')" in source[snapshot - 400:snapshot + 200]


def test_gateway_settlement_persists_snapshot_before_save():
    source = (Path(__file__).resolve().parents[1] / "api" / "gateway_chat.py").read_text()
    snapshot = source.index("s.last_context_breakdown = normalized_snapshot(gateway_breakdown, s)")
    save = source.index("s.save()", snapshot)
    assert snapshot < save


def test_gateway_cancel_restore_reinstates_previous_snapshot():
    source = (Path(__file__).resolve().parents[1] / "api" / "gateway_chat.py").read_text()
    assert 'previous_context_breakdown = getattr(s, "last_context_breakdown", None)' in source
    restore = source[source.index("def _restore_cancelled_success_writeback"):]
    assert "s.last_context_breakdown = previous_context_breakdown" in restore[:600]


def test_context_breakdown_profile_mismatch_is_409(monkeypatch):
    session = SimpleNamespace(session_id="s1", profile="other")
    monkeypatch.setattr(routes, "get_session", lambda sid, metadata_only=False: session)
    monkeypatch.setattr(routes, "_session_visible_to_active_profile", lambda profile, handler: False)
    handler = _Handler()

    routes.handle_get(handler, urlparse("http://example/api/session/context-breakdown?session_id=s1"))

    assert handler.status == 409
    assert handler.json_body()["code"] == "session_profile_mismatch"
