"""User metrics processing pipeline."""

import datetime
from typing import Any, Callable

TOP_TIER_SCORE_MULTIPLIER = 1.2

UserStats = dict[str, Any]


def export_user_metrics_report(
    raw_payload: dict[str, Any],
    threshold: float,
    format_func: Callable[[dict[str, float]], str],
) -> str:
    stats_by_user = _collect_qualifying_user_stats(raw_payload, threshold)
    return _render_report(stats_by_user, format_func)


def _collect_qualifying_user_stats(
    raw_payload: dict[str, Any], threshold: float
) -> dict[str, UserStats]:
    if not _has_tracked_user_data(raw_payload):
        return {}
    stats_by_user: dict[str, UserStats] = {}
    for item in raw_payload["data"]:
        stats = _stats_for_tracked_item(item, threshold)
        if stats is not None:
            stats_by_user[item["user_id"]] = stats
    return stats_by_user


def _has_tracked_user_data(raw_payload: dict[str, Any]) -> bool:
    return bool(raw_payload) and isinstance(raw_payload, dict) and "data" in raw_payload


def _stats_for_tracked_item(item: dict[str, Any], threshold: float) -> UserStats | None:
    if not _is_tracked_user(item):
        return None
    active_metrics = [metric for metric in item["metrics"] if isinstance(metric, dict)]
    if not any(metric.get("status") == "active" for metric in active_metrics):
        return None
    return _stats_from_metrics(active_metrics, threshold)


def _is_tracked_user(item: dict[str, Any]) -> bool:
    return (
        isinstance(item, dict)
        and "user_id" in item
        and "metrics" in item
        and str(item["user_id"]).startswith("usr_")
    )


def _stats_from_metrics(metrics: list[dict[str, Any]], threshold: float) -> UserStats | None:
    average_score = _average_score(metrics)
    if average_score is None or average_score < threshold:
        return None
    return {
        "average": average_score,
        "is_top_tier": average_score > threshold * TOP_TIER_SCORE_MULTIPLIER,
        "last_seen": datetime.datetime.now().isoformat(),
    }


def _average_score(metrics: list[dict[str, Any]]) -> float | None:
    valid_scores = [
        float(metric["score"])
        for metric in metrics
        if "score" in metric and isinstance(metric["score"], (int, float))
    ]
    if not valid_scores:
        return None
    return sum(valid_scores) / len(valid_scores)


def _render_report(
    stats_by_user: dict[str, UserStats], format_func: Callable[[dict[str, float]], str]
) -> str:
    report_lines = []
    for user_id, stats in stats_by_user.items():
        summary = format_func({user_id: stats["average"]})
        tier = "TOP" if stats["is_top_tier"] else "STD"
        report_lines.append(f"[{stats['last_seen']}] USER {user_id} | TIER: {tier} | {summary}")
    return "\n".join(report_lines)
