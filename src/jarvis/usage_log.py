"""Local usage metrics: how often Jarvis is asked and how long the user waits.

Each spoken request appends one JSON line to ``usage_log.jsonl`` beside the
database when ``usage_log_enabled`` is true. Lines hold timings and outcomes
only, never the words spoken or the reply, so the file can be read or shared
without exposing conversations.

Run ``python -m jarvis.usage_log`` for a per-day report.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

from .debug import debug_log

FILE_NAME = "usage_log.jsonl"
_write_lock = threading.Lock()


def usage_log_path(cfg: Any) -> Optional[Path]:
    """Where usage lines go for this configuration, or None when disabled."""
    if getattr(cfg, "usage_log_enabled", False) is not True:
        return None
    db_path = getattr(cfg, "db_path", None)
    if not db_path or str(db_path) == ":memory:":
        return None
    return Path(os.path.expanduser(str(db_path))).parent / FILE_NAME


@dataclass
class RequestTiming:
    """Monotonic timestamps of one spoken request, filled as it progresses."""

    source: str
    started: float
    heard: Optional[float] = None
    replied: Optional[float] = None
    voice: Optional[float] = None
    speech_seconds: Optional[float] = None
    ok: bool = True
    _written: bool = field(default=False, repr=False)

    def record(self) -> dict:
        def span(start, end):
            return round(end - start, 2) if start is not None and end is not None else None

        return {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "source": self.source,
            "transcribe_s": span(self.started, self.heard),
            "reply_s": span(self.heard if self.heard is not None else self.started, self.replied),
            "wait_to_voice_s": span(self.started, self.voice),
            "speech_s": round(self.speech_seconds, 2) if self.speech_seconds is not None else None,
            "ok": self.ok,
        }


def write_timing(cfg: Any, timing: Optional[RequestTiming]) -> None:
    """Append the request once; never raises into the voice path."""
    if timing is None or timing._written:
        return
    path = usage_log_path(cfg)
    if path is None:
        return
    timing._written = True
    try:
        line = json.dumps(timing.record(), ensure_ascii=False)
        with _write_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        debug_log(f"usage line written ({timing.source})", "usage")
    except Exception as exc:
        debug_log(f"usage line not written: {exc}", "usage")


def now() -> float:
    return time.monotonic()


def read_records(path: Path) -> list[dict]:
    """Records from the log, skipping lines that are not valid JSON objects."""
    records = []
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict) and isinstance(item.get("ts"), str):
                    records.append(item)
    except FileNotFoundError:
        pass
    return records


def daily_summary(records: Iterable[dict]) -> list[dict]:
    """Per-day counts and wait statistics, oldest day first."""
    days: dict[str, list[dict]] = {}
    for item in records:
        days.setdefault(item["ts"][:10], []).append(item)
    summary = []
    for day in sorted(days):
        items = days[day]
        waits = sorted(w for w in (i.get("wait_to_voice_s") for i in items) if isinstance(w, (int, float)))
        summary.append({
            "day": day,
            "requests": len(items),
            "failed": sum(1 for i in items if i.get("ok") is False),
            "median_wait_s": round(statistics.median(waits), 1) if waits else None,
            "worst_wait_s": waits[-1] if waits else None,
        })
    return summary


def main(argv: Optional[list[str]] = None) -> int:
    from .config import load_settings

    cfg = load_settings()
    path = Path(os.path.expanduser(str(cfg.db_path))).parent / FILE_NAME
    records = read_records(path)
    if not records:
        state = "on" if usage_log_path(cfg) else "off (set usage_log_enabled to true)"
        print(f"📊 No usage recorded yet in {path}\n   Usage log is {state}.")
        return 0
    print(f"📊 Jarvis usage — {path}")
    print(f"   {'day':<12}{'requests':>9}{'failed':>8}{'median wait':>13}{'worst':>8}")
    for row in daily_summary(records):
        median = f"{row['median_wait_s']} s" if row["median_wait_s"] is not None else "—"
        worst = f"{row['worst_wait_s']} s" if row["worst_wait_s"] is not None else "—"
        print(f"   {row['day']:<12}{row['requests']:>9}{row['failed']:>8}{median:>13}{worst:>8}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
