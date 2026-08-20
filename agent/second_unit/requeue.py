"""Frame re-queue planning — the one thing Second Unit proposes rather than observes.

Every other module here reads telemetry. This one is the write side of the loop:
once the investigation has named a root cause, somebody still has to decide which
frames go back on the farm, which machines they run on, and what that will cost.
That decision is where the observability work finally turns into saved money.

Two deliberate design choices, both of which are the point rather than incidental:

1.  This is a PURE FUNCTION. It performs no I/O and makes no Grafana calls. All
    Grafana access in this project travels through the MCP server, so a helper
    that quietly opened its own HTTP connection would be both a violation of that
    rule and an untestable dependency. This module does arithmetic on values the
    agent has already gathered through MCP, and nothing else.

2.  It reports its own COVERAGE. The agent discovers failed frame numbers by
    reading FATAL log lines, and Loki returns at most `limit` lines per query, so
    the observed frame list is normally a sample rather than the population. A
    planner that silently planned the sample would hand a supervisor a re-queue
    list that looks authoritative and is quietly short — exactly the class of
    confident-but-wrong output this project spends most of its instructions
    guarding against. So the caller must pass the metric-derived expected count,
    and the result carries an explicit completeness flag that the Report stage is
    instructed to surface.
"""

from __future__ import annotations

from .queries import GPU_COST_PER_SECOND


def _contiguous_ranges(frames: list[int]) -> list[str]:
    """Collapse a sorted frame list into compact ranges.

    Render wranglers submit ranges, not thousands of individual frame numbers, so
    `801-806` is the form that can actually be pasted into a scheduler. Gaps are
    preserved rather than smoothed over: in this incident the affected nodes fail
    only on a subset of the frames they touch, so the gaps are real and
    re-queueing across them would re-render work that already succeeded.
    """
    if not frames:
        return []

    ranges: list[str] = []
    start = previous = frames[0]

    for frame in frames[1:]:
        if frame == previous + 1:
            previous = frame
            continue
        ranges.append(str(start) if start == previous else f"{start}-{previous}")
        start = previous = frame

    ranges.append(str(start) if start == previous else f"{start}-{previous}")
    return ranges


def propose_requeue(
    observed_failed_frames: list[int],
    expected_failed_frame_count: int,
    affected_nodes: list[str],
    healthy_nodes: list[str],
    mean_render_seconds: float,
) -> dict:
    """Turn investigation findings into a concrete frame re-queue plan.

    Args:
        observed_failed_frames: Frame numbers actually read from FATAL log lines.
            Pass only frames you genuinely observed. This function will never
            extend, interpolate or infer the list, because a fabricated frame
            number costs real GPU time when a human acts on it.
        expected_failed_frame_count: The failed frame total Triage measured from
            metrics. Used solely to report coverage, never to invent frames.
        affected_nodes: Nodes implicated in the incident. These are HELD out of
            rotation, not reused.
        healthy_nodes: Nodes eligible to receive re-queued work.
        mean_render_seconds: Mean successful render time in seconds, from metrics.

    Returns:
        A plan describing which frame ranges to re-submit, which nodes to submit
        them to, which nodes to hold, the cost and time estimate, and an explicit
        statement of whether the frame list is complete or a sample.
    """
    frames = sorted({int(f) for f in observed_failed_frames if int(f) > 0})

    if not frames:
        return {
            "status": "no_frames_supplied",
            "detail": (
                "No failed frame numbers were supplied, so no re-queue plan was "
                "produced. Report the re-queue plan as unavailable. Do not "
                "estimate a frame list from the failure count."
            ),
        }

    held = list(dict.fromkeys(affected_nodes))
    eligible = [n for n in dict.fromkeys(healthy_nodes) if n not in set(held)]

    # Round-robin across healthy nodes only. The affected nodes are excluded on
    # purpose: until the asset is re-synced they are the machines most likely to
    # reproduce the failure, and re-queueing onto them converts a recoverable
    # incident into a doubled bill.
    assignments: list[dict] = []
    if eligible:
        buckets: dict[str, list[int]] = {node: [] for node in eligible}
        for index, frame in enumerate(frames):
            buckets[eligible[index % len(eligible)]].append(frame)
        assignments = [
            {
                "node": node,
                "frame_count": len(node_frames),
                "frames": _contiguous_ranges(node_frames),
            }
            for node, node_frames in buckets.items()
        ]

    observed = len(frames)
    expected = max(0, int(expected_failed_frame_count))
    complete = bool(expected) and observed >= expected

    if not expected:
        coverage_note = (
            "No metric-derived failure count was supplied, so coverage could not "
            "be assessed. Do not claim this list is complete."
        )
    elif complete:
        coverage_note = (
            f"All {expected} failed frames are accounted for in the plan."
        )
    else:
        coverage_note = (
            f"This plan covers {observed} of {expected} failed frames "
            f"({observed / expected:.0%}). The remainder were not present in the "
            "log lines read, most likely because the Loki query returned up to "
            "its line limit. Present this as a partial plan covering observed "
            "frames only, and raise the log query limit to plan the full set."
        )

    if mean_render_seconds > 0:
        gpu_seconds = observed * mean_render_seconds
        estimate = {
            "rework_cost_usd": round(gpu_seconds * GPU_COST_PER_SECOND, 2),
            "machine_hours": round(gpu_seconds / 3600, 2),
            "estimated_wall_clock_hours": (
                round(gpu_seconds / 3600 / len(eligible), 2) if eligible else None
            ),
            "basis": (
                f"{observed} frames x {mean_render_seconds:.1f}s mean render x "
                f"${GPU_COST_PER_SECOND}/GPU-second, spread across "
                f"{len(eligible)} healthy nodes"
            ),
        }
    else:
        estimate = {
            "rework_cost_usd": None,
            "machine_hours": None,
            "estimated_wall_clock_hours": None,
            "basis": (
                "No mean render time was supplied, so cost and duration are "
                "unavailable. Report them as unavailable rather than estimating."
            ),
        }

    return {
        "status": "ok",
        "preconditions": [
            "Fix the implicated asset first — re-sync or roll back. Re-queueing "
            "onto a broken asset reproduces the failure and doubles the spend.",
            "Confirm the alert has cleared before submitting, so a still-active "
            "fault is not masked by fresh work.",
        ],
        "hold_nodes": {
            "nodes": held,
            "count": len(held),
            "reason": (
                "Implicated in the incident. Hold out of rotation until the asset "
                "is verified, then return them to the pool."
            ),
        },
        "requeue": {
            "frame_ranges": _contiguous_ranges(frames),
            "frame_count": observed,
            "target_node_count": len(eligible),
            "assignments": assignments,
            "order": (
                "Ascending frame order. Dailies are reviewed in sequence, so the "
                "earliest frames unblock the supervisor's review soonest."
            ),
        },
        "coverage": {
            "observed": observed,
            "expected": expected,
            "complete": complete,
            "note": coverage_note,
        },
        "estimate": estimate,
    }
