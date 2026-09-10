"""ADK Agent path for artifact-grounded revision suggestions via MCP."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.genai import types

from agent_runner import _require_authentication


APP_NAME = "ai_usage_skill_visualizer_revision_agent"
USER_ID = "local_revision_user"
SESSION_ID = "local_revision_session"
DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_MODEL = "gemini-3.8-flash"


def _toolset(mcp_url: str) -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=mcp_url,
            timeout=10.0,
            sse_read_timeout=60.0,
        ),
        tool_filter=["evaluate_ai_usage"],
    )


def _before_tool(tool: Any, args: dict[str, Any], tool_context: Any) -> None:
    print(f"MCP_TOOL_CALL name={getattr(tool, 'name', '<unknown>')} args={json.dumps(args, ensure_ascii=False)}")
    return None


def _after_tool(tool: Any, args: dict[str, Any], tool_context: Any, tool_response: dict[str, Any]) -> None:
    print(
        f"MCP_TOOL_RESULT name={getattr(tool, 'name', '<unknown>')} "
        f"result={json.dumps(tool_response, ensure_ascii=False, default=str)}"
    )
    return None


def build_agent(mcp_url: str) -> Agent:
    return Agent(
        name="artifact_revision_agent",
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        instruction=(
            "You are a human-centered AI usage reviewer. When asked to review an "
            "artifact, call evaluate_ai_usage with the supplied conversation log "
            "and actual artifact text. After receiving the tool result, generate "
            "specific improvement descriptions grounded only in text explicitly present "
            "in the supplied conversation and actual artifact. Include "
            "the current overall score out of 500, score gap, strongest and weakest "
            "areas. Group all minus_points by their returned area_key and produce "
            "one concrete improvement suggestion per evaluation axis, preserving every "
            "minus_point's area_key, area, axis_score, finding, and evidence exactly. "
            "Do not invent options, criteria, people, requirements, constraints, audiences, "
            "background, policy, comparisons, revision history, decisions, conclusions, or "
            "other facts absent from the inputs. If information is missing, describe only what "
            "cannot be confirmed and the observable improved state; do not fill the gap. "
            "Treat extracted actions in the MCP result as auxiliary evidence only; never create, "
            "remove, or modify minus_points from actions. "
            "Do not use a fixed finding-to-text mapping. Do not generate a rewritten artifact, "
            "example text, prompt example, imperative action, procedure, navigation, task list, "
            "next step, automatic fix, or automatic reevaluation. Explain the improved state and stop. "
            "Do not assign points, predict score increases, promise 500/500, rerun "
            "evaluation, regenerate a report, modify the artifact, or send anything. "
            "The user decides whether to apply any suggestion. For greetings or "
            "unrelated conversation, do not call the evaluation tool."
        ),
        tools=[_toolset(mcp_url)],
        before_tool_callback=_before_tool,
        after_tool_callback=_after_tool,
    )


async def run(conversation_log: str, output_text: str, artifact_name: str, mcp_url: str) -> str:
    _require_authentication()
    sessions = InMemorySessionService()
    await sessions.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    runner = Runner(agent=build_agent(mcp_url), app_name=APP_NAME, session_service=sessions)
    prompt = (
        "Review this actual artifact and suggest concrete human-reviewed revisions.\n\n"
        f"Conversation log:\n{conversation_log}\n\n"
        f"Artifact name: {artifact_name}\n"
        f"Actual artifact:\n{output_text}"
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=message):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(part.text or "" for part in event.content.parts if part.text)
    if not final_text:
        raise RuntimeError("Agent completed without a final text response.")
    return final_text


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversation-log", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--artifact-name", default="final-output.txt")
    parser.add_argument("--mcp-url", default=os.getenv("MCP_SERVER_URL", DEFAULT_MCP_URL))
    args = parser.parse_args()
    try:
        answer = asyncio.run(run(args.conversation_log, args.artifact, args.artifact_name, args.mcp_url))
    except RuntimeError as exc:
        print(f"AUTH_OR_AGENT_SETUP_REQUIRED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print("AGENT_FINAL_RESPONSE")
    print(answer)


if __name__ == "__main__":
    main()
