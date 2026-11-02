"""Builtin tools that reach the internet stay closed until the user allows them."""
from types import SimpleNamespace

import pytest

from jarvis.config import get_default_config
from jarvis.tools import registry
from jarvis.tools.builtin import time_tool
from jarvis.tools.network import NETWORK_TOOLS
from jarvis.tools.registry import builtin_tools_for, run_tool_with_retries

pytestmark = pytest.mark.unit


def _cfg(enabled):
    return SimpleNamespace(
        network_tools_enabled=enabled, web_search_enabled=True, voice_debug=False,
        location_enabled=False, location_auto_detect=False, location_ip_address=None,
        location_cgnat_resolve_public_ip=False, location_cache_minutes=60,
        llm_tools_timeout_sec=5.0, mcps={},
    )


def _run(cfg, name, args):
    return run_tool_with_retries(
        db=None, cfg=cfg, tool_name=name, tool_args=args, system_prompt="",
        original_prompt="", redacted_text="", max_retries=0,
    )


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("a network request was made while network tools are off")

    import requests
    monkeypatch.setattr(requests, "get", refuse)
    monkeypatch.setattr(requests, "post", refuse)
    monkeypatch.setattr(requests.Session, "request", refuse)
    monkeypatch.setattr(time_tool, "_geocode_timezone", refuse)


def test_network_tools_are_off_by_default():
    assert get_default_config()["network_tools_enabled"] is False


def test_network_tools_leave_the_catalogue_while_the_gate_is_closed():
    closed = builtin_tools_for(_cfg(False))
    opened = builtin_tools_for(_cfg(True))

    assert not NETWORK_TOOLS & closed.keys()
    assert NETWORK_TOOLS <= opened.keys()
    assert {"getTime", "localFiles", "stop", "toolSearchTool"} <= closed.keys()


@pytest.mark.parametrize("value", [None, "true", 1, "yes"])
def test_only_a_real_true_opens_the_gate(value):
    assert not NETWORK_TOOLS & builtin_tools_for(_cfg(value)).keys()


@pytest.mark.usefixtures("no_network")
@pytest.mark.parametrize("name,args", [
    ("webSearch", {"search_query": "jarvis song"}),
    ("fetchWebPage", {"url": "https://example.com"}),
    ("getWeather", {"location": "Paris"}),
])
def test_a_named_network_tool_is_refused_without_a_request(name, args):
    result = _run(_cfg(False), name, args)

    assert result.success is False
    assert "network_tools_enabled" in result.reply_text


@pytest.mark.usefixtures("no_network")
def test_time_in_a_city_without_its_own_zone_falls_back_to_local_time_offline():
    result = _run(_cfg(False), "getTime", {"location": "Belo Horizonte"})

    assert result.success is True
    assert "cannot be looked up offline" in result.reply_text
    assert "The user's own local time is:" in result.reply_text


@pytest.mark.usefixtures("no_network")
@pytest.mark.parametrize("args", [{}, {"location": "America/Sao_Paulo"}])
def test_local_time_and_timezone_names_work_offline(args):
    result = _run(_cfg(False), "getTime", args)

    assert result.success is True
    assert "Current time" in result.reply_text


def test_tool_search_only_surfaces_allowed_tools(monkeypatch):
    from jarvis.tools.base import ToolContext
    from jarvis.tools.builtin import tool_search

    seen = {}

    def fake_select_tools(**kwargs):
        seen["catalogue"] = set(kwargs["builtin_tools"])
        return ["webSearch", "getTime"]

    monkeypatch.setattr(tool_search, "select_tools", fake_select_tools)
    monkeypatch.setattr(tool_search, "get_llm_backend", lambda cfg: None)
    monkeypatch.setattr(tool_search, "get_embedding_backend", lambda cfg: None)
    monkeypatch.setattr(tool_search, "resolve_model", lambda cfg, tier: "m")
    cfg = _cfg(False)
    cfg.embedding_model = "e"
    context = ToolContext(None, cfg, "", "", "", 0, lambda message: None)

    result = tool_search.ToolSearchTool().run({"query": "search the web"}, context)

    assert not NETWORK_TOOLS & seen["catalogue"]
    assert "webSearch" not in result.reply_text
    assert "getTime" in result.reply_text


def test_registry_gate_precedes_the_tool(monkeypatch):
    called = []
    monkeypatch.setitem(registry.BUILTIN_TOOLS, "webSearch",
                        SimpleNamespace(execute=lambda **kw: called.append(kw)))

    _run(_cfg(False), "webSearch", {"search_query": "x"})

    assert called == []
