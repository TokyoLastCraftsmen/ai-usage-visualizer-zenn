# AI Usage Skill Visualizer — Zenn MCP E2E

This is the first implementation milestone for the 第5回 Agentic AI Hackathon
with Google Cloud. It verifies only the MCP transport path:

```text
MCP Client → Streamable HTTP MCP Server → evaluate_ai_usage_demo → fixed JSON result
```

The first milestone's fixed demo path is retained for transport testing. The
current revision adds an optional ADK/Gemini path, a read-only production
evaluation adapter, and artifact-grounded revision suggestions. PDF, WebMCP,
Chrome extensions, and reverse handoff remain out of scope.

## Requirements

- Python 3.12+
- `mcp==1.27.2` (the official MCP Python SDK)

Install dependencies:

```powershell
py -3 -m pip install -r requirements.txt
```

## Run locally

Terminal 1:

```powershell
$env:PORT = "8000"
py -3 mcp_server.py
```

Terminal 2:

```powershell
py -3 mcp_client.py
```

The client performs initialization, tool discovery, `evaluate_ai_usage_demo`
tool invocation, and exact result assertions. The MCP endpoint is:

```text
http://127.0.0.1:8000/mcp
```

The server reads `PORT`, defaulting to `8000` locally and accepting Cloud Run's
injected port when deployed later.

## Minimal ADK / Gemini Agent E2E

The second milestone adds an ADK Agent that uses the existing MCP server as a
remote Streamable HTTP toolset:

```text
ADK Agent → McpToolset → http://127.0.0.1:8000/mcp
         → evaluate_ai_usage_demo → MCP result → Gemini response
```

Install the pinned dependencies:

```powershell
py -3 -m pip install -r requirements.txt
```

For local Gemini API mode, create an API key in Google AI Studio and set it in
the process environment. Do not put the key in source files:

```powershell
$env:GOOGLE_GENAI_USE_VERTEXAI = "FALSE"
$env:GOOGLE_GENAI_USE_ENTERPRISE = "FALSE"
$env:GOOGLE_API_KEY = "YOUR_API_KEY"
$env:GEMINI_MODEL = "gemini-3.8-flash"
```

Alternatively, use Vertex AI mode with Application Default Credentials:

```powershell
gcloud auth application-default login
$env:GOOGLE_GENAI_USE_VERTEXAI = "TRUE"
$env:GOOGLE_CLOUD_PROJECT = "YOUR_PROJECT_ID"
$env:GOOGLE_CLOUD_LOCATION = "global"
$env:GEMINI_MODEL = "gemini-3.8-flash"
```

Start the MCP server in Terminal 1, then run the Agent in Terminal 2:

```powershell
$env:PORT = "8000"
py -3 mcp_server.py
```

```powershell
py -3 agent_runner.py "Evaluate the demo AI usage."
```

The runner prints `MCP_TOOL_CALL` and `MCP_TOOL_RESULT` evidence when the
Agent selects the MCP tool, followed by `AGENT_FINAL_RESPONSE`. To test the
non-tool path:

```powershell
py -3 agent_runner.py "Hello."
```

To verify ADK-side MCP discovery without making a Gemini API call:

```powershell
py -3 agent_runner.py --discovery-only
```

The Agent instruction does not contain the fixed score. The score and area
names in the final response must come from the MCP result.

The local API-key setup follows Google's ADK quickstart. Vertex AI mode uses
the documented `GOOGLE_GENAI_USE_VERTEXAI`, project, location, and ADC setup.

## Zenn Edition analysis flow

The Zenn repo contains the evaluation analyzer/scorer needed for its local and
Cloud Run execution. It sends the following to Gemini for concrete,
human-reviewed revision candidates:

```text
conversation log + actual artifact + evaluation evidence
  → bundled analyzer/scorer
  → overall score and five dimensions
  → score gap = max(0, 500 - overall_score)
  → Gemini JSON suggestions tied to the actual artifact
  → UI + handoff payload
```

The evaluation engine is bundled under `engine/`; no external local repository
is required at runtime. Suggestions never contain point allocations or
score-increase guarantees, and the application never applies them,
reruns evaluation, regenerates reports, or sends a chat message automatically.

Run the minimal UI/API locally after configuring Gemini credentials:

```powershell
py -3 web_app.py
```

Open `http://127.0.0.1:8080/`, paste the conversation log and actual artifact,
then select `START ANALYSIS`. The API endpoint is `POST /api/analyze`.

The MCP server also exposes `evaluate_ai_usage` for the ADK path. The existing
fixed `evaluate_ai_usage_demo` tool remains unchanged for the earlier E2E.

For the artifact-grounded ADK Agent path, provide the actual log and artifact:

```powershell
py -3 revision_agent_runner.py `
  --conversation-log "User: I need a clear landing page. Assistant: Here are options." `
  --artifact "START ANALYSIS" `
  --artifact-name "landing-page-copy.txt"
```

This Agent calls `evaluate_ai_usage` through MCP, then generates concrete
revision candidates from the returned evaluation and the artifact text. It
does not apply changes or send messages.
