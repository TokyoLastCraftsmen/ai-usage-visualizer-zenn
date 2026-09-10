import hashlib
import base64
import io
import json
import logging
import os
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

LOGGER = logging.getLogger(__name__)

try:
    import numpy as np
except Exception:
    np = None

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None


STEP_PATTERN = re.compile(r"【\s*Step\s*(\d+)\s*】", re.IGNORECASE)
LOG_BLOCK_PATTERN = re.compile(r"^\[LOG_(\d+)\]\s*$", re.IGNORECASE | re.MULTILINE)
CHATGPT_ROLE_PATTERN = re.compile(
    r"^\s*---\s*(?:(\d+)\.\s*)?(USER|ASSISTANT)\s*---\s*$",
    re.IGNORECASE | re.MULTILINE,
)

SECTION_KEYS = {
    "判断": ["判断", "Decision"],
    "修正": ["修正", "Revision"],
    "採否": ["採否", "採用", "不採用", "採用傾向", "不採用傾向", "Selection"],
    "理由": ["理由", "Reason"],
}

ENGLISH_SECTION_LABELS = {"decision", "revision", "selection", "reason"}

STRUCTURE_KEYWORDS = [
    "構造", "構成", "順番", "並び", "配置",
    "導線", "UI", "設計", "見出し", "分類",
    "ラベル", "用語", "CTA", "HERO",
    "structure", "section", "headline", "heading", "paragraph",
    "button", "call-to-action", "call to action", "layout", "order",
    "line above", "hero section", "wording",
]



EDGE_CANDIDATES = [
    Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
    Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe"),
]

