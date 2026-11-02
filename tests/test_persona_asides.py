"""persona_asides_enabled swaps the witty butler for a plain persona."""
import json
import os
from unittest.mock import patch

import pytest

from jarvis.config import get_default_config, load_settings
from jarvis.system_prompt import build_system_prompt

pytestmark = pytest.mark.unit

WITTY = "dry, witty, and lightly sarcastic"
PLAIN = "Answer exactly what was asked, then stop"


def test_asides_stay_on_by_default():
    assert get_default_config()["persona_asides_enabled"] is True
    assert WITTY in build_system_prompt("Jarvis")
    assert "say the time without the date" not in build_system_prompt("Jarvis")


def test_the_plain_persona_drops_the_aside_rules_and_keeps_the_shared_ones():
    prompt = build_system_prompt("Friday", asides=False)

    assert PLAIN in prompt
    assert "one short sentence whenever it answers the question" in prompt
    assert "say the time without the date" in prompt
    assert "named Friday" in prompt
    assert WITTY not in prompt
    assert "one short dry observation" not in prompt
    assert "Flat, neutral, encyclopedic replies are" not in prompt
    assert "No markdown tables or complex formatting." in prompt
    assert "[Context: ...]" in prompt


@pytest.mark.parametrize("value,expected", [(False, False), (True, True), (None, True), ("false", True)])
def test_only_false_turns_the_asides_off(tmp_path, value, expected):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"persona_asides_enabled": value}), encoding="utf-8")

    with patch.dict(os.environ, {"JARVIS_CONFIG_PATH": str(path)}):
        assert load_settings().persona_asides_enabled is expected


@pytest.mark.parametrize("enabled,marker", [(False, PLAIN), (True, WITTY)])
def test_the_reply_engine_uses_the_configured_persona(mock_config, db, dialogue_memory, enabled, marker):
    from jarvis.reply import engine as engine_mod

    mock_config.persona_asides_enabled = enabled
    systems = []

    def fake_chat(*args, **kwargs):
        systems.append(kwargs["messages"][0]["content"])
        return {"message": {"role": "assistant", "content": "São 10h42."}}

    with patch.object(engine_mod, "chat_with_messages", side_effect=fake_chat), \
         patch.object(engine_mod, "select_tools", return_value=["stop"]), \
         patch.object(engine_mod, "extract_search_params_for_memory", return_value={"keywords": []}), \
         patch.object(engine_mod, "plan_query", return_value=["Reply to the user."]):
        engine_mod.run_reply_engine(db=db, cfg=mock_config, tts=None,
                                    text="que horas são", dialogue_memory=dialogue_memory)

    assert systems and marker in systems[0]
