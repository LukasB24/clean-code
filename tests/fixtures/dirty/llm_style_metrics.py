from typing import Any, Callable
from functools import reduce
import datetime


def process_and_export_user_metrics(
    raw_payload: dict[str, Any],
    threshold: float,
    format_func: Callable[[dict[str, float]], str]
) -> str:
    processed_data: dict[str, dict[str, Any]] = {}

    if raw_payload and isinstance(raw_payload, dict) and "data" in raw_payload:
        for item in raw_payload["data"]:
            if isinstance(item, dict) and "user_id" in item and "metrics" in item:
                if str(item["user_id"]).startswith("usr_"):
                    active_flags: list[bool] = [
                        True if m.get("status") == "active" else False
                        for m in item["metrics"]
                        if isinstance(m, dict)
                    ]

                    if any(active_flags):
                        valid_scores: list[float] = [
                            float(m["score"])
                            for m in item["metrics"]
                            if "score" in m and isinstance(m["score"], (int, float))
                        ]

                        if len(valid_scores) > 0:
                            avg_score: float = reduce(lambda a, b: a + b, valid_scores) / len(valid_scores)
                            if avg_score >= threshold:
                                processed_data[item["user_id"]] = {
                                    "average": avg_score,
                                    "is_top_tier": True if avg_score > threshold * 1.2 else False,
                                    "last_seen": datetime.datetime.now().isoformat()
                                }

    final_report: list[str] = []
    for uid, stats in processed_data.items():
        report_line: str = format_func({uid: stats["average"]})
        final_report.append(f"[{stats['last_seen']}] USER {uid} | TIER: {'TOP' if stats['is_top_tier'] else 'STD'} | {report_line}")

    return "\n".join(final_report)
