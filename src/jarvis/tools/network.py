"""Network gate for builtin tools.

Jarvis is offline-first: builtin tools that reach the internet stay off
until the user turns on ``network_tools_enabled``. While the gate is closed
those tools are left out of every catalogue the models see (router,
planner, toolSearchTool) and are refused if a model names them anyway.
"""

from __future__ import annotations

from typing import Any, Mapping

from .types import ToolExecutionResult

# Builtin tools whose every call reaches the internet. getTime is not here:
# the user's own local time needs no network; only its city lookup does,
# and the tool gates that branch itself.
NETWORK_TOOLS = frozenset({"webSearch", "fetchWebPage", "getWeather"})


def network_tools_enabled(cfg: Any) -> bool:
    """True only when the configuration explicitly allows network tools."""
    return getattr(cfg, "network_tools_enabled", False) is True


def offline_tools(tools: Mapping[str, Any], cfg: Any) -> dict:
    """Return the tools a reply may use under the current network setting."""
    if network_tools_enabled(cfg):
        return dict(tools)
    return {name: tool for name, tool in tools.items() if name not in NETWORK_TOOLS}


def network_disabled_result(what: str) -> ToolExecutionResult:
    """Explain to the model why a network action did not run."""
    message = (
        f"{what} needs the internet, and network tools are turned off "
        "(network_tools_enabled is false). Answer from what you already "
        "know, or tell the user this needs the network."
    )
    return ToolExecutionResult(success=False, reply_text=message, error_message=message)
