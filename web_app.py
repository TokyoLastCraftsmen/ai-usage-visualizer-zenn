"""Small browser UI for the Zenn Edition analysis flow."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from analysis_service import analyze_and_suggest
from pdf_report import generate_zenn_japanese_pdf
from mcp_server import mcp


class AnalysisRequest(BaseModel):
    conversation_log: str
    output_text: str
    artifact_name: str = "final-output.txt"
    artifact_text: str = ""


class PdfRequest(BaseModel):
    result: dict[str, Any]
    output_title: str = ""
    output_text: str = ""
    artifact_name: str = "final-output.txt"
    artifact_text: str = ""


mcp_http_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="AI Usage Skill Visualizer Zenn Edition", lifespan=lifespan)
EXTENSION_ZIP = Path(__file__).with_name("ai-usage-visualizer-extension.zip")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).with_name("index.html"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/downloads/ai-usage-visualizer-extension.zip")
def download_extension() -> FileResponse:
    return FileResponse(
        EXTENSION_ZIP,
        media_type="application/zip",
        filename="ai-usage-visualizer-extension.zip",
    )


@app.post("/api/analyze")
def analyze(request: AnalysisRequest) -> JSONResponse:
    try:
        return JSONResponse(analyze_and_suggest(**request.model_dump()))
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)


@app.post("/api/report/pdf")
def report_pdf(request: PdfRequest) -> Response:
    """Download a PDF from the completed result; evaluation is never rerun here."""
    try:
        pdf_bytes = generate_zenn_japanese_pdf(
            request.result,
            output_title=request.output_title,
            output_text=request.output_text,
            artifact_name=request.artifact_name,
            artifact_text=request.artifact_text,
        )
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="ai-usage-report.pdf"'},
    )


# FastMCP supplies the existing Streamable HTTP implementation. Mounting it
# last keeps the Web/API routes above on the same ASGI application and exposes
# its configured /mcp route without starting a second process or port.
app.mount("/", mcp_http_app)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
