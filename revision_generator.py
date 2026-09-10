"""Gemini-based concrete revision suggestion generation."""

from __future__ import annotations

import json
import os
from typing import Any

from google import genai
from google.genai import types


DEFAULT_MODEL = "gemini-3.8-flash"


REVISION_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "area_key": {"type": "string"},
                    "area": {"type": "string"},
                    "axis_score": {"type": "integer"},
                    "minus_points": {"type": "array", "items": {"type": "string"}},
                    "finding": {"type": "string"},
                    "improvement_suggestion": {"type": "string"},
                    "evidence": {"type": "string"},
                    "target": {"type": "string"},
                    "proposed_change": {"type": "string"},
                    "example": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "area_key",
                    "area",
                    "axis_score",
                    "minus_points",
                    "improvement_suggestion",
                ],
            },
        },
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["suggestions", "limitations"],
}


def _model_input(evaluation: dict[str, Any]) -> str:
    evidence = evaluation.get("evidence", {})
    dimensions = evaluation.get("dimensions", {})
    grouped: dict[str, list[dict[str, Any]]] = {str(key): [] for key in dimensions}
    area_names: dict[str, str] = {}
    for point in evaluation.get("minus_points", []):
        if not isinstance(point, dict):
            continue
        area_key = str(point.get("area_key", ""))
        if area_key in grouped:
            grouped[area_key].append(point)
            area_names.setdefault(area_key, str(point.get("area", area_key)))
    axis_groups = [
        {
            "area_key": area_key,
            "area": area_names.get(area_key, area_key),
            "axis_score": dimensions.get(area_key),
            "minus_points": points,
        }
        for area_key, points in grouped.items()
        if points
    ]
    return "\n".join(
        [
            "Conversation log evidence:",
            str(evidence.get("conversation_log_raw", evidence.get("conversation_log", ""))),
            "Actual artifact evidence:",
            f"Name: {evidence.get('artifact_name', '')}",
            str(evidence.get("artifact_text", "")),
            "Extracted semantic actions (auxiliary for scoring, required evidence for suggestions):",
            json.dumps(evaluation.get("actions", []), ensure_ascii=False, default=str),
            "Evaluation result and actual minus_points:",
            json.dumps(
                {
                    "report_id": evaluation.get("report_id"),
                    "overall_score": evaluation.get("overall_score"),
                    "score_gap": evaluation.get("score_gap"),
                    "dimensions": evaluation.get("dimensions"),
                    "strongest_area": evaluation.get("strongest_area"),
                    "weakest_area": evaluation.get("weakest_area"),
                    "evaluation_comments": evaluation.get("evaluation_comments"),
                    "axis_groups": axis_groups,
                    "actions": evaluation.get("actions", []),
                    "trace_summary": evaluation.get("trace_summary"),
                    "visual_analysis": evaluation.get("visual_analysis"),
                    "artifact_type": evaluation.get("artifact_type"),
                    "artifact_match": evaluation.get("artifact_match"),
                },
                ensure_ascii=False,
                default=str,
            ),
        ]
    )


def generate_revision_suggestions(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Ask Gemini for artifact-grounded suggestions; never modify the artifact."""

    client = genai.Client()
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            "Generate exactly one improvement_suggestion for each supplied axis "
                            "group. For each axis, first inspect the full conversation log, "
                            "actual artifact text, and extracted semantic actions for concrete "
                            "facts relevant to that axis, then inspect the actual minus_points "
                            "and their evidence. Treat actions as auxiliary for scoring but "
                            "mandatory evidence to cross-check and concretize the conversation. "
                            "Use every available runtime-specific fact that is relevant; do "
                            "not end with generic advice when concrete facts are available. "
                            "Do not merely restate or summarize a minus_point. Explain what "
                            "the input already records, what remains insufficient or not fully "
                            "traceable, and what observable state would count as improvement. "
                            "If a minus_point appears to conflict with or partially overlap "
                            "actual evidence, preserve the minus_point unchanged, acknowledge "
                            "the existing evidence, and describe only the remaining gap and "
                            "desired improved state. Never claim that existing comparison, "
                            "adoption, rejection, reasons, revisions, priority changes, or "
                            "policy changes are absent when they are present in the inputs. "
                            "Keep the sequence existing evidence -> remaining gap -> improved "
                            "observable state clear in the suggestion. Ground every statement "
                            "only in text explicitly present in the supplied conversation log, "
                            "actual artifact text, minus_points, existing evidence, and actions. "
                            "Preserve area_key, area, axis_score, every minus_point, finding, "
                            "and evidence exactly. Do not infer or invent options, criteria, "
                            "people, requirements, constraints, audiences, background, policy, "
                            "comparisons, revision history, decisions, conclusions, or any "
                            "other facts absent from those inputs. If the input lacks specific "
                            "information, say only what cannot be confirmed and describe the "
                            "improved state without inventing details. "
                            "Do not produce a rewritten artifact, completed example, sample "
                            "sentence, prompt example, action, procedure, task list, navigation, "
                            "next step, automatic fix, or reevaluation. Do not use imperative "
                            "wording. Do not assign points, recalculate scores, create findings, "
                            "create evidence, or change evaluation data. Return JSON matching "
                            "the requested schema.\n\n" + _model_input(evaluation)
                        )
                    )
                ],
            )
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=REVISION_SCHEMA,
        ),
    )
    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned an empty revision suggestion response")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Gemini did not return valid JSON") from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("suggestions"), list):
        raise RuntimeError("Gemini response did not match the revision suggestion schema")
    return parsed
