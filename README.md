# AI Usage Skill Visualizer

AI Usage Skill Visualizer is an application for visualizing how people use AI.
It evaluates the human decision-making process behind an AI-assisted output—not
the performance of the AI model itself.

- Live demo: https://ai-usage-visualizer-zenn-492894093470.asia-northeast1.run.app
- GitHub: https://github.com/TokyoLastCraftsmen/ai-usage-visualizer-zenn

## What it is

Users provide an AI conversation log and the actual artifact or final output.
The application analyzes how decisions, selections, revisions, and human
judgment in the conversation relate to the resulting artifact.

It produces an overall evaluation, axis-specific evidence, context-specific
improvement suggestions, and an eight-page Japanese PDF report.

## Problem

Many AI evaluations focus on model performance, benchmarks, adoption, or usage
volume. Those measures do not show whether a person made deliberate choices,
reviewed alternatives, preserved human ownership, or connected the AI process
to the final result.

AI Usage Skill Visualizer focuses on that human side of AI use:

- What did the person decide?
- Which proposals were adopted or rejected?
- How was the output revised?
- How did the process affect the final artifact?
- Did the person retain final judgment and responsibility?

## Approach

The application combines the conversation record with the actual output rather
than evaluating either one in isolation. A bundled analyzer and scorer produce
the five-axis evaluation. Gemini then generates artifact-grounded improvement
suggestions from the evaluation evidence and supplied material. Suggestions are
presented for human review; the application does not automatically apply them
or send messages.

## What is evaluated

Each axis is scored from 0 to 100, for a maximum Overall Score of 500:

1. Output Logic — how clearly the output is structured and reasoned
2. Decision Process — how choices and judgments are represented
3. Iteration Process — how revision and improvement are evidenced
4. Human Ownership — whether human judgment remains visible and decisive
5. Overall Consistency — how well the process, evidence, and output align

The report also presents evaluation summaries, evidence-bound prose, and
improvement suggestions tied to the available context.

## How it works

```text
Conversation log + actual artifact
        ↓
Evaluation adapter → analyzer → scorer
        ↓
Overall score + five-axis evaluation + evidence
        ↓
Gemini-backed improvement suggestions
        ↓
Browser result view, handoff payload, and PDF report
```

## Architecture

```mermaid
flowchart TD
    U[User / Browser] --> UI[Web UI on Cloud Run]
    CE[AI Visualization Log Extractor] -->|conversation log| UI
    UI --> A[/api/analyze]
    UI --> P[/api/report/pdf]
    UI --> D[/downloads/ai-usage-visualizer-extension.zip]
    UI --> M[/mcp]

    A --> EA[evaluation_adapter]
    EA --> AN[analyzer]
    AN --> SC[scorer]
    EA --> SUG[revision suggestion generation]
    SUG --> G[Gemini]
    A --> R[Evaluation result + suggestions]

    P --> PR[pdf_report]
    PR --> PAY[build_report_payload]
    PAY --> EBP[evidence-bound prose]
    EBP --> RL[ReportLab]
    RL --> PP[pypdf]
    PP --> QR[Page 1 / Page 8 QR verification]

    MC[MCP Client / AI Agent] -->|Streamable HTTP| M
    M --> DEMO[evaluate_ai_usage_demo]
    DEMO --> FIXED[Fixed demo JSON]
    M --> EVAL[evaluate_ai_usage]
    EVAL --> EA
    EA --> R

    SM[Secret Manager] -. credentials and QR HMAC secret .-> UI
    AR[Artifact Registry] -. container image .-> UI
    CB[Cloud Build] -. builds image .-> AR
    CL[Cloud Logging] -. runtime logs .-> UI
```

## Google Cloud / Gemini

The production service runs on Google Cloud:

- Cloud Run provides the Web UI, REST API, PDF endpoint, ZIP download, and MCP
  Streamable HTTP endpoint as one service.
- Gemini API is used by the revision suggestion generator to interpret the
  finalized evaluation evidence and produce concrete, context-specific
  suggestions. The bundled scorer produces the five-axis score; Gemini does
  not recalculate that score.
- Secret Manager supplies the Gemini API credential and QR HMAC signing secret
  to the runtime. Secret values are never stored in this repository.
- Artifact Registry stores the container image.
- Cloud Build builds the container image.
- Cloud Logging stores Cloud Run runtime logs.

The current production model setting is `gemini-3.6-flash`.

## MCP

The production service exposes MCP as Streamable HTTP at `/mcp`.

Available tools:

- `evaluate_ai_usage_demo` — fixed result for MCP transport and discovery tests
- `evaluate_ai_usage` — evaluates a conversation log and actual artifact

MCP-compatible clients and AI agents can call the evaluation capability as an
external tool. The interface returns evaluation information and does not move
final judgment or responsibility from the person to the agent.

