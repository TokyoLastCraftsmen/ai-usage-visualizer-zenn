"""Minimal Streamable HTTP MCP client for the local E2E verification."""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


EXPECTED_RESULT: dict[str, Any] = {
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


def _structured_result(call_result: Any) -> dict[str, Any]:
    """Extract the structured payload returned by the MCP SDK."""

    structured = getattr(call_result, "structuredContent", None)
    if structured is None:
        structured = getattr(call_result, "structured_content", None)
    if not isinstance(structured, dict):
        raise AssertionError(f"tool result did not contain structured content: {call_result!r}")
    # The SDK may wrap a function's returned object in a `result` field.
    result = structured.get("result", structured)
    if not isinstance(result, dict):
        raise AssertionError(f"unexpected structured content shape: {structured!r}")
    return result


async def run(url: str) -> dict[str, Any]:
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            discovered_names = [tool.name for tool in tools.tools]
            expected_name = "evaluate_ai_usage_demo"
            if expected_name not in discovered_names:
                raise AssertionError(f"unexpected tool discovery result: {discovered_names!r}")

            call_result = await session.call_tool(expected_name, arguments={})
            result = _structured_result(call_result)
            if result != EXPECTED_RESULT:
                raise AssertionError(f"unexpected tool result: {result!r}")

            return {
                "transport": "streamable-http",
                "server_url": url,
                "discovered_tools": discovered_names,
                "tool_call": expected_name,
                "result": result,
                "assertions": {
                    "discovery": True,
                    "tool_call": True,
                    "overall_score_438": result["overall_score"] == 438,
                    "score_out_of_500": result["overall_score"] <= 500,
                },
            }


async def run_evaluation(url: str, conversation_log: str, output_text: str, artifact_name: str, artifact_text: str) -> dict[str, Any]:
    async with streamable_http_client(url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            discovered_names = [tool.name for tool in tools.tools]
            expected_name = "evaluate_ai_usage"
            if expected_name not in discovered_names:
                raise AssertionError(f"{expected_name} was not discovered: {discovered_names!r}")
            call_result = await session.call_tool(
                expected_name,
                arguments={
                    "conversation_log": conversation_log,
                    "output_text": output_text,
                    "artifact_name": artifact_name,
                    "artifact_text": artifact_text,
                },
            )
            result = _structured_result(call_result)
            return {
                "transport": "streamable-http",
                "discovered_tools": discovered_names,
                "tool_call": expected_name,
                "result": result,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000/mcp")
    parser.add_argument("--evaluate", action="store_true", help="Call the production-backed evaluation tool.")
    parser.add_argument("--conversation-log", default="User: I need a clear artifact. Assistant: Here is a draft.")
    parser.add_argument("--output-text", default="A clear artifact draft.")
    parser.add_argument("--artifact-name", default="final-output.txt")
    parser.add_argument("--artifact-text", default="", help="Optional artifact text separate from the final output.")
    args = parser.parse_args()
    result = asyncio.run(run_evaluation(args.url, args.conversation_log, args.output_text, args.artifact_name, args.artifact_text or args.output_text)) if args.evaluate else asyncio.run(run(args.url))
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
