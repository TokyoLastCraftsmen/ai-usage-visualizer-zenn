"""Minimal ADK agent E2E client for the local MCP server.

The agent decides whether to call the discovered MCP tool. The fixed demo
score is intentionally not present in the agent instruction; it must come
from the MCP tool result.
"""

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


APP_NAME = "ai_usage_skill_visualizer_zenn"
USER_ID = "local_e2e_user"
SESSION_ID = "local_e2e_session"
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
DEMO_TOOL_NAME = "evaluate_ai_usage_demo"


def _require_authentication() -> None:
    """Fail early with setup instructions instead of guessing credentials."""

    use_vertex = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "FALSE").strip().upper() == "TRUE"
    if use_vertex:
        missing = [name for name in ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION") if not os.getenv(name)]
        if missing:
            raise RuntimeError(
                "Vertex AI mode requires: " + ", ".join(missing) + ". "
                "Configure ADC with `gcloud auth application-default login`."
            )
        return
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError(
            "GOOGLE_API_KEY is not set. Create a key in Google AI Studio and set "
            "$env:GOOGLE_API_KEY before running the Gemini E2E, or use Vertex AI "
            "mode as described in README.md."
        )


def _toolset(url: str) -> McpToolset:
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(
            url=url,
            timeout=10.0,
            sse_read_timeout=60.0,
        ),
        tool_filter=[DEMO_TOOL_NAME],
    )


def _before_tool(tool: Any, args: dict[str, Any], tool_context: Any) -> None:
    print(f"MCP_TOOL_CALL name={getattr(tool, 'name', '<unknown>')} args={json.dumps(args, ensure_ascii=False)}")


def _after_tool(tool: Any, args: dict[str, Any], tool_context: Any, tool_response: dict[str, Any]) -> None:
    print(
        f"MCP_TOOL_RESULT name={getattr(tool, 'name', '<unknown>')} "
        f"result={json.dumps(tool_response, ensure_ascii=False, default=str)}"
    )


def build_agent(mcp_url: str) -> Agent:
    """Build an ADK Agent with the official remote MCP toolset."""

    return Agent(
        name="ai_usage_evaluator_agent",
        model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
        instruction=(
            "You are an AI usage evaluation assistant. Use the "
            "evaluate_ai_usage_demo MCP tool when the user asks to evaluate the "
            "demo AI usage or requests its score. Base every score and area name "
            "on the tool result you receive; never invent or assume values. "
            "For unrelated greetings or general conversation, do not call the "
            "evaluation tool. Reply naturally and concisely. When the user asks "
            "how to improve, first inspect the tool result and identify the "
            "weakest area and its score. Treat that returned area and score as "
            "the basis for your judgment: explain why it needs improvement, "
            "then generate three concrete improvement actions specific to that "
            "area and choose one single most important next action. Do not use "
            "a fixed improvement script or assume that the weakest area is any "
            "particular dimension; adapt to whatever the tool returns. Never "
            "automatically edit the artifact or rerun the evaluation. Include "
            "the overall score out of 500, strongest area, weakest area, the "
            "reason, three actions, and the single next action in the user's "
            "language."
        ),
        tools=[_toolset(mcp_url)],
        before_tool_callback=_before_tool,
        after_tool_callback=_after_tool,
    )


async def run_prompt(prompt: str, mcp_url: str) -> str:
    _require_authentication()
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
    )
    runner = Runner(
        agent=build_agent(mcp_url),
        app_name=APP_NAME,
        session_service=session_service,
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])
    final_text = ""
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=message,
    ):
        if event.is_final_response() and event.content and event.content.parts:
            final_text = "".join(part.text or "" for part in event.content.parts if part.text)
    if not final_text:
        raise RuntimeError("Agent completed without a final text response.")
    return final_text


async def discover_tools(mcp_url: str) -> list[str]:
    """Verify ADK-side MCP tool discovery without calling Gemini."""

    toolset = _toolset(mcp_url)
    try:
        tools = await toolset.get_tools(None)
        return [tool.name for tool in tools]
    finally:
        await toolset.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default="Evaluate the demo AI usage.")
    parser.add_argument("--mcp-url", default=os.getenv("MCP_SERVER_URL", DEFAULT_MCP_URL))
    parser.add_argument("--discovery-only", action="store_true", help="Discover MCP tools without calling Gemini.")
    args = parser.parse_args()
    try:
        if args.discovery_only:
            names = asyncio.run(discover_tools(args.mcp_url))
            print(json.dumps({"discovered_tools": names}, ensure_ascii=False, indent=2))
            return
        answer = asyncio.run(run_prompt(args.prompt, args.mcp_url))
    except RuntimeError as exc:
        print(f"AUTH_OR_AGENT_SETUP_REQUIRED: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    print("AGENT_FINAL_RESPONSE")
    print(answer)


if __name__ == "__main__":
    main()
