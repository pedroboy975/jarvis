"""getTime answers offline: zone-named cities resolve, others fall back to local time."""
from types import SimpleNamespace

import pytest

from jarvis.tools.builtin import time_tool
from jarvis.tools.registry import run_tool_with_retries

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def no_geocoding(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("getTime reached the geocoding service")

    monkeypatch.setattr(time_tool, "_geocode_timezone", refuse)


def _cfg(network=False):
    return SimpleNamespace(network_tools_enabled=network, voice_debug=False, mcps={},
                           location_enabled=False, location_auto_detect=False,
                           location_ip_address=None, location_cgnat_resolve_public_ip=False,
                           location_cache_minutes=60, llm_tools_timeout_sec=5.0)


def _run(location, network=False):
    return run_tool_with_retries(db=None, cfg=_cfg(network), tool_name="getTime",
                                 tool_args={"location": location}, system_prompt="",
                                 original_prompt="", redacted_text="", max_retries=0)


@pytest.mark.parametrize("place,zone", [
    ("São Paulo", "America/Sao_Paulo"), ("sao paulo", "America/Sao_Paulo"),
    ("Manaus", "America/Manaus"), ("Lisbon", "Europe/Lisbon"),
    ("New York", "America/New_York"), ("Tokyo", "Asia/Tokyo"),
    ("Kinshasa, Congo", "Africa/Kinshasa"),
])
def test_cities_that_name_a_zone_resolve_offline(place, zone):
    assert time_tool._offline_zone(place) == zone


@pytest.mark.parametrize("place", ["Belo Horizonte", "Jângeles", "", "Etc", "GMT"])
def test_other_places_do_not_match_a_zone(place):
    assert time_tool._offline_zone(place) is None


def test_a_zone_named_city_answers_with_its_time_without_network():
    result = _run("São Paulo")

    assert result.success is True
    assert result.reply_text.startswith("Current time in São Paulo:")


def test_an_unknown_place_answers_with_labelled_local_time_without_network():
    result = _run("Jângeles")

    assert result.success is True
    assert "'Jângeles' cannot be looked up offline" in result.reply_text
    assert "not confirmed" in result.reply_text
    assert "The user's own local time is:" in result.reply_text


def test_zone_named_cities_skip_geocoding_even_with_network_on():
    assert _run("Tokyo", network=True).reply_text.startswith("Current time in Tokyo:")


def test_shared_names_with_different_clocks_are_left_out(monkeypatch):
    time_tool._zones_by_city.cache_clear()
    monkeypatch.setattr(time_tool, "available_timezones",
                        lambda: {"America/Springfield", "Europe/Springfield", "Asia/Tokyo"})
    real = time_tool._same_clock
    monkeypatch.setattr(time_tool, "_same_clock",
                        lambda a, b: False if "Springfield" in a else real(a, b))
    try:
        assert time_tool._offline_zone("Springfield") is None
        assert time_tool._offline_zone("Tokyo") == "Asia/Tokyo"
    finally:
        time_tool._zones_by_city.cache_clear()