Production verification completed successfully for `initialize`, `tools/list`,
and `evaluate_ai_usage_demo`, with no HTTP 404, HTTP 500, or session error.

## Chrome Extension

**AI Visualization Log Extractor** is a Chrome extension that extracts AI
conversation logs from supported AI chat pages such as ChatGPT, Claude, and
Gemini, making them easier to provide as Visualizer input.

The production UI provides the download link:

`/downloads/ai-usage-visualizer-extension.zip`

The verified production response is HTTP 200 with a 12,845-byte ZIP file. This
extension is the conversation-log extractor and is separate from any reverse
handoff extension.

## PDF Report

The application generates an eight-page Japanese evaluation report through:

```text
POST /api/report/pdf
→ web_app.py
→ pdf_report.py
→ build_report_payload()
→ build_evidence_bound_prose()
→ generate_report_ja_from_canonical_payload()
→ ReportLab / pypdf
```

The PDF is generated from the completed evaluation and does not rerun the
evaluation. Page 1 contains the evaluation-criteria QR code and Page 8 contains
the verification QR code. QR payloads use HMAC-SHA256 signing; the signing
secret is supplied through Secret Manager and is not included here.

## Canonical Sample

The canonical sample is a reproducibility check against the published sample
input, not a product-performance benchmark.

- Overall: **427 / 500**
- Output Logic: **95**
- Decision Process: **77**
- Iteration Process: **78**
- Human Ownership: **82**
- Overall Consistency: **95**

The canonical sample also produces the verified eight-page Japanese PDF.

## Live Demo

Open the [production application](https://ai-usage-visualizer-zenn-492894093470.asia-northeast1.run.app)
to try the browser flow.

## Quick Demo Flow

1. Open the Live Demo.
2. Click **Sample Data**.
3. Start the analysis.
4. Review the Overall Score and five dimensions.
5. Review the evidence and improvement suggestions.
6. Generate the PDF report.

The Chrome extension is an optional separate flow for extracting a conversation
log before analysis.

## Local Development

Install the pinned dependencies:

```powershell
py -3 -m pip install -r requirements.txt
```

Run the complete Web UI and API locally:

```powershell
$env:PORT = "8080"
$env:GEMINI_MODEL = "gemini-3.6-flash"
$env:GOOGLE_API_KEY = "YOUR_API_KEY"
$env:AI_USAGE_SKILL_VISUALIZER_QR_HMAC_SECRET = "YOUR_QR_HMAC_SECRET"
py -3 web_app.py
```

Open `http://127.0.0.1:8080/`. The local Web UI uses `/api/analyze`,
`/api/report/pdf`, and `/mcp` on the same port. The QR HMAC secret is required
when generating a PDF. Do not commit API keys or signing secrets.

For the standalone MCP transport check, run:

```powershell
$env:PORT = "8000"
py -3 mcp_server.py
```

In another terminal:

```powershell
py -3 mcp_client.py --url "http://127.0.0.1:8000/mcp"
```

The ADK examples are available in `agent_runner.py` and
`revision_agent_runner.py`; they require the corresponding Gemini credentials
and use the MCP endpoint as configured by their command-line options.

## Environment / Secrets

For local development, provide credentials through environment variables or
Application Default Credentials. For production, Cloud Run receives the
Gemini credential and QR HMAC signing secret from Google Secret Manager.

Never place secret values in source files, README content, browser payloads, or
commits.

## API / Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Web UI |
| `GET /health` | Health check |
| `POST /api/analyze` | Evaluate a conversation log and artifact, then generate suggestions |
| `POST /api/report/pdf` | Generate the completed Japanese PDF report |
| `GET /downloads/ai-usage-visualizer-extension.zip` | Download the Chrome extension |
| `POST /mcp` | MCP Streamable HTTP transport |

## Repository Structure

- `web_app.py` — FastAPI Web UI, REST endpoints, and MCP mount
- `index.html` — browser UI and client-side flow
- `evaluation_adapter.py` — evaluation input/output adapter
- `analysis_service.py` — evaluation, suggestions, and handoff payload
- `engine/` — analyzer, scorer, action extraction, summarizer, and evidence-bound prose
- `revision_generator.py` — Gemini-backed improvement suggestions
- `mcp_server.py` / `mcp_client.py` — MCP tools and client verification
- `pdf_report.py` — completed-result PDF adapter
- `pdf_generator_en.py` — ReportLab / pypdf PDF implementation
- `Dockerfile` — Cloud Run container image definition
- `ai-usage-visualizer-extension.zip` — downloadable Chrome extension

## Human-in-the-loop principle

The application makes AI-assisted work more visible; it does not replace human
judgment. Evaluation results and suggestions are presented for review. The
person decides whether to adopt any suggestion, make any revision, or take any
next action, and remains responsible for the final output.

## Hackathon

Prepared for the Google Cloud Japan AI Hackathon Vol.5.

Demo video: To be added for hackathon submission.
