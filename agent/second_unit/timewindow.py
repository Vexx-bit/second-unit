"""Deterministic time arithmetic for the investigation crew.

Why this module exists: the model is unreliable at converting Unix epochs to
calendar dates. In one run it read ``1787217004.551`` out of a Prometheus range
response and reported it as ``2026-08-08T11:50:04.551Z`` -- twelve days early.
Every downstream log and trace query was then bounded to that date, so a window
meant to be twenty minutes wide silently became twelve days wide. No tool
errored. The stage went on to cite a healthy-node "control" trace recorded
during the *previous day's* run as proof about the current incident.

The instruction to bound the window was right. The arithmetic underneath it was
wrong. Prose cannot fix arithmetic, so the conversion lives here as code and is
handed to the agents as tools.

Everything in this module is a pure function. No I/O, no HTTP, no MCP -- only
``datetime.now`` for freshness checks, so the behaviour is reproducible.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

# A single incident window is minutes wide. Anything approaching two hours means
# the bound has failed and an earlier simulator run is being merged in.
MAX_WINDOW_MINUTES = 90

# Telemetry older than this cannot belong to the run being investigated.
MAX_ONSET_AGE_HOURS = 6

# Clock skew between the exporter and Grafana Cloud, tolerated in the future.
FUTURE_TOLERANCE_SECONDS = 300


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _normalise_to_seconds(value: float) -> float:
    """Prometheus returns seconds, Grafana annotations milliseconds, Loki
    nanoseconds. Normalise by magnitude instead of trusting the caller to say
    which unit it pasted.
    """
    seconds = float(value)
    while abs(seconds) > 1e11:
        seconds /= 1000.0
    return seconds


def _format(moment: datetime) -> str:
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z"


def epoch_to_rfc3339(epoch: float) -> dict:
    """Convert a Unix timestamp to an RFC3339 UTC string. Use this for EVERY
    timestamp you report or pass to another tool. Do not convert epochs yourself.

    Accepts seconds, milliseconds or nanoseconds -- the unit is detected from the
    magnitude, so a raw Loki nanosecond timestamp can be passed straight through.

    Args:
        epoch: The Unix timestamp exactly as it appeared in the tool response.

    Returns:
        rfc3339: the UTC timestamp string, safe to pass as startRfc3339.
        epoch_seconds / epoch_ms: the same instant in both units. epoch_ms is
            what create_annotation wants.
        age_seconds / age_hours: how far in the past this instant is.
        plausible: False when the instant is more than MAX_ONSET_AGE_HOURS old or
            meaningfully in the future. A False here means the sample belongs to
            an earlier simulator run, not to the incident under investigation --
            re-derive it from a range query bounded to the last 30 minutes rather
            than building a window around it.
        note: a plain-language reading of the result.
    """
    try:
        seconds = _normalise_to_seconds(epoch)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "reason": f"not a number: {epoch!r}",
            "note": "Pass the timestamp verbatim from the tool response.",
        }

    try:
        moment = datetime.fromtimestamp(seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return {
            "ok": False,
            "reason": f"epoch out of range: {seconds}",
            "note": "Check the unit -- this is not a plausible Unix timestamp.",
        }

    age = (_now() - moment).total_seconds()
    plausible = -FUTURE_TOLERANCE_SECONDS <= age <= MAX_ONSET_AGE_HOURS * 3600

    if age < -FUTURE_TOLERANCE_SECONDS:
        note = "This instant is in the future. Something is wrong with the unit."
    elif plausible:
        note = f"{age / 60:.1f} minutes old -- consistent with the current run."
    else:
        note = (
            f"{age / 3600:.1f} hours old. This does NOT belong to the current "
            "run. Do not bound a window to it; re-derive the onset from a range "
            "query over the last 30 minutes."
        )

    return {
        "ok": True,
        "rfc3339": _format(moment),
        "epoch_seconds": seconds,
        "epoch_ms": int(round(seconds * 1000)),
        "age_seconds": round(age, 1),
        "age_hours": round(age / 3600.0, 3),
        "plausible": plausible,
        "note": note,
    }


def investigation_window(onset_epoch: float, lead_minutes: int = 10) -> dict:
    """Turn a measured failure onset into the bounded window for log and trace
    queries. Call this once, then reuse ``start_rfc3339`` on every query.

    Args:
        onset_epoch: The timestamp of the first non-zero failure sample, exactly
            as it appeared in the Prometheus range response.
        lead_minutes: How far before onset to start the window, so a triggering
            change is visible. Ten minutes is the default and is usually right.

    Returns:
        valid: whether this window may be used. If False, STOP -- do not run the
            query with a substitute window and do not run it unbounded.
        reason: why it was rejected.
        start_rfc3339: pass verbatim as startRfc3339 (Loki) and start (Tempo).
        start_epoch_seconds: feed to check_evidence_timestamp.
        onset_rfc3339 / onset_epoch_ms: the onset itself. onset_epoch_ms is the
            value create_annotation must be anchored to.
        end_rfc3339: now. Leaving endRfc3339 off is equivalent and preferred.
        width_minutes: how wide the window ended up. A correct incident window is
            tens of minutes; anything near MAX_WINDOW_MINUTES means the onset is
            wrong.
    """
    converted = epoch_to_rfc3339(onset_epoch)
    if not converted.get("ok"):
        return {"valid": False, "reason": converted.get("reason", "bad onset")}

    lead = max(0, int(lead_minutes))
    onset = datetime.fromtimestamp(converted["epoch_seconds"], tz=timezone.utc)
    start = onset - timedelta(minutes=lead)
    now = _now()
    width_minutes = (now - start).total_seconds() / 60.0

    if not converted["plausible"]:
        return {
            "valid": False,
            "reason": (
                f"onset is {converted['age_hours']} hours old, which is older "
                "than the current run. Re-derive it with a range query over the "
                "last 30 minutes before bounding anything."
            ),
            "onset_rfc3339": converted["rfc3339"],
            "width_minutes": round(width_minutes, 1),
        }

    if width_minutes > MAX_WINDOW_MINUTES:
        return {
            "valid": False,
            "reason": (
                f"window would be {width_minutes:.0f} minutes wide, over the "
                f"{MAX_WINDOW_MINUTES} minute cap. A window this wide contains "
                "more than one simulator run and will merge two incidents."
            ),
            "onset_rfc3339": converted["rfc3339"],
            "width_minutes": round(width_minutes, 1),
        }

    return {
        "valid": True,
        "start_rfc3339": _format(start),
        "start_epoch_seconds": start.timestamp(),
        "onset_rfc3339": converted["rfc3339"],
        "onset_epoch_ms": converted["epoch_ms"],
        "end_rfc3339": _format(now),
        "width_minutes": round(width_minutes, 1),
        "lead_minutes": lead,
        "note": (
            "Pass start_rfc3339 on every query_loki_logs and "
            "tempo_traceql-search call. Anchor the annotation to onset_epoch_ms."
        ),
    }


def check_evidence_timestamp(evidence_epoch: float, window_start_epoch: float) -> dict:
    """Check that a specific log line or trace actually falls inside the bounded
    window before you cite it as evidence.

    This exists because ``tempo_traceql-search`` will return traces older than
    the ``start`` you asked for. A control trace from a previous run proves
    nothing about the current incident, and citing one is how a correct-sounding
    conclusion gets built on the wrong evidence.

    Args:
        evidence_epoch: startTimeUnixNano of the trace, or the Loki line
            timestamp, verbatim.
        window_start_epoch: start_epoch_seconds from investigation_window.

    Returns:
        in_window: False means DISCARD this trace or log line. Do not cite it.
        evidence_rfc3339, window_start_rfc3339: both instants, for your write-up.
        seconds_before_window: how far outside the window it fell.
    """
    evidence = epoch_to_rfc3339(evidence_epoch)
    start = epoch_to_rfc3339(window_start_epoch)
    if not evidence.get("ok") or not start.get("ok"):
        return {
            "in_window": False,
            "reason": "could not parse one of the timestamps",
        }

    delta = evidence["epoch_seconds"] - start["epoch_seconds"]
    in_window = delta >= 0
    return {
        "in_window": in_window,
        "evidence_rfc3339": evidence["rfc3339"],
        "window_start_rfc3339": start["rfc3339"],
        "seconds_before_window": round(-delta, 1) if delta < 0 else 0.0,
        "note": (
            "Inside the window -- safe to cite."
            if in_window
            else "Outside the window. This is from an earlier run. Discard it."
        ),
    }
