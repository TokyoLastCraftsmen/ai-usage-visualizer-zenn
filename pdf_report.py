"""Zenn adapter for the published Japanese production PDF renderer."""

from __future__ import annotations

import os
import logging
import importlib
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from copy import deepcopy
from datetime import datetime
from typing import Any
from pathlib import Path

from pdf_generator_en import generate_report_ja_from_canonical_payload
from engine.evidence_bound_prose import build_evidence_bound_prose


LOGGER = logging.getLogger(__name__)


def _load_public_pdf_generator():
    """Load the unchanged public fixed-template generator bundled for runtime."""
    configured = str(os.getenv("PUBLIC_JP_PDF_APP_DIR", "") or "").strip()
    candidates = [
        Path(__file__).resolve().parent,
        Path(configured) if configured else None,
        Path(r"C:\Users\TokyoLastCraftsmen\-ai-visualizer-app\app"),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        candidate = candidate.resolve()
        module_path = candidate / "pdf_generator.py"
        if module_path.exists():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return importlib.import_module("pdf_generator")
    raise RuntimeError(
        "公開版PDF generatorが見つかりません。"
        "PUBLIC_JP_PDF_APP_DIRまたは公開版repoの配置を確認してください。"
    )


def _export_pdf_with_isolated_profile(pptx_path: Path, pdf_path: Path) -> bool:
    """Run the public export command with a fresh LibreOffice profile."""
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    # LibreOffice on this Windows installation can hang when its conversion
    # output/profile directories are created directly beside the caller's
    # working files. Keep both temporary directories in a normal runtime
    # subdirectory, while still removing the per-run directories below.
    lo_temp_root = pdf_path.parent.resolve()
    lo_temp_root.mkdir(parents=True, exist_ok=True)
    run_token = uuid.uuid4().hex
    conversion_path = lo_temp_root / f"lo-export-{os.getpid()}-{run_token}"
    profile_path = lo_temp_root / f"lo-profile-{os.getpid()}-{run_token}"
    conversion_path.mkdir(parents=True, exist_ok=False)
    profile_path.mkdir(parents=True, exist_ok=False)
    conversion_dir = str(conversion_path)
    profile_dir = str(profile_path)
    try:
        started = time.perf_counter()
        soffice_candidates = [
            str(os.getenv("SOFFICE_PATH", "") or "").strip(),
            shutil.which("soffice") or "",
            shutil.which("libreoffice") or "",
            "/usr/bin/soffice",
            "/usr/bin/libreoffice",
            r"C:\Program Files\LibreOffice\program\soffice.exe",
            r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        ]
        soffice_path = next((Path(item) for item in soffice_candidates if item and Path(item).exists()), None)
        if soffice_path is None:
            LOGGER.error("ZENN_LO_EXPORT_MISSING soffice.exe")
            return False
        profile_uri = profile_dir.replace("\\", "/")
        if not profile_uri.startswith("file:///"):
            profile_uri = "file:///" + profile_uri.lstrip("/")
        converted = Path(conversion_dir) / f"{pptx_path.stem}.pdf"
        stdout_path = Path(conversion_dir) / "soffice.stdout.txt"
        stderr_path = Path(conversion_dir) / "soffice.stderr.txt"
        try:
            with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
                process = subprocess.Popen(
                    [
                        str(soffice_path),
                        f"-env:UserInstallation={profile_uri}",
                        "--headless",
                        "--nologo",
                        "--nofirststartwizard",
                        "--convert-to",
                        "pdf",
                        "--outdir",
                        str(Path(conversion_dir).resolve()),
                        str(pptx_path.resolve()),
                    ],
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                )
                deadline = time.monotonic() + 90.0
                while time.monotonic() < deadline:
                    if converted.exists() and converted.stat().st_size > 0:
                        break
                    if process.poll() is not None:
                        break
                    time.sleep(0.25)
                if process.poll() is None:
                    if converted.exists() and converted.stat().st_size > 0:
                        try:
                            process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.terminate()
                    else:
                        process.terminate()
                        process.wait(timeout=5)
                return_code = process.returncode
        except (OSError, subprocess.TimeoutExpired):
            LOGGER.exception("ZENN_LO_EXPORT_TIMEOUT pptx=%s", pptx_path)
            return False
        elapsed = time.perf_counter() - started
        stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
        stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
        LOGGER.info(
            "ZENN_LO_EXPORT_RESULT return_code=%s elapsed_seconds=%.3f pdf_exists=%s stdout=%s stderr=%s",
            return_code,
            elapsed,
            converted.exists(),
            stdout_text.strip(),
            stderr_text.strip(),
        )
        if not converted.exists() or converted.stat().st_size <= 0:
            return False
        if converted.resolve() != pdf_path.resolve():
            if pdf_path.exists():
                pdf_path.unlink()
            converted.replace(pdf_path)
        return pdf_path.exists() and pdf_path.stat().st_size > 0
    finally:
        shutil.rmtree(conversion_dir, ignore_errors=True)
        shutil.rmtree(profile_dir, ignore_errors=True)


AXES = (
    ("output_logic", "アウトプットの論理性"),
    ("decision_process", "判断プロセス"),
    ("iteration_process", "修正プロセス"),
    ("human_ownership", "判断の主体性"),
    ("overall_consistency", "全体整合性"),
)

AXIS_LABELS = {
    "output_logic": "Output Logic",
    "decision_process": "Decision Process",
    "iteration_process": "Iteration Process",
    "human_ownership": "Human Ownership",
    "overall_consistency": "Overall Consistency",
}

CANONICAL_PAYLOAD_KEYS = (
    "target_name", "target_work", "doc_id", "meta_info",
    "overall_summary", "ai_capability_evaluation", "output_logic_evaluation",
    "judgment_process_evaluation", "revision_process_evaluation",
    "agency_process_evaluation", "consistency_process_evaluation",
    "thought_output_relation", "third_party_visibility", "applicable_domain_text",
    "applicable_business_list", "ai_use_scope_statement", "page6_transparency_text",
    "page6_responsibility_structure", "page6_responsibility_body",
)


def _text(value: Any, fallback: str = "") -> str:
    if isinstance(value, (list, tuple)):
        return " / ".join(_text(item) for item in value if _text(item))
    return str(value or fallback).strip()


def _detail(evaluation: dict[str, Any], key: str) -> dict[str, Any]:
    details = evaluation.get("evaluation_comments") or {}
    value = details.get(key, {})
    return value if isinstance(value, dict) else {}


def _detail_text(detail: dict[str, Any]) -> str:
    parts: list[str] = []
    for field in ("reasons", "evidence", "risk_flags"):
        value = detail.get(field)
        if isinstance(value, list):
            parts.extend(_text(item) for item in value if _text(item))
        elif _text(value):
            parts.append(_text(value))
    return " ".join(dict.fromkeys(parts))


def _axis_text(evaluation: dict[str, Any], key: str, label: str) -> str:
    detail = _detail(evaluation, key)
    body = _detail_text(detail)
    return body or f"{label}について、提出された対話ログと成果物から確認できる内容を整理しました。"


def _canonical_evaluation_result(
    evaluation: dict[str, Any], output_text: str, artifact_name: str
) -> dict[str, Any]:
    """Adapt the completed Zenn result into the public canonical fact schema.

    This adapter consumes the existing evaluation and extracted actions only.
    It deliberately excludes conversation, artifact, and raw evidence text.
    """
    dimensions = evaluation.get("dimensions") or {}
    actions = evaluation.get("actions") or []
    if not isinstance(actions, list):
        actions = []

    def record(action: dict[str, Any]) -> dict[str, Any]:
        evidence = _text(action.get("evidence"), _text(action.get("text")))
        return {
            "option": _text(action.get("target"), evidence[:180]),
            "original_text": evidence[:180],
            "before": _text(action.get("before")),
            "after": _text(action.get("after")),
            "reason": _text(action.get("reason")),
            "accepted": action.get("polarity") == "positive" and action.get("type") == "adoption",
            "rejected": action.get("polarity") == "negative" or action.get("type") == "rejection",
        }

    decisions = [record(a) for a in actions if a.get("type") in {"comparison", "reason", "priority_change", "policy_change"}]
    revisions = [record(a) for a in actions if a.get("type") == "revision"]
    adoptions = [record(a) for a in actions if a.get("type") in {"adoption", "rejection"}]
    structures = [
        record(a) for a in actions
        if any(term in _text(a.get("evidence"), _text(a.get("text"))).lower()
               for term in ("構成", "区分", "導線", "structure", "section", "two-role"))
    ]
    if not structures and any(term in _text(output_text).lower() for term in ("構成", "区分", "導線", "structure", "section", "two-role")):
        structures = [{"option": "two-role structure", "original_text": "", "before": "", "after": "", "reason": "", "accepted": True, "rejected": False}]
    source_text = " ".join(
        _text(a.get("evidence"), _text(a.get("text"))) for a in actions
    ) + " " + _text(output_text)
    domains = {
        "output_structure": any(term in source_text.lower() for term in ("構成", "区分", "導線", "structure", "section")),
        "product_specification": any(term in source_text.lower() for term in ("仕様", "specification")),
        "requirements_and_constraints": any(term in source_text.lower() for term in ("入力", "確認", "状態保持", "requirement", "validation")),
    }
    strong = bool(decisions and revisions and adoptions and structures)
    source_facts = {
        "decisions": decisions,
        "revisions": revisions,
        "adoptions": adoptions,
        "structure_decisions": structures,
        "output_relationship": [{"confirmed": True}] if output_text.strip() else [],
        "applicable_domains": domains,
    }
    return {
        "schema_version": 1,
        "logic_version": "zenn-canonical-adapter-v1",
        "doc_id": _text(evaluation.get("report_id")),
        "input_digest": "",
        "source": {"mode": "live_analysis", "object": "evaluation_result", "path": "evaluation"},
        "scores": {
            "total_score": int(evaluation.get("overall_score", 0) or 0),
            "dimension_scores": {key: int(dimensions.get(key, 0) or 0) for key in (
                "output_logic", "decision_process", "iteration_process", "human_ownership", "overall_consistency"
            )},
        },
        "counts": {"decisions": len(decisions), "revisions": len(revisions), "adoptions": len(adoptions), "structure_decisions": len(structures)},
        "source_facts": source_facts,
        "axis_sections": {key: {} for key in ("overall", "output_logic", "judgment_process", "iteration_process", "human_ownership", "overall_consistency")},
        "content_plan": {
            "responsibility": {"conclusion_level": "strong" if strong else "limited"},
            "thought_output_relation": {"conclusion_level": "strong" if output_text.strip() and strong else "limited"},
        },
    }


def generate_zenn_japanese_pdf(
    result: dict[str, Any],
    *,
    output_title: str,
    output_text: str,
    artifact_name: str,
    artifact_text: str,
) -> bytes:
    """Render the already completed result; this function never evaluates again."""
    evaluation = result.get("evaluation") or {}
    if not isinstance(evaluation, dict):
        raise ValueError("evaluation result is required")
    # The public app allocates the document id when the completed analysis is
    # stored, immediately before export.  Use that same production format;
    # the local evaluator id is not a PDF metadata id.
    now = datetime.now()
    report_id = now.strftime("%Y%m%d%H%M%S")
    user_name = _text(result.get("name"), _text(result.get("user_name")))
    dimensions = evaluation.get("dimensions") or {}
    public_scores = {
        "成果物論理性": int(dimensions.get("output_logic", 0) or 0),
        "判断プロセス": int(dimensions.get("decision_process", 0) or 0),
        "修正プロセス": int(dimensions.get("iteration_process", 0) or 0),
        "判断主体性": int(dimensions.get("human_ownership", 0) or 0),
        "全体整合性": int(dimensions.get("overall_consistency", 0) or 0),
    }
    analysis_data = {
        "total_score": evaluation.get("overall_score", 0),
        "scores": public_scores,
        "report_id": report_id,
        "output_title": output_title,
        "target_work_name": output_title,
        "generated_date": now.strftime("%Y-%m-%d"),
        "pdf_name": user_name,
        "name": user_name,
        "user_name": user_name,
        "output_text": output_text,
    }
    # The completed evaluation is adapted into canonical facts; evaluation is
    # never rerun and raw artifact/log/evidence text is not copied to payload.
    canonical_result = _canonical_evaluation_result(evaluation, output_text, artifact_name)
    report_data: dict[str, Any] = {}
    public_pdf_generator = _load_public_pdf_generator()
    payload = public_pdf_generator.build_report_payload(
        deepcopy(analysis_data), report_data, report_id, ""
    )
    canonical_payload = {key: _text(payload.get(key)) for key in CANONICAL_PAYLOAD_KEYS}
    canonical_payload.update({
        "target_name": user_name,
        "target_work": output_title,
        "doc_id": report_id,
        "meta_info": now.strftime("%Y.%m.%d"),
    })
    # Match the published app: canonical prose is generated once from facts
    # and then overlays the shared report payload before rendering.
    canonical_payload.update(build_evidence_bound_prose(canonical_result, language="ja"))
    missing = [
        key for key, value in canonical_payload.items()
        if not value and key != "applicable_business_list"
    ]
    if missing:
        raise RuntimeError("日本語canonical PDF payloadが不完全です: " + ", ".join(missing))
    qr_secret = str(os.getenv("AI_USAGE_SKILL_VISUALIZER_QR_HMAC_SECRET", "") or "").strip()
    if not qr_secret:
        raise RuntimeError("QR signing is not configured.")
    return generate_report_ja_from_canonical_payload(
        analysis_data=analysis_data,
        japanese_payload=canonical_payload,
        include_qr=True,
        qr_signing_secret=qr_secret,
    )
