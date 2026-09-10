"""Minimal MCP server for the Zenn hackathon E2E milestone.

This milestone intentionally returns a fixed demo result.  Evaluation logic,
Gemini, ADK, PDF generation, and WebMCP are out of scope for this server.
"""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from evaluation_adapter import evaluate


DEMO_RESULT: dict[str, Any] = {
    "report_id": "DEMO-MCP-001",
    "overall_score": 438,
    "dimensions": {
        "output_logic": 95,
        "decision_process": 77,
        "iteration_process": 68,
        "human_ownership": 99,
        "overall_consistency": 99,
    },
    "strongest_area": "Human Ownership",
    "weakest_area": "Iteration Process",
    "status": "success",
}


mcp = FastMCP(
    "ai-usage-skill-visualizer-zenn",
    instructions="Minimal MCP E2E server for the AI Usage Skill Visualizer hackathon project.",
    host="0.0.0.0",
    port=int(os.getenv("PORT", "8000")),
    streamable_http_path="/mcp",
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def evaluate_ai_usage_demo() -> dict[str, Any]:
    """Return the fixed result used to verify MCP discovery and tool calls."""

    # Return a fresh top-level object so callers cannot mutate the module
    # constant during an in-process test.
    return {
        **DEMO_RESULT,
        "dimensions": {**DEMO_RESULT["dimensions"]},
    }


@mcp.tool()
def evaluate_ai_usage(
    conversation_log: str,
    output_text: str,
    artifact_name: str = "final-output.txt",
    artifact_text: str = "",
) -> dict[str, Any]:
    """Evaluate a conversation and its actual artifact using the existing engine."""

    return evaluate(conversation_log, output_text, artifact_name, artifact_text)


if __name__ == "__main__":
    try:
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        # Keep Ctrl+C a clean local shutdown rather than a traceback.
        pass
