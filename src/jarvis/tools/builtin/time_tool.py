"""Current time and date for any location or timezone.

Resolves a user-named place (city, country) to its IANA timezone via the
same Open-Meteo geocoding endpoint the weather tool uses, then formats the
current instant in that zone with ``format_time_context``. A bare IANA
zone name (``Europe/Athens``) and a city that names a zone (``São Paulo``,
``Tokyo``: matched against the zoneinfo database, ignoring accents and case)
are resolved without a network call. With network tools off, any other place
returns the user's own local time, labelled as unconfirmed for that place.

The tool is deliberately LLM-free: timezone arithmetic is deterministic,
so time questions never ride on a small model's ability to compute UTC
offsets. The user's OWN local time is already injected into the assistant's
context each reply and needs no tool; this exists for the case the context
cannot cover — a named place in another timezone.
"""

import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple

import requests

try:
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones
except ImportError:  # pragma: no cover - Python < 3.9
    ZoneInfo = None  # type: ignore[assignment]
    ZoneInfoNotFoundError = Exception  # type: ignore[assignment,misc]
    available_timezones = None  # type: ignore[assignment]

from ...debug import debug_log
from ...utils.location import get_location_context_with_timezone
from ...utils.time_context import format_time_context
from ..base import Tool, ToolContext
from ..network import network_tools_enabled
from ..types import ToolExecutionResult

# Open-Meteo geocoding returns an IANA ``timezone`` field per result (the
# same free, key-less endpoint getWeather already uses for its lookups).
_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# Cache of lowercased location string -> (iana_zone, display_name).
# Repeated questions about the same city must not re-hit the network.
_geocode_cache: Dict[str, Tuple[Optional[str], str]] = {}

# A bare IANA zone path ("Europe/Athens", "Asia/Tokyo", "America/New_York").
# The "/" never appears in a plain city name, so it disambiguates zone
# arguments from places without needing a lookup.
_IANA_ZONE_RE = re.compile(r"^[A-Za-z_+-]+(?:/[A-Za-z_+-]+)+$")


def _is_valid_iana_zone(value: str) -> bool:
    """Return True when ``value`` is a zone path zoneinfo actually knows."""
    if ZoneInfo is None or not _IANA_ZONE_RE.match(value.strip()):
        return False
    try:
        ZoneInfo(value.strip())
        return True
    except (ZoneInfoNotFoundError, ValueError):
        return False


def _zone_key(text: str) -> str:
    """Compare place names without accents, case, spaces or punctuation."""
    decomposed = unicodedata.normalize("NFKD", text)
    letters = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", letters.casefold())


@lru_cache(maxsize=1)
def _zones_by_city() -> Dict[str, str]:
    """Last segment of each canonical IANA zone ("Sao_Paulo") -> the zone.

    A city segment shared by zones that keep different clocks is left out, so
    a match never picks the wrong offset; aliases of one clock collapse to the
    shortest name.
    """
    if available_timezones is None:
        return {}
    found: Dict[str, Optional[str]] = {}
    for zone in sorted(available_timezones(), key=lambda z: (len(z), z)):
        region, _, city = zone.partition("/")
        if not city or region in ("Etc", "SystemV", "US", "Canada", "Brazil", "Mexico", "Chile"):
            continue
        key = _zone_key(city.rsplit("/", 1)[-1])
        if not key:
            continue
        if key not in found:
            found[key] = zone
        elif found[key] is not None and not _same_clock(found[key], zone):
            found[key] = None
    return {key: zone for key, zone in found.items() if zone}


def _same_clock(first: str, second: str) -> bool:
    """True when two zones show the same offset in January and July."""
    from datetime import datetime
    try:
        zones = (ZoneInfo(first), ZoneInfo(second))
    except (ZoneInfoNotFoundError, ValueError):
        return False
    year = datetime.now().year
    return all(
        datetime(year, month, 15, 12, tzinfo=zones[0]).utcoffset()
        == datetime(year, month, 15, 12, tzinfo=zones[1]).utcoffset()
        for month in (1, 7)
    )


def _offline_zone(location: str) -> Optional[str]:
    """IANA zone named after a city ("São Paulo" -> America/Sao_Paulo), offline."""
    return _zones_by_city().get(_zone_key(location.split(",")[0]))


def _geocode_timezone(location: str, timeout_sec: float) -> Tuple[Optional[str], str]:
    """Resolve a place name to its IANA timezone.

    Returns ``(iana_zone, display_name)``. ``iana_zone`` is None when the
    place could not be geocoded or carries no timezone; ``display_name`` is
    the geocoded place name ("Thessaloniki, Central Macedonia, Greece") for
    the reply, or the raw input when the lookup failed.
    """
    key = location.strip().lower()
    cached = _geocode_cache.get(key)
    if cached is not None:
        return cached

    params = {
        "name": location.strip(),
        "count": 1,
        "language": "en",
        "format": "json",
    }
    geo_response = requests.get(_GEOCODING_URL, params=params, timeout=timeout_sec)
    geo_response.raise_for_status()
    geo_data = geo_response.json()
    results = geo_data.get("results") or []
    if not results:
        result = (None, location.strip())
        _geocode_cache[key] = result
        return result

    place = results[0]
    display = place.get("name", location.strip())
    admin1 = place.get("admin1", "")
    country = place.get("country", "")
    if admin1 and admin1 != display:
        display += f", {admin1}"
    if country:
        display += f", {country}"
    result = (place.get("timezone"), display)
    _geocode_cache[key] = result
    return result


