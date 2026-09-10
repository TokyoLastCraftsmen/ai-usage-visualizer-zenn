"""Small browser UI for the Zenn Edition analysis flow."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from analysis_service import analyze_and_suggest


class AnalysisRequest(BaseModel):
    conversation_log: str
    output_text: str
    artifact_name: str = "final-output.txt"
    artifact_text: str = ""


app = FastAPI(title="AI Usage Skill Visualizer Zenn Edition")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).with_name("index.html"))


@app.post("/api/analyze")
def analyze(request: AnalysisRequest) -> JSONResponse:
    try:
        return JSONResponse(analyze_and_suggest(**request.model_dump()))
    except (ValueError, RuntimeError) as exc:
        return JSONResponse({"status": "error", "error": str(exc)}, status_code=400)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
