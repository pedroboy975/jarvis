"""A plan that calls a tool which does not exist must not be narrated as done."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from jarvis.reply.planner import invented_tool_names

pytestmark = pytest.mark.unit

KNOWN = ["localFiles", "getTime", "stop", "toolSearchTool"]
PLAN = ["deleteNote id='note-teste'", "Reply to the user confirming the note was deleted."]


@pytest.mark.parametrize("plan,expected", [
    (PLAN, ["deleteNote"]),
    (["deleteNote(id='x')", "Reply to the user."], ["deleteNote"]),
    (["localFiles operation='read' path='a.md'", "Reply to the user."], []),
    (["get the weather for Paris", "Reply to the user."], []),
    (["getTime", "Reply to the user."], []),
    (["Reply to the user."], []),
    (["deleteNote id='a'", "deleteNote id='b'", "getTime", "Reply."], ["deleteNote"]),
    ([], []),
])
def test_invented_tool_calls_are_detected(plan, expected):
    assert invented_tool_names(plan, KNOWN) == expected


def _run(mock_config, db, dialogue_memory, replies):
    from jarvis.reply import engine as engine_mod

    mock_config.ollama_chat_model = "gemma4:e2b"  # SMALL → text tools and evidence gate
    mock_config.llm_chat_model = "gemma4:e2b"
    systems, invoked = [], []

    def fake_chat(*args, **kwargs):
        systems.append(kwargs["messages"][0]["content"])
        return {"message": {"role": "assistant", "content": replies[min(len(systems), len(replies)) - 1]}}

    def fake_tool(db, cfg, tool_name, tool_args, **kwargs):
        invoked.append(tool_name)
        raise AssertionError("no tool should run for this plan")

    with patch.object(engine_mod, "run_tool_with_retries", side_effect=fake_tool), \
         patch.object(engine_mod, "chat_with_messages", side_effect=fake_chat), \
         patch.object(engine_mod, "select_tools", return_value=["localFiles", "stop"]), \
         patch.object(engine_mod, "extract_search_params_for_memory", return_value={"keywords": []}), \
         patch.object(engine_mod, "plan_query", return_value=list(PLAN)):
        reply = engine_mod.run_reply_engine(
            db=db, cfg=mock_config, tts=None, text="apague a nota teste",
            dialogue_memory=dialogue_memory,
        )
    return reply, systems, invoked


def test_the_reply_model_sees_an_execution_record_not_the_task_list(mock_config, db, dialogue_memory):
    reply, systems, invoked = _run(mock_config, db, dialogue_memory,
                                   ['{"blocker": "Não consigo apagar notas."}'])

    assert "EXECUTION RECORD AT HAND-OFF" in systems[0]
    assert '"deleteNote"' in systems[0]
    assert "ACTION PLAN for this query" not in systems[0]
    assert "confirming the note was deleted" not in systems[0]
    assert invoked == []
    assert reply == "Não consigo apagar notas."


def test_a_false_completion_claim_is_not_delivered(mock_config, db, dialogue_memory):
    from jarvis.reply.engine import _UNEXECUTED_ACTION_REPLY

    reply, systems, _ = _run(mock_config, db, dialogue_memory,
                             ["A nota teste foi apagada.", "Pronto, a nota foi apagada."])

    assert len(systems) == 2, "one grounded correction turn, then the honest fallback"
    assert "apagada" not in (reply or "")
    assert reply == _UNEXECUTED_ACTION_REPLY


def test_a_corrected_honest_blocker_is_delivered(mock_config, db, dialogue_memory):
    reply, _, _ = _run(mock_config, db, dialogue_memory,
                       ["A nota teste foi apagada.", '{"blocker": "Não tenho como apagar notas."}'])

    assert reply == "Não tenho como apagar notas."