def _local_zone(context: ToolContext) -> Optional[str]:
    """The user's own zone: GeoIP when available, else None (the OS zone).

    With location_enabled false the GeoIP lookup is skipped: the user turned
    location off, and the lookup only printed setup instructions for a
    missing database on every time question.
    """
    if context.cfg is None or getattr(context.cfg, "location_enabled", True) is False:
        return None
    try:
        _, tz_name = get_location_context_with_timezone(
            config_ip=getattr(context.cfg, "location_ip_address", None),
            auto_detect=getattr(context.cfg, "location_auto_detect", True),
            resolve_cgnat_public_ip=getattr(context.cfg, "location_cgnat_resolve_public_ip", True),
            location_cache_minutes=getattr(context.cfg, "location_cache_minutes", 60),
        )
        return tz_name
    except Exception as e:
        debug_log(f"getTime: local tz lookup failed: {e}", "tools")
        return None


class TimeTool(Tool):
    """Tool for getting the current time/date in any location or timezone."""

    @property
    def name(self) -> str:
        return "getTime"

    @property
    def description(self) -> str:
        return (
            "Current time and date in a specific city, country, or timezone "
            "(e.g. 'what time is it in London?', 'what's the date in Tokyo?'). "
            "Use for time/date questions about a place other than the user's "
            "own location — their local time is already in the assistant's "
            "context and needs no tool. NOT for weather; that is getWeather."
        )

    @property
    def inputSchema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": (
                        "OPTIONAL. City name, country, or IANA timezone "
                        "(e.g. 'Thessaloniki', 'Japan', 'Europe/Athens'). "
                        "Set it when the user names a place. If omitted, "
                        "returns the user's local time — which is already in "
                        "the assistant's context."
                    ),
                }
            },
            "required": [],
        }

    def run(self, args: Optional[Dict[str, Any]], context: ToolContext) -> ToolExecutionResult:
        """Get the current time for the requested place (or the user's own)."""
        context.user_print("🕐 Checking time...")

        timeout_sec = 8.0
        if context.cfg is not None:
            timeout_sec = float(getattr(context.cfg, "llm_tools_timeout_sec", 8.0))

        location_str = ""
        if args and isinstance(args, dict):
            raw_location = args.get("location")
            location_str = str(raw_location).strip() if raw_location else ""

        try:
            if location_str:
                offline_zone = None if _is_valid_iana_zone(location_str) else _offline_zone(location_str)
                if _is_valid_iana_zone(location_str):
                    tz_name = location_str.strip()
                    display = tz_name
                elif offline_zone is not None:
                    # The place names a time zone itself; no lookup needed.
                    tz_name, display = offline_zone, location_str
                elif not network_tools_enabled(context.cfg):
                    # Resolving any other place needs the geocoding service. Give
                    # the user's own time instead, clearly labelled, so a small
                    # model can still answer (most places a user names share
                    # their zone) without claiming the place's time is known.
                    debug_log("getTime: city lookup refused, network tools are off", "tools")
                    context.user_print("🔒 City lookup blocked: network tools are turned off")
                    local_time = format_time_context(_local_zone(context))
                    return ToolExecutionResult(
                        success=True,
                        reply_text=(
                            f"The time zone of '{location_str}' cannot be looked up offline "
                            "(network tools are off), so its time is not confirmed. "
                            f"The user's own local time is: {local_time}. Tell the user "
                            "this local time and, in the same sentence, that the time "
                            f"zone of '{location_str}' could not be checked offline."
                        ),
                    )
                else:
                    tz_name, display = _geocode_timezone(location_str, timeout_sec)
                    if tz_name is None:
                        if not display or display.lower() == location_str.lower():
                            return ToolExecutionResult(
                                success=False,
                                reply_text=(
                                    f"Could not find location '{location_str}'. "
                                    "Try a different city name or spelling."
                                ),
                            )
                        return ToolExecutionResult(
                            success=False,
                            reply_text=(
                                f"Could not determine the timezone for "
                                f"'{display}'."
                            ),
                        )
                time_str = format_time_context(tz_name)
                short_name = display.split(",")[0].strip()
                context.user_print(f"✅ Current time in {short_name}: {time_str}")
                return ToolExecutionResult(
                    success=True,
                    reply_text=f"Current time in {display}: {time_str}",
                )

            # No location — the user's own local time.
            time_str = format_time_context(_local_zone(context))
            context.user_print(f"✅ Current time: {time_str}")
            return ToolExecutionResult(
                success=True,
                reply_text=f"Current time: {time_str}",
            )

        except requests.exceptions.Timeout:
            debug_log("time request timed out", "tools")
            context.user_print("⚠️ Time service timeout.")
            return ToolExecutionResult(
                success=False,
                reply_text="Time service is taking too long to respond. Please try again.",
            )
        except requests.exceptions.RequestException as e:
            debug_log(f"time request failed: {e}", "tools")
            context.user_print("⚠️ Time service unavailable.")
            return ToolExecutionResult(
                success=False,
                reply_text="Time service is temporarily unavailable. Please try again later.",
            )
        except Exception as e:
            debug_log(f"time error: {e}", "tools")
            context.user_print("⚠️ Error getting time.")
            return ToolExecutionResult(
                success=False,
                reply_text=f"Error getting time: {e}",
            )
