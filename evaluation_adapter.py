"""Adapter for the self-contained Zenn evaluation engine."""

from __future__ import annotations

import hashlib
from typing import Any

from engine import action_extractor, analyzer, scorer


AXIS_MAP = {
    "成果物論理性": "output_logic",
    "判断プロセス": "decision_process",
    "修正プロセス": "iteration_process",
    "判断主体性": "human_ownership",
    "全体整合性": "overall_consistency",
}

AXIS_LABELS = {
    "output_logic": "Output Logic",
    "decision_process": "Decision Process",
    "iteration_process": "Iteration Process",
    "human_ownership": "Human Ownership",
    "overall_consistency": "Overall Consistency",
}


def _excerpt(value: Any, limit: int = 4000) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit] + "\n[excerpt truncated]"


def _minus_points(axis_details: dict[str, Any], dimensions: dict[str, int]) -> list[dict[str, Any]]:
    """Expose only negative findings already emitted by the scorer."""

    points: list[dict[str, Any]] = []
    for axis, details in axis_details.items():
        if not isinstance(details, dict):
            continue
        normalized_axis = AXIS_MAP.get(axis, axis)
        risk_flags = details.get("risk_flags", [])
        if not isinstance(risk_flags, list):
            continue
        for finding in risk_flags:
            if not str(finding or "").strip():
                continue
            point: dict[str, Any] = {
                "area_key": normalized_axis,
                "area": AXIS_LABELS.get(normalized_axis, normalized_axis),
                "axis_score": dimensions.get(normalized_axis),
                "score": dimensions.get(normalized_axis),
                "finding": finding,
                "source": "existing_evaluation.axis_details.risk_flags",
            }
            evidence = details.get("evidence", [])
            if isinstance(evidence, list) and evidence:
                point["evidence"] = evidence
            points.append(point)
    return points


def evaluate(conversation_log: str, output_text: str, artifact_name: str = "final-output.txt", artifact_text: str = "") -> dict[str, Any]:
    """Evaluate one conversation and its actual artifact using the existing engine."""

    if not str(conversation_log or "").strip():
        raise ValueError("conversation_log is required")
    if not str(output_text or "").strip():
        raise ValueError("output_text is required")

    artifact_summary = artifact_text or output_text
    artifact_items = [{"name": artifact_name or "final-output.txt", "type": "text/plain", "text": artifact_summary}]
    analyzed = analyzer.analyze(str(conversation_log), artifact_summary, artifact_items=artifact_items)
    scorer_input = analyzed
    scorer_output_text = str(output_text)
    if artifact_text and artifact_text == output_text and "文章成果物:" not in scorer_output_text:
        scorer_input = dict(analyzed)
        scorer_input["output_text"] = ""
        scorer_input["artifact_context_text"] = ""
        scorer_input["actual_output_text"] = str(artifact_text).strip()
        scorer_output_text = "文章成果物:\n" + scorer_output_text
    scored = scorer.score(scorer_input, scorer_output_text)
    actions = action_extractor.extract_actions(str(conversation_log))
    raw_scores = scored.get("scores", {}) if isinstance(scored, dict) else {}
    dimensions = {
        target: int(raw_scores[source])
        for source, target in AXIS_MAP.items()
        if source in raw_scores
    }
    if len(dimensions) != len(AXIS_MAP):
        raise RuntimeError(f"production scorer returned incomplete dimensions: {raw_scores!r}")

    axis_details = scored.get("axis_details", {}) if isinstance(scored, dict) else {}
    lowest_axis = min(dimensions, key=dimensions.get)
    highest_axis = max(dimensions, key=dimensions.get)
    reverse_axis_map = {value: key for key, value in AXIS_MAP.items()}
    stable_id = hashlib.sha256((conversation_log + "\n" + output_text).encode("utf-8")).hexdigest()[:12].upper()
    return {
        "report_id": "ZENN-LOCAL-" + stable_id,
        "overall_score": int(scored.get("total_score", sum(dimensions.values()))),
        "score_gap": max(0, 500 - int(scored.get("total_score", sum(dimensions.values())))),
        "dimensions": dimensions,
        "strongest_area": AXIS_LABELS[highest_axis],
        "weakest_area": AXIS_LABELS[lowest_axis],
        "evaluation_comments": {
            axis: axis_details.get(reverse_axis_map[axis], {}) for axis in dimensions
        },
        "minus_points": _minus_points(axis_details, dimensions),
        "actions": actions,
        "trace_summary": scored.get("trace_summary", {}),
        "visual_analysis": scored.get("visual_evaluation", {}),
        "artifact_type": scored.get("artifact_type", "unknown"),
        "artifact_match": scored.get("artifact_match", {}),
        "evidence": {
            "conversation_log": _excerpt(conversation_log),
            "conversation_log_raw": str(conversation_log),
            "artifact_name": artifact_name or "final-output.txt",
            "artifact_text": _excerpt(artifact_summary),
        },
    }
