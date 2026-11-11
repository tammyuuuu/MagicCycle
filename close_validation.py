"""Conservative validation primitives for the test site's closing-price pipeline.

Agreement between independent providers is a cross-check, not exchange certification.
Checks do not imply exchange certification.
"""
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path

CALENDAR = Path(__file__).with_name("ashare_calendar.json")

def previous_session(day: date) -> date:
    calendar = json.loads(CALENDAR.read_text(encoding="utf8"))
    first, last = date.fromisoformat(calendar["valid_from"]), date.fromisoformat(calendar["valid_through"])
    if not first <= day <= last:
        raise ValueError("交易日历超出有效范围")
    cursor = day - timedelta(days=1)
    while first <= cursor <= last:
        closed = cursor.weekday() >= 5 or any(date.fromisoformat(a) <= cursor <= date.fromisoformat(b) for a, b in calendar["closed_ranges"])
        if not closed:
            return cursor
        cursor -= timedelta(days=1)
    raise ValueError("交易日历不足以回溯")

def validate_observations(first, second, expected_date):
    """Check explicit date, independent source identity, positive finite value and equality."""
    if not first or not second:
        return False, "not_ready"
    if not first.get("source") or not second.get("source") or first["source"] == second["source"]:
        return False, "invalid_sources"
    try:
        if date.fromisoformat(first["date"]) != expected_date or date.fromisoformat(second["date"]) != expected_date:
            return False, "not_ready"
        a, b = float(first["close"]), float(second["close"])
    except (KeyError, TypeError, ValueError):
        return False, "invalid_data"
    if not (math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0):
        return False, "invalid_data"
    if not math.isclose(a, b, rel_tol=0, abs_tol=1e-8):
        return False, "mismatch"
    return True, "matched"


def validate_bar(frame, expected_date):
    """Require a uniquely dated, finite positive close for the requested session."""
    if frame is None or frame.empty or "close" not in frame.columns:
        return False, "not_ready"
    rows = frame[frame.index.date == expected_date]
    if len(rows) == 0:
        return False, "not_ready"
    if len(rows) != 1:
        return False, "invalid_data"
    try:
        close = float(rows.iloc[0]["close"])
    except (ValueError, TypeError):
        return False, "invalid_data"
    return (True, "valid") if math.isfinite(close) and close > 0 else (False, "invalid_data")