LP_CTA_KEYWORDS = [
    "cta", "今すぐ", "申し込み", "申込", "無料", "診断",
    "相談", "問い合わせ", "資料請求", "始める", "確認する", "登録",
]
LP_PRICE_KEYWORDS = [
    "円", "¥", "税込", "税抜", "月額", "年額", "価格", "料金", "プラン", "無料",
]
LP_TRUST_KEYWORDS = [
    "実績", "導入", "お客様", "運営", "会社", "保証",
    "利用規約", "プライバシー", "返金", "メディア掲載", "監修", "レビュー",
]
LP_FAQ_KEYWORDS = ["faq", "よくある質問", "q&a", "質問"]
LP_COMPARE_KEYWORDS = ["比較", "他社", "違い", "vs", "選ばれる理由", "比較表"]
LP_PROBLEM_KEYWORDS = ["課題", "悩み", "不安", "困る", "できない", "失敗"]
LP_SOLUTION_KEYWORDS = ["解決", "改善", "できる", "実現", "提供", "サポート", "最適化"]
LP_HERO_KEYWORDS = ["あなた", "向け", "課題", "解決", "結果", "成果", "今すぐ", "悩み"]
BROWSER_UI_KEYWORDS = [
    "http", "https", "www.", "localhost", "chrome", "edge", "safari",
    "戻る", "進む", "再読み込み", "検索", "タブ",
]
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_VISUAL_MODEL = "gpt-4o-mini"
ARTIFACT_TEXT_LIMIT = 6000
OCR_LOCAL_TIMEOUT_SECONDS = 6
OCR_OPENAI_TIMEOUT_SECONDS = 15
# =========================================================
# main
# =========================================================
def analyze(
    log_text: str,
    artifact_summary_text: str = "",
    artifact_items: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    log_text = _safe_text(log_text)
    artifact_summary_text = _safe_text(artifact_summary_text)
    artifact_items = artifact_items if isinstance(artifact_items, list) else []
    LOGGER.info(
        "ANALYZER_CORE_START log_chars=%s artifact_summary_chars=%s artifact_items=%s",
        len(log_text),
        len(artifact_summary_text),
        len(artifact_items),
    )

    visual_input_mode = _detect_visual_input_mode(artifact_summary_text, artifact_items=artifact_items)
    LOGGER.info(
        "VISUAL_MODE_DETECTED enabled=%s mode=%s image_count=%s",
        bool(visual_input_mode.get("enabled")) if isinstance(visual_input_mode, dict) else False,
        visual_input_mode.get("mode") if isinstance(visual_input_mode, dict) else "",
        visual_input_mode.get("image_count") if isinstance(visual_input_mode, dict) else "",
    )
    visual_lp_analysis = _build_visual_lp_analysis(visual_input_mode, artifact_items)
    LOGGER.info(
        "VISUAL_LAYOUT_ANALYSIS_END enabled=%s status=%s mode=%s ocr_engine=%s ocr_blocks=%s",
        bool(visual_lp_analysis.get("enabled")) if isinstance(visual_lp_analysis, dict) else False,
        visual_lp_analysis.get("status") if isinstance(visual_lp_analysis, dict) else "",
        visual_lp_analysis.get("mode") if isinstance(visual_lp_analysis, dict) else "",
        visual_lp_analysis.get("ocr_engine") if isinstance(visual_lp_analysis, dict) else "",
        visual_lp_analysis.get("ocr_block_count") if isinstance(visual_lp_analysis, dict) else "",
    )
    visual_input_mode = _resolve_visual_mode(visual_input_mode, visual_lp_analysis)
    visual_evaluation = _build_visual_evaluation_from_lp_analysis(visual_lp_analysis, visual_input_mode)
    enriched_output = _build_output_text(
        artifact_summary_text,
        artifact_items=artifact_items,
        visual_input_mode=visual_input_mode,
        visual_lp_analysis=visual_lp_analysis,
    )
    actual_output_text = _extract_manual_output_text(artifact_summary_text)
    artifact_context_text = _extract_artifact_context_text(artifact_summary_text)
    page_output_text = _extract_page_output_text(enriched_output)
    LOGGER.info(
        "ANALYZER_CORE_OUTPUT_READY enriched_chars=%s page_output_chars=%s artifact_context_chars=%s",
        len(enriched_output),
        len(page_output_text),
        len(artifact_context_text),
    )

    structured_steps: List[Dict[str, Any]] = []
    log_blocks = _split_log_blocks(log_text)
    step_counter = 0

    for log_block_id, block_text in log_blocks:
        step_records = _split_step_records(block_text)
        for block_step_index, step_record in enumerate(step_records, start=1):
            step_text = _safe_text(step_record.get("text", ""))
            assistant_context = _safe_text(step_record.get("assistant_context", ""))
            step_counter += 1
            parsed = _parse_step(step_text)
            selected_option = _resolve_selected_option_content(step_text, assistant_context)
            if selected_option and _safe_text(parsed.get("採否", "")):
                parsed["採否"] = f"{parsed['採否']}\nSelected option content: {selected_option}"

            structured_steps.append({
                "step_id": step_counter,
                "log_block_id": log_block_id,
                "log_block_label": f"LOG_{log_block_id}",
                "log_block_step_index": block_step_index,
                "judgment": parsed.get("判断", ""),
                "revision": parsed.get("修正", ""),
                "adoption": parsed.get("採否", ""),
                "reason": parsed.get("理由", ""),
                "raw": step_text,
                "assistant_context": assistant_context,
                "before_after": _extract_before_after(step_text),
            })

    decisions, revisions, adoptions, structure_decisions = _rebuild_collections(structured_steps)
    step_profile = _analyze_step_quality(
        structured_steps=structured_steps,
        decisions=decisions,
        revisions=revisions,
        adoptions=adoptions,
        structure_decisions=structure_decisions,
    )
    log_source_profile = _analyze_log_source_profile(structured_steps, log_text)

    result = {
        "log_text": log_text,
        "artifact_summary_text": artifact_summary_text,
        "output_text": enriched_output,
        "actual_output_text": actual_output_text,
        "artifact_context_text": artifact_context_text,
        "page_output_text": page_output_text,
        "visual_input_mode": visual_input_mode,
        "visual_lp_analysis": visual_lp_analysis,
        "visual_evaluation": visual_evaluation,
        "log_blocks": [{"log_block_id": block_id, "text": block_text} for block_id, block_text in log_blocks],
        "structured_steps": structured_steps,
        "decisions": decisions,
        "revisions": revisions,
        "adoptions": adoptions,
        "structure_decisions": structure_decisions,
        "step_profile": step_profile,
        "log_source_profile": log_source_profile,
    }
    LOGGER.info("ANALYZER_CORE_END decisions=%s revisions=%s adoptions=%s", len(decisions), len(revisions), len(adoptions))
    return result


# =========================================================
# 成果物解析
# =========================================================
def _build_output_text(
    text: str,
    artifact_items: List[Dict[str, Any]] | None = None,
    visual_input_mode: Dict[str, Any] | None = None,
    visual_lp_analysis: Dict[str, Any] | None = None,
) -> str:
    text = _safe_text(text)
    artifact_items = artifact_items if isinstance(artifact_items, list) else []
    visual_input_mode = visual_input_mode if isinstance(visual_input_mode, dict) else {}
    visual_lp_analysis = visual_lp_analysis if isinstance(visual_lp_analysis, dict) else {}

    urls = _extract_urls(text)
    blocks: List[str] = []

    if text:
        blocks.append(text)

    artifact_set_text = _build_artifact_set_context(text, artifact_items)
    if artifact_set_text:
        blocks.append(artifact_set_text)

    fetched_any = False

    for url in urls[:3]:
        page_block = _fetch_url_summary(url)
        if page_block and "URL_FETCH_FAILED:" not in page_block:
            fetched_any = True
            blocks.append(page_block)
        elif page_block:
            blocks.append(page_block)

    if urls and not fetched_any:
        for url in urls[:3]:
            failed_marker = f"URL_FETCH_FAILED: {url}"
            if failed_marker not in blocks:
                blocks.append(failed_marker)

    if visual_input_mode.get("enabled"):
        image_count = int(visual_input_mode.get("image_count", 0))
        file_names = visual_input_mode.get("image_files", []) or []
        visual_mode_label = _safe_text(visual_input_mode.get("mode", "")) or "lp_ui_screenshot"
        mode_lines = [
            f"VISUAL_MODE: {visual_mode_label}",
            f"SCREENSHOT_COUNT: {image_count}",
            "SCREENSHOT_ROLE: primary_artifact_body",
            "SCREENSHOT_SEQUENCE: unordered_artifact_set",
            "LP_UI_VIEWPOINTS: hero_appeal / cta_layout / information_flow / trust_elements / visual_unity / whitespace_balance",
        ]
        if file_names:
            mode_lines.append(f"SCREENSHOT_FILES: {' / '.join(file_names)}")
            mode_lines.append(f"SCREENSHOT_FILES_TOTAL: {len(file_names)}")
        mode_lines.extend(_format_visual_lp_analysis_lines(visual_lp_analysis))
        blocks.append("\n".join(mode_lines))

    return "\n\n".join([b for b in blocks if _safe_text(b)]).strip()


def _extract_artifact_file_names(text: str) -> List[str]:
    file_names: List[str] = []
    for row in _safe_text(text).splitlines():
        stripped = _safe_text(row)
        if not stripped.startswith("-"):
            continue
        name = stripped[1:].strip()
        if name and name not in file_names:
            file_names.append(name)
    return file_names


def _build_artifact_set_context(
    artifact_summary_text: str,
    artifact_items: List[Dict[str, Any]],
) -> str:
    artifact_items = artifact_items if isinstance(artifact_items, list) else []
    urls = _extract_urls(artifact_summary_text)
    manual_text = _extract_manual_output_text(_safe_text(artifact_summary_text))
    file_items = [item for item in artifact_items if isinstance(item, dict)]
    if not (urls or manual_text or file_items):
        return ""

    sorted_items = sorted(
        file_items,
        key=lambda item: (
            _artifact_kind(_safe_text(item.get("name", "")), _safe_text(item.get("type", ""))),
            _safe_text(item.get("name", "")).lower(),
        ),
    )
    type_counts: Dict[str, int] = {}
    image_names: List[str] = []
    extracted_blocks: List[str] = []
    embedded_media_count = 0

    for item in sorted_items:
        name = _safe_text(item.get("name", ""))
        mime_type = _safe_text(item.get("type", ""))
        kind = _artifact_kind(name, mime_type)
        type_counts[kind] = type_counts.get(kind, 0) + 1
        raw_bytes = item.get("bytes", b"")
        if kind == "image":
            if name:
                image_names.append(name)
            continue
        if isinstance(raw_bytes, (bytes, bytearray)) and raw_bytes:
            embedded_media_count += _count_embedded_media(bytes(raw_bytes), name)
            extracted = _extract_text_from_artifact_bytes(bytes(raw_bytes), name, mime_type)
            if extracted:
                label = name or kind
                extracted_blocks.append(f"ARTIFACT_TEXT[{label}]: {extracted[:ARTIFACT_TEXT_LIMIT]}")

    source_types: List[str] = []
    if urls:
        source_types.append("url")
    if manual_text:
        source_types.append("manual_text")
    source_types.extend([kind for kind in sorted(type_counts.keys()) if kind not in source_types])

    lines = [
        "ARTIFACT_SET_MODE: integrated_output_set",
        "ARTIFACT_SET_ROLE: single_evaluation_artifact",
        f"ARTIFACT_SET_ITEM_COUNT: {int(bool(urls)) + int(bool(manual_text)) + len(file_items)}",
        f"ARTIFACT_SET_TYPES: {' / '.join(source_types) if source_types else 'none'}",
    ]
    if type_counts:
        lines.append(
            "ARTIFACT_FILE_COUNTS: "
            + " / ".join(f"{kind}={count}" for kind, count in sorted(type_counts.items()))
        )
    if image_names:
        lines.append("ARTIFACT_IMAGE_ROLE: primary_artifact_body")
        lines.append(f"ARTIFACT_IMAGE_COUNT: {len(image_names)}")
        lines.append(f"ARTIFACT_IMAGE_FILES: {' / '.join(image_names)}")
    if embedded_media_count:
        lines.append(f"ARTIFACT_EMBEDDED_MEDIA_COUNT: {embedded_media_count}")
    if extracted_blocks:
        lines.append("ARTIFACT_TEXT_EXTRACTION_READY: yes")
        lines.extend(extracted_blocks[:8])
    elif file_items:
        lines.append("ARTIFACT_TEXT_EXTRACTION_READY: partial")

    return "\n".join(lines).strip()


def _artifact_kind(name: str, mime_type: str = "") -> str:
    candidate = _safe_text(name).lower()
    mime = _safe_text(mime_type).lower()
    if _is_image_like_name(candidate) or mime.startswith("image/"):
        return "image"
    if candidate.endswith(".pdf") or "pdf" in mime:
        return "pdf"
    if candidate.endswith(".docx") or "word" in mime:
        return "word"
    if candidate.endswith(".xlsx") or "spreadsheet" in mime or "excel" in mime:
        return "excel"
    if candidate.endswith(".pptx") or "presentation" in mime or "powerpoint" in mime:
        return "powerpoint"
    return "file"


def _extract_text_from_artifact_bytes(raw_bytes: bytes, name: str, mime_type: str = "") -> str:
    kind = _artifact_kind(name, mime_type)
    try:
        if kind == "pdf":
            return _extract_pdf_text(raw_bytes)
        if kind == "word":
            return _extract_docx_text(raw_bytes)
        if kind == "excel":
            return _extract_xlsx_text(raw_bytes)
        if kind == "powerpoint":
            return _extract_pptx_text(raw_bytes)
    except Exception:
        return ""
    return ""


def _extract_pdf_text(raw_bytes: bytes) -> str:
    for module_name in ("PyPDF2", "pypdf"):
        try:
            module = __import__(module_name)
            reader = module.PdfReader(io.BytesIO(raw_bytes))
            pages = []
            for page in getattr(reader, "pages", [])[:8]:
                pages.append(_normalize_space(page.extract_text() or ""))
            return _normalize_space(" ".join(pages))
        except Exception:
            continue
    return ""


def _extract_docx_text(raw_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = [
            name for name in zf.namelist()
            if name.startswith("word/") and name.endswith(".xml") and (
                name == "word/document.xml" or name.startswith("word/header") or name.startswith("word/footer")
            )
        ]
        return _extract_text_from_xml_files(zf, sorted(names))


def _extract_pptx_text(raw_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        names = [
            name for name in zf.namelist()
            if name.startswith("ppt/slides/slide") and name.endswith(".xml")
        ]
        return _extract_text_from_xml_files(zf, sorted(names, key=_natural_key))


def _extract_xlsx_text(raw_bytes: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
        shared_strings = _extract_xlsx_shared_strings(zf)
        names = [
            name for name in zf.namelist()
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        ]
        values: List[str] = []
        for name in sorted(names, key=_natural_key)[:10]:
            try:
                root = ET.fromstring(zf.read(name))
            except Exception:
                continue
            for cell in root.iter():
                if not cell.tag.endswith("c"):
                    continue
                cell_type = cell.attrib.get("t", "")
                value = ""
                for child in cell:
                    if child.tag.endswith("v") and child.text:
                        value = child.text
                        break
                    if child.tag.endswith("is"):
                        value = " ".join(t.text or "" for t in child.iter() if t.tag.endswith("t"))
                        break
                if not value:
                    continue
                if cell_type == "s":
                    try:
                        value = shared_strings[int(value)]
                    except Exception:
                        pass
                values.append(_normalize_space(value))
                if len(values) >= 400:
                    break
        return _normalize_space(" ".join(v for v in values if v))


def _extract_xlsx_shared_strings(zf: zipfile.ZipFile) -> List[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except Exception:
        return []
    result: List[str] = []
    for item in root.iter():
        if not item.tag.endswith("si"):
            continue
        result.append(_normalize_space(" ".join(t.text or "" for t in item.iter() if t.tag.endswith("t"))))
    return result


def _extract_text_from_xml_files(zf: zipfile.ZipFile, names: List[str]) -> str:
    values: List[str] = []
    for name in names[:20]:
        try:
            root = ET.fromstring(zf.read(name))
        except Exception:
            continue
        for node in root.iter():
            if node.tag.endswith("t") and node.text:
                values.append(_normalize_space(node.text))
                if len(values) >= 600:
                    break
    return _normalize_space(" ".join(value for value in values if value))


def _count_embedded_media(raw_bytes: bytes, name: str) -> int:
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            lower_name = _safe_text(name).lower()
            if lower_name.endswith(".docx"):
                prefix = "word/media/"
            elif lower_name.endswith(".xlsx"):
                prefix = "xl/media/"
            elif lower_name.endswith(".pptx"):
                prefix = "ppt/media/"
            else:
                prefix = ""
            if not prefix:
                return 0
            return sum(1 for entry in zf.namelist() if entry.startswith(prefix))
    except Exception:
        return 0


def _natural_key(value: str) -> List[Any]:
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", _safe_text(value))]


def _detect_visual_input_mode(
    artifact_summary_text: str,
    artifact_items: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    file_names = _extract_artifact_file_names(artifact_summary_text)
    image_files = [
        name for name in file_names
        if re.search(r"\.(png|jpg|jpeg|webp|bmp|gif)$", name, re.IGNORECASE) or "スクショ" in name
    ]

    artifact_items = artifact_items if isinstance(artifact_items, list) else []
    artifact_image_files: List[str] = []
    for item in artifact_items:
        if not isinstance(item, dict):
            continue
        name = _safe_text(item.get("name", ""))
        mime_type = _safe_text(item.get("type", "")).lower()
        if _is_image_like_name(name) or mime_type.startswith("image/"):
            if name and name not in artifact_image_files:
                artifact_image_files.append(name)

    merged_image_files = _dedupe_keep_order(image_files + artifact_image_files)

    explicit_count = 0
    match = re.search(r"追加ファイル数\s*:\s*(\d+)", _safe_text(artifact_summary_text))
    if match:
        explicit_count = int(match.group(1))

    visible_image_count = len(merged_image_files)
    image_count = max(visible_image_count, explicit_count if visible_image_count else 0)
    enabled = image_count >= 1

    return {
        "enabled": enabled,
        "mode": "artifact_image_set" if enabled else "default",
        "image_count": image_count,
        "sequence_assumption": "unordered_artifact_set" if enabled else "",
        "image_files": merged_image_files,
    }


def _resolve_visual_mode(
    visual_input_mode: Dict[str, Any],
    visual_lp_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    mode = dict(visual_input_mode if isinstance(visual_input_mode, dict) else {})
    if not mode.get("enabled"):
        mode["mode"] = "default"
        return mode

    analysis = visual_lp_analysis if isinstance(visual_lp_analysis, dict) else {}
    resolved_mode = _safe_text(analysis.get("mode", ""))
    if resolved_mode in {"web_lp_screenshot", "lp_ui_screenshot", "artifact_image_set"}:
        mode["mode"] = resolved_mode
    elif not _safe_text(mode.get("mode", "")):
        mode["mode"] = "artifact_image_set"
    return mode


def _is_image_like_name(name: str) -> bool:
    candidate = _safe_text(name)
    if not candidate:
        return False
    return bool(re.search(r"\.(png|jpg|jpeg|webp|bmp|gif)$", candidate, re.IGNORECASE) or "スクショ" in candidate)


def _extract_visual_image_items(artifact_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for idx, item in enumerate(artifact_items):
        if not isinstance(item, dict):
            continue
        name = _safe_text(item.get("name", ""))
        mime_type = _safe_text(item.get("type", "")).lower()
        raw_bytes = item.get("bytes", b"")
        if not (isinstance(raw_bytes, (bytes, bytearray)) and raw_bytes):
            continue
        if not (_is_image_like_name(name) or mime_type.startswith("image/")):
            continue
        items.append({
            "name": name or f"screenshot_{idx + 1}.png",
            "bytes": bytes(raw_bytes),
            "type": mime_type,
        })
    return sorted(items, key=lambda item: _safe_text(item.get("name", "")).lower())


def _open_image_from_bytes(raw_bytes: bytes) -> Any:
    if Image is None or not raw_bytes:
        return None
    try:
        with Image.open(io.BytesIO(raw_bytes)) as src:
            rgb = src.convert("RGB")
    except Exception:
        return None

    if rgb.width > 1080:
        ratio = 1080.0 / float(rgb.width)
        rgb = rgb.resize((1080, max(1, int(rgb.height * ratio))))
    return rgb


def _resolve_ocr_engine() -> str:
    try:
        import pytesseract  # type: ignore
        tesseract_cmd = getattr(getattr(pytesseract, "pytesseract", None), "tesseract_cmd", "tesseract")
        subprocess.run(
            [tesseract_cmd, "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
        )
        return "local_tesseract"
    except Exception:
        pass

    if _safe_text(os.getenv("OPENAI_API_KEY", "")):
        return "openai_vision"
    return "none"


def _extract_text_blocks_for_image(
    image: Any,
    image_bytes: bytes,
    ocr_engine_hint: str,
) -> Tuple[List[Dict[str, Any]], str]:
    LOGGER.info("OCR_START engine_hint=%s image_bytes=%s", ocr_engine_hint, len(image_bytes or b""))
    if ocr_engine_hint == "local_tesseract":
        local = _local_ocr_text_blocks(image)
        if local:
            LOGGER.info("OCR_END engine=local_tesseract blocks=%s", len(local))
            return local, "local_tesseract"

    if ocr_engine_hint in {"openai_vision", "local_tesseract"}:
        cloud = _openai_ocr_text_blocks(image_bytes)
        if cloud:
            LOGGER.info("OCR_END engine=openai_vision blocks=%s", len(cloud))
            return cloud, "openai_vision"

    LOGGER.info("OCR_END engine=none blocks=0")
    return [], "none"


def _local_ocr_text_blocks(image: Any) -> List[Dict[str, Any]]:
    try:
        import pytesseract  # type: ignore
    except Exception:
        return []

    result: List[Dict[str, Any]] = []
    for lang in ("jpn+eng", "eng"):
        try:
            LOGGER.info("OCR_LOCAL_ATTEMPT_START lang=%s timeout=%s", lang, OCR_LOCAL_TIMEOUT_SECONDS)
            data = pytesseract.image_to_data(
                image,
                output_type=pytesseract.Output.DICT,
                lang=lang,
                timeout=OCR_LOCAL_TIMEOUT_SECONDS,
            )
            LOGGER.info("OCR_LOCAL_ATTEMPT_END lang=%s", lang)
        except Exception:
            LOGGER.exception("OCR_LOCAL_ATTEMPT_EXCEPTION lang=%s", lang)
            continue

        texts = data.get("text", []) if isinstance(data, dict) else []
        lefts = data.get("left", []) if isinstance(data, dict) else []
        tops = data.get("top", []) if isinstance(data, dict) else []
        widths = data.get("width", []) if isinstance(data, dict) else []
        heights = data.get("height", []) if isinstance(data, dict) else []
        confs = data.get("conf", []) if isinstance(data, dict) else []

        for idx in range(min(len(texts), len(lefts), len(tops), len(widths), len(heights))):
            text = _normalize_space(texts[idx])
            if len(text) < 2:
                continue
            conf = _safe_float(confs[idx] if idx < len(confs) else 0.0)
            if conf < 25:
                continue

            result.append({
                "text": text,
                "x": _safe_float(lefts[idx]),
                "y": _safe_float(tops[idx]),
                "w": _safe_float(widths[idx]),
                "h": _safe_float(heights[idx]),
                "confidence": _clamp(conf / 100.0),
            })

        if result:
            break

    return result


def _image_bytes_to_data_url(image_bytes: bytes) -> str:
    if not image_bytes:
        return ""

    try:
        if Image is not None:
            with Image.open(io.BytesIO(image_bytes)) as img:
                rgb = img.convert("RGB")
                buffer = io.BytesIO()
                rgb.save(buffer, format="PNG", optimize=True)
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                return f"data:image/png;base64,{encoded}"
    except Exception:
        pass

    encoded_raw = base64.b64encode(image_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded_raw}"


def _openai_ocr_text_blocks(image_bytes: bytes) -> List[Dict[str, Any]]:
    api_key = _safe_text(os.getenv("OPENAI_API_KEY", ""))
    if not api_key:
        return []

    data_url = _image_bytes_to_data_url(image_bytes)
    if not data_url:
        return []

    payload = {
        "model": _safe_text(os.getenv("OPENAI_VISUAL_MODEL", DEFAULT_VISUAL_MODEL)) or DEFAULT_VISUAL_MODEL,
        "input": [
            {
                "role": "system",
                "content": [{
                    "type": "input_text",
                    "text": "LPスクリーンショットのOCR抽出器です。JSONのみを返してください。",
                }],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "画像内の可読テキストを抽出し、各テキストの位置を返してください。"
                            "x,y,w,h は 0.0-1.0 の相対座標で、最大80件まで返してください。"
                        ),
                    },
                    {
                        "type": "input_image",
                        "image_url": data_url,
                    },
                ],
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "screenshot_ocr_blocks",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "blocks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "text": {"type": "string"},
                                    "x": {"type": "number"},
                                    "y": {"type": "number"},
                                    "w": {"type": "number"},
                                    "h": {"type": "number"},
                                    "confidence": {"type": "number"},
                                },
                                "required": ["text", "x", "y", "w", "h", "confidence"],
                            },
                        }
                    },
                    "required": ["blocks"],
                },
            }
        },
    }

    try:
        LOGGER.info("OCR_OPENAI_REQUEST_START timeout=%s image_bytes=%s", OCR_OPENAI_TIMEOUT_SECONDS, len(image_bytes or b""))
        response = requests.post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=OCR_OPENAI_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
    except Exception:
        LOGGER.exception("OCR_OPENAI_REQUEST_EXCEPTION")
        return []

    raw = _extract_openai_output_text(body)
    if not raw:
        LOGGER.info("OCR_OPENAI_NO_OUTPUT_TEXT")
        return []

    try:
        parsed = json.loads(raw)
    except Exception:
        LOGGER.exception("OCR_OPENAI_PARSE_EXCEPTION")
        return []

    blocks = parsed.get("blocks", []) if isinstance(parsed, dict) else []
    result: List[Dict[str, Any]] = []
    for item in blocks[:80]:
        if not isinstance(item, dict):
            continue
        text = _normalize_space(item.get("text", ""))
        if len(text) < 2:
            continue
        result.append({
            "text": text,
            "x": _clamp(_safe_float(item.get("x", 0.0))),
            "y": _clamp(_safe_float(item.get("y", 0.0))),
            "w": _clamp(_safe_float(item.get("w", 0.0))),
            "h": _clamp(_safe_float(item.get("h", 0.0))),
            "confidence": _clamp(_safe_float(item.get("confidence", 0.5))),
        })
    LOGGER.info("OCR_OPENAI_PARSE_END blocks=%s", len(result))
    return result


def _extract_openai_output_text(response_body: Dict[str, Any]) -> str:
    output_text = response_body.get("output_text") if isinstance(response_body, dict) else ""
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    output = response_body.get("output", []) if isinstance(response_body, dict) else []
    if isinstance(output, list):
        for item in output:
            content = item.get("content", []) if isinstance(item, dict) else []
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                text_value = part.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    return text_value.strip()
    return ""


def _measure_image_layout(image: Any) -> Tuple[float, float, int]:
    gray = image.convert("L")

    if np is not None:
        arr = np.asarray(gray, dtype=np.float32) / 255.0
        whitespace = float((arr >= 0.94).mean())
        dark_ratio = float((arr <= 0.82).mean())
        section_breaks = _estimate_section_breaks_from_array(arr)
        return _clamp(whitespace), _clamp(dark_ratio), int(section_breaks)

    data = list(gray.getdata())
    if not data:
        return 0.0, 0.0, 0

    count = float(len(data))
    whitespace = sum(1 for px in data if px >= 240) / count
    dark_ratio = sum(1 for px in data if px <= 210) / count
    return _clamp(whitespace), _clamp(dark_ratio), 0


def _estimate_section_breaks_from_array(gray_array: Any) -> int:
    if np is None:
        return 0
    if gray_array is None or getattr(gray_array, "ndim", 0) != 2:
        return 0

    row_ink = (gray_array < 0.88).mean(axis=1)
    gap_rows = row_ink < 0.025
    min_gap = max(12, int(gray_array.shape[0] * 0.012))

    breaks = 0
    run = 0
    for is_gap in gap_rows.tolist():
        if is_gap:
            run += 1
        else:
            if run >= min_gap:
                breaks += 1
            run = 0

    if run >= min_gap:
        breaks += 1
    return max(0, breaks - 1)


def _measure_visual_regions(image: Any) -> Dict[str, float]:
    if np is None:
        return {
            "top_ink": 0.0,
            "middle_ink": 0.0,
            "bottom_ink": 0.0,
            "middle_saturation": 0.0,
            "bottom_saturation": 0.0,
        }

    arr = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
    h = arr.shape[0]
    if h <= 0:
        return {
            "top_ink": 0.0,
            "middle_ink": 0.0,
            "bottom_ink": 0.0,
            "middle_saturation": 0.0,
            "bottom_saturation": 0.0,
        }

    top = arr[: max(1, int(h * 0.35)), :, :]
    middle = arr[max(1, int(h * 0.35)): max(2, int(h * 0.70)), :, :]
    bottom = arr[max(1, int(h * 0.70)):, :, :]

    def _ink(region: Any) -> float:
        if region.size == 0:
            return 0.0
        gray = region.mean(axis=2)
        return float((gray <= 0.82).mean())

    def _sat(region: Any) -> float:
        if region.size == 0:
            return 0.0
        sat = region.max(axis=2) - region.min(axis=2)
        return float((sat >= 0.35).mean())

    return {
        "top_ink": _ink(top),
        "middle_ink": _ink(middle),
        "bottom_ink": _ink(bottom),
        "middle_saturation": _sat(middle),
        "bottom_saturation": _sat(bottom),
    }


def _contains_keyword(text_lower: str, keywords: List[str]) -> bool:
    for keyword in keywords:
        candidate = _safe_text(keyword).lower()
        if candidate and candidate in text_lower:
            return True
    return False


def _visual_band_label(y_value: float) -> str:
    if y_value < 0.34:
        return "top"
    if y_value < 0.70:
        return "middle"
    return "bottom"


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def _clamp(value: Any, lower: float = 0.0, upper: float = 1.0) -> float:
    v = _safe_float(value)
    if v < lower:
        return lower
    if v > upper:
        return upper
    return v


def _mean(values: List[Any]) -> float:
    valid = [_safe_float(v) for v in values]
    if not valid:
        return 0.0
    return sum(valid) / max(1, len(valid))


def _analyze_single_lp_screenshot(
    entry: Dict[str, Any],
    index: int,
    y_offset: float,
    total_height: float,
    ocr_engine_hint: str,
) -> Dict[str, Any]:
    image = entry.get("image")
    if image is None:
        return {
            "ocr_engine": "none",
            "ocr_block_count": 0,
            "whitespace_ratio": 0.0,
            "text_density": 0.0,
            "section_break_count": 0,
            "avg_text_length": 0.0,
            "top_heading_count": 0,
            "top_hero_hit": 0,
            "headings": [],
            "cta_texts": [],
            "trust_texts": [],
            "price_texts": [],
            "faq_texts": [],
            "compare_texts": [],
            "cta_positions": [],
            "stage_points": [],
            "browser_ui_text_hit": 0,
            "browser_ui_bar_signal": 0.0,
            "portrait_ratio": 0.0,
        }

    width = max(1, int(entry.get("width", 1)))
    height = max(1, int(entry.get("height", 1)))
    image_bytes = entry.get("item", {}).get("bytes", b"")

    whitespace_ratio, dark_ratio, section_break_count = _measure_image_layout(image)
    region_signals = _measure_visual_regions(image)

    ocr_image = image
    if ImageOps is not None:
        try:
            ocr_image = ImageOps.autocontrast(image.convert("L")).convert("RGB")
        except Exception:
            ocr_image = image

    text_blocks, used_engine = _extract_text_blocks_for_image(
        image=ocr_image,
        image_bytes=image_bytes,
        ocr_engine_hint=ocr_engine_hint,
    )

    headings: List[str] = []
    cta_texts: List[str] = []
    trust_texts: List[str] = []
    price_texts: List[str] = []
    faq_texts: List[str] = []
    compare_texts: List[str] = []
    cta_positions: List[str] = []
    stage_points: List[Tuple[str, float]] = []
    text_lengths: List[int] = []

    ocr_area = 0.0
    top_heading_count = 0
    top_hero_hit = 0
    browser_ui_text_hit = 0

    for block in text_blocks:
        text = _normalize_space(block.get("text", ""))
        if not text:
            continue

        x = _safe_float(block.get("x", 0.0))
        y = _safe_float(block.get("y", 0.0))
        w = _safe_float(block.get("w", 0.0))
        h = _safe_float(block.get("h", 0.0))

        if max(x, y, w, h) <= 1.2:
            x *= width
            y *= height
            w *= width
            h *= height

        if w <= 0 or h <= 0:
            continue

        text_lengths.append(len(text))
        ocr_area += max(0.0, w) * max(0.0, h)

        y_center_local = _clamp((y + h * 0.5) / max(1.0, float(height)))
        y_center_global = _clamp((y_offset + y + h * 0.5) / max(1.0, total_height))

        lower = text.lower()
        heading_like = len(text) >= 4 and (h / max(1.0, float(height)) >= 0.032 or len(text) <= 28)

        if heading_like and y_center_local <= 0.38:
            top_heading_count += 1
            headings.append(text)
            if index == 0:
                stage_points.append(("hero", y_center_global))

        if index == 0 and y_center_local <= 0.38 and _contains_keyword(lower, LP_HERO_KEYWORDS):
            top_hero_hit += 1
            stage_points.append(("hero", y_center_global))

        if index == 0 and y_center_local <= 0.14 and _contains_keyword(lower, BROWSER_UI_KEYWORDS):
            browser_ui_text_hit += 1

        if _contains_keyword(lower, LP_CTA_KEYWORDS):
            cta_texts.append(text)
            cta_positions.append(_visual_band_label(y_center_global))
            stage_points.append(("cta", y_center_global))

        if _contains_keyword(lower, LP_TRUST_KEYWORDS):
            trust_texts.append(text)
            stage_points.append(("trust", y_center_global))

        if _contains_keyword(lower, LP_PRICE_KEYWORDS):
            price_texts.append(text)

        if _contains_keyword(lower, LP_FAQ_KEYWORDS):
            faq_texts.append(text)

        if _contains_keyword(lower, LP_COMPARE_KEYWORDS):
            compare_texts.append(text)

        if _contains_keyword(lower, LP_PROBLEM_KEYWORDS):
            stage_points.append(("problem", y_center_global))

        if _contains_keyword(lower, LP_SOLUTION_KEYWORDS):
            stage_points.append(("solution", y_center_global))

    if not text_blocks:
        if region_signals.get("top_ink", 0.0) >= 0.012:
            top_heading_count = max(top_heading_count, 1)
            top_hero_hit = max(top_hero_hit, 1)
            if index == 0:
                stage_points.append(("hero", _clamp((y_offset + height * 0.16) / max(1.0, total_height))))
        if region_signals.get("middle_saturation", 0.0) >= 0.012:
            cta_positions.append("middle")
        if region_signals.get("bottom_saturation", 0.0) >= 0.014 or region_signals.get("bottom_ink", 0.0) >= 0.050:
            cta_positions.append("bottom")
            stage_points.append(("cta", _clamp((y_offset + height * 0.84) / max(1.0, total_height))))
        if section_break_count >= 2:
            stage_points.append(("solution", _clamp((y_offset + height * 0.50) / max(1.0, total_height))))
            stage_points.append(("trust", _clamp((y_offset + height * 0.70) / max(1.0, total_height))))
        used_engine = "layout_only"

    image_area = float(width * height)
    ocr_area_ratio = _clamp(ocr_area / image_area) if image_area > 0 else 0.0
    text_density = _clamp(dark_ratio * 0.55 + ocr_area_ratio * 0.45)
    avg_text_length = _mean(text_lengths)

    return {
        "ocr_engine": used_engine,
        "ocr_block_count": len(text_blocks),
        "whitespace_ratio": whitespace_ratio,
        "text_density": text_density,
        "section_break_count": section_break_count,
        "avg_text_length": avg_text_length,
        "top_heading_count": top_heading_count,
        "top_hero_hit": top_hero_hit,
        "headings": _dedupe_keep_order(headings)[:6],
        "cta_texts": _dedupe_keep_order(cta_texts)[:6],
        "trust_texts": _dedupe_keep_order(trust_texts)[:6],
        "price_texts": _dedupe_keep_order(price_texts)[:4],
        "faq_texts": _dedupe_keep_order(faq_texts)[:4],
        "compare_texts": _dedupe_keep_order(compare_texts)[:4],
        "cta_positions": _dedupe_keep_order(cta_positions),
        "stage_points": stage_points,
        "browser_ui_text_hit": browser_ui_text_hit,
        "browser_ui_bar_signal": _clamp(region_signals.get("top_ink", 0.0) / 0.12),
        "portrait_ratio": float(height) / max(1.0, float(width)),
    }


def _build_visual_lp_analysis(
    visual_input_mode: Dict[str, Any],
    artifact_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    LOGGER.info(
        "VISUAL_LAYOUT_START enabled=%s artifact_items=%s",
        bool(visual_input_mode.get("enabled")) if isinstance(visual_input_mode, dict) else False,
        len(artifact_items) if isinstance(artifact_items, list) else 0,
    )
    if not isinstance(visual_input_mode, dict) or not visual_input_mode.get("enabled"):
        LOGGER.info("VISUAL_LAYOUT_SKIPPED reason=visual_mode_disabled")
        return {
            "enabled": False,
            "mode": "default",
            "status": "visual_mode_disabled",
        }

    if Image is None:
        LOGGER.info("VISUAL_LAYOUT_SKIPPED reason=pil_missing")
        return {
            "enabled": False,
            "mode": "artifact_image_set",
            "status": "pil_missing",
            "message": "Pillow が未導入のため画像レイアウト解析を実行できませんでした。",
        }

    image_items = _extract_visual_image_items(artifact_items)
    LOGGER.info("VISUAL_LAYOUT_IMAGES image_items=%s", len(image_items))
    if len(image_items) < 1:
        LOGGER.info("VISUAL_LAYOUT_SKIPPED reason=insufficient_images")
        return {
            "enabled": False,
            "mode": "artifact_image_set",
            "status": "insufficient_images",
            "message": "画像入力を検知しましたが、解析に使える画像データが不足しています。",
        }

    opened: List[Dict[str, Any]] = []
    for item in image_items:
        image = _open_image_from_bytes(item.get("bytes", b""))
        if image is None:
            continue
        opened.append({
            "item": item,
            "image": image,
            "width": int(image.width),
            "height": int(image.height),
        })

    if len(opened) < 1:
        LOGGER.info("VISUAL_LAYOUT_SKIPPED reason=image_decode_failed")
        return {
            "enabled": False,
            "mode": "artifact_image_set",
            "status": "image_decode_failed",
            "message": "画像読み込みに失敗し、成果物画像として解析できませんでした。",
        }

    total_height = sum(max(1, int(entry["height"])) for entry in opened)
    ocr_engine_hint = _resolve_ocr_engine()
    LOGGER.info(
        "VISUAL_LAYOUT_OPENED opened=%s total_height=%s ocr_engine_hint=%s",
        len(opened),
        total_height,
        ocr_engine_hint,
    )

    per_image: List[Dict[str, Any]] = []
    y_offset = 0.0
    for index, entry in enumerate(opened):
        LOGGER.info(
            "VISUAL_LAYOUT_IMAGE_START index=%s width=%s height=%s",
            index,
            entry.get("width"),
            entry.get("height"),
        )
        analyzed = _analyze_single_lp_screenshot(
            entry=entry,
            index=index,
            y_offset=y_offset,
            total_height=float(total_height),
            ocr_engine_hint=ocr_engine_hint,
        )
        per_image.append(analyzed)
        LOGGER.info(
            "VISUAL_LAYOUT_IMAGE_END index=%s ocr_engine=%s ocr_blocks=%s",
            index,
            analyzed.get("ocr_engine"),
            analyzed.get("ocr_block_count"),
        )
        y_offset += float(entry.get("height", 0) or 0)

    headings = _dedupe_keep_order([text for image in per_image for text in image.get("headings", [])])
    cta_texts = _dedupe_keep_order([text for image in per_image for text in image.get("cta_texts", [])])
    trust_texts = _dedupe_keep_order([text for image in per_image for text in image.get("trust_texts", [])])
    price_texts = _dedupe_keep_order([text for image in per_image for text in image.get("price_texts", [])])
    faq_texts = _dedupe_keep_order([text for image in per_image for text in image.get("faq_texts", [])])
    compare_texts = _dedupe_keep_order([text for image in per_image for text in image.get("compare_texts", [])])

    stage_positions: Dict[str, float] = {}
    cta_positions: List[str] = []
    used_engines = _dedupe_keep_order([_safe_text(image.get("ocr_engine", "none")) for image in per_image])

    for image in per_image:
        for label in image.get("cta_positions", []):
            if label:
                cta_positions.append(label)
        for stage, point in image.get("stage_points", []):
            if stage not in stage_positions:
                stage_positions[stage] = float(point)
            else:
                stage_positions[stage] = min(stage_positions[stage], float(point))

    cta_position_labels = _dedupe_keep_order(cta_positions)
    avg_whitespace = _mean([float(image.get("whitespace_ratio", 0.0)) for image in per_image])
    avg_text_density = _mean([float(image.get("text_density", 0.0)) for image in per_image])
    avg_text_length = _mean([float(image.get("avg_text_length", 0.0)) for image in per_image if float(image.get("avg_text_length", 0.0)) > 0])
    section_break_count = int(sum(int(image.get("section_break_count", 0)) for image in per_image))
    avg_portrait_ratio = _mean([float(image.get("portrait_ratio", 0.0)) for image in per_image])
    browser_ui_text_hits = int(sum(int(image.get("browser_ui_text_hit", 0)) for image in per_image[:1]))
    browser_ui_bar_signal = _clamp(_mean([float(image.get("browser_ui_bar_signal", 0.0)) for image in per_image[:1]]))

    first_image = per_image[0] if per_image else {}
    top_heading_score = _clamp(float(first_image.get("top_heading_count", 0)) / 2.0)
    top_hero_score = _clamp(float(first_image.get("top_hero_hit", 0)) / 3.0)
    hero_position_score = 1.0 if stage_positions.get("hero", 1.0) <= 0.30 else (0.40 if "hero" in stage_positions else 0.0)
    hero_score = _clamp(top_heading_score * 0.45 + top_hero_score * 0.30 + hero_position_score * 0.25)

    cta_count_score = _clamp((len(cta_texts) + len(cta_position_labels)) / 3.0)
    cta_top = 1.0 if "top" in cta_position_labels else 0.0
    cta_middle = 1.0 if "middle" in cta_position_labels else 0.0
    cta_bottom = 1.0 if "bottom" in cta_position_labels else 0.0
    cta_position_score = cta_top * 0.20 + cta_middle * 0.35 + cta_bottom * 0.45
    cta_score = _clamp(cta_count_score * 0.55 + cta_position_score * 0.45)

    expected_flow = ["hero", "problem", "solution", "trust", "cta"]
    found_flow = [stage for stage in expected_flow if stage in stage_positions]
    flow_coverage = len(found_flow) / max(1, len(expected_flow))
    if len(found_flow) >= 2:
        ordered_hits = 0
        for left, right in zip(found_flow, found_flow[1:]):
            if stage_positions[left] <= stage_positions[right] + 0.02:
                ordered_hits += 1
        flow_order_score = ordered_hits / max(1, len(found_flow) - 1)
    else:
        flow_order_score = 0.0
    flow_score = _clamp(flow_coverage * 0.55 + flow_order_score * 0.45)

    trust_count_score = _clamp(len(trust_texts) / 3.0)
    trust_position = stage_positions.get("trust")
    trust_position_score = 0.0
    if trust_position is not None:
        trust_position_score = 1.0 if 0.35 <= trust_position <= 0.90 else 0.55
    faq_bonus = 0.15 if faq_texts else 0.0
    trust_score = _clamp(trust_count_score * 0.55 + trust_position_score * 0.30 + faq_bonus)

    whitespace_score = _clamp(1.0 - abs(avg_whitespace - 0.40) / 0.30)
    info_density_score = _clamp(1.0 - abs(avg_text_density - 0.48) / 0.38)

    line_fit_score = 0.60
    if avg_text_length > 0:
        line_fit_score = _clamp(1.0 - _clamp((avg_text_length - 26.0) / 34.0))
    section_score = _clamp(section_break_count / max(3.0, len(per_image) * 3.0))
    mobile_score = _clamp(flow_score * 0.35 + whitespace_score * 0.30 + line_fit_score * 0.20 + section_score * 0.15)

    dropoff_risk = _clamp(
        (1.0 - hero_score) * 0.24
        + (1.0 - flow_score) * 0.30
        + (1.0 - cta_score) * 0.22
        + (1.0 - trust_score) * 0.14
        + (1.0 - mobile_score) * 0.10
    )

    overall = _clamp(
        hero_score * 0.20
        + cta_score * 0.22
        + flow_score * 0.23
        + trust_score * 0.14
        + whitespace_score * 0.09
        + info_density_score * 0.12
    )

    strengths: List[str] = []
    risks: List[str] = []

    textual_signals = " ".join(headings + cta_texts + trust_texts + price_texts + faq_texts + compare_texts).lower()
    browser_token_hit = 1.0 if any(token in textual_signals for token in ["http", "www.", "localhost", ".com", ".jp"]) else 0.0
    browser_ui_score = _clamp(
        min(1.0, browser_ui_text_hits / 2.0) * 0.55
        + browser_ui_bar_signal * 0.30
        + browser_token_hit * 0.15
    )
    vertical_page_score = _clamp((avg_portrait_ratio - 1.20) / 0.80)
    heading_section_score = _clamp(
        _clamp(len(headings) / 4.0) * 0.55
        + _clamp(section_break_count / max(3.0, len(per_image) * 3.0)) * 0.45
    )
    cta_presence_score = _clamp((1.0 if cta_texts else 0.0) * 0.65 + (1.0 if cta_position_labels else 0.0) * 0.35)

    is_web_lp_screenshot = (
        browser_ui_score >= 0.45
        and vertical_page_score >= 0.45
        and heading_section_score >= 0.45
        and cta_presence_score >= 0.45
    )

    if hero_score >= 0.62:
        strengths.append("Heroが強く、ファーストビューで視線停止点を作れています。")
    if cta_score >= 0.60:
        strengths.append("CTA位置が適切で、申込み導線が視認しやすい配置です。")
    if flow_score >= 0.60:
        strengths.append("上→中→下の視線導線が自然で、読み進めやすい構成です。")
    if whitespace_score >= 0.58:
        strengths.append("余白バランスが良く、スマホ閲覧でも詰まり感を抑えています。")
    if trust_score >= 0.55:
        strengths.append("信頼要素の配置が確認でき、CTA前の不安低減に寄与しています。")

    if hero_score < 0.45:
        risks.append("Hero訴求が弱く、ファーストビューでの離脱リスクがあります。")
    if cta_score < 0.45:
        risks.append("CTA視認性が不足し、申込み導線で迷いやすい状態です。")
    if flow_score < 0.45:
        risks.append("情報の流れが途切れやすく、中盤での離脱リスクが高めです。")
    if info_density_score < 0.45:
        risks.append("情報密度の偏りがあり、読み負荷が高いセクションが見られます。")
    if trust_score < 0.40:
        risks.append("信頼導線が弱く、CTA直前での不安解消が不足しています。")

    comment = (
        f"Hero強度 {int(round(hero_score * 100))} / CTA誘導力 {int(round(cta_score * 100))} / "
        f"視線導線 {int(round(flow_score * 100))} を基準に実画像評価しました。"
    )
    summary = (
        f"余白設計 {int(round(whitespace_score * 100))}・情報密度適正 {int(round(info_density_score * 100))}・"
        f"スマホ閲覧性 {int(round(mobile_score * 100))} を確認。離脱リスクは {int(round(dropoff_risk * 100))} です。"
    )

    result = {
        "enabled": True,
        "mode": "web_lp_screenshot" if is_web_lp_screenshot else "artifact_image_set",
        "status": "ok",
        "source": "image_ocr_layout",
        "image_count": len(per_image),
        "ocr_engine": used_engines[0] if used_engines else "none",
        "ocr_engines": used_engines,
        "ocr_block_count": int(sum(int(image.get("ocr_block_count", 0)) for image in per_image)),
        "metrics": {
            "overall": overall,
            "hero": hero_score,
            "cta": cta_score,
            "flow": flow_score,
            "trust": trust_score,
            "whitespace": whitespace_score,
            "info_density": avg_text_density,
            "info_density_score": info_density_score,
            "mobile": mobile_score,
            "dropoff_risk": dropoff_risk,
        },
        "layout": {
            "average_whitespace": avg_whitespace,
            "section_break_count": section_break_count,
            "cta_positions": cta_position_labels,
            "flow_stages": found_flow,
            "avg_portrait_ratio": avg_portrait_ratio,
        },
        "media_conditions": {
            "browser_ui_present": bool(browser_ui_score >= 0.45),
            "vertical_page": bool(vertical_page_score >= 0.45),
            "heading_section_structure": bool(heading_section_score >= 0.45),
            "cta_present": bool(cta_presence_score >= 0.45),
            "browser_ui_score": browser_ui_score,
            "vertical_page_score": vertical_page_score,
            "heading_section_score": heading_section_score,
            "cta_presence_score": cta_presence_score,
        },
        "signals": {
            "headings": headings,
            "cta_texts": cta_texts,
            "trust_texts": trust_texts,
            "price_texts": price_texts,
            "faq_texts": faq_texts,
            "compare_texts": compare_texts,
        },
        "strengths": strengths,
        "risks": risks,
        "comment": comment,
        "summary": summary,
    }
    LOGGER.info(
        "VISUAL_LAYOUT_END status=ok mode=%s overall=%.3f ocr_blocks=%s",
        result["mode"],
        overall,
        result["ocr_block_count"],
    )
    return result


def _build_visual_evaluation_from_lp_analysis(
    visual_lp_analysis: Dict[str, Any],
    visual_input_mode: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(visual_input_mode, dict) or not visual_input_mode.get("enabled"):
        return {}

    if not isinstance(visual_lp_analysis, dict) or not visual_lp_analysis.get("enabled"):
        message = _safe_text(visual_lp_analysis.get("message", "")) if isinstance(visual_lp_analysis, dict) else ""
        if not message:
            message = "画像ベースLP解析を試行しましたが、OCRまたはレイアウト情報が不足して解析を完了できませんでした。"
        return {
            "enabled": False,
            "status": _safe_text(visual_lp_analysis.get("status", "lp_visual_analysis_unavailable")) if isinstance(visual_lp_analysis, dict) else "lp_visual_analysis_unavailable",
            "message": message,
        }

    metrics = visual_lp_analysis.get("metrics", {}) if isinstance(visual_lp_analysis.get("metrics", {}), dict) else {}
    hero_score = int(round(_clamp(_safe_float(metrics.get("hero", 0.0))) * 100))
    cta_score = int(round(_clamp(_safe_float(metrics.get("cta", 0.0))) * 100))
    flow_score = int(round(_clamp(_safe_float(metrics.get("flow", 0.0))) * 100))
    trust_score = int(round(_clamp(_safe_float(metrics.get("trust", 0.0))) * 100))
    whitespace_score = int(round(_clamp(_safe_float(metrics.get("whitespace", 0.0))) * 100))
    density_score = int(round(_clamp(_safe_float(metrics.get("info_density_score", 0.0))) * 100))
    mobile_score = int(round(_clamp(_safe_float(metrics.get("mobile", 0.0))) * 100))
    risk_score = int(round(_clamp(_safe_float(metrics.get("dropoff_risk", 0.0))) * 100))
    total_score = int(round(_clamp(_safe_float(metrics.get("overall", 0.0))) * 100))

    return {
        "enabled": True,
        "status": "ok",
        "source": "screenshot_lp_analysis",
        "scores": {
            "第一印象": int(round((hero_score * 0.55 + flow_score * 0.45))),
            "視線導線": flow_score,
            "余白設計": whitespace_score,
            "信頼感": trust_score,
            "CTA視認性": cta_score,
            "情報密度": density_score,
            "スマホ閲覧性": mobile_score,
            "離脱リスク": risk_score,
        },
        "total_score": total_score,
        "mode": _safe_text(visual_lp_analysis.get("mode", "lp_ui_screenshot")) or "lp_ui_screenshot",
        "comment": _safe_text(visual_lp_analysis.get("comment", "")),
        "summary": _safe_text(visual_lp_analysis.get("summary", "")),
        "strengths": visual_lp_analysis.get("strengths", []) if isinstance(visual_lp_analysis.get("strengths", []), list) else [],
        "risks": visual_lp_analysis.get("risks", []) if isinstance(visual_lp_analysis.get("risks", []), list) else [],
    }


def _float_line(prefix: str, value: Any) -> str:
    return f"{prefix}: {_safe_float(value):.4f}"


def _format_visual_lp_analysis_lines(visual_lp_analysis: Dict[str, Any]) -> List[str]:
    if not isinstance(visual_lp_analysis, dict):
        return []

    if not visual_lp_analysis.get("enabled"):
        message = _safe_text(visual_lp_analysis.get("message", ""))
        status = _safe_text(visual_lp_analysis.get("status", ""))
        if not message and not status:
            return []
        lines = [f"LP_ANALYSIS_STATUS: {status or 'unavailable'}"]
        if message:
            lines.append(f"LP_ANALYSIS_MESSAGE: {message}")
        return lines

    metrics = visual_lp_analysis.get("metrics", {}) if isinstance(visual_lp_analysis.get("metrics", {}), dict) else {}
    layout = visual_lp_analysis.get("layout", {}) if isinstance(visual_lp_analysis.get("layout", {}), dict) else {}
    signals = visual_lp_analysis.get("signals", {}) if isinstance(visual_lp_analysis.get("signals", {}), dict) else {}

    lines = [
        f"LP_ANALYSIS_SOURCE: {_safe_text(visual_lp_analysis.get('source', 'image_ocr_layout')) or 'image_ocr_layout'}",
        f"LP_MEDIA_MODE: {_safe_text(visual_lp_analysis.get('mode', 'lp_ui_screenshot')) or 'lp_ui_screenshot'}",
        f"LP_OCR_ENGINE: {_safe_text(visual_lp_analysis.get('ocr_engine', 'none')) or 'none'}",
        f"LP_OCR_BLOCK_COUNT: {int(visual_lp_analysis.get('ocr_block_count', 0) or 0)}",
        _float_line("LP_HERO_SCORE", metrics.get("hero", 0.0)),
        _float_line("LP_CTA_SCORE", metrics.get("cta", 0.0)),
        _float_line("LP_FLOW_SCORE", metrics.get("flow", 0.0)),
        _float_line("LP_TRUST_SCORE", metrics.get("trust", 0.0)),
        _float_line("LP_WHITESPACE_SCORE", metrics.get("whitespace", 0.0)),
        _float_line("LP_INFO_DENSITY", metrics.get("info_density", 0.0)),
        _float_line("LP_INFO_DENSITY_SCORE", metrics.get("info_density_score", 0.0)),
        _float_line("LP_MOBILE_SCORE", metrics.get("mobile", 0.0)),
        _float_line("LP_DROPOFF_RISK", metrics.get("dropoff_risk", 0.0)),
        _float_line("LP_OVERALL_SCORE", metrics.get("overall", 0.0)),
        f"LP_SECTION_BREAK_COUNT: {int(layout.get('section_break_count', 0) or 0)}",
    ]

    cta_positions = layout.get("cta_positions", []) if isinstance(layout.get("cta_positions", []), list) else []
    flow_stages = layout.get("flow_stages", []) if isinstance(layout.get("flow_stages", []), list) else []
    if cta_positions:
        lines.append(f"LP_CTA_POSITIONS: {' / '.join(str(label) for label in cta_positions)}")
    if flow_stages:
        lines.append(f"LP_FLOW_STAGES: {' / '.join(str(stage) for stage in flow_stages)}")

    for key, prefix in [
        ("headings", "LP_HEADINGS"),
        ("cta_texts", "LP_CTA_TEXTS"),
        ("price_texts", "LP_PRICE_TEXTS"),
        ("trust_texts", "LP_TRUST_TEXTS"),
        ("faq_texts", "LP_FAQ_TEXTS"),
        ("compare_texts", "LP_COMPARE_TEXTS"),
    ]:
        values = signals.get(key, []) if isinstance(signals.get(key, []), list) else []
        clipped = [_safe_text(value) for value in values if _safe_text(value)]
        if clipped:
            lines.append(f"{prefix}: {' / '.join(clipped)}")

    lines.append(f"LP_ANALYZED_IMAGE_COUNT: {int(visual_lp_analysis.get('image_count', 0) or 0)}")

    comment = _safe_text(visual_lp_analysis.get("comment", ""))
    summary = _safe_text(visual_lp_analysis.get("summary", ""))
    if comment:
        lines.append(f"LP_VISUAL_COMMENT: {comment}")
    if summary:
        lines.append(f"LP_VISUAL_SUMMARY: {summary}")
    media_conditions = visual_lp_analysis.get("media_conditions", {}) if isinstance(visual_lp_analysis.get("media_conditions", {}), dict) else {}
    if media_conditions:
        lines.append(
            "LP_MEDIA_CONDITIONS: "
            f"browser_ui={bool(media_conditions.get('browser_ui_present'))} / "
            f"vertical={bool(media_conditions.get('vertical_page'))} / "
            f"structure={bool(media_conditions.get('heading_section_structure'))} / "
            f"cta={bool(media_conditions.get('cta_present'))}"
        )
    return lines


def _extract_manual_output_text(text: str) -> str:
    rows = text.splitlines()
    capture = False
    collected: List[str] = []

    for row in rows:
        stripped = _safe_text(row)
        if not capture:
            if stripped == "文章成果物:" or stripped.startswith("文章成果物:"):
                capture = True
                after = stripped.replace("文章成果物:", "", 1).strip()
                if after:
                    collected.append(after)
            continue

        collected.append(row.rstrip())

    # Preserve the submitted artifact's paragraph structure. The scorer
    # normalizes blank-line differences for identity checks, so removing them
    # here would create a second, semantically identical artifact variant.
    return "\n".join(collected).strip()


def _extract_artifact_context_text(text: str) -> str:
    prefixes = (
        "品名:",
        "簡単な説明:",
        "品名・説明:",
        "対象URL:",
        "追加ファイル数:",
    )
    lines: List[str] = []
    for row in text.splitlines():
        stripped = _safe_text(row)
        if not stripped:
            continue
        if stripped.startswith(prefixes) or stripped.startswith("-"):
            lines.append(stripped)
    return "\n".join(lines).strip()


def _extract_page_output_text(text: str) -> str:
    lines: List[str] = []
    for row in text.splitlines():
        stripped = _safe_text(row)
        if not stripped:
            continue
        if stripped.startswith("LP_") or stripped.startswith((
            "SOURCE_URL:",
            "PAGE_EVALUATION_READY:",
            "FETCH_MODE:",
            "REQUEST_STATUS:",
            "REQUEST_EXCEPTION:",
            "REQUEST_HTML_CHARS:",
            "RENDERED_FALLBACK_REASON:",
            "JS_RENDER_REQUIRED:",
            "RAW_HTML_PATH:",
            "RAW_HTML_CHARS:",
            "RENDERED_HTML_PATH:",
            "RENDERED_HTML_CHARS:",
            "EXTRACTED_TEXT_CHARS:",
            "SECTION_COUNT:",
            "H1_COUNT:",
            "H2_COUNT:",
            "H3_COUNT:",
            "BUTTON_COUNT:",
            "CTA_COUNT:",
            "LINK_TEXT_COUNT:",
            "ARIA_LABEL_COUNT:",
            "FORM_PRESENT:",
            "FAQ_PRESENT:",
            "QR_PRESENT:",
            "IMAGE_ALT_COUNT:",
            "PAGE_TITLE:",
            "META:",
            "H1:",
            "H2:",
            "H3:",
            "LINK_TEXTS:",
            "ARIA_LABELS:",
            "CTA_BUTTONS:",
            "SECTIONS:",
            "BODY:",
            "TEXT:",
            "VISUAL_MODE:",
            "SCREENSHOT_COUNT:",
            "SCREENSHOT_SEQUENCE:",
            "SCREENSHOT_FILES:",
            "LP_UI_VIEWPOINTS:",
            "URL_FETCH_FAILED:",
        )):
            lines.append(stripped)
    return "\n".join(lines).strip()

def _extract_urls(text: str) -> List[str]:
    raw_urls = re.findall(r"https?://[^\s\"'<>]+", text)
    cleaned: List[str] = []

    for url in raw_urls:
        u = url.strip().rstrip(".,);]}>")
        if u and u not in cleaned:
            cleaned.append(u)

    return cleaned


def _fetch_url_summary(url: str) -> str:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    output_dir = Path("outputs") / "url_fetch"
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_html_path = output_dir / f"{digest}_raw.html"
    rendered_html_path = output_dir / f"{digest}_rendered.html"
    debug_lines = [f"SOURCE_URL: {url}"]

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

        session = requests.Session()
        session.trust_env = False
        response = session.get(
            url,
            timeout=12,
            headers=headers,
            allow_redirects=True,
        )
        debug_lines.append(f"REQUEST_STATUS: {response.status_code}")

        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"

        html_text = response.text
        debug_lines.append(f"REQUEST_HTML_CHARS: {len(html_text)}")

        if response.status_code == 403:
            debug_lines.append("RENDERED_FALLBACK_REASON: static_403")
            rendered = _fetch_rendered_html(url)
            _append_rendered_debug(debug_lines, rendered)
            rendered_html = _safe_text(rendered.get("html", ""))
            if rendered_html:
                rendered_html_path.write_text(rendered_html, encoding="utf-8")
                rendered_snapshot = _extract_page_snapshot(
                    url=url,
                    html_text=rendered_html,
                    fetch_mode="rendered",
                    raw_html_path="",
                    raw_html_chars=len(html_text),
                    rendered_html_path=str(rendered_html_path.resolve()),
                    rendered_html_chars=len(rendered_html),
                    js_render_required=True,
                )
                if rendered_snapshot.get("evaluation_ready"):
                    return "\n".join(debug_lines + rendered_snapshot.get("lines", []))
                return "\n".join(_dedupe_keep_order(debug_lines + rendered_snapshot.get("lines", []) + [f"URL_FETCH_FAILED: {url}"]))
            failure_lines = _build_fetch_failure_lines(url=url, debug_lines=debug_lines, fallback_html="")
            return "\n".join(failure_lines)

        response.raise_for_status()
        raw_html_path.write_text(html_text, encoding="utf-8")
        static_snapshot = _extract_page_snapshot(
            url=url,
            html_text=html_text,
            fetch_mode="static",
            raw_html_path=str(raw_html_path.resolve()),
            raw_html_chars=len(html_text),
            rendered_html_path="",
            rendered_html_chars=0,
            js_render_required=False,
        )

        chosen_snapshot = static_snapshot
        if _needs_rendered_fallback(static_snapshot):
            debug_lines.append("RENDERED_FALLBACK_REASON: static_snapshot_low_quality")
            rendered = _fetch_rendered_html(url)
            _append_rendered_debug(debug_lines, rendered)
            rendered_html = _safe_text(rendered.get("html", ""))
            if rendered_html:
                rendered_html_path.write_text(rendered_html, encoding="utf-8")
                rendered_snapshot = _extract_page_snapshot(
                    url=url,
                    html_text=rendered_html,
                    fetch_mode="rendered",
                    raw_html_path=str(raw_html_path.resolve()),
                    raw_html_chars=len(html_text),
                    rendered_html_path=str(rendered_html_path.resolve()),
                    rendered_html_chars=len(rendered_html),
                    js_render_required=True,
                )
                if _snapshot_quality_score(rendered_snapshot) >= _snapshot_quality_score(static_snapshot):
                    chosen_snapshot = rendered_snapshot

        if not chosen_snapshot.get("evaluation_ready"):
            rendered = _fetch_rendered_html(url)
            _append_rendered_debug(debug_lines, rendered)
            rendered_html = _safe_text(rendered.get("html", ""))
            if rendered_html:
                rendered_snapshot = _extract_page_snapshot(
                    url=url,
                    html_text=rendered_html,
                    fetch_mode="rendered",
                    raw_html_path=str(raw_html_path.resolve()),
                    raw_html_chars=len(html_text),
                    rendered_html_path=str(rendered_html_path.resolve()),
                    rendered_html_chars=len(rendered_html),
                    js_render_required=True,
                )
                if _snapshot_quality_score(rendered_snapshot) > _snapshot_quality_score(chosen_snapshot):
                    chosen_snapshot = rendered_snapshot
            if not chosen_snapshot.get("evaluation_ready"):
                failure_lines = debug_lines + chosen_snapshot.get("lines", []) + [f"URL_FETCH_FAILED: {url}"]
                return "\n".join(_dedupe_keep_order(failure_lines))

        return "\n".join(debug_lines + chosen_snapshot.get("lines", []))

    except Exception as exc:
        debug_lines.append(f"REQUEST_EXCEPTION: {type(exc).__name__}: {exc}")
        debug_lines.append("RENDERED_FALLBACK_REASON: request_exception")
        rendered = _fetch_rendered_html(url)
        _append_rendered_debug(debug_lines, rendered)
        rendered_html = _safe_text(rendered.get("html", ""))
        if rendered_html:
            rendered_html_path.write_text(rendered_html, encoding="utf-8")
            rendered_snapshot = _extract_page_snapshot(
                url=url,
                html_text=rendered_html,
                fetch_mode="rendered",
                raw_html_path="",
                raw_html_chars=0,
                rendered_html_path=str(rendered_html_path.resolve()),
                rendered_html_chars=len(rendered_html),
                js_render_required=True,
            )
            if rendered_snapshot.get("evaluation_ready"):
                return "\n".join(debug_lines + rendered_snapshot.get("lines", []))
            return "\n".join(_dedupe_keep_order(debug_lines + rendered_snapshot.get("lines", []) + [f"URL_FETCH_FAILED: {url}"]))
        failure_lines = _build_fetch_failure_lines(url=url, debug_lines=debug_lines, fallback_html="")
        return "\n".join(failure_lines)


def _append_rendered_debug(debug_lines: List[str], rendered: Dict[str, Any]) -> None:
    browser_path = _safe_text(rendered.get("browser_path", ""))
    if browser_path:
        debug_lines.append(f"RENDERED_BROWSER_PATH: {browser_path}")
    returncode = rendered.get("returncode")
    if returncode is not None:
        debug_lines.append(f"RENDERED_RETURN_CODE: {returncode}")
    stderr = _safe_text(rendered.get("stderr", ""))
    if stderr:
        debug_lines.append(f"RENDERED_STDERR: {stderr[:400]}")


def _build_fetch_failure_lines(*, url: str, debug_lines: List[str], fallback_html: str) -> List[str]:
    lines = list(debug_lines)
    html_text = _safe_text(fallback_html)
    if html_text:
        soup = BeautifulSoup(html_text, "html.parser")
        for tag in soup(["script", "style", "noscript", "svg"]):
            tag.decompose()
        title = _normalize_space(soup.title.string if soup.title and soup.title.string else "")
        meta_desc = _extract_meta_description(soup)
        dense_text = _extract_dense_text(soup)
        if _is_meaningful_title(title):
            lines.append(f"PAGE_TITLE: {title}")
        if meta_desc:
            lines.append(f"META: {meta_desc}")
        if dense_text:
            lines.append(f"TEXT: {dense_text[:1200]}")
    lines.append(f"URL_FETCH_FAILED: {url}")
    return lines


def _fetch_rendered_html(url: str) -> Dict[str, Any]:
    browser_path = _find_edge_path()
    if not browser_path:
        return {"html": "", "browser_path": "", "returncode": None, "stderr": "Edge not found"}

    command = [
        str(browser_path),
        "--headless=new",
        "--disable-gpu",
        "--guest",
        "--no-sandbox",
        "--no-first-run",
        "--hide-scrollbars",
        "--run-all-compositor-stages-before-draw",
        "--virtual-time-budget=9000",
        "--window-size=1440,3200",
        "--dump-dom",
        url,
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=35,
            check=False,
        )
    except Exception as exc:
        return {"html": "", "browser_path": str(browser_path), "returncode": None, "stderr": f"{type(exc).__name__}: {exc}"}

    if completed.returncode != 0:
        return {"html": "", "browser_path": str(browser_path), "returncode": completed.returncode, "stderr": _safe_text(completed.stderr)}

    return {"html": _safe_text(completed.stdout), "browser_path": str(browser_path), "returncode": completed.returncode, "stderr": _safe_text(completed.stderr)}


def _find_edge_path() -> Path | None:
    for candidate in EDGE_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def _extract_page_snapshot(
    *,
    url: str,
    html_text: str,
    fetch_mode: str,
    raw_html_path: str,
    raw_html_chars: int,
    rendered_html_path: str,
    rendered_html_chars: int,
    js_render_required: bool,
) -> Dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")

    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()

    title = _normalize_space(soup.title.string if soup.title and soup.title.string else "")
    meta_desc = _extract_meta_description(soup)
    h1_list = _collect_h1_list(soup)
    h2_list = _collect_h2_list(soup)
    h3_list = _collect_h3_list(soup)
    button_texts = _collect_button_texts(soup)
    cta_buttons = _collect_cta_buttons(soup)
    link_texts = _collect_link_texts(soup)
    aria_label_texts = _collect_aria_label_texts(soup)
    section_pairs = _collect_structured_sections(soup)
    body_candidates = _collect_body_candidates(soup)
    dense_text = _extract_dense_text(soup)
    faq_present = _has_faq_content(soup, dense_text)
    form_present = bool(soup.find("form"))
    qr_present = _has_qr_signal(soup, dense_text)
    image_alt_count = _count_meaningful_alt(soup)

    section_texts = [f"{heading}: {body}" if heading and body else (heading or body) for heading, body in section_pairs]

    lines: List[str] = [
        f"SOURCE_URL: {url}",
        f"FETCH_MODE: {fetch_mode}",
        f"JS_RENDER_REQUIRED: {'yes' if js_render_required else 'no'}",
        f"RAW_HTML_PATH: {raw_html_path}",
        f"RAW_HTML_CHARS: {raw_html_chars}",
        f"EXTRACTED_TEXT_CHARS: {len(dense_text)}",
        f"SECTION_COUNT: {len(section_pairs)}",
        f"H1_COUNT: {len(h1_list)}",
        f"H2_COUNT: {len(h2_list)}",
        f"H3_COUNT: {len(h3_list)}",
        f"BUTTON_COUNT: {len(button_texts)}",
        f"CTA_COUNT: {len(cta_buttons)}",
        f"LINK_TEXT_COUNT: {len(link_texts)}",
        f"ARIA_LABEL_COUNT: {len(aria_label_texts)}",
        f"FORM_PRESENT: {'yes' if form_present else 'no'}",
        f"FAQ_PRESENT: {'yes' if faq_present else 'no'}",
        f"QR_PRESENT: {'yes' if qr_present else 'no'}",
        f"IMAGE_ALT_COUNT: {image_alt_count}",
    ]

    if rendered_html_path:
        lines.append(f"RENDERED_HTML_PATH: {rendered_html_path}")
        lines.append(f"RENDERED_HTML_CHARS: {rendered_html_chars}")

    if _is_meaningful_title(title):
        lines.append(f"PAGE_TITLE: {title}")
    if meta_desc:
        lines.append(f"META: {meta_desc}")
    if h1_list:
        lines.append("H1: " + " / ".join(h1_list[:3]))
    if h2_list:
        lines.append("H2: " + " / ".join(h2_list[:8]))
    if h3_list:
        lines.append("H3: " + " / ".join(h3_list[:8]))
    if link_texts:
        lines.append("LINK_TEXTS: " + " / ".join(link_texts[:16]))
    if aria_label_texts:
        lines.append("ARIA_LABELS: " + " / ".join(aria_label_texts[:16]))
    if cta_buttons:
        lines.append("CTA_BUTTONS: " + " / ".join(cta_buttons[:8]))
    if section_texts:
        lines.append("SECTIONS: " + " / ".join(section_texts[:10]))
    if body_candidates:
        lines.append("BODY: " + " / ".join(body_candidates[:12]))
    if dense_text:
        if not body_candidates:
            lines.append("TEXT: " + dense_text[:2600])
        elif len(" ".join(body_candidates)) < 600:
            lines.append("TEXT: " + dense_text[:2200])

    title_signal = bool(_is_meaningful_title(title) or meta_desc)
    structure_signal_count = len(h1_list) + len(h2_list) + len(h3_list) + len(section_pairs) + len(body_candidates)
    action_signal_count = len(cta_buttons) + len(button_texts) + len(link_texts) + len(aria_label_texts)
    has_content = bool(dense_text and title_signal and structure_signal_count >= 2)
    evaluation_ready = bool(
        has_content
        and len(dense_text) >= 700
        and structure_signal_count >= 3
        and action_signal_count >= 1
    )
    lines.insert(2, f"PAGE_EVALUATION_READY: {'yes' if evaluation_ready else 'no'}")

    return {
        "lines": lines,
        "has_content": has_content,
        "evaluation_ready": evaluation_ready,
        "text_chars": len(dense_text),
        "heading_count": len(h1_list) + len(h2_list) + len(h3_list),
        "section_count": len(section_pairs),
        "cta_count": len(cta_buttons),
        "button_count": len(button_texts),
        "link_count": len(link_texts),
        "aria_label_count": len(aria_label_texts),
        "body_count": len(body_candidates),
    }


def _needs_rendered_fallback(snapshot: Dict[str, Any]) -> bool:
    if not isinstance(snapshot, dict):
        return True
    if not snapshot.get("has_content"):
        return True
    if int(snapshot.get("text_chars", 0) or 0) < 500:
        return True
    if int(snapshot.get("heading_count", 0) or 0) < 3:
        return True
    if int(snapshot.get("section_count", 0) or 0) < 3:
        return True
    if int(snapshot.get("cta_count", 0) or 0) < 1:
        if int(snapshot.get("button_count", 0) or 0) + int(snapshot.get("link_count", 0) or 0) < 1:
            return True
    if not snapshot.get("evaluation_ready"):
        return True
    return False


def _snapshot_quality_score(snapshot: Dict[str, Any]) -> int:
    if not isinstance(snapshot, dict):
        return 0
    return (
        int(snapshot.get("text_chars", 0) or 0)
        + int(snapshot.get("heading_count", 0) or 0) * 120
        + int(snapshot.get("section_count", 0) or 0) * 160
        + int(snapshot.get("cta_count", 0) or 0) * 220
        + int(snapshot.get("button_count", 0) or 0) * 80
        + int(snapshot.get("link_count", 0) or 0) * 70
        + int(snapshot.get("aria_label_count", 0) or 0) * 40
        + int(snapshot.get("body_count", 0) or 0) * 90
    )


def _extract_meta_description(soup: BeautifulSoup) -> str:
    meta_desc = ""
    meta_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
    if meta_tag:
        meta_desc = _safe_text(meta_tag.get("content", ""))
    if not meta_desc:
        og_desc = soup.find("meta", attrs={"property": re.compile(r"og:description", re.I)})
        if og_desc:
            meta_desc = _safe_text(og_desc.get("content", ""))
    return _normalize_space(meta_desc)


def _collect_h1_list(soup: BeautifulSoup) -> List[str]:
    items: List[str] = []
    for tag in soup.find_all("h1")[:5]:
        text = _normalize_space(tag.get_text(" ", strip=True))
        if _is_good_heading_text(text):
            items.append(text)
    return _dedupe_keep_order(items)


def _collect_h2_list(soup: BeautifulSoup) -> List[str]:
    items: List[str] = []
    for tag in soup.find_all("h2")[:12]:
        text = _normalize_space(tag.get_text(" ", strip=True))
        if _is_good_heading_text(text):
            items.append(text)
    return _dedupe_keep_order(items)


def _collect_h3_list(soup: BeautifulSoup) -> List[str]:
    items: List[str] = []
    for tag in soup.find_all("h3")[:12]:
        text = _normalize_space(tag.get_text(" ", strip=True))
        if _is_good_heading_text(text):
            items.append(text)
    return _dedupe_keep_order(items)


def _collect_button_texts(soup: BeautifulSoup) -> List[str]:
    items: List[str] = []
    for tag in soup.find_all(["button", "a", "input"])[:60]:
        text = _normalize_space(tag.get_text(" ", strip=True))
        if not text and tag.name == "input":
            text = _normalize_space(tag.get("value", ""))
        if len(text) < 2 or len(text) > 80:
            continue
        if _looks_like_navigation_or_noise(text):
            continue
        items.append(text)
    return _dedupe_keep_order(items)


def _collect_link_texts(soup: BeautifulSoup) -> List[str]:
    items: List[str] = []
    for tag in soup.find_all("a")[:120]:
        href = _safe_text(tag.get("href", ""))
        if not href:
            continue
        text = _normalize_space(tag.get_text(" ", strip=True))
        if not text:
            text = _normalize_space(tag.get("aria-label", "") or tag.get("title", ""))
        if len(text) < 2 or len(text) > 100:
            continue
        if _looks_like_navigation_or_noise(text) and not _looks_like_cta_text(text):
            continue
        items.append(text)
    return _dedupe_keep_order(items)


def _collect_aria_label_texts(soup: BeautifulSoup) -> List[str]:
    items: List[str] = []
    for tag in soup.find_all(attrs={"aria-label": True})[:120]:
        text = _normalize_space(tag.get("aria-label", ""))
        if len(text) < 2 or len(text) > 120:
            continue
        if _looks_like_navigation_or_noise(text) and not _looks_like_cta_text(text):
            continue
        items.append(text)

    for tag in soup.find_all(attrs={"title": True})[:80]:
        text = _normalize_space(tag.get("title", ""))
        if len(text) < 2 or len(text) > 120:
            continue
        if _looks_like_navigation_or_noise(text) and not _looks_like_cta_text(text):
            continue
        items.append(text)
    return _dedupe_keep_order(items)


def _collect_cta_buttons(soup: BeautifulSoup) -> List[str]:
    candidates = _collect_button_texts(soup) + _collect_link_texts(soup) + _collect_aria_label_texts(soup)
    return _dedupe_keep_order([text for text in candidates if _looks_like_cta_text(text)])


def _looks_like_cta_text(text: str) -> bool:
    cta_keywords = [
        "無料",
        "診断",
        "確認",
        "申し込み",
        "申込",
        "相談",
        "問い合わせ",
        "始める",
        "見える化",
        "証明",
        "購入",
        "予約",
        "登録",
        "ダウンロード",
        "資料",
        "詳しく",
        "詳細",
    ]
    return any(keyword in _safe_text(text) for keyword in cta_keywords)


def _append_attribute_text_candidates(soup: BeautifulSoup, candidates: List[str]) -> None:
    for attr in ("aria-label", "title", "alt"):
        for tag in soup.find_all(attrs={attr: True})[:120]:
            text = _normalize_space(tag.get(attr, ""))
            if _is_good_content_text(text) and not _looks_like_navigation_or_noise(text):
                candidates.append(text)



def _collect_structured_sections(soup: BeautifulSoup) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []

    heading_tags = soup.find_all(["h2", "h3"])
    for heading in heading_tags[:12]:
        heading_text = _normalize_space(heading.get_text(" ", strip=True))
        if not _is_good_heading_text(heading_text):
            continue

        body_parts: List[str] = []
        sibling = heading.find_next_sibling()

        checked = 0
        while sibling is not None and checked < 6:
            checked += 1

            if getattr(sibling, "name", "") in ["h1", "h2", "h3"]:
                break

            text = _normalize_space(sibling.get_text(" ", strip=True))
            if _is_good_content_text(text) and not _looks_like_navigation_or_noise(text):
                body_parts.append(text)

            sibling = sibling.find_next_sibling()

        merged = " / ".join(body_parts[:2]).strip()
        if merged:
            pairs.append((heading_text, merged))
        else:
            pairs.append((heading_text, ""))

    result: List[Tuple[str, str]] = []
    seen = set()
    for heading, body in pairs:
        key = f"{heading}|||{body}"
        if key in seen:
            continue
        seen.add(key)
        result.append((heading, body))

    if result:
        return result[:10]

    h1_list = _collect_h1_list(soup)
    body_candidates = _collect_body_candidates(soup)
    fallback_pairs: List[Tuple[str, str]] = []
    for index, heading in enumerate(h1_list[:6]):
        body = body_candidates[index] if index < len(body_candidates) else ""
        if heading or body:
            fallback_pairs.append((heading, body))

    if fallback_pairs:
        return fallback_pairs[:10]

    generic_pairs: List[Tuple[str, str]] = []
    for body in body_candidates[:6]:
        if body:
            generic_pairs.append(("", body))

    return generic_pairs[:10]


def _collect_body_candidates(soup: BeautifulSoup) -> List[str]:
    candidates: List[str] = []

    priority_selectors = [
        "main",
        "article",
        "[role='main']",
        ".main",
        "#main",
        ".content",
        "#content",
        ".post",
        ".entry-content",
        ".page-content",
        ".richText",
        ".rich-text",
        ".section",
        ".container",
        "[data-testid]",
        "[data-hook]",
        "[class*='wix']",
        "[data-classname*='wix']",
    ]

    selected_nodes = []
    for selector in priority_selectors:
        try:
            selected_nodes.extend(soup.select(selector))
        except Exception:
            continue

    if not selected_nodes:
        search_roots = [soup]
    else:
        # Reduce duplicate roots and keep the most likely content containers.
        search_roots = []
        for node in selected_nodes:
            if node not in search_roots:
                search_roots.append(node)
            if len(search_roots) >= 8:
                break

    for root in search_roots:
        for tag in root.find_all(["p", "li", "h3", "h4", "section", "div", "span"]):
            text = _normalize_space(tag.get_text(" ", strip=True))
            if not _is_good_content_text(text):
                continue
            if _looks_like_navigation_or_noise(text):
                continue
            candidates.append(text)

    _append_attribute_text_candidates(soup, candidates)
    candidates = _dedupe_keep_order(candidates)

    filtered: List[str] = []
    for text in candidates:
        if _looks_like_footer_or_legal(text):
            continue
        if _looks_like_heading_only(text):
            continue
        filtered.append(text)

    ranked = sorted(filtered, key=_body_candidate_score, reverse=True)
    ranked = _dedupe_keep_order(ranked)

    return ranked[:20]


def _body_candidate_score(text: str) -> int:
    score = 0
    t = _safe_text(text)

    if 24 <= len(t) <= 260:
        score += 3
    if len(t) >= 40:
        score += 2
    if any(k in t for k in ["あなた", "AI", "証明", "活用", "レポート", "診断", "成果", "見える化", "可視化"]):
        score += 4
    if "©" in t or "All Rights Reserved" in t:
        score -= 10
    if re.search(r"^(home|top|menu)$", t, flags=re.I):
        score -= 10

    return score


def _extract_dense_text(soup: BeautifulSoup) -> str:
    text = _normalize_space(soup.get_text(" ", strip=True))
    if not text:
        return ""
    return text


def _has_faq_content(soup: BeautifulSoup, dense_text: str) -> bool:
    if soup.find_all("details"):
        return True
    lowered = dense_text.lower()
    return any(keyword in lowered for keyword in ["faq", "よくある質問", "q&a", "質問"])


def _has_qr_signal(soup: BeautifulSoup, dense_text: str) -> bool:
    lowered = dense_text.lower()
    if "qr" in lowered or "qrコード" in lowered:
        return True
    for img in soup.find_all("img")[:40]:
        alt = _safe_text(img.get("alt", "")).lower()
        src = _safe_text(img.get("src", "")).lower()
        if "qr" in alt or "qr" in src:
            return True
    return False


def _count_meaningful_alt(soup: BeautifulSoup) -> int:
    count = 0
    for img in soup.find_all("img")[:80]:
        alt = _safe_text(img.get("alt", ""))
        if len(alt) >= 2 and not _looks_like_navigation_or_noise(alt):
            count += 1
    return count


def _is_good_content_text(text: str) -> bool:
    t = _safe_text(text)
    if len(t) < 18:
        return False
    if len(t) > 1200:
        return False
    if re.fullmatch(r"[-#*=/\s]+", t):
        return False
    return True


def _is_good_heading_text(text: str) -> bool:
    t = _safe_text(text)
    if len(t) < 2:
        return False
    if len(t) > 120:
        return False
    if _looks_like_navigation_or_noise(t):
        return False
    if _looks_like_footer_or_legal(t):
        return False
    return True


def _is_meaningful_title(text: str) -> bool:
    t = _safe_text(text)
    if len(t) < 2:
        return False
    if _looks_like_footer_or_legal(t):
        return False
    return True


def _looks_like_heading_only(text: str) -> bool:
    t = _safe_text(text)
    if len(t) <= 20 and not re.search(r"[。！？!?]", t):
        return True
    return False


def _looks_like_footer_or_legal(text: str) -> bool:
    t = _safe_text(text)

    footer_patterns = [
        r"all rights reserved",
        r"copyright",
        r"©",
        r"プライバシー",
        r"利用規約",
        r"特定商取引法",
        r"会社概要",
        r"お問い合わせ",
        r"問い合わせ",
    ]

    for pattern in footer_patterns:
        if re.search(pattern, t, flags=re.IGNORECASE):
            return True

    if re.fullmatch(r"[0-9]{4}", t):
        return True

    return False


def _looks_like_navigation_or_noise(text: str) -> bool:
    t = _safe_text(text)

    noise_patterns = [
        r"^(menu|home|top|login|signup)$",
        r"^(お問い合わせ|問い合わせ|プライバシー|利用規約|特定商取引法|会社概要)$",
        r"^(次へ|前へ|戻る|一覧|続きを読む)$",
        r"^(無料公開中|β版無料公開中)$",
    ]

    if len(t) <= 6:
        return True

    for pattern in noise_patterns:
        if re.search(pattern, t, flags=re.IGNORECASE):
            return True

    same_char_ratio = _max_same_char_ratio(t)
    if same_char_ratio >= 0.7 and len(t) >= 10:
        return True

    return False


def _max_same_char_ratio(text: str) -> float:
    if not text:
        return 0.0

    counts = {}
    for ch in text:
        counts[ch] = counts.get(ch, 0) + 1

    max_count = max(counts.values())
    return max_count / max(1, len(text))


# =========================================================
# Step分割
# =========================================================
def _split_log_blocks(text: str) -> List[Tuple[int, str]]:
    if not text:
        return []

    matches = list(LOG_BLOCK_PATTERN.finditer(text))
    if not matches:
        return [(1, text.strip())] if text.strip() else []

    blocks: List[Tuple[int, str]] = []
    for idx, match in enumerate(matches):
        block_id = int(match.group(1))
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            blocks.append((block_id, chunk))

    return blocks


def _split_steps(text: str) -> List[str]:
    if not text:
        return []

    role_steps = _split_chatgpt_user_steps(text)
    if role_steps:
        return role_steps

    matches = list(STEP_PATTERN.finditer(text))
    if not matches:
        return [text.strip()]

    steps: List[str] = []

    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            steps.append(chunk)

    return steps


def _split_step_records(text: str) -> List[Dict[str, str]]:
    matches = list(CHATGPT_ROLE_PATTERN.finditer(text))
    if not matches:
        return [{"text": step, "assistant_context": ""} for step in _split_steps(text)]

    records: List[Dict[str, str]] = []
    pending_assistant = ""
    for idx, match in enumerate(matches):
        role = _safe_text(match.group(2)).upper()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if not chunk:
            continue
        if role == "ASSISTANT":
            pending_assistant = chunk
            continue
        if role == "USER":
            records.append({"text": chunk, "assistant_context": pending_assistant})
            pending_assistant = ""
    return records


def _resolve_selected_option_content(user_text: str, assistant_context: str) -> str:
    selection = re.search(
        r"\b(?:use|keep|choose|select|adopt|approve)\s+"
        r"(option|approach|message)\s+([a-z]|\d+)\b",
        _safe_text(user_text),
        re.IGNORECASE,
    )
    if not selection or not _safe_text(assistant_context):
        return ""

    target_type = selection.group(1)
    target_id = selection.group(2)
    option_match = re.search(
        rf"(?:^|\n)\s*{re.escape(target_type)}\s+{re.escape(target_id)}\s*[:：]\s*(.*?)"
        rf"(?=\n\s*{re.escape(target_type)}\s+(?:[a-z]|\d+)\s*[:：]|\Z)",
        assistant_context,
        re.IGNORECASE | re.DOTALL,
    )
    if not option_match:
        return ""
    return _safe_text(option_match.group(1))[:800]


def _split_chatgpt_user_steps(text: str) -> List[str]:
    matches = list(CHATGPT_ROLE_PATTERN.finditer(text))
    if not matches:
        return []

    steps: List[str] = []
    for idx, match in enumerate(matches):
        role = _safe_text(match.group(2)).upper()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if role == "USER" and chunk:
            steps.append(chunk)
    return steps


# =========================================================
# Step解析
# =========================================================
def _append_section_value(result: Dict[str, str], key: str, lines: List[str]) -> None:
    text = "\n".join(_safe_text(line) for line in lines if _safe_text(line)).strip()
    if not text:
        return

    existing = _safe_text(result.get(key, ""))
    if existing:
        result[key] = f"{existing}\n{text}"
    else:
        result[key] = text


def _parse_step(step_text: str) -> Dict[str, str]:
    result = {
        "判断": "",
        "修正": "",
        "採否": "",
        "理由": "",
    }

    current_key = None
    buffer: List[str] = []

    lines = step_text.splitlines()

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        key, inline_text = _detect_section_key(stripped)
        if key:
            if current_key and buffer:
                _append_section_value(result, current_key, buffer)
            current_key = key
            buffer = [inline_text] if inline_text else []
            continue

        if current_key:
            buffer.append(stripped)

    if current_key and buffer:
        _append_section_value(result, current_key, buffer)

    _apply_natural_language_classification(step_text, result)

    return result


def _apply_natural_language_classification(step_text: str, result: Dict[str, str]) -> None:
    text = _normalize_natural_user_text(step_text)
    if not text or not _should_classify_natural_step(text, result):
        return

    decision = _is_natural_decision(text)
    adoption = _is_natural_adoption_or_rejection(text)
    revision = _is_natural_revision_or_direction_change(text)
    reason = _extract_natural_reason(text) if (decision or adoption or revision) else ""

    if decision and not _safe_text(result.get("判断", "")):
        result["判断"] = text
    if adoption and not _safe_text(result.get("採否", "")):
        result["採否"] = text
    if revision and not _safe_text(result.get("修正", "")):
        result["修正"] = text
    if reason and not _safe_text(result.get("理由", "")):
        result["理由"] = reason


def _normalize_natural_user_text(text: str) -> str:
    lines: List[str] = []
    for line in _safe_text(text).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if CHATGPT_ROLE_PATTERN.match(stripped):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _should_classify_natural_step(text: str, result: Dict[str, str]) -> bool:
    if any(_safe_text(result.get(key, "")) for key in ("判断", "修正", "採否", "理由")):
        return False
    if _looks_like_english_process_step(text):
        if len(text) > 1600:
            return False
    else:
        if len(text) > 320:
            return False
        if len([line for line in text.splitlines() if _safe_text(line)]) > 4:
            return False
    if _is_obvious_work_report_text(text):
        return False
    return True


def _looks_like_english_process_step(text: str) -> bool:
    patterns = [
        r"\b(?:use|keep|choose|select|reject|adopt|approve)\s+"
        r"(?:option|approach|message)\s+(?:[a-z]|\d+)\b",
        r"\b(?:please\s+)?(?:revise|replace|change|changes|update|preserve|remove|avoid|rewrite|"
        r"reorganize|restructure|add)\b",
        r"\b(?:do not|don't)\s+(?:use|rewrite|change|add)\b",
        r"\b(?:agreed|this is closer|the .+ works?)\b",
        r"\b(?:headline|paragraph|button|call[- ]to[- ]action|cta|hero section)\b",
        r"\b(?:approve(?:d)?\b.+\b(?:as\s+)?final|reject\s+further\s+changes?|"
        r"no\s+further\s+revisions?\s+(?:is|are)\s+required)\b",
        r"\b(?:keep\s+the\s+current\s+version|use\s+this\s+final\s+structure|"
        r"(?:use|choose)\s+the\s+current\s+version\s+as\s+final)\b",
    ]
    return _has_natural_pattern(text, patterns)


def _has_natural_pattern(text: str, patterns: List[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _is_obvious_work_report_text(text: str) -> bool:
    value = _safe_text(text)
    if not value:
        return False
    report_patterns = [
        r"^(作成|変更|修正|追加|実装|確認)しました",
        r"^(確認結果|変更内容|実装内容|作成ファイル|変更ファイル)",
        r"(manifest\.json|popup\.js|content\.js)",
    ]
    return _has_natural_pattern(value, report_patterns)


def _is_natural_decision(text: str) -> bool:
    patterns = [
        r"どう[？?]?$",
        r"これでいい(?:かな)?",
        r"これ違う",
        r"それは違う",
        r"これだと弱い",
        r"この方がいい",
        r"こっちがいい",
        r"こっちでいく",
        r"これにする",
        r"こうする",
        r"(?:した|する|やる|通した|解析した|拾った|取得した)方がいい",
        r"の方がいい",
        r"仕方ない(?:だろ)?",
        r"意味(?:が)?ない",
        r"いらん|いらない|不要",
        r"やめる|外す|削る|減らす|少なくする|多すぎる",
        r"戻す|元に戻す|戻そう",
        r"拡張側ではなくアプリ側|アプリ側で",
        r"フィルターを甘くして|フィルターを厳しくして",
        r"変更|修正|調整|追加|削除|差し替え|簡素化",
        r"方針変更|方向転換|やっぱり?|こっちにする|まずは戻す|次は",
        r"\b(?:use|keep|choose|select|adopt|approve|reject)\s+"
        r"(?:option|approach|message)\s+(?:[a-z]|\d+)\b",
        r"\b(?:agreed|this is closer|the (?:paragraph|headline|copy|version) works?)\b",
        r"\b(?:do not|don't)\s+(?:use|rewrite|change|add)\b",
        r"\bkeep\b.+\bunchanged\b",
        r"\b(?:want|should)\b.+\b(?:headline|paragraph|button|section|line|brand|reader)\b",
        r"\bapprove(?:d)?\b.+\b(?:as\s+)?final\b",
        r"\breject\s+further\s+changes?\b",
        r"\bno\s+further\s+revisions?\s+(?:is|are)\s+required\b",
        r"\bkeep\s+the\s+current\s+version\b",
        r"\buse\s+this\s+final\s+structure\b",
        r"\b(?:use|choose)\s+the\s+current\s+version\s+as\s+final\b",
    ]
    return _has_natural_pattern(text, patterns)


def _is_natural_adoption_or_rejection(text: str) -> bool:
    patterns = [
        r"採用|不採用|却下|決定|確定",
        r"これでいく|こっちでいく|これにする|こっちにする",
        r"拡張側ではなくアプリ側",
        r"いらん|いらない|不要|使わない|やめる|外す|削る",
        r"減らす|少なくする|多すぎる|意味(?:が)?ない|仕方ない(?:だろ)?",
        r"\b(?:use|keep|choose|select|adopt|approve|reject)\s+"
        r"(?:option|approach|message)\s+(?:[a-z]|\d+)\b",
        r"\b(?:agreed|this is closer|the (?:paragraph|headline|copy|version) works?)\b",
        r"\b(?:do not|don't)\s+use\b",
        r"\bkeep\b.+\bunchanged\b",
        r"\b(?:feels?|sounds?)\s+(?:too\s+)?(?:grand|promotional|abstract|corporate|generic|repetitive)\b",
        r"\bapprove(?:d)?\b.+\b(?:as\s+)?final\b",
        r"\breject\s+further\s+changes?\b",
        r"\bno\s+further\s+revisions?\s+(?:is|are)\s+required\b",
        r"\bkeep\s+the\s+current\s+version\b",
        r"\buse\s+this\s+final\s+structure\b",
        r"\b(?:use|choose)\s+the\s+current\s+version\s+as\s+final\b",
    ]
    return _has_natural_pattern(text, patterns)


def _is_natural_revision_or_direction_change(text: str) -> bool:
    patterns = [
        r"修正|変更|戻す|元に戻す|戻そう|直す|いじる|調整",
        r"追加|削除|差し替え|簡素化|減らす|増やす",
        r"フィルターを甘くして|フィルターを厳しくして",
        r"アプリで解析した方がいい|アプリ側で.*(?:通した|解析した|拾った|取得した)方がいい",
        r"方針変更|方向転換|やっぱり?|こっちにする|まずは戻す|次は",
        r"\b(?:please\s+)?revise\b|\brevise\b.+\b(?:again|once more|only)\b",
        r"\b(?:replace|update|preserve|remove|avoid|rewrite|reorganize|restructure)\b",
        r"\b(?:also\s+)?changes?\b",
        r"\b(?:do not|don't)\s+(?:use|rewrite)\b",
        r"\badd\s+(?:one|a)\s+(?:short\s+)?(?:line|section|paragraph)\b",
        r"\bkeep\b.+\bunchanged\b",
        r"\bcreate\s+the\s+complete\s+revised\s+version\b",
    ]
    return _has_natural_pattern(text, patterns)


def _extract_natural_reason(text: str) -> str:
    if _has_natural_pattern(text, [r"から", r"ので", r"ため", r"仕方ない(?:だろ)?", r"意味(?:が)?ない"]):
        return text
    english_reason_patterns = [
        r"\bbecause\b", r"\bsince\b", r"\bso that\b", r"\bthe point is\b",
        r"\b(?:feels?|sounds?)\b", r"\btoo\s+(?:grand|promotional|abstract|corporate|generic)\b",
        r"\b(?:clearer|clearest|shorter|works better|important)\b",
        r"\bshould first\b", r"\bnot push\b", r"\brepetitive\b",
    ]
    sentences = [
        _safe_text(part)
        for part in re.split(r"(?<=[.!?])\s+|\n+", text)
        if _safe_text(part)
    ]
    reasons = [sentence for sentence in sentences if _has_natural_pattern(sentence, english_reason_patterns)]
    if reasons:
        return "\n".join(reasons[:4])
    return ""


def _normalize_section_line(line: str) -> str:
    line = _safe_text(line)
    return re.sub(r"^[#>*\-\s・●▪◦]+", "", line).strip()


def _match_section_label(line: str, pattern: str):
    if pattern.lower() in ENGLISH_SECTION_LABELS:
        return re.match(
            rf"^(?:【\s*)?({re.escape(pattern)})(?:\s*】)?"
            rf"(?:\s*[:：]\s*(.*)|\s*)$",
            line,
            flags=re.IGNORECASE,
        )
    return re.match(
        rf"^(?:【\s*)?({re.escape(pattern)})(?:\s*】)?\s*[:：]?\s*(.*)$",
        line,
    )


def _strip_section_prefix(line: str) -> str:
    normalized = _normalize_section_line(line)
    for patterns in SECTION_KEYS.values():
        for pattern in patterns:
            prefix_match = _match_section_label(normalized, pattern)
            if prefix_match:
                return _safe_text(prefix_match.group(2))
    return normalized


def _detect_section_key(line: str) -> tuple[str, str]:
    normalized = _normalize_section_line(line)

    for key, patterns in SECTION_KEYS.items():
        for p in patterns:
            match = _match_section_label(normalized, p)
            if not match:
                continue

            label = _safe_text(match.group(1))
            rest = _safe_text(match.group(2))

            if key == "採否":
                inline_text = label if not rest else f"{label}：{rest}"
                return key, inline_text

            return key, rest

    return "", ""


# =========================================================
# before→after抽出
# =========================================================
def _extract_english_before_after_labels(text: str) -> Dict[str, str]:
    buffers: Dict[str, List[str]] = {"before": [], "after": []}
    current_key = ""

    for raw_line in str(text or "").splitlines():
        stripped = raw_line.strip()
        marker = re.match(r"^(before|after)\s*[:：]\s*(.*)$", stripped, flags=re.IGNORECASE)
        if marker:
            current_key = marker.group(1).lower()
            inline_text = _safe_text(marker.group(2))
            if inline_text:
                buffers[current_key].append(inline_text)
            continue

        if not current_key or not stripped:
            continue

        section_key, _inline_text = _detect_section_key(stripped)
        if section_key:
            current_key = ""
            continue

        buffers[current_key].append(stripped)

    return {
        "before": "\n".join(buffers["before"]).strip(),
        "after": "\n".join(buffers["after"]).strip(),
    }


def _extract_before_after(text: str) -> Dict[str, str]:
    result = _extract_english_before_after_labels(text)
    if result["before"] or result["after"]:
        return result

    normalized_lines = [_strip_section_prefix(line) for line in text.splitlines() if _safe_text(line)]

    for line in normalized_lines:
        arrow_match = re.search(r"(.+?)\s*→\s*(.+)", line)
        if arrow_match:
            result["before"] = arrow_match.group(1).strip()
            result["after"] = arrow_match.group(2).strip()
            return result

    english_change = re.search(
        r"\bchange\b.*?\bfrom\s+[“\"]?([^”\"\n]+?)[”\"]?\s+to\s+(.+?)(?:[.!?]|$)",
        text,
        re.IGNORECASE | re.DOTALL,
    )
    if english_change:
        result["before"] = _safe_text(english_change.group(1))
        result["after"] = _safe_text(english_change.group(2))
        return result

    if _is_natural_revision_or_direction_change(text):
        quoted = [_safe_text(value) for value in re.findall(r"[“\"]([^”\"]+)[”\"]", text) if _safe_text(value)]
        revision_lines = [
            _safe_text(line)
            for line in re.split(r"(?<=[.!?])\s+|\n+", text)
            if _safe_text(line) and _is_natural_revision_or_direction_change(line)
        ]
        if quoted and revision_lines:
            result["before"] = "; ".join(quoted[:3])
            result["after"] = " ".join(revision_lines[:3])
            return result

        kara_match = re.search(
            r"(.+?)から(.+?)(?:に|へ)\s*(?:変更|修正|戻す|戻した|直す|調整|差し替え|変える|する|した)",
            line,
        )
        if kara_match:
            result["before"] = kara_match.group(1).strip()
            result["after"] = kara_match.group(2).strip()
            return result

    return result


# =========================================================
# scorer用の再構築
# =========================================================
def _rebuild_collections(
    structured_steps: List[Dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    decisions: List[Dict[str, Any]] = []
    revisions: List[Dict[str, Any]] = []
    adoptions: List[Dict[str, Any]] = []
    structure_decisions: List[Dict[str, Any]] = []

    for step in structured_steps:
        step_id = step.get("step_id")

        judgment = _safe_text(step.get("judgment"))
        revision = _safe_text(step.get("revision"))
        adoption = _safe_text(step.get("adoption"))
        reason = _safe_text(step.get("reason"))

        if judgment:
            decisions.append({
                "step_id": step_id,
                "text": judgment,
                "reason": reason,
            })

        if revision:
            revisions.append({
                "step_id": step_id,
                "text": revision,
                "reason": reason,
                "before_after": step.get("before_after", {}),
            })

        if adoption:
            adoptions.append({
                "step_id": step_id,
                "text": adoption,
                "reason": reason,
            })

        combined = "\n".join([judgment, revision, adoption]).strip()

        if combined and _is_structure_related(combined):
            structure_decisions.append({
                "step_id": step_id,
                "text": combined,
                "reason": reason,
            })

    return decisions, revisions, adoptions, structure_decisions


def _analyze_step_quality(
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    step_count = len(structured_steps)
    if step_count <= 0:
        return {
            "step_count": 0,
            "before_after_count": 0,
            "adoption_count": 0,
            "reason_count": 0,
            "structure_change_count": 0,
            "user_decision_count": 0,
            "comparison_count": 0,
            "continuous_improvement_span": 0,
            "unresolved_judgment_count": 0,
            "before_after_ratio": 0.0,
            "adoption_ratio": 0.0,
            "reason_density": 0.0,
            "structure_change_ratio": 0.0,
            "user_decision_ratio": 0.0,
            "comparison_ratio": 0.0,
            "step_quality_score": 0.0,
        }

    before_after_count = 0
    adoption_count = 0
    reason_count = 0
    structure_change_count = 0
    user_decision_count = 0
    comparison_count = 0
    unresolved_judgment_count = 0
    longest_revision_streak = 0
    current_revision_streak = 0

    user_decision_patterns = [
        r"ユーザー", r"自分", r"最終判断", r"決定", r"採用", r"不採用", r"却下", r"選択", r"選別", r"支持",
        r"(?i)\b(?:use|keep|choose|select)\s+option\s+\d+\b",
        r"(?i)\b(?:agreed|works?|closer|do not|don't)\b",
    ]
    comparison_patterns = [
        r"比較", r"一方", r"ではなく", r"より", r"案", r"重複", r"分離", r"統合", r"先行", r"最短導線",
        r"(?i)\b(?:option|alternative)s?\b", r"(?i)\b(?:clearer|clearest|shorter|repetitive)\b",
    ]
    structure_patterns = [
        r"構造", r"構成", r"導線", r"セクション", r"見出し", r"CTA", r"HERO", r"分類", r"ナビ", r"リンク",
        r"(?i)\b(?:structure|section|headline|heading|paragraph|button|call[- ]to[- ]action|cta|hero|layout)\b",
    ]

    for step in structured_steps:
        judgment = _safe_text(step.get("judgment", ""))
        revision = _safe_text(step.get("revision", ""))
        adoption = _safe_text(step.get("adoption", ""))
        reason = _safe_text(step.get("reason", ""))
        raw = _safe_text(step.get("raw", ""))
        before_after = step.get("before_after", {}) if isinstance(step.get("before_after", {}), dict) else {}
        before_text = _safe_text(before_after.get("before", ""))
        after_text = _safe_text(before_after.get("after", ""))

        if adoption:
            adoption_count += 1
        if reason:
            reason_count += 1

        if (before_text and after_text) or ("変更前" in raw and "変更後" in raw) or ("→" in revision):
            before_after_count += 1

        joined = "\n".join([judgment, revision, adoption, reason, raw]).strip()
        if any(re.search(pattern, joined) for pattern in structure_patterns):
            structure_change_count += 1
        if any(re.search(pattern, joined) for pattern in user_decision_patterns):
            user_decision_count += 1
        if any(re.search(pattern, joined) for pattern in comparison_patterns):
            comparison_count += 1

        if judgment and not adoption:
            unresolved_judgment_count += 1

        if revision:
            current_revision_streak += 1
            longest_revision_streak = max(longest_revision_streak, current_revision_streak)
        else:
            current_revision_streak = 0

    # 保険的に collections 由来の件数と整合
    adoption_count = max(adoption_count, len([x for x in adoptions if _safe_text(x.get("text", ""))]))
    structure_change_count = max(structure_change_count, len([x for x in structure_decisions if _safe_text(x.get("text", ""))]))

    before_after_ratio = before_after_count / max(1, step_count)
    adoption_ratio = adoption_count / max(1, step_count)
    reason_density = reason_count / max(1, step_count)
    structure_change_ratio = structure_change_count / max(1, step_count)
    user_decision_ratio = user_decision_count / max(1, step_count)
    comparison_ratio = comparison_count / max(1, step_count)
    continuity_ratio = longest_revision_streak / max(1, step_count)

    step_quality_score = (
        before_after_ratio * 0.22
        + adoption_ratio * 0.18
        + reason_density * 0.22
        + structure_change_ratio * 0.14
        + user_decision_ratio * 0.14
        + comparison_ratio * 0.10
        + continuity_ratio * 0.10
    )
    step_quality_score -= min(0.24, unresolved_judgment_count / max(1, step_count) * 0.24)
    step_quality_score = max(0.0, min(1.0, step_quality_score))

    return {
        "step_count": step_count,
        "before_after_count": before_after_count,
        "adoption_count": adoption_count,
        "reason_count": reason_count,
        "structure_change_count": structure_change_count,
        "user_decision_count": user_decision_count,
        "comparison_count": comparison_count,
        "continuous_improvement_span": longest_revision_streak,
        "unresolved_judgment_count": unresolved_judgment_count,
        "before_after_ratio": round(before_after_ratio, 4),
        "adoption_ratio": round(adoption_ratio, 4),
        "reason_density": round(reason_density, 4),
        "structure_change_ratio": round(structure_change_ratio, 4),
        "user_decision_ratio": round(user_decision_ratio, 4),
        "comparison_ratio": round(comparison_ratio, 4),
        "continuity_ratio": round(continuity_ratio, 4),
        "step_quality_score": round(step_quality_score, 4),
        "has_high_quality_step_log": bool(
            step_count >= 5
            and before_after_ratio >= 0.45
            and adoption_ratio >= 0.45
            and reason_density >= 0.55
        ),
    }


def _analyze_log_source_profile(structured_steps: List[Dict[str, Any]], log_text: str) -> Dict[str, Any]:
    step_count = len([step for step in structured_steps if isinstance(step, dict)])
    if step_count <= 0:
        return {
            "is_structured_extraction_log": False,
            "has_source_quote": False,
            "explicit_field_ratio": 0.0,
            "source_quote_ratio": 0.0,
            "reason_ratio": 0.0,
            "adoption_ratio": 0.0,
            "before_after_marker_ratio": 0.0,
        }

    explicit_field_count = 0
    source_quote_count = 0
    reason_count = 0
    adoption_count = 0
    before_after_count = 0
    original_text = _safe_text(log_text)
    header_hint = bool(re.search(r"(AI Conversation Log|ChatGPT User Conversation Log|ChatGPT Conversation Log)", original_text))

    for step in structured_steps:
        raw = _safe_text(step.get("raw", ""))
        has_japanese_fields = bool(
            re.search(r"判断\s*[：:]", raw)
            and re.search(r"修正\s*[：:]", raw)
        )
        has_english_fields = bool(
            re.search(r"^\s*Decision\s*[：:]", raw, flags=re.IGNORECASE | re.MULTILINE)
            and re.search(r"^\s*Revision\s*[：:]", raw, flags=re.IGNORECASE | re.MULTILINE)
        )
        if has_japanese_fields or has_english_fields:
            explicit_field_count += 1
        if re.search(r"(元発言|原文|引用|ユーザー発言)\s*[：:]", raw):
            source_quote_count += 1
        if _safe_text(step.get("reason", "")):
            reason_count += 1
        if _safe_text(step.get("adoption", "")):
            adoption_count += 1
        has_japanese_before_after = bool(
            re.search(r"変更前\s*[：:].+変更後\s*[：:]", raw, flags=re.DOTALL)
        )
        has_english_before_after = bool(
            re.search(r"^\s*Before\s*[：:].+^\s*After\s*[：:]", raw, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
        )
        if has_japanese_before_after or has_english_before_after:
            before_after_count += 1

    explicit_field_ratio = explicit_field_count / max(1, step_count)
    source_quote_ratio = source_quote_count / max(1, step_count)
    reason_ratio = reason_count / max(1, step_count)
    adoption_ratio = adoption_count / max(1, step_count)
    before_after_marker_ratio = before_after_count / max(1, step_count)
    is_structured_extraction_log = bool(
        explicit_field_ratio >= 0.70
        and reason_ratio >= 0.60
        and adoption_ratio >= 0.50
        and before_after_marker_ratio >= 0.40
        and source_quote_ratio < 0.50
    )

    return {
        "is_structured_extraction_log": is_structured_extraction_log,
        "has_source_quote": source_quote_ratio >= 0.50,
        "header_hint": header_hint,
        "explicit_field_ratio": round(explicit_field_ratio, 4),
        "source_quote_ratio": round(source_quote_ratio, 4),
        "reason_ratio": round(reason_ratio, 4),
        "adoption_ratio": round(adoption_ratio, 4),
        "before_after_marker_ratio": round(before_after_marker_ratio, 4),
    }


# =========================================================
# 判定ロジック
# =========================================================
def _is_structure_related(text: str) -> bool:
    lowered = _safe_text(text).lower()
    for kw in STRUCTURE_KEYWORDS:
        if kw.lower() in lowered:
            return True
    return False


# =========================================================
# 共通
# =========================================================
def _normalize_space(text: Any) -> str:
    t = _safe_text(text)
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _dedupe_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []

    for item in items:
        t = _safe_text(item)
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        result.append(t)

    return result


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()



