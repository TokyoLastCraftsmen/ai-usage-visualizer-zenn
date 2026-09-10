"""Application service for evaluation, revision suggestions, and handoff."""

from __future__ import annotations

from typing import Any

from evaluation_adapter import evaluate
from revision_generator import generate_revision_suggestions


def build_handoff_payload(evaluation: dict[str, Any], suggestions: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_id": evaluation["report_id"],
        "overall_score": evaluation["overall_score"],
        "score_gap": evaluation["score_gap"],
        "dimensions": evaluation["dimensions"],
        "strongest_area": evaluation["strongest_area"],
        "weakest_area": evaluation["weakest_area"],
        "ai_generated_revision_suggestions": suggestions.get("suggestions", []),
        "limitations": suggestions.get("limitations", []),
        "instructions": {
            "do_not_rerun_evaluation": True,
            "do_not_regenerate_existing_report": True,
            "do_not_auto_send": True,
            "human_reviews_and_applies_any_change": True,
        },
    }


def analyze_and_suggest(
    conversation_log: str,
    output_text: str,
    artifact_name: str = "final-output.txt",
    artifact_text: str = "",
) -> dict[str, Any]:
    evaluation = evaluate(conversation_log, output_text, artifact_name, artifact_text)
    suggestions = generate_revision_suggestions(evaluation)
    return {
        "evaluation": evaluation,
        "suggestions": suggestions,
        "handoff_payload": build_handoff_payload(evaluation, suggestions),
    }
