"""Builtin tools the user switches off are never offered and never run."""
import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from jarvis.config import _normalise_disabled_tools, get_default_config, load_settings
from jarvis.tools import registry
from jarvis.tools.registry import builtin_tools_for, run_tool_with_retries

pytestmark = pytest.mark.unit

MEALS = ["logMeal", "fetchMeals", "deleteMeal"]


def _cfg(disabled, network=True):
    return SimpleNamespace(disabled_tools=disabled, network_tools_enabled=network,
                           voice_debug=False, mcps={})


def _run(cfg, name, args):
    return run_tool_with_retries(
        db=None, cfg=cfg, tool_name=name, tool_args=args, system_prompt="",
        original_prompt="", redacted_text="", max_retries=0,
    )


def test_no_tool_is_disabled_by_default():
    assert get_default_config()["disabled_tools"] == []


def test_disabled_tools_leave_the_catalogue():
    tools = builtin_tools_for(_cfg(MEALS))

    assert not set(MEALS) & tools.keys()
    assert {"getTime", "localFiles", "screenshot", "webSearch"} <= tools.keys()


def test_disabled_tools_combine_with_the_network_gate():
    tools = builtin_tools_for(_cfg(["deleteMeal"], network=False))

    assert "deleteMeal" not in tools
    assert "webSearch" not in tools
    assert "logMeal" in tools


@pytest.mark.parametrize("value", [None, "deleteMeal", 3, {"deleteMeal": True}])
def test_only_a_list_switches_tools_off_at_runtime(value):
    assert "deleteMeal" in builtin_tools_for(_cfg(value))


def test_the_reply_loop_tools_cannot_be_switched_off():
    tools = builtin_tools_for(_cfg(["stop", "toolSearchTool"]))

    assert {"stop", "toolSearchTool"} <= tools.keys()


def test_a_named_disabled_tool_is_refused_before_it_runs(monkeypatch):
    called = []
    monkeypatch.setitem(registry.BUILTIN_TOOLS, "deleteMeal",
                        SimpleNamespace(execute=lambda **kw: called.append(kw)))

    result = _run(_cfg(MEALS), "deleteMeal", {"meal_description": "teste"})

    assert called == []
    assert result.success is False
    assert "disabled_tools" in result.reply_text
    assert "unavailable" in result.reply_text


@pytest.mark.parametrize("value,expected", [
    (["deleteMeal", " logMeal ", "deleteMeal", ""], ["deleteMeal", "logMeal"]),
    ("logMeal, fetchMeals", ["logMeal", "fetchMeals"]),
    (["stop", "toolSearchTool", "screenshot"], ["screenshot"]),
    (None, []),
])
def test_configured_names_are_normalised(value, expected):
    assert _normalise_disabled_tools(value) == expected


def test_settings_load_the_disabled_tools(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"disabled_tools": MEALS + ["stop"]}), encoding="utf-8")

    with patch.dict(os.environ, {"JARVIS_CONFIG_PATH": str(path)}):
        settings = load_settings()

    assert settings.disabled_tools == MEALS
