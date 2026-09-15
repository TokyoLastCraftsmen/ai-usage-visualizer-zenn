from __future__ import annotations

import os
import re
import shutil
import subprocess
import zipfile
import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List


LOGGER = logging.getLogger(__name__)

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

PPT_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
A14_NS = "http://schemas.microsoft.com/office/drawing/2010/main"
NS = {"p": PPT_NS, "a": A_NS}

AXIS_ORDER = ["成果物論理性", "判断プロセス", "修正プロセス", "判断主体性", "全体整合性"]
AXIS_ALIASES = {
    "アウトプット論理性": "成果物論理性",
    "成果物論理性": "成果物論理性",
    "判断プロセス": "判断プロセス",
    "修正プロセス": "修正プロセス",
    "判断主体性": "判断主体性",
    "全体整合性": "全体整合性",
    "Output Logic": "成果物論理性",
    "output_logic": "成果物論理性",
    "Decision Process": "判断プロセス",
    "decision_process": "判断プロセス",
    "judgment_process": "判断プロセス",
    "Iteration Process": "修正プロセス",
    "iteration_process": "修正プロセス",
    "revision_process": "修正プロセス",
    "Human Ownership": "判断主体性",
    "human_ownership": "判断主体性",
    "human_agency": "判断主体性",
    "Overall Consistency": "全体整合性",
    "overall_consistency": "全体整合性",
    "謌先棡迚ｩ隲也炊諤ｧ": "成果物論理性",
    "蛻､譁ｭ繝励Ο繧ｻ繧ｹ": "判断プロセス",
    "菫ｮ豁｣繝励Ο繧ｻ繧ｹ": "修正プロセス",
    "蛻､譁ｭ荳ｻ菴捺ｧ": "判断主体性",
    "蜈ｨ菴捺紛蜷域ｧ": "全体整合性",
}

FORBIDDEN_TERMS = [
    "PAGE_TITLE",
    "PAGE_EVALUATION_READY",
    "SOURCE_URL",
    "URL_FETCH_FAILED",
    "H1",
    "H2",
    "H3",
    "CTA_BUTTONS",
    "LINK_TEXTS",
    "ARIA_LABELS",
    "SECTIONS",
    "FETCH_MODE",
]

DEFAULT_TEMPLATE_CANDIDATES = [
    os.getenv("AI_REPORT_TEMPLATE_PATH", ""),
    "app/report_template_completed.pptx",
    "app/template_new.pptx",
    "tmp/ui_reference.pptx",
    str(APP_DIR / "report_template_completed.pptx"),
    str(APP_DIR / "template_new.pptx"),
    str(APP_DIR / "AI可視化レポート.pptx"),
]

# テンプレの見た目維持: shape index 差し込み
SLIDE_SHAPE_MAP: Dict[int, Dict[int, str]] = {
    1: {
        5: "target_work",
        7: "doc_id",
        9: "target_name",
        13: "meta_info",
    },
    2: {
        5: "axis_output_logic_comment",
        6: "axis_output_logic_score",
        11: "axis_judgment_comment",
        12: "axis_judgment_score",
        14: "axis_revision_comment",
        15: "axis_revision_score",
        18: "axis_agency_comment",
        19: "axis_agency_score",
        21: "axis_consistency_comment",
        22: "axis_consistency_score",
    },
    3: {},
    4: {},
    5: {},
    6: {},
}

FIELD_LIMITS: Dict[str, Dict[str, int]] = {
    "target_work": {"chars": 74},
    "doc_id": {"chars": 24},
    "target_name": {"chars": 24},
    "overall_summary": {"chars": 280, "sentences": 5},
    "analysis_method": {"chars": 320, "sentences": 7},
    "total_score": {"chars": 16},
    "strengths_bullets": {"chars": 220, "lines": 4, "line_chars": 56},
    "weaknesses_bullets": {"chars": 180, "lines": 3, "line_chars": 48},
    "meta_info": {"chars": 16},
    "axis_output_logic_comment": {"chars": 360, "sentences": 6},
    "axis_judgment_comment": {"chars": 360, "sentences": 6},
    "axis_revision_comment": {"chars": 360, "sentences": 6},
    "axis_agency_comment": {"chars": 360, "sentences": 6},
    "axis_consistency_comment": {"chars": 360, "sentences": 6},
    "improve_bullets": {"chars": 190, "lines": 4, "line_chars": 46},
    "responsibility_header": {"chars": 140},
    "responsibility_body": {"chars": 380, "sentences": 6},
    "risk_bullets": {"chars": 320, "lines": 7, "line_chars": 42},
    # 3P 左中央は現行フォーマット（3項目）に合わせる
    "aptitude_bullets": {"chars": 260, "lines": 6, "line_chars": 42},
    # 3P 左上（活用可能領域）は枠内収まりを優先
    "summary_text": {"chars": 340, "sentences": 6},
    # 3P 左下（段落）は枠バランスに合わせて充填
    "usage_note": {"chars": 230, "sentences": 4},
    "page3_summary_bullets": {"chars": 160, "lines": 3, "line_chars": 40},
    "transparency_bullets": {"chars": 320, "lines": 7, "line_chars": 42},
    "relation_analysis_text": {"chars": 430},
    "visibility_analysis_text": {"chars": 430},
    "improve_points_text": {"chars": 430},
    "next_action_text": {"chars": 380},
}

MIN_FILL_RATIO: Dict[str, float] = {
    "overall_summary": 0.86,
    "analysis_method": 0.88,
    "axis_output_logic_comment": 0.78,
    "axis_judgment_comment": 0.78,
    "axis_revision_comment": 0.78,
    "axis_agency_comment": 0.78,
    "axis_consistency_comment": 0.78,
    "responsibility_body": 0.88,
    "risk_bullets": 0.72,
    "summary_text": 0.80,
    "usage_note": 0.78,
}

FILLER_SENTENCES: Dict[str, List[str]] = {
    "overall_summary": [
        "AIを道具として使いながら、仕上げの責任を自分の側に残せています。",
        "迷った場面でも判断の軸へ戻れるため、提案や制作で強みになりやすい力です。",
    ],
    "axis_output_logic_comment": [],
    "axis_judgment_comment": [],
    "axis_revision_comment": [],
    "axis_agency_comment": [],
    "axis_consistency_comment": [],
    "summary_text": [
        "短時間で案を広げつつ、最終判断を自分の言葉で扱える点が強みです。",
    ],
    "usage_note": [
        "積み重ねるほど、AIに振り回されず自分の判断軸で進めやすくなります。",
    ],
    "responsibility_body": [
        "最終判断の所在が明確なため、AI利用後も自分の言葉で説明できます。",
        "生成結果は補助材料であり、成果物の責任主体は人に残ります。",
    ],
    "risk_bullets": [],
}

# フォーマット末尾に入れた行数指定に合わせる。
# display_width は日本語を約2幅で数えるため、1行あたり約34〜36幅を基準にする。
LINE_RULES: Dict[str, Dict[str, int]] = {
    "overall_summary": {"min": 110, "max": 150, "sentences": 3, "lines": 4},
    "axis_output_logic_comment": {"min": 175, "max": 205, "sentences": 5, "lines": 7},
    "axis_judgment_comment": {"min": 175, "max": 205, "sentences": 5, "lines": 7},
    "axis_revision_comment": {"min": 175, "max": 205, "sentences": 5, "lines": 7},
    "axis_agency_comment": {"min": 175, "max": 205, "sentences": 5, "lines": 7},
    "axis_consistency_comment": {"min": 175, "max": 205, "sentences": 5, "lines": 7},
    "summary_text": {"min": 135, "max": 160, "sentences": 4, "lines": 5},
    "usage_note": {"min": 145, "max": 170, "sentences": 4, "lines": 5},
    "responsibility_body": {"min": 170, "max": 210, "sentences": 5, "lines": 6},
    "risk_bullets": {"min": 145, "max": 170, "sentences": 4, "lines": 7},
}

JP_FONT_FAMILY = "BIZ UDP明朝 Medium"
BRAND_FONT_FAMILY = "Orbitron"
BRAND_TEXT_MARKERS = ("TLC imagine", "Certified by")
BRAND_CHAR_SPACING = 260
CERTIFICATE_BRAND_FONT_SIZE = 1600
BRAND_TEXT_COMPACT_MARKERS = ("tlcimagine", "certifiedby")
MOJIBAKE_TOKENS = ("繧", "縺", "譁ｭ", "蛻､", "菫ｮ", "蜈ｨ", "荳ｻ菴", "謌先棡")
TEMPLATE_CLONE_ONLY = False
FIXED_PAYLOAD_KEYS = {
    "target_work",
    "doc_id",
    "target_name",
    "analysis_method",
    "total_score",
    "strengths_title",
    "weaknesses_title",
    "meta_info",
    "responsibility_header",
    "responsibility_body",
    "aptitude_bullets",
    "transparency_bullets",
    "relation_analysis_text",
    "visibility_analysis_text",
    "improve_points_text",
    "next_action_text",
    "overall_total_score",
    "ai_capability_score",
    "ai_capability_evaluation",
    "output_logic_evaluation",
    "judgment_process_evaluation",
    "revision_process_evaluation",
    "agency_process_evaluation",
    "consistency_process_evaluation",
    "thought_output_relation",
    "third_party_visibility",
    "applicable_domain_text",
    "applicable_business_list",
    "page6_transparency_text",
    "page6_responsibility_structure",
    "page6_responsibility_body",
}

BANNED_AI_PHRASES = {
    "高い水準にある": "実務投入に耐える完成度です",
    "確認された": "読み取れます",
    "成立している": "機能しています",
    "評価される": "見なせます",
    "高い水準で成立しており": "実務に使える形でまとまっており",
}

USER_FACING_REPLACEMENTS = {
    "BODY本文が取得されており、ページ内容を直接評価できます。": "本文内容まで確認できています。",
    "BODY本文": "本文内容",
    "BODY": "ページ本文",
    "CTA_BUTTONS": "行動導線",
    "CTA": "行動導線",
    "SECTIONS": "ページ構成",
    "FETCH_MODE": "確認方式",
    "artifact": "アウトプット",
    "raw": "入力内容",
    "debug": "",
}
GUIDE_LINE_COLORS = {"FF0000", "00B050", "70AD47", "92D050", "00FF00"}
GREEN_GUIDE_COLORS = {"00B050", "70AD47", "92D050", "00FF00"}


def _safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = _sanitize_unicode_text(value)
    return text if text else default


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_text(value: Any) -> str:
    text = str(value or "")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def _normalize_replace_text(value: Any) -> str:
    """差し込み時は先頭改行を保持し、末尾だけ整える。"""
    text = str(value or "")
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def _ensure_heading_blank_line(text: str, heading: str) -> str:
    """指定見出しの直下に必ず1行空きを入れる。"""
    src = _normalize_replace_text(text)
    if not src:
        return src
    lines = src.splitlines()
    if not lines:
        return src

    def _norm(s: str) -> str:
        return re.sub(r"\s+", "", s)

    heading_norm = _norm(heading)
    first_norm = _norm(lines[0])
    if heading_norm not in first_norm:
        return src

    if len(lines) >= 2 and lines[1].strip() in ("", "\u200B", "\u2060"):
        return src
    lines.insert(1, "\u200B")
    return "\n".join(lines)


def _sanitize_unicode_text(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""

    # 制御文字除去（改行とタブは保持）
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    # 置換文字・不可視系の除去
    text = text.replace("\uFFFD", "").replace("\uFEFF", "")
    # ASCII疑問符は見た目崩れ原因になりやすいため全角へ
    text = text.replace("?", "？")
    # よく混入する非対応記号の正規化
    text = (
        text.replace("—", "―")
        .replace("–", "―")
        .replace("−", "―")
        .replace("~", "〜")
        .replace("·", "・")
    )
    return re.sub(r"[ \t]+", " ", text).strip()


def _is_mojibake_text(text: str) -> bool:
    if not text:
        return False
    return any(token in text for token in MOJIBAKE_TOKENS)


def _display_width(text: str) -> float:
    width = 0.0
    for ch in str(text or ""):
        if ch in "ilI.,:;!/|()[] ":
            width += 0.45
        elif ord(ch) < 128:
            width += 0.62
        else:
            width += 1.0
    return width


def _naturalize_generated_text(text: str) -> str:
    cleaned = _normalize_text(text)
    if not cleaned:
        return ""
    for src, dst in BANNED_AI_PHRASES.items():
        cleaned = cleaned.replace(src, dst)
    for src, dst in USER_FACING_REPLACEMENTS.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = cleaned.replace("成果物", "アウトプット")
    cleaned = re.sub(r"\bartifact\b", "アウトプット", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\braw\b", "入力内容", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdebug\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("未反映判断", "決めた内容の残し漏れ")
    cleaned = cleaned.replace("未反映の判断", "決めた内容の残し漏れ")
    cleaned = cleaned.replace("明文化", "言葉に残すこと")
    cleaned = cleaned.replace("接続根拠", "つながりの理由")
    cleaned = cleaned.replace("対応関係", "つながり")
    cleaned = cleaned.replace("反映整合", "反映のそろい")
    cleaned = cleaned.replace("粒度を揃える", "書き方を短くそろえる")
    cleaned = cleaned.replace("粒度をそろえる", "書き方を短くそろえる")
    cleaned = cleaned.replace("粒度", "詳しさ")
    cleaned = cleaned.replace("余地があります", "補うと伝わりやすくなります")
    cleaned = cleaned.replace("余地があり", "補う点があり")
    cleaned = cleaned.replace("余地が残", "補う点が残")
    cleaned = cleaned.replace("安定します", "ぶれにくくなります")
    cleaned = cleaned.replace("安定化できます", "次の案件でも使いやすくなります")
    cleaned = cleaned.replace("向上します", "伸びます")
    cleaned = cleaned.replace("高まります", "伝わりやすくなります")
    cleaned = cleaned.replace("確認できます", "読み取れます")
    cleaned = cleaned.replace("評価されます", "信頼につながります")
    # 重複した同文を抑制（再帰を避けるため簡易分割）
    rough = re.split(r"(?<=[。！？])", cleaned)
    sentences = [s.strip() for s in rough if s.strip()]
    if not sentences:
        return cleaned
    unique: List[str] = []
    seen: set[str] = set()
    for s in sentences:
        key = re.sub(r"\s+", "", s)
        if key in seen:
            continue
        seen.add(key)
        unique.append(s)
    return "".join(unique)


def _remove_internal_terms(text: str) -> str:
    cleaned = _sanitize_unicode_text(text)
    if not cleaned:
        return ""

    if _is_mojibake_text(cleaned):
        return ""

    for token in FORBIDDEN_TERMS:
        cleaned = cleaned.replace(token, "")

    cleaned = cleaned.replace("成果物", "アウトプット")
    cleaned = re.sub(r"\bartifact\b", "アウトプット", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\braw\b", "入力内容", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdebug\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+\s*/\s*500\b", "", cleaned)
    cleaned = re.sub(r"\b\d+\s*/\s*100\b", "", cleaned)
    cleaned = re.sub(r"総合点は[^。！？\n]*", "", cleaned)
    cleaned = cleaned.replace("確認できた根拠として、", "")
    cleaned = cleaned.replace("実務運用に耐える水準ですが、", "")
    cleaned = cleaned.replace("高い水準で成立しており、", "")
    cleaned = cleaned.replace("判断結果に再現性があります。", "")
    cleaned = cleaned.replace("成果物", "アウトプット")
    cleaned = re.sub(r"\bartifact\b", "アウトプット", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\braw\b", "入力内容", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bdebug\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"(?<!before/after)の変化と反映箇所", "before/afterの変化と反映箇所", cleaned)
    cleaned = re.sub(r"(?<!before/after)の差分、試行結果", "before/afterの差分、試行結果", cleaned)
    cleaned = re.sub(r"(before/after){2,}", "before/after", cleaned)
    cleaned = re.sub(r"\b\d+\s*点\b", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if _is_mojibake_text(cleaned):
        return ""
    return _naturalize_generated_text(cleaned)


def _is_incomplete_sentence(text: str) -> bool:
    t = text.rstrip("。！？ ").strip()
    if not t:
        return True
    bad_endings = (
        "で",
        "が",
        "を",
        "に",
        "は",
        "と",
        "の",
        "も",
        "へ",
        "から",
        "より",
        "まで",
        "や",
        "し",
    )
    return any(t.endswith(x) for x in bad_endings)


def _sentence_candidates(text: Any) -> List[str]:
    source = _remove_internal_terms(str(text or ""))
    if not source:
        return []

    source = source.replace("\n・", "\n")
    source = source.replace("。", "。\n")
    source = source.replace("！", "！\n")
    source = source.replace("？", "？\n")

    results: List[str] = []
    seen: set[str] = set()
    for raw in source.split("\n"):
        sentence = raw.strip(" ・-")
        if not sentence:
            continue
        sentence = re.sub(r"^(成果物論理性|判断プロセス|修正プロセス|判断主体性|全体整合性)\s*[：:]\s*", "", sentence)
        sentence = re.sub(r"^(長所|短所|改善示唆|改善点|活用適性分野|応用可能領域|リスク評価)\s*[：:]\s*", "", sentence)
        sentence = re.sub(r"^強みは", "", sentence)
        if sentence[-1] not in ("。", "！", "？"):
            sentence += "。"
        if len(sentence) < 8:
            continue
        if _is_incomplete_sentence(sentence):
            continue
        key = re.sub(r"\s+", "", sentence)
        if key in seen:
            continue
        seen.add(key)
        results.append(sentence)
    return results


def _fit_plain(text: Any, max_chars: int, fallback: str = "") -> str:
    if max_chars <= 0:
        return ""
    source = _remove_internal_terms(str(text or ""))
    if not source:
        source = _remove_internal_terms(fallback)
    if _display_width(source) <= max_chars:
        return source
    clipped = ""
    for ch in source:
        candidate = clipped + ch
        if _display_width(candidate) > max_chars:
            break
        clipped = candidate
    return clipped.strip()


def _fit_multiline_block(
    text: Any,
    *,
    max_total_chars: int,
    max_lines: int,
    max_line_chars: int,
    fallback: str = "",
) -> str:
    """
    改行を維持しつつ、総量・行数・1行幅を同時に抑える。
    4ページ目の可読性と枠内収まりを優先する。
    """
    if max_total_chars <= 0 or max_lines <= 0 or max_line_chars <= 0:
        return ""

    def _wrap_line(line: str) -> List[str]:
        src = _remove_internal_terms(line)
        if not src:
            return []
        out: List[str] = []
        buf = ""
        for ch in src:
            cand = buf + ch
            if _display_width(cand) > max_line_chars and buf:
                out.append(buf.strip())
                buf = ch
            else:
                buf = cand
        if buf.strip():
            out.append(buf.strip())
        return out

    def _build_lines(raw: str) -> List[str]:
        out: List[str] = []
        for ln in str(raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = ln.strip()
            if not line:
                continue
            parts = _wrap_line(line)
            if not parts:
                continue
            for part in parts:
                out.append(part)
                if len(out) >= max_lines:
                    return out
        return out

    lines = _build_lines(str(text or ""))
    if not lines:
        lines = _build_lines(str(fallback or ""))
    if not lines:
        return ""

    clipped: List[str] = []
    used = 0.0
    for line in lines:
        w = _display_width(line)
        if clipped and used + w > max_total_chars:
            break
        if not clipped and w > max_total_chars:
            # 単独行でも収まらない場合は行内でさらに切る
            small = ""
            for ch in line:
                cand = small + ch
                if _display_width(cand) > max_total_chars:
                    break
                small = cand
            if small.strip():
                clipped.append(small.strip())
            break
        clipped.append(line)
        used += w
        if len(clipped) >= max_lines:
            break
    return "\n".join(clipped).strip()


def _force_page4_breaks(text: str) -> str:
    src = str(text or "")
    if not src:
        return ""
    src = src.replace("\r\n", "\n").replace("\r", "\n")
    src = re.sub(r"。([②③])", r"。\n\1", src)
    src = re.sub(r"。([・])", r"。\n\1", src)
    src = re.sub(r"\n{3,}", "\n\n", src)
    return src.strip()


def _short_date(text: str) -> str:
    src = _safe_text(text)
    if not src:
        return datetime.now().strftime("%Y.%m.%d")
    m = re.search(r"(\d{4})[^\d]?(\d{1,2})[^\d]?(\d{1,2})", src)
    if m:
        return f"{int(m.group(1)):04d}.{int(m.group(2)):02d}.{int(m.group(3)):02d}"
    return src.replace("年", ".").replace("月", ".").replace("日", "").strip(". ")


def _display_doc_id(doc_id: str) -> str:
    src = _safe_text(doc_id)
    if re.fullmatch(r"\d{10,14}", src):
        return src
    return datetime.now().strftime("%Y%m%d%H%M%S")


def _display_url(url: str) -> str:
    source = _safe_text(url)
    if not source:
        return ""
    source = re.sub(r"^https?://", "", source)
    source = source.rstrip("/")
    if len(source) <= 32:
        return source
    parts = source.split("/", 1)
    host = parts[0]
    tail = f"/{parts[1]}" if len(parts) > 1 else ""
    if len(host) <= 24:
        shortened = f"{host}{tail[:8]}"
        return shortened[:32]
    return host[:29] + "..."


def _compact_target_work(text: str) -> str:
    source = _remove_internal_terms(text)
    if not source:
        return ""
    source = source.replace("webページ", "Web")
    source = source.replace("有料導線", "有料導線")
    source = re.sub(r"\s+", " ", source).strip()
    parts = [p.strip() for p in re.split(r"[｜|/\n]+", source) if p.strip()]
    unique: List[str] = []
    for part in parts:
        if part not in unique:
            unique.append(part)
    merged = " ｜ ".join(unique) if unique else source
    if _display_width(merged) <= FIELD_LIMITS["target_work"]["chars"]:
        return merged
    merged = merged.replace("AI活用能力可視化システム", "AI可視化")
    merged = merged.replace("システム", "")
    merged = merged.replace("  ", " ").strip()
    return merged


def _fit_prose(text: Any, max_chars: int, max_sentences: int, fallback: str) -> str:
    if max_chars <= 0:
        return ""

    candidates = _sentence_candidates(text)
    if not candidates:
        candidates = _sentence_candidates(fallback)

    out: List[str] = _pack_sentences(
        candidates,
        max_chars=max_chars,
        max_sentences=max_sentences,
        min_fill_ratio=0.0,
    )

    if out:
        return "".join(out)

    fallback_candidates = _sentence_candidates(fallback)
    for sentence in fallback_candidates:
        if _display_width(sentence) <= max_chars:
            return sentence
    return "評価情報を整理しました。"


def _fit_bullets(
    text: Any,
    max_lines: int,
    max_line_chars: int,
    max_total_chars: int,
    fallback_items: List[str],
) -> str:
    candidates = _sentence_candidates(text)
    bullets: List[str] = []
    bullet_keys: set[str] = set()
    total = 0

    def _expand_items(item_text: str) -> List[str]:
        # 文章途中切れや読点分割を避け、完全文だけを採用する
        base = _remove_internal_terms(item_text).rstrip("。！？").strip()
        if not base:
            return []
        if _display_width(base) <= max_line_chars:
            return [base]
        return []

    for sentence in candidates:
        if len(bullets) >= max_lines:
            break
        for item in _expand_items(sentence):
            if len(bullets) >= max_lines:
                break
            bullet = f"・{item}"
            key = re.sub(r"\s+", "", bullet)
            if key in bullet_keys:
                continue
            if total + _display_width(bullet) > max_total_chars:
                continue
            bullets.append(bullet)
            bullet_keys.add(key)
            total += _display_width(bullet)

    if len(bullets) < max_lines:
        for item in fallback_items:
            if len(bullets) >= max_lines:
                break
            for cleaned in _expand_items(item):
                if len(bullets) >= max_lines:
                    break
                bullet = f"・{cleaned}"
                key = re.sub(r"\s+", "", bullet)
                if key in bullet_keys:
                    continue
                if total + _display_width(bullet) > max_total_chars:
                    continue
                bullets.append(bullet)
                bullet_keys.add(key)
                total += _display_width(bullet)

    return "\n".join(bullets)


def _split_existing_bullets_for_layout(text: str, *, max_lines: int, max_line_chars: int) -> str:
    """既存の箇条書き文だけを、表示枠に合わせて改行分割する。"""
    src = _normalize_text(text)
    raw_items = [line.strip() for line in src.splitlines() if line.strip()]
    items: List[str] = []
    for raw in raw_items:
        clean = raw.lstrip("・").strip()
        if clean:
            items.append(clean)

    lines: List[str] = []
    for item in items:
        if len(lines) >= max_lines:
            break
        wrapped = _fit_multiline_block(
            item,
            max_total_chars=max_line_chars * max(1, max_lines - len(lines)),
            max_lines=max(1, max_lines - len(lines)),
            max_line_chars=max_line_chars,
            fallback=item,
        )
        parts = [part.strip() for part in wrapped.splitlines() if part.strip()]
        for part_index, part in enumerate(parts):
            if len(lines) >= max_lines:
                break
            prefix = "・" if part_index == 0 else "　"
            lines.append(prefix + part)
    return "\n".join(lines)


def _fit_bullets_full_sentence(
    text: Any,
    max_lines: int,
    max_line_chars: int,
    max_total_chars: int,
    fallback: str,
) -> str:
    lines: List[str] = []
    used_width = 0.0
    def _append_from(source: Any) -> None:
        nonlocal used_width
        for sentence in _sentence_candidates(source):
            if len(lines) >= max_lines:
                break
            content = sentence.rstrip("。！？").strip()
            if not content:
                continue
            if _display_width(content) > max_line_chars:
                continue
            bullet = f"・{content}"
            w = _display_width(bullet)
            if used_width + w > max_total_chars:
                break
            if bullet not in lines:
                lines.append(bullet)
                used_width += w

    _append_from(text)
    if not lines:
        _append_from(fallback)
    return "\n".join(lines)


def _collapse_cjk_spacing(text: str) -> str:
    """日本語文字間に混入した不要スペースを除去する。"""
    if not text:
        return ""
    # CJK + 半角/全角スペース + CJK を詰める
    return re.sub(r"([\u3040-\u30FF\u4E00-\u9FFF])[\u0020\u3000]+([\u3040-\u30FF\u4E00-\u9FFF])", r"\1\2", text)


def _dedupe_lines_by_keywords(text: str, keywords: List[str]) -> str:
    """同義キーワード重複行を1行にまとめる（見出し行は維持）。"""
    if not text:
        return ""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    kept: List[str] = []
    seen_kw: set[str] = set()
    for ln in lines:
        if ln.startswith("■"):
            kept.append(ln)
            continue
        matched = next((kw for kw in keywords if kw in ln), "")
        if matched:
            if matched in seen_kw:
                continue
            seen_kw.add(matched)
        if ln not in kept:
            kept.append(ln)
    return "\n".join(kept)


def _polish_axis_comment(text: str) -> str:
    """2Pの不自然な文接続を最小補正。"""
    out = _normalize_text(text)
    if not out:
        return ""
    # 例: 「明確さが 比較・取捨選択...」のような接続崩れを補正
    out = out.replace("明確さが 比較・採否", "明確さがあり、比較・取捨選択")
    out = out.replace("整合性が 比較", "整合性があり、比較")
    out = out.replace("根拠として、 、", "根拠として、")
    out = re.sub(r"([。！？])\1+", r"\1", out)
    return out


def _collect_fitted_sentences(text: Any, max_chars: int, max_sentences: int) -> List[str]:
    return _pack_sentences(
        _sentence_candidates(text),
        max_chars=max_chars,
        max_sentences=max_sentences,
        min_fill_ratio=0.0,
    )


def _pack_sentences(
    sentences: List[str],
    max_chars: int,
    max_sentences: int,
    min_fill_ratio: float,
) -> List[str]:
    if max_chars <= 0 or max_sentences <= 0:
        return []

    filtered: List[str] = []
    seen: set[str] = set()
    for sentence in sentences:
        s = _normalize_text(sentence)
        if not s:
            continue
        width = _display_width(s)
        if width > max_chars:
            continue
        key = re.sub(r"\s+", "", s)
        if key in seen:
            continue
        seen.add(key)
        filtered.append(s)
        if len(filtered) >= 24:
            break

    best: List[str] = []
    best_width = 0.0
    target = max_chars * max(0.0, min(0.98, min_fill_ratio))

    def _walk(idx: int, chosen: List[str], width_sum: float) -> None:
        nonlocal best, best_width
        if width_sum > max_chars:
            return

        better = False
        if width_sum > best_width:
            better = True
        elif abs(width_sum - best_width) < 0.01 and len(chosen) > len(best):
            better = True
        if better:
            best = list(chosen)
            best_width = width_sum

        if idx >= len(filtered) or len(chosen) >= max_sentences:
            return

        remaining_possible = width_sum
        for j in range(idx, min(len(filtered), idx + (max_sentences - len(chosen)))):
            remaining_possible += _display_width(filtered[j])
        if remaining_possible < best_width:
            return

        candidate = filtered[idx]
        w = _display_width(candidate)
        if width_sum + w <= max_chars:
            chosen.append(candidate)
            _walk(idx + 1, chosen, width_sum + w)
            chosen.pop()
        _walk(idx + 1, chosen, width_sum)

    _walk(0, [], 0.0)

    if best_width >= target:
        return best

    # 充填率に満たない場合は長い文優先で再度詰める
    filtered_sorted = sorted(filtered, key=_display_width, reverse=True)
    greedy: List[str] = []
    total = 0.0
    for sentence in filtered_sorted:
        if len(greedy) >= max_sentences:
            break
        w = _display_width(sentence)
        if total + w > max_chars:
            continue
        greedy.append(sentence)
        total += w
    if total > best_width:
        return greedy
    return best


def _fit_prose_full(
    text: Any,
    max_chars: int,
    max_sentences: int,
    fallback: str,
    min_fill_ratio: float,
    extra_sentences: List[str] | None = None,
) -> str:
    candidates = _sentence_candidates(text)
    if not candidates:
        candidates = _sentence_candidates(fallback)
    if extra_sentences:
        seen = {re.sub(r"\s+", "", s) for s in candidates}
        for sentence in _sentence_candidates("。".join(extra_sentences)):
            key = re.sub(r"\s+", "", sentence)
            if key in seen:
                continue
            seen.add(key)
            candidates.append(sentence)
    packed = _pack_sentences(
        candidates,
        max_chars=max_chars,
        max_sentences=max_sentences,
        min_fill_ratio=min_fill_ratio,
    )
    if packed:
        return "".join(packed)
    return _fit_prose(text, max_chars, max_sentences, fallback)


def _fit_dense_from_sources(
    sources: List[str],
    max_chars: int,
    max_sentences: int,
    min_fill_ratio: float,
    fallback: str,
    extra_sentences: List[str] | None = None,
) -> str:
    merged_candidates: List[str] = []
    seen: set[str] = set()

    for source in sources + (["。".join(extra_sentences)] if extra_sentences else []):
        for sentence in _sentence_candidates(source):
            key = re.sub(r"\s+", "", sentence)
            if key in seen:
                continue
            seen.add(key)
            merged_candidates.append(sentence)

    packed = _pack_sentences(
        merged_candidates,
        max_chars=max_chars,
        max_sentences=max_sentences,
        min_fill_ratio=min_fill_ratio,
    )
    if packed:
        return "".join(packed)

    return _fit_prose_full(
        " ".join(sources),
        max_chars=max_chars,
        max_sentences=max_sentences,
        fallback=fallback,
        min_fill_ratio=max(0.6, min_fill_ratio - 0.1),
        extra_sentences=extra_sentences,
    )


def _fit_to_line_rule(field_key: str, sources: List[str], fallback: str) -> str:
    rule = LINE_RULES.get(field_key)
    if not rule:
        limit = FIELD_LIMITS[field_key]
        return _fit_dense_from_sources(
            sources=sources,
            max_chars=limit["chars"],
            max_sentences=limit["sentences"],
            fallback=fallback,
            min_fill_ratio=MIN_FILL_RATIO.get(field_key, 0.78),
        )
    return _fit_dense_from_sources(
        sources=sources,
        max_chars=rule["max"],
        max_sentences=rule["sentences"],
        fallback=fallback,
        min_fill_ratio=rule["min"] / max(1, rule["max"]),
        extra_sentences=FILLER_SENTENCES.get(field_key),
    )


def _with_fixed_heading(heading: str, body: str, max_chars: int) -> str:
    head = _fit_plain(heading, max_chars, heading)
    remain = max(0, int(max_chars - _display_width(head)))
    if remain <= 8:
        return head
    b = _fit_plain(body, remain, "")
    if not b:
        return head
    return f"{head}{b}"


def _indent_prose_lines(text: str) -> str:
    """本文行のみ先頭を全角1文字下げる（見出し・箇条書きは除外）。"""
    src = _normalize_text(text)
    if not src:
        return ""
    out: List[str] = []
    for ln in src.splitlines():
        line = ln.rstrip()
        if not line:
            out.append("")
            continue
        stripped = line.lstrip()
        # 見出し直下の空行制御（\u200B）は空行として維持する
        if stripped in ("\u200B", "\u2060"):
            out.append("")
            continue
        if stripped.startswith(("■", "・", "-", "●")):
            out.append(stripped)
            continue
        if stripped.startswith("　"):
            out.append(stripped)
            continue
        out.append("　" + stripped)
    return "\n".join(out)


def _normalize_scores(data: Dict[str, Any]) -> Dict[str, int]:
    raw_scores = data.get("scores", {})
    normalized = {axis: 0 for axis in AXIS_ORDER}

    if isinstance(raw_scores, dict):
        for raw_key, raw_value in raw_scores.items():
            axis = AXIS_ALIASES.get(_safe_text(raw_key), _safe_text(raw_key))
            if axis in normalized:
                normalized[axis] = max(0, min(100, _safe_int(raw_value, 0)))

        # キーが壊れているケースへのフォールバック（順序対応）
        if sum(1 for v in normalized.values() if v > 0) <= 1 and len(raw_scores) == 5:
            vals = [max(0, min(100, _safe_int(v, 0))) for v in raw_scores.values()]
            for idx, axis in enumerate(AXIS_ORDER):
                normalized[axis] = vals[idx] if idx < len(vals) else 0

    # scores が崩れている場合の救済（axis_details から再構築）
    if sum(1 for v in normalized.values() if v > 0) <= 1:
        axis_details = data.get("axis_details", {})
        if isinstance(axis_details, dict):
            for raw_key, detail in axis_details.items():
                axis = AXIS_ALIASES.get(_safe_text(raw_key), _safe_text(raw_key))
                if axis not in normalized:
                    continue
                if isinstance(detail, dict):
                    normalized[axis] = max(0, min(100, _safe_int(detail.get("score"), normalized[axis])))

    return normalized


def _build_axis_comment(report_data: Dict[str, Any], axis: str, fallback: str) -> str:
    axis_blocks = report_data.get("axis_comment_blocks", {})
    axis_comments = report_data.get("axis_comments", {})
    source = ""

    if isinstance(axis_blocks, dict):
        source = _safe_text(axis_blocks.get(axis))
    if not source and isinstance(axis_comments, dict):
        source = _safe_text(axis_comments.get(axis))

    key = (
        "axis_output_logic_comment"
        if axis == "成果物論理性"
        else "axis_judgment_comment"
        if axis == "判断プロセス"
        else "axis_revision_comment"
        if axis == "修正プロセス"
        else "axis_agency_comment"
        if axis == "判断主体性"
        else "axis_consistency_comment"
    )
    limit = FIELD_LIMITS[key]
    return _fit_prose(source, limit["chars"], limit["sentences"], fallback)


def _axis_display_sentence(axis: str, score: int, visual_artifact: bool = False) -> str:
    if axis == "成果物論理性":
        if visual_artifact:
            if score >= 90:
                return "画面上の視覚的優先順位が整理され、情報密度と視線誘導が自然につながっています。"
            if score >= 75:
                return "視覚構成の芯は見えており、配置と強弱で初見の相手にも意図を届けやすい状態です。"
            return "画面構成の軸はありますが、余白や強弱で次に見る場所をもう少し示したい状態です。"
        if score >= 90:
            return "読み手が迷わず進める順番で、主張と行動がつながっています。"
        if score >= 75:
            return "構成の芯は見えており、初見の相手にも意図を届けやすい状態です。"
        return "構成の軸はありますが、読み手が次に何をすればよいかをもう少し示したい状態です。"
    if axis == "判断プロセス":
        if score >= 90:
            return "複数案を比べ、理由を添えて選ぶ判断ができています。"
        if score >= 75:
            return "判断の筋道は見えていますが、選んだ基準を短く残すと伝達が速くなります。"
        if score < 40:
            return "判断に関する記録は限られており、比較観点や採否理由を十分に追いにくい状態です。"
        if score < 60:
            return "判断に関する記録は一部見られますが、比較観点や採否理由は限定的です。"
        return "判断の記録は一部あります。比較した観点を残すと、自分でも後から選び直しやすくなります。"
    if axis == "修正プロセス":
        if score >= 90:
            return "一度で終わらせず、修正を重ねて完成度を上げられています。"
        if score >= 75:
            return "修正の流れはありますが、変更の狙いを残すと次の案件にも活かせます。"
        if score < 40:
            return "修正方針の記録は見られますが、変更理由や修正経緯を十分に確認しにくい状態です。"
        if score < 60:
            return "修正に関する記録は一部見られますが、変更理由や修正経緯は限定的です。"
        return "修正の動きはありますが、改善の狙いをもう一段明確にしたい状態です。"
    if axis == "判断主体性":
        if score >= 90:
            return "AI案を受け取りつつ、人が選び直して最終形を決められています。"
        if score >= 75:
            return "主導権は保たれていますが、差し戻した理由を残すと信頼が増します。"
        if score < 60:
            return "人による判断の記録は一部見られますが、最終判断の根拠を説明するには記録が不足しています。"
        return "主体性は見えていますが、なぜ選ばなかったかを残すと判断力が伝わります。"
    if visual_artifact:
        if score >= 90:
            return "ログ上の判断が画面上の配置、強弱、視線誘導に残り、見た目と意図がつながっています。"
        if score >= 75:
            return "大枠の流れは通っており、画面上の優先順位と判断記録の対応も確認できます。"
        return "主要な判断は残っていますが、配置や強弱に最後まで反映されたか見直したい状態です。"
    if score >= 90:
        return "決めた方針がアウトプットに残り、提出物としての筋が通っています。"
    if score >= 75:
        return "大枠の流れは通っていますが、最後の照合を入れると提出前の安心感が増します。"
    return "主要な判断は残っていますが、決めた内容が最後まで反映されたか見直したい状態です。"


def _axis_evidence_sentence(axis: str, source: str, visual_artifact: bool = False) -> str:
    cleaned = _remove_internal_terms(source)
    if not cleaned:
        return ""

    if axis == "成果物論理性":
        if visual_artifact:
            return "スクショ上の視覚構成、余白、情報密度まで見えているため、画面上の伝わり方を具体的に判断できます。"
        if "BODY本文" in source or "ページ内容" in source:
            return "本文内容まで見えているため、構成と伝わり方を具体的に判断できます。"
        if "未反映" in source:
            return "一部の判断は最終形への残し方が弱く、なぜその構成にしたかを補いたい箇所です。"
    elif axis == "判断プロセス":
        if "比較" in cleaned or "採否" in cleaned:
            return "比較、取捨選択、理由がつながり、自分の判断を振り返りやすい記録です。"
    elif axis == "修正プロセス":
        if "複数回" in cleaned or "構造修正" in cleaned:
            return "単発の直しではなく、構造まで見直して品質を上げる姿勢が見えます。"
    elif axis == "判断主体性":
        if "主導権" in cleaned or "最終判断" in cleaned:
            return "外部案をそのまま通さず、人が選んで仕上げている点が信頼につながります。"
    elif axis == "全体整合性":
        if visual_artifact:
            return "ログ上の判断と画面上の配置、強弱、視線誘導の対応を確認できます。"
        if "未反映" in cleaned:
            return "決めた内容が残りきらない箇所があるため、提出前の照合が効果的です。"
        if "反映" in cleaned:
            return "決めた内容がアウトプットに残っており、説明と実物のずれを抑えられています。"

    candidates = _sentence_candidates(cleaned)
    if not candidates:
        return ""
    first = candidates[0]
    if _display_width(first) <= 42:
        return first
    return ""


def _display_axis_comment(report_data: Dict[str, Any], axis: str, score: int, fallback: str) -> str:
    axis_blocks = report_data.get("axis_comment_blocks", {})
    axis_comments = report_data.get("axis_comments", {})
    source = ""
    if isinstance(axis_blocks, dict):
        source = _safe_text(axis_blocks.get(axis))
    if not source and isinstance(axis_comments, dict):
        source = _safe_text(axis_comments.get(axis))

    source_context = report_data.get("evaluation_source", {})
    source_mode = _safe_text(source_context.get("mode")) if isinstance(source_context, dict) else ""
    visual_artifact = source_mode in {"artifact_image_set", "screenshot_lp"} or _is_visual_artifact_context(source)

    first = _axis_display_sentence(axis, score, visual_artifact=visual_artifact)
    evidence = _axis_evidence_sentence(axis, source, visual_artifact=visual_artifact)
    if not evidence and score >= 70:
        evidence = fallback
    source_sentences = _collect_fitted_sentences(source, 220, 2)

    candidates: List[str] = [first]
    if evidence:
        candidates.append(evidence)
    for s in source_sentences:
        if s and s not in candidates:
            candidates.append(s)

    key = (
        "axis_output_logic_comment"
        if axis == "成果物論理性"
        else "axis_judgment_comment"
        if axis == "判断プロセス"
        else "axis_revision_comment"
        if axis == "修正プロセス"
        else "axis_agency_comment"
        if axis == "判断主体性"
        else "axis_consistency_comment"
    )
    comment = _fit_to_line_rule(key, candidates, first + evidence)
    return _polish_axis_comment(comment)


def _build_overall_summary(report_data: Dict[str, Any], scores: Dict[str, int]) -> str:
    top_axis = max(scores.items(), key=lambda x: x[1])[0] if scores else "判断プロセス"
    weak_axis = min(scores.items(), key=lambda x: x[1])[0] if scores else "全体整合性"

    first_map = {
        "成果物論理性": "アウトプットの構成は整理され、主張も伝わりやすい状態です。",
        "判断プロセス": "比較と理由が明確で、判断の流れに迷いがありません。",
        "修正プロセス": "修正は段階的に進み、完成度を丁寧に高めています。",
        "判断主体性": "AI案を選別しながら、人が主導権を保てています。",
        "全体整合性": "決めた内容がアウトプットに反映され、全体の流れも安定しています。",
    }
    second_map = {
        "成果物論理性": "構成意図を一文添えると、初見の相手にも価値が届きやすくなります。",
        "判断プロセス": "優先順位の書き分けが増えると、会議や企画の場で説明しやすくなります。",
        "修正プロセス": "変更理由を短く残すと、改善内容を次の案件にも活かせます。",
        "判断主体性": "差し戻し理由を残せると、主体性の強さがより明確になります。",
        "全体整合性": "決めた内容を最後に照合すると、提出前の安心感が増します。",
    }
    text = first_map.get(top_axis, "判断と修正の流れは整理されており、全体の完成度は安定しています。")
    if weak_axis != top_axis:
        text += second_map.get(weak_axis, "判断理由を短く残すと、自分の選択を後から見直しやすくなります。")
    total = sum(max(0, min(100, _safe_int(value))) for value in scores.values())
    if total >= 350:
        text += "本件は確認できる判断記録とアウトプット反映をもとに評価しています。"
        text += "今後は決めた内容を最後に見直し、判断理由を短く同じ形で残すことで、選択の再現性が高まります。"
    else:
        text += "本件は判断記録や修正経緯に不足が残るため、確認できた内容に限定して評価しています。"
        text += "今後は採否理由、修正理由、反映箇所を残すことで、判断の流れを追いやすくする必要があります。"

    axis_comments = report_data.get("axis_comments", {})
    top_axis_comment = ""
    weak_axis_comment = ""
    if isinstance(axis_comments, dict):
        top_axis_comment = _remove_internal_terms(_safe_text(axis_comments.get(top_axis)))
        weak_axis_comment = _remove_internal_terms(_safe_text(axis_comments.get(weak_axis)))

    return _fit_to_line_rule(
        "overall_summary",
        sources=[
            text,
            _safe_text(report_data.get("overall_comment")),
            top_axis_comment,
            weak_axis_comment,
            _safe_text(report_data.get("improve_text")),
        ],
        fallback=text,
    )


def _integrate_strengths_into_overall(text: str) -> str:
    return _single_line_prose(_normalize_text(text))


def _single_line_prose(text: Any) -> str:
    clean = _remove_internal_terms(_safe_text(text))
    clean = clean.replace("\r\n", "\n").replace("\r", "\n")
    clean = re.sub(r"^[・\-]\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"^[①②③④⑤]\s*", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"\s*\n+\s*", "", clean)
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()


def _humanize_transferable_prose(text: Any) -> str:
    """履歴書・面接回答に転用しやすい自然な言い回しへ寄せる。"""
    clean = _single_line_prose(text).replace("アウトプット", "成果物")
    replacements = [
        ("できるほか、", "でき、"),
        ("することで、", "すると、"),
        ("行うことで、", "行うと、"),
        ("が成立している", "を作れます"),
        ("が保持されている", "を残しています"),
        ("として機能している", "として使っています"),
        ("が確認可能な状態", "を確認しています"),
        ("を追跡可能な状態", "を後から追える形にしています"),
        ("へ接続している", "につなげています"),
        ("品質を高められる", "改善を進められる"),
        ("品質を高める", "改善する"),
        ("最適化", "見直し"),
        ("アウトプット構成", "成果物の流れ"),
        ("行動導線", "次の行動"),
        ("採否", "採用する内容"),
    ]
    for before, after in replacements:
        clean = clean.replace(before, after)
    clean = re.sub(r"(比較)の比較検討", r"\1検討", clean)
    clean = clean.replace("構成の構成", "構成")
    clean = clean.replace("修正の改善", "改善")
    clean = re.sub(r"(できます。)(また、)?\1+", r"\1", clean)
    clean = re.sub(r"、{2,}", "、", clean)
    clean = re.sub(r"。{2,}", "。", clean)
    stripped = clean.strip("、。 ")
    return stripped + ("。" if stripped else "")


def _strip_list_markers_to_prose(text: Any) -> str:
    lines = []
    for line in _safe_text(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = re.sub(r"^\s*[・\-]\s*", "", line)
        line = re.sub(r"^\s*[①②③④⑤]\s*", "", line)
        line = line.strip()
        if line:
            lines.append(line)
    return _single_line_prose("".join(lines))


def _build_analysis_method(report_data: Dict[str, Any], scores: Dict[str, int]) -> str:
    # 1ページ目左欄は固定文（フォーマット準拠）
    return (
        "■ 解析方法\n\n"
        "本解析は、対話ログおよびアウトプット、並びに両者の因果関係または対応関係を基礎データとし、"
        "当該関係に基づいて処理状態情報を生成し、当該処理状態情報を可視化するものです。"
        "解析は以下の情報に基づいて実施しています。"
        "対話ログ（対話履歴・修正履歴・生成履歴）、アウトプット、対話ログとアウトプットの因果関係または対応関係。"
    )


def _build_aptitude_fallback_items() -> List[str]:
    return [
        "構造設計業務（アプリ構造設計・仕様設計）",
        "意思決定業務（方針決定・重要判断）",
        "改善業務（プロセス改善・仕様見直し）",
    ]


def _build_page3_summary_items() -> List[str]:
    return [
        "比較して選ぶ作業でAIを活かせます",
        "修正を重ねる制作運用に向いています",
        "最終判断が必要な提案業務にも使えます",
    ]


def _build_aptitude_short_items(text: str) -> List[str]:
    source = _remove_internal_terms(text)
    mapping = [
        (("企画", "要件", "構造", "仕様"), "構造設計業務（アプリ構造設計・仕様設計）"),
        (("判断", "方針", "意思決定", "採否"), "意思決定業務（方針決定・重要判断）"),
        (("改善", "運用", "修正", "見直し"), "改善業務（プロセス改善・仕様見直し）"),
    ]
    items: List[str] = []
    for keys, label in mapping:
        if any(k in source for k in keys):
            items.append(label)
    for fallback in _build_aptitude_fallback_items():
        if fallback not in items:
            items.append(fallback)
        if len(items) >= 3:
            break
    return items[:3]


def _build_growth_note(report_data: Dict[str, Any]) -> str:
    base = _safe_text(report_data.get("improve_text"))
    risk = _safe_text(report_data.get("risk_text"))
    text = (
        "同じ型で使い続けるほど、案を選ぶ時の迷いが減っていきます。"
        "説明の材料が蓄積され、制作後の振り返りにも強くなります。"
        "改善の型が身につけば、次の案件でも品質を再現しやすくなります。"
        "AIを速さだけでなく、考えを整える相棒として扱えるようになります。"
    )
    if "QR" in base or "QR" in risk:
        text += "共有導線まで意識できると、見せた後の行動設計にも強くなります。"
    if "視覚設計" in base or "視覚設計" in risk:
        text += "見た目の判断軸が育つほど、デザイン判断も自分の言葉で扱いやすくなります。"
    return text


AXIS_LABEL_MAP: Dict[str, str] = {
    AXIS_ORDER[0]: "アウトプットの論理性",
    AXIS_ORDER[1]: "判断プロセス",
    AXIS_ORDER[2]: "修正プロセス",
    AXIS_ORDER[3]: "判断主体性",
    AXIS_ORDER[4]: "全体整合性",
}


def _clean_report_sentence(text: str) -> str:
    src = _remove_internal_terms(_safe_text(text))
    if not src:
        return ""
    src = src.replace("高い水準", "実務で使える状態")
    src = src.replace("成立している", "形になっている")
    src = src.replace("確認された", "読み取れた")
    src = src.replace("評価される", "判断できる")
    src = re.sub(r"\s+", "", src)
    src = re.sub(r"(。)\1+", "。", src)
    return src


def _first_fact_sentence(*texts: str) -> str:
    for t in texts:
        for s in _sentence_candidates(_clean_report_sentence(t)):
            if _display_width(s) >= 12:
                return s
    return ""


def _humanize_fact_sentence(axis: str, fact: str) -> str:
    """生の評価断片を、商品レポート向けの意味ある一文へ寄せる。"""
    src = _clean_report_sentence(fact)
    if not src:
        return ""
    if axis == AXIS_ORDER[0] and ("本文" in src or "構成評価" in src or "確認" in src):
        return "ページ本文まで見たうえで、主張と読み進める流れを捉えられています。"
    if axis == AXIS_ORDER[1] and ("比較" in src or "採否" in src or "理由" in src):
        return "選択肢を並べるだけでなく、選んだ理由まで自分の言葉で扱えています。"
    if axis == AXIS_ORDER[2] and ("複数回" in src or "修正" in src or "完成度" in src):
        return "一度の修正で止めず、段階を踏んで仕上げに近づけています。"
    if axis == AXIS_ORDER[3] and ("AI案" in src or "最終判断" in src or "そのまま" in src):
        return "AIの案を材料として扱い、最後は自分の判断で整えています。"
    if axis == AXIS_ORDER[4] and ("QR" in src or "視覚設計" in src or "導線" in src):
        return ""
    return src


def _short_fact_from_sources(axis: str, *texts: str) -> str:
    joined = _clean_report_sentence("。".join(t for t in texts if t))
    for sentence in _sentence_candidates(joined):
        if _display_width(sentence) <= 54 and _display_width(sentence) >= 18:
            return sentence
    if axis == AXIS_ORDER[0]:
        return "ログ内で構成順序と導線判断が確認される。"
    if axis == AXIS_ORDER[1]:
        return "ログ内で比較、採否、理由づけが確認される。"
    if axis == AXIS_ORDER[2]:
        return "ログ内で修正意図と変更手順が確認される。"
    if axis == AXIS_ORDER[3]:
        return "ログ内でAI案の採否判断が確認される。"
    return "ログ内で判断内容と最終反映が確認される。"


def _context_markers(*texts: str) -> Dict[str, str]:
    src = _clean_report_sentence("。".join(t for t in texts if t))

    target = "アウトプット"
    if "LP" in src or "ランディング" in src:
        target = "LP"
    elif "資料" in src:
        target = "資料"
    elif "ページ" in src:
        target = "ページ"

    route = "導線"
    if "CTA" in src or "ボタン" in src:
        route = "CTA"
    elif "有料導線" in src:
        route = "有料導線"
    elif "行動導線" in src:
        route = "行動導線"

    structure = "構成"
    if "構成順" in src or "説明順" in src:
        structure = "構成順"
    elif "見出し" in src:
        structure = "見出し構成"
    elif "配置" in src:
        structure = "配置"

    return {"target": target, "route": route, "structure": structure}


def _is_visual_artifact_context(*texts: str) -> bool:
    src = "。".join(_safe_text(t) for t in texts if t)
    markers = [
        "artifact_image_set",
        "画像成果物評価",
        "画像・スクショ",
        "スクリーンショット",
        "スクショ",
        "視覚構成",
        "余白設計",
        "情報密度",
        "視線導線",
        "UI構成",
    ]
    return any(marker in src for marker in markers)


def _rewrite_visual_artifact_report_text(text: Any) -> str:
    """Screenshot-only reports should describe visual structure, not fetched page text."""
    rewritten = _safe_text(text)
    if not rewritten:
        return ""

    replacements = [
        ("LP構成", "画面構成"),
        ("本文配置", "配置バランス"),
        ("本文順", "視覚的優先順位"),
        ("見出し順", "視覚的優先順位"),
        ("説明接続", "情報接続"),
        ("主張から根拠", "重要情報から視線誘導"),
        ("主張、根拠、行動導線", "情報優先順位、強弱、視線誘導"),
        ("読み順", "視線の流れ"),
        ("行動導線", "視線誘導"),
        ("有料導線", "視線誘導"),
        ("導線配置", "視線誘導設計"),
        ("導線構造", "視線誘導構造"),
        ("導線選定", "視線誘導設計"),
        ("導線位置", "視線誘導位置"),
        ("導線調整", "視線誘導調整"),
        ("ページ本文", "画面情報"),
        ("本文内容", "表示情報"),
        ("本文", "表示情報"),
        ("説明順", "視覚的優先順位"),
        ("見出し構成", "UI階層"),
        ("構成順", "レイアウト順"),
        ("構成判断", "レイアウト判断"),
        ("最終構成", "最終レイアウト"),
        ("構成接続", "レイアウト接続"),
        ("構成反映", "レイアウト反映"),
        ("出力構造", "画面構造"),
        ("表示構造", "視覚構造"),
        ("理解経路", "視線経路"),
        ("読み手が情報を理解して行動へ進む過程", "見る人が重要情報を見つけ、次の判断へ進む過程"),
        ("訴求の入口から視線誘導まで", "視覚的な入口から重要情報、視線誘導まで"),
    ]
    for before, after in replacements:
        rewritten = rewritten.replace(before, after)
    return rewritten


def _extract_prefixed_line(text: str, prefix: str) -> str:
    for row in str(text or "").splitlines():
        stripped = row.strip()
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()
    return ""


def _split_marker_values(text: str) -> List[str]:
    return [part.strip() for part in str(text or "").split("/") if part.strip()]


def _lp_specific_summary(*texts: str) -> Dict[str, str]:
    src = "\n".join(str(t or "") for t in texts if str(t or "").strip())
    title = _extract_prefixed_line(src, "PAGE_TITLE:")
    h1 = _split_marker_values(_extract_prefixed_line(src, "H1:"))
    cta = _split_marker_values(_extract_prefixed_line(src, "CTA_BUTTONS:"))
    links = _split_marker_values(_extract_prefixed_line(src, "LINK_TEXTS:"))
    headline = h1[0] if h1 else title
    action = cta[0] if cta else (links[0] if links else "")
    return {
        "title": _remove_internal_terms(title),
        "headline": _remove_internal_terms(headline),
        "action": _remove_internal_terms(action),
    }


def _lp_specific_phrase(*texts: str) -> str:
    summary = _lp_specific_summary(*texts)
    headline = summary.get("headline", "")
    action = summary.get("action", "")
    title = summary.get("title", "")
    if headline and action:
        return f"取得したLPでは「{headline}」と「{action}」が確認できる。"
    if headline:
        return f"取得したLPでは「{headline}」が確認できる。"
    if title:
        return f"取得したWebページ「{title}」を評価対象に含めている。"
    return ""


def _evaluation_rate(total_score: int | None) -> int:
    score = _safe_int(total_score, 0)
    rate = score / 500.0 * 100
    return int(round(max(15, min(85, rate))))


def _improvement_rate(total_score: int | None) -> int:
    return 100 - _evaluation_rate(total_score)


def _build_ai_capability_evaluation(
    source_text: str,
    improve_text: str,
    weakness_text: str,
    score: int = 0,
    total_score: int | None = None,
) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    eval_rate = _evaluation_rate(total_score)

    if eval_rate < 40:
        comment = (
            "AI利用の記録と、人が判断に関わった痕跡は確認できる。"
            "AI案に対して不要点を示したり、修正方向を変えたりした発言は、人が成果物づくりに関与した根拠になる。"
            "比較検討、修正、採否の入口となる記録も一部残っている。"
            f"一方で、判断・修正・採否の流れと{target}の{structure}や{route}との対応はまだ薄い。"
        )
        relation = (
            "確認できた判断を起点に評価するが、理由や反映箇所は継続して追えるほど残っていない。"
            f"{target}のどこに判断が反映されたかを残すと、AI利用と成果物のつながりを説明しやすくなる。"
            f"構成、本文、{route}のどこへ修正が移ったかを残すことが次の評価材料になる。"
            "どの判断が成果物へつながったかを補う余地がある。"
        )
        conclusion = "この利用者は、AI案に対して違和感や不要点を示しながら、成果物づくりに関与している段階である。現時点では人が判断した痕跡を評価しつつ、判断理由、採否理由、修正経緯を増やすことで、AIをどう使ったかを説明しやすくなる。"
    elif eval_rate < 60:
        comment = (
            f"AI案をそのまま採用せず、{target}の{structure}や{route}を見ながら判断した記録が見られる。"
            "比較、修正、採否の材料も一部確認できる。"
            "不要な案を見送り、別の方式へ寄せた発言は、AIを材料として使いながら人が選別した根拠になる。"
            f"構成、本文、{route}への反映も一部読み取れる。"
        )
        relation = (
            "ログ上の判断とアウトプットの対応は一部追える。"
            f"特に、採用した内容や削った内容が{target}の表示順や{route}に影響した箇所は評価材料になる。"
            "判断から修正へ進み、その修正が成果物側へ移った箇所では、AI活用の流れを説明できる。"
            "一方で、判断理由や修正経緯はまだ記録の粒度にばらつきがある。"
        )
        conclusion = (
            "この利用者は、AI案を比較材料として使い、採用する内容と見送る内容を人が選びながら成果物へ近づけている。"
            "現状は評価材料と改善余地が併存する段階であり、採否理由、修正経緯、反映箇所を補うことで、AI活用の過程をより明確に説明できる。"
        )
    elif eval_rate < 80:
        comment = (
            f"AI案を材料にしながら、{target}の{structure}や{route}に関する判断・修正・採否が確認できる。"
            "成果物への反映も記録が残る範囲で読み取れる。"
            "比較した案から必要なものを選び、不要な要素を見送る流れがあるため、単なるAI出力の転記ではない。"
            f"構成、本文順、{route}の調整にも人の判断が表れている。"
        )
        relation = (
            "判断内容とアウトプットの対応は概ね確認できる。"
            f"人が選んだ内容は、{structure}、本文順、{route}の調整として成果物側にも表れている。"
            "ログ上の判断から修正へ進み、その結果が成果物に残るため、AI利用と完成形の関係を説明しやすい。"
            "改善点は、判断理由、採否理由、修正経緯を同じ粒度で残すことである。"
        )
        conclusion = "この利用者は、AIを案出しや整理の補助として使いながら、比較、採否、修正方針を人側で決めて成果物へ反映している。現在は実務で使える判断過程が見える段階であり、理由と反映箇所がそろうほど評価根拠はさらに明確になる。"
    else:
        comment = (
            f"AI案をそのまま採用せず、{target}の{structure}や{route}を判断材料にし、"
            "ログ上の判断・修正・採否の流れと最終アウトプットへの反映の対応を確認できる。"
            "比較した案を選別し、採用する内容と見送る内容を分けた記録も残っている。"
            f"構成、本文、{route}へ判断が移った範囲も総合評価の根拠になる。"
        )
        relation = (
            "ログ上の判断・修正・採否の流れとアウトプットとの対応は概ね確認できる。"
            f"判断は{structure}、本文順、{route}の調整に結びつき、成果物の読み順や導線設計へ反映されている。"
            "判断から修正、成果物反映までのつながりが残るため、AIをどう使って完成形へ近づけたかを説明しやすい。"
            "各判断が最終形にどのように関係したかも、記録が残る範囲で確認できる。"
        )
        conclusion = (
            "この利用者は、AIを情報生成支援として使いながら、比較、採否、修正方針、最終反映を人側で管理している。"
            "AIに任せきるのではなく、成果物の構成や導線に合わせて判断を加えている点が強みであり、判断の理由と反映先がそろうほど、AI活用能力の説明力も高くなる。"
        )
    return "\n".join(
        [
            "①評価",
            comment,
            "②因果関係",
            relation,
            "③結論",
            conclusion,
        ]
    )


def _build_output_logic_evaluation(
    source_text: str,
    improve_text: str,
    weakness_text: str,
    score: int = 0,
    total_score: int | None = None,
) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    lp_phrase = _lp_specific_phrase(source_text, improve_text, weakness_text)
    eval_rate = _evaluation_rate(total_score)

    if eval_rate < 40:
        evaluation = (
            (lp_phrase if lp_phrase else "")
            + f"{target}の主張、根拠、{route}の順序に評価材料は見られる。"
            "AI案をそのまま並べるのではなく、読み手に伝える順序を選ぼうとした痕跡がある。"
            f"ただし、{structure}や本文配置とのつながりはまだ補強が必要である。"
        )
        relation = (
            "ログ上の構成順、修正内容、採否判断と最終表示との対応は一部見られる。"
            "採用した情報と見送った情報の差が残るほど、なぜその表示順になったかを説明しやすくなる。"
            f"判断が見出し、本文、{route}のいずれに対応するかが残る部分は、論理性の根拠になる。"
            f"反映箇所を残すと、見出し順、本文配置、{route}との関係を説明しやすい。"
        )
        conclusion = "確認できた構成材料を評価し、判断理由と反映箇所の記録を次の改善点とする。対応が残る部分は評価材料になり、成果物の論理性を説明する根拠にもなる。"
    elif eval_rate < 60:
        evaluation = (
            (lp_phrase if lp_phrase else "")
            + f"{target}の主張、根拠、{route}の順序にはまとまりが見られる。"
            "見出し、本文、行動導線を別々に置くのではなく、読み手の流れに合わせて整理しようとした記録がある。"
            f"{structure}や本文配置も一部評価できる。"
        )
        relation = (
            "ログ上の構成順、修正内容、採否判断と、見出し順、本文配置、導線との対応は一部見られる。"
            "採用した内容がどの見出しや導線へ移ったかが残る範囲では、成果物との関係も説明できる。"
            f"特に、{route}や表示順の調整は、読み手を次の行動へ進める設計判断として評価できる。"
            "改善点は、どの判断がどこへ反映されたかをそろえることである。"
        )
        conclusion = "情報の提示順、説明のつながり、導線配置を評価しつつ、判断理由と反映記録の粒度を補う。確認範囲も評価材料になり、論理性の根拠として扱える。"
    else:
        evaluation = (
            (lp_phrase if lp_phrase else "")
            + f"{target}は、主張から根拠、{route}までの順序に一定のまとまりがある。"
            "AIが出した候補を材料にしつつ、読み手が理解しやすい順序へ整理した点も評価材料になる。"
            f"{structure}と本文配置も読み順の判断材料として確認できる。"
        )
        relation = (
            "ログ上の構成順、修正内容、採否判断と、見出し順、本文配置、導線の対応を一部確認できる。"
            "判断内容が表示順や導線に結びつくことで、成果物の論理展開を支える関係が生まれている。"
            f"AI案から残した要素が{structure}や{route}へ反映されている点も評価根拠になる。"
            "評価は、実際に残っている判断記録と表示結果の対応範囲に基づく。"
        )
        conclusion = "情報の提示順、説明のつながり、導線配置は確認できる範囲で評価できる。判断記録との対応も評価材料になり、なぜその成果物構成になったかを説明する根拠になる。"
    return "\n".join(
        [
            "①評価",
            evaluation,
            "②因果関係",
            relation,
            "③結論",
            conclusion,
        ]
    )


def _build_judgment_process_evaluation(
    source_text: str,
    improve_text: str,
    weakness_text: str,
    score: int = 0,
    total_score: int | None = None,
) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    eval_rate = _evaluation_rate(total_score)

    if eval_rate < 40:
        evaluation = (
            "判断に関する記録は一部見られ、AI案をそのまま受け取っていない点は評価できる。"
            "比較や採否を行った痕跡も残っている。"
            "短い発言であっても、不要と判断した内容や戻すと決めた内容は、人が選別した根拠になる。"
        )
        relation = (
            f"一方で、比較観点、採否理由、{target}の{structure}や{route}との関係はまだ薄い。"
            "判断そのものは見えるが、なぜその選択をしたかが残るほど成果物との関係は説明しやすい。"
            "どの判断が成果物へつながったかは追加記録が必要である。"
        )
        conclusion = "確認できた判断を土台に、選んだ理由と見送った理由、反映先の関係を補う段階である。残った判断は評価材料になり、判断プロセスの入口として扱える。"
    elif eval_rate < 60:
        evaluation = (
            "AI案をそのまま通さず、比較や採否の判断が行われている。"
            "候補の中から残す内容と削る内容を分けており、目的に合わせて人が判断した流れが見られる。"
            f"{target}の{structure}選択と表示順にも一部対応が見られる。"
        )
        relation = (
            "ログ上の採否判断や優先順位と、構成選択、導線配置、表示順との対応は一部見られる。"
            "採用した判断が見出し順や導線位置に反映されることで、判断と成果物の関係が読み取りやすくなる。"
            "比較から採用・不採用までの分岐が残る箇所は、判断プロセスの評価根拠になる。"
            "判断過程と結果の対応は、記録の粒度をそろえるとさらに伝わりやすい。"
        )
        conclusion = "判断履歴を評価しつつ、採用理由、見送った内容、成果物への反映先の関係を次に補う。確認できた採否は、判断プロセスの評価根拠になる。"
    else:
        evaluation = (
            "AI案を比較し、採否や優先順位を自分で判断した記録が確認できる。"
            "必要な案を残し、不要な案を見送る流れがあるため、AI任せではなく人の判断で方向を決めている。"
            f"{target}の{structure}選択と表示順にも対応が見られる。"
        )
        relation = (
            "採否判断と構成選択、導線配置、表示順との対応を記録から読み取れる。"
            "判断が成果物の配置や導線に反映されることで、比較検討が最終形へつながった根拠になる。"
            "比較から採用・不採用までの分岐が成果物要素へつながる点も、判断プロセスの評価を支える。"
            "一方で、判断理由の粒度をそろえると第三者にも意図が伝わりやすい。"
        )
        conclusion = "比較、採否、反映の流れが残ることで、なぜその成果物構成になったのかを説明しやすい。比較した観点と採否理由を同じ形式で残し、反映先までそろうほど、判断の質と点数の根拠も明確になる。"
    return "\n".join(
        [
            "①評価",
            evaluation,
            "②因果関係",
            relation,
            "③結論",
            conclusion,
        ]
    )


def _build_revision_process_evaluation(
    source_text: str,
    improve_text: str,
    weakness_text: str,
    score: int = 0,
    total_score: int | None = None,
) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    eval_rate = _evaluation_rate(total_score)

    if eval_rate < 40:
        evaluation = (
            "修正方針や変更の動きは確認できる。"
            "成果物を直しながら進めた痕跡も残っている。"
            "方式を変える、戻す、削るといった発言は、完成形へ向けて人が調整した根拠になる。"
            "差分、修正理由、反映箇所はまだ補強が必要である。"
        )
        relation = (
            f"{target}の{structure}や{route}へ影響した修正は一部見られるが、対応関係は追い切れない箇所がある。"
            "修正方針が成果物の表示や導線へどう反映されたかを残すと、改善の流れを説明しやすい。"
            "修正前後の違いを残すと評価材料が増える。"
        )
        conclusion = "確認できた修正内容を評価し、次は変更理由、差分、反映箇所を残す段階である。修正方針そのものは評価材料になり、記録が増えるほど改善プロセスとして読み取りやすくなる。"
    elif eval_rate < 60:
        evaluation = (
            "修正判断と変更方針は見られ、改善に向けて手を入れた流れが確認できる。"
            "修正前後の違いや反映先も一部読み取れる。"
            "不要な機能を外す、表示を変える、取得方式を変えるといった判断は、成果物を目的へ近づける修正として評価できる。"
            f"{target}の{structure}、配置、{route}との対応も一部見られる。"
        )
        relation = "ログ上の修正判断と最終形の対応は一部見える。修正内容が構成、配置、導線へ反映されることで、改善判断が成果物へつながった根拠になる。改善点は、修正理由、差分、反映箇所を同じ粒度で残すことである。"
        conclusion = "修正判断と最終形の対応が残ることで、どの変更方針が成果物の改善へつながったのかを説明しやすい。変更理由と反映箇所をそろえるほど、改善を重ねた過程も安定した評価材料になる。"
    else:
        evaluation = (
            "修正判断、変更方針、反映先の記録が確認できる。"
            "修正を重ねながら成果物を整えた流れも見える。"
            "AI案を受けた後に、そのまま進めず、表示方法や取得方式を調整した点も評価根拠になる。"
            f"{target}の{structure}、配置、{route}との対応も読み取れる。"
        )
        relation = (
            "ログ上の修正判断と最終形の対応が見え、改善の流れとして評価できる。"
            "修正内容が成果物の構成や導線へ反映されているため、対話上の判断と完成形のつながりも説明しやすい。"
            "各修正の理由がそろうと、反映先との関係もさらに説明しやすい。"
        )
        conclusion = "修正履歴、変更方針、反映先が残ることで、改善がどの順序で進んだのかを追跡しやすい。各修正の理由と差分を短く統一して残すほど、変更方針、反映先、最終形の関係がより明確になる。"
    return "\n".join(
        [
            "①評価",
            evaluation,
            "②因果関係",
            relation,
            "③結論",
            conclusion,
        ]
    )


def _build_agency_process_evaluation(
    source_text: str,
    improve_text: str,
    weakness_text: str,
    score: int = 0,
    total_score: int | None = None,
) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    eval_rate = _evaluation_rate(total_score)

    if eval_rate < 40:
        evaluation = (
            "人による判断の記録は一部見られ、AI任せにしていない痕跡は確認できる。"
            "AI案を選別した記録も限定的に残っている。"
            "不要、戻す、変えるといった発言は、AIの提案をそのまま採用しなかった根拠になる。"
            "短い発言でも、人が方向を変えた場面は主体性の材料になる。"
        )
        relation = (
            f"一方で、採否、優先順位、{target}の{structure}や{route}への反映理由はまだ補足が必要である。"
            "人が何を残し、何を見送ったかを成果物の反映先と結び付けると、判断主体の所在が明確になる。"
            "人がどこで最終判断したかは追加記録で明確になる。"
        )
        conclusion = "主体性の材料はある。次は選んだ理由、見送った理由、最終判断の所在を残す段階である。選別の痕跡は評価でき、AI利用における人の関与を示す根拠になる。"
    elif eval_rate < 60:
        evaluation = (
            "AI案を参照した後に、人が採否や優先順位を判断した記録が一定程度見られる。"
            "不要な案を見送った痕跡も評価材料になる。"
            "AIの出力を受けてから、どの案を残すか、どの方式を採るかを人が選んでいる点が重要である。"
            f"その選別が{target}の{structure}や{route}に移っている点も主体性の根拠になる。"
        )
        relation = (
            f"採否や優先順位と、{target}の{structure}、表示順、{route}との対応は一部確認できる。"
            "採用した内容が成果物に残り、見送った内容が削られているほど、主体的な選別として読み取りやすい。"
            "優先した案と見送った案の差が成果物に残る点は、主体的な選別の根拠になる。"
            "ただし、理由の残り方にはばらつきがある。"
        )
        conclusion = "AI案に対して採用、不採用、優先順位を人が扱っているため、最終判断が利用者側に残っていることを説明しやすい。採否理由と反映経路をそろえるほど、AI任せではない選別の過程も第三者に伝わりやすくなる。"
    else:
        evaluation = (
            "AI案を参照しつつ、人が採否や優先順位を判断した記録が確認できる。"
            "不要な案を選別し、進める内容を決めた痕跡も残っている。"
            "候補の比較、採用、不採用を人が扱っているため、最終判断の主体が利用者側に残っている。"
            f"選んだ内容が{target}の{structure}や{route}へ反映されている点も、AI任せではない根拠になる。"
        )
        relation = (
            f"採否や優先順位と、{target}の{structure}、表示順、{route}との対応も読み取れる。"
            "その対応は、AIが出した案を人が目的に合わせて選び、成果物へ反映した根拠になる。"
            "比較、採用、不採用、優先順位が反映先と結び付く点が、主体性の評価を支える。"
            "見送った理由が残るほど、判断主体の所在がより明確になる。"
        )
        conclusion = "AI案を比較し、採用する内容と見送る内容を人が決めているため、最終判断の主体は利用者側に残っている。採用した理由と見送った理由を短く残すほど、AI案の扱い方と最終成果物への反映関係も明確になる。"
    return "\n".join(
        [
            "①評価",
            evaluation,
            "②因果関係",
            relation,
            "③結論",
            conclusion,
        ]
    )


def _build_consistency_process_evaluation(
    source_text: str,
    improve_text: str,
    weakness_text: str,
    score: int = 0,
    total_score: int | None = None,
) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    lp_phrase = _lp_specific_phrase(source_text, improve_text, weakness_text)
    eval_rate = _evaluation_rate(total_score)

    if eval_rate < 40:
        evaluation = (
            (lp_phrase if lp_phrase else "")
            + "ログ上の判断、修正、採否と最終アウトプットの対応は一部確認できる。"
            "成果物へ反映されたと見られる箇所も限定的に残っている。"
            "判断内容が成果物の構成や導線へつながる部分は、全体整合性の評価材料になる。"
            f"判断と{structure}、本文、{route}が対応する箇所は、スコアの根拠として扱える。"
        )
        relation = (
            f"ただし、{target}の{structure}、本文、表示順、{route}へ何が反映されたかは補足が必要である。"
            "対応が断片的な場合でも、残っている反映箇所を起点に判断と成果物の関係を確認できる。"
            "判断と反映箇所を結び付ける記録はまだ少ない。"
        )
        conclusion = "確認できた対応を評価し、判断記録、修正理由、最終形の照合材料を増やす段階である。評価は、残っている一致箇所と不足している説明材料の両方を見る。"
    elif eval_rate < 60:
        evaluation = (
            (lp_phrase if lp_phrase else "")
            + "ログ上の判断、修正、採否が最終アウトプットへ一部反映されている。"
            "構成や表示順の調整も評価材料として見られる。"
            "AI案を比較して選んだ内容が、成果物の構成や導線へ残っている点は整合性の根拠になる。"
            f"修正した内容が本文配置や{route}に反映された箇所も、対応関係として評価できる。"
        )
        relation = (
            f"{target}の{structure}、本文、表示順、{route}との対応は記録が残る範囲で確認できる。"
            "判断と成果物の対応がそろう箇所では、対話上の意図と完成形の関係も説明しやすい。"
            "どの判断がどの修正を生み、どの表示・導線へ移ったかを確認できる部分が、整合性を支えている。"
            "一方で、判断理由と反映箇所の粒度にはばらつきがある。"
        )
        conclusion = "判断、修正、構成、導線のつながりが残ることで、対話上の選択が成果物のどこへ反映されたかを説明しやすい。反映箇所の照合記録が増えるほど、確認できた対応は点数の根拠として扱いやすくなる。"
    else:
        evaluation = (
            (lp_phrase if lp_phrase else "")
            + "ログ上の判断、修正、採否が最終アウトプットへ一部反映され、"
            f"{target}の{structure}、本文、表示順、{route}との対応が確認できる。"
            "対話上で選んだ内容が成果物側にも残っているため、判断と完成形のつながりを説明しやすい。"
            "採用した内容と見送った内容の差が成果物上にも表れる点は、全体整合性の根拠になる。"
        )
        relation = "ログ上の判断や修正と、構成、本文、表示順、導線の各要素との対応は、確認できる範囲に限られる。対応が残る箇所では、どの判断がどの要素に影響したかを読み取れる。判断から修正、構成反映までの連鎖が残る点も、全体整合性の評価を支える。"
        conclusion = "評価は、実際に残っている判断記録と最終構成の対応範囲に基づく。反映理由がそろうほど整合性は伝わりやすい。"
        conclusion += "確認できた対応も評価材料になる。"
    return "\n".join(
        [
            "①評価",
            evaluation,
            "②因果関係",
            relation,
            "③結論",
            conclusion,
        ]
    )


def _build_thought_output_relation(source_text: str, improve_text: str, weakness_text: str, scores: Dict[str, int] | None = None) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    total = sum(max(0, min(100, _safe_int(value))) for value in (scores or {}).values())
    eval_rate = _evaluation_rate(total)

    if eval_rate < 40:
        thought = (
            "ログ上では、比較検討、修正判断、採否判断の一部を確認できる。"
            "AI案をそのまま受け取らず、人が違和感や不要点を示した記録も評価材料になる。"
            "どの案を残すか、どの方式をやめるかを示す発言は、思考プロセスの入口として扱える。"
        )
        output = (
            f"{target}側への反映も一部見られるが、{structure}や{route}との対応は補強が必要である。"
            "反映先が明確な箇所では、判断が成果物の表示や構成へ影響したことを確認できる。"
            "どの判断がどの箇所へ反映されたかは、まだ記録の追加余地がある。"
        )
        relation = (
            "確認できた思考プロセスを評価し、次は判断理由、修正理由、反映箇所を残すことで因果関係を強める。"
            "判断内容と成果物側の変化を一対で残すと、なぜその形になったかを説明しやすい。"
            "評価は、残っている判断と成果物の対応範囲に基づく。"
        )
        return "\n".join(["①思考プロセス", thought[:150], "②アウトプット", output[:150], "③因果関係", relation[:150]])
    if eval_rate < 60:
        thought = (
            "比較検討、修正判断、情報優先順位に関する記録が確認できる。"
            "採用する内容や見送る内容を人が選別した流れも一部残っている。"
            "AI案を受けてから方針を変える、削る、戻すといった判断も思考の流れとして評価できる。"
        )
        output = (
            f"{target}の{structure}、本文配置、表示順、{route}との対応も一部確認できる。"
            "選んだ内容がどの見出しや導線に反映されたかが残る部分は、成果物側の根拠になる。"
            "判断内容が成果物のどこへ反映されたかは、記録が残る範囲で読み取れる。"
        )
        relation = (
            "思考プロセスとアウトプットとの因果関係は一部評価できる。"
            "ただし、判断理由と反映先の粒度がそろうほど、対話から成果物までの流れはさらに明確になる。"
            "改善点は、判断理由、修正理由、反映箇所の記録粒度をそろえることである。"
        )
        return "\n".join(["①思考プロセス", thought[:150], "②アウトプット", output[:150], "③因果関係", relation[:150]])

    thought = (
        "比較検討、改善判断、情報優先順位に関する記録が確認できる。"
        "AI案を材料にしながら、人が採用内容、修正方針、表示順を選んだ流れも読み取れる。"
        "候補を比較して選ぶ過程が残るため、成果物の方向性を人が決めたことも説明しやすい。"
    )
    output = (
        f"{target}の{structure}、本文配置、表示順、{route}との対応も確認できる。"
        "採用した内容や修正した内容が成果物に残っており、対話上の判断が完成形に影響している。"
        "判断内容が最終成果物の構成や導線へ反映された範囲も評価材料になる。"
    )
    relation = (
        "思考プロセスとアウトプットとの因果関係は、記録が残っている範囲で評価できる。"
        "判断、修正、採否の記録が成果物側の表示や構成に対応しているため、評価根拠として扱える。"
        "さらに判断理由と反映箇所がそろうほど、第三者にも経緯を説明しやすくなる。"
    )
    return "\n".join(
        [
            "①思考プロセス",
            thought[:150],
            "②アウトプット",
            output[:150],
            "③因果関係",
            relation[:150],
        ]
    )


def _build_third_party_visibility(source_text: str, improve_text: str, weakness_text: str, scores: Dict[str, int] | None = None) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    total = sum(max(0, min(100, _safe_int(value))) for value in (scores or {}).values())

    if total < 300:
        visible = (
            "第三者が読み取れる判断材料は一部に限られる。"
            "一方で、AI案をそのまま採用せず、不要点や変更方針を示した記録は確認できる。"
            "短い判断発言であっても、何を見送り、どの方向へ直すかを示していれば、人の判断として読み取れる。"
        )
        unclear = (
            f"{target}の{structure}、本文配置、{route}との対応理由は、ログ上の情報だけでは追いにくい箇所がある。"
            "判断理由、修正理由、反映箇所の記録が不足すると、経緯の説明が弱くなる。"
            "採用した内容と見送った内容の差が残っていない場合、最終成果物とのつながりも確認しにくい。"
        )
        evaluation = (
            "判断根拠と修正経緯の記録は十分ではないが、確認できた判断内容は評価材料になる。"
            "次は選んだ理由と見送った理由を残す必要がある。"
            "反映先まで残るほど、判断が成果物へどう影響したかを説明しやすくなる。"
        )
        return "\n".join(["①伝わるポイント", visible, "②伝わりにくいポイント", unclear, "③評価につながるポイント", evaluation])

    visible = (
        "第三者は、判断履歴、修正理由、改善目的、構成変更、表示順、情報優先順位を一部確認できる。"
        f"{route}の反映経路も、記録が残っている範囲で確認できる。"
        "AI案をそのまま通さず、採用する内容と見送る内容を人が分けている点も読み取れる。"
    )
    unclear = (
        "判断飛躍、思考省略、前提共有不足、専門語依存、表示密度が残る箇所では、"
        f"{target}の{structure}、本文配置、{route}との対応理由は、第三者に伝わりにくい箇所が残る。"
        "採否理由や修正理由の粒度がそろわない場合、なぜその形にしたのかを補って読む必要がある。"
    )
    evaluation = (
        "判断履歴、修正履歴、改善優先順位、構成調整の記録をもとに、第三者が確認できる範囲を評価する。"
        "説明可能性は、判断構造と出力構造の対応が記録として残っている範囲に限られる。"
        "理由と反映先の記録が不足する箇所は改善余地として扱う。"
    )
    return "\n".join(
        [
            "①伝わるポイント",
            visible,
            "②伝わりにくいポイント",
            unclear,
            "③評価につながるポイント",
            evaluation,
        ]
    )


def _has_any_marker(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _applicable_business_items(source_text: str, scores: Dict[str, int] | None = None) -> List[str]:
    scores = scores or {}
    src = _clean_report_sentence(source_text)
    total = sum(max(0, min(100, _safe_int(value))) for value in scores.values())
    if total < 300:
        return []

    output_logic = _safe_int(scores.get("成果物論理性"), 0)
    judgment = _safe_int(scores.get("判断プロセス"), 0)
    revision = _safe_int(scores.get("修正プロセス"), 0)
    consistency = _safe_int(scores.get("全体整合性"), 0)

    items: List[str] = []
    structure_markers = ("構成", "情報設計", "見出し", "本文順", "説明順", "構成反映")
    route_markers = ("導線", "CTA", "表示順", "行動導線", "有料導線", "ボタン")
    revision_markers = ("修正", "変更", "改善", "履歴", "差分", "反映箇所")

    if output_logic >= 60 and consistency >= 50 and _has_any_marker(src, structure_markers):
        items.append("・構成設計業務（情報設計・構成反映）")
    if output_logic >= 65 and judgment >= 50 and _has_any_marker(src, route_markers):
        items.append("・導線設計業務（表示順・行動導線）")
    if revision >= 60 and judgment >= 50 and _has_any_marker(src, revision_markers):
        items.append("・改善管理業務（判断履歴・修正追跡）")

    return items[:3]


def _build_applicable_domain_text(source_text: str, improve_text: str, weakness_text: str, scores: Dict[str, int] | None = None) -> str:
    total = sum(max(0, min(100, _safe_int(value))) for value in (scores or {}).values())
    items = _applicable_business_items(source_text, scores)
    if total < 300 or not items:
        return (
            "AI案を比較し、不要点や修正方針を示した記録は確認できる。"
            "ただし、判断理由、修正経緯、反映箇所の記録が十分ではないため、"
            "活用可能領域を広く特定するには情報が不足している。"
            "現時点では、確認できた判断内容、修正方針、採否の痕跡を評価し、"
            "記録不足を改善点として扱う。"
            "判断と成果物の対応が増えるほど、適用できる業務範囲も具体化しやすくなる。"
        )
    return (
        "判断履歴、修正経緯、整合性確認、構成反映に関する記録が確認できる範囲で、"
        "活用可能領域を評価しています。"
        "確認できた内容は、構成設計、導線設計、改善管理などに関連する評価材料になる。"
        "表示する領域は、判断理由と反映箇所が記録として残っているものに限ります。"
    )


def _flatten_applicable_evidence(value: Any, depth: int = 0) -> List[str]:
    if value is None or depth > 6:
        return []
    if isinstance(value, dict):
        parts: List[str] = []
        for item in value.values():
            parts.extend(_flatten_applicable_evidence(item, depth + 1))
        return parts
    if isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            parts.extend(_flatten_applicable_evidence(item, depth + 1))
        return parts
    text = re.sub(r"\s+", " ", _safe_text(value)).strip()
    return [text] if text else []


def _has_applicable_evidence(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _join_evidence_labels(labels: List[str]) -> str:
    return "、".join(dict.fromkeys(label for label in labels if label))


def _has_confirmed_release_review(evidence_parts: List[str]) -> bool:
    approval_markers = (
        "final release approval",
        "publication approval",
        "publish approval",
        "final review approval",
        "最終公開承認",
        "公開承認",
        "公開判断",
        "最終レビュー承認",
    )
    negative_markers = (
        "not available",
        "not confirmed",
        "unconfirmed",
        "cannot confirm",
        "no record",
        "未確認",
        "確認できない",
        "記録がない",
        "記録なし",
    )
    for part in evidence_parts:
        if not _has_applicable_evidence(part, approval_markers):
            continue
        if not _has_applicable_evidence(part, negative_markers):
            return True
    return False


def _evidence_based_applicable_business_items(
    source_text: str,
    data: Any = None,
    report_data: Any = None,
) -> List[str]:
    data = data if isinstance(data, dict) else {}
    report_data = report_data if isinstance(report_data, dict) else {}

    evidence_parts: List[str] = []
    if source_text:
        evidence_parts.append(_clean_report_sentence(source_text))
    for key in (
        "structured_steps",
        "decision_records",
        "judgment_records",
        "comparison_records",
        "revision_history",
        "before_after",
        "limitations",
        "log_text",
        "input_text",
        "output_text",
    ):
        evidence_parts.extend(_flatten_applicable_evidence(data.get(key)))
    for key in (
        "overall_comment",
        "axis_comment_blocks",
        "decision_output_trace",
        "case_specific_evidence",
        "judgment_records",
        "revision_records",
    ):
        evidence_parts.extend(_flatten_applicable_evidence(report_data.get(key)))

    evidence_parts = list(dict.fromkeys(part for part in evidence_parts if part))
    evidence = "\n".join(evidence_parts)
    if not evidence:
        return []

    items: List[str] = []

    requirement_markers = (
        "要件",
        "条件",
        "制約",
        "前提",
        "requirement",
        "condition",
        "constraint",
        "criteria",
    )
    if _has_applicable_evidence(evidence, requirement_markers):
        if _has_applicable_evidence(
            evidence,
            ("repair", "parts availability", "frame condition", "technical compatibility", "修理", "部品"),
        ):
            reason = "修理・部品交換の適用条件を限定"
        else:
            reason = "目的、条件、制約を確認"
        items.append(f"・要件整理（{reason}）")

    comparison_markers = (
        "比較",
        "候補",
        "compare",
        "comparison",
        "candidate",
        "alternative",
        "direction a",
        "direction b",
        "direction c",
    )
    if _has_applicable_evidence(evidence, comparison_markers):
        compared: List[str] = []
        if _has_applicable_evidence(evidence, ("direction a", "direction b", "direction c", "訴求方向")):
            compared.append("訴求方向")
        if _has_applicable_evidence(evidence, ("story-first", "difference-first", "structure", "構成案")):
            compared.append("ページ構成")
        if _has_applicable_evidence(evidence, ("headline", "見出し")):
            compared.append("見出し")
        if _has_applicable_evidence(evidence, ("cta", "call to action")):
            compared.append("CTA候補")
        reason = _join_evidence_labels(compared) or "複数の候補案"
        items.append(f"・複数案の比較検討（{reason}を比較）")

    adoption_markers = (
        "採用",
        "不採用",
        "見送",
        "不要",
        "accept",
        "adopt",
        "reject",
        "do not use",
        "not use",
        "set aside",
    )
    if _has_applicable_evidence(evidence, adoption_markers):
        selected: List[str] = []
        if _has_applicable_evidence(evidence, ("direction a", "direction b", "direction c", "方向案")):
            selected.append("方向案")
        if _has_applicable_evidence(evidence, ("story-first", "difference-first", "構成案")):
            selected.append("構成案")
        if _has_applicable_evidence(
            evidence,
            ("headline", "wording", "built", "fully repairable", "luxury", "heritage", "forever", "masterpiece", "表現"),
        ):
            selected.append("表現候補")
        if _has_applicable_evidence(evidence, ("cta", "call to action")):
            selected.append("CTA")
        reason = _join_evidence_labels(selected) or "必要な案と不要な案"
        items.append(f"・採用・不採用判断（{reason}の採否を判断）")

    structure_markers = (
        "構成",
        "優先順位",
        "表示順",
        "配置",
        "導線",
        "structure",
        "priority",
        "display order",
        "placement",
        "section order",
        "primary cta",
        "secondary cta",
    )
    if _has_applicable_evidence(evidence, structure_markers):
        designed: List[str] = []
        if _has_applicable_evidence(
            evidence,
            ("structure", "section order", "display order", "placement", "構成", "表示順", "配置"),
        ):
            designed.append("セクション順・情報配置")
        if _has_applicable_evidence(evidence, ("priority", "primary cta", "secondary cta", "優先順位")):
            designed.append("CTAの優先順位")
        reason = _join_evidence_labels(designed) or "構成と情報の優先順位"
        items.append(f"・情報構成・優先順位設計（{reason}を決定）")

    copy_markers = (
        "copy",
        "headline",
        "wording",
        "biography",
        "repair section",
        "explanation",
        "見出し",
        "本文",
        "説明文",
        "紹介文",
        "文言",
    )
    revision_markers = (
        "修正",
        "変更",
        "改善",
        "replace",
        "revise",
        "revision",
        "reuse",
        "moved",
    )
    if _has_applicable_evidence(evidence, copy_markers) and _has_applicable_evidence(evidence, revision_markers):
        revised: List[str] = []
        if _has_applicable_evidence(evidence, ("headline", "見出し")):
            revised.append("見出し")
        if _has_applicable_evidence(
            evidence,
            ("repair section", "fully repairable", "repair wording", "修理", "部品交換"),
        ):
            revised.append("修理条件の説明")
        if _has_applicable_evidence(evidence, ("biography", "紹介文")):
            revised.append("紹介文")
        if _has_applicable_evidence(
            evidence,
            ("wording", "built", "luxury", "heritage", "forever", "masterpiece", "文言"),
        ):
            revised.append("表現")
        reason = _join_evidence_labels(revised) or "見出しと説明文"
        items.append(f"・コピー・説明文の改善（{reason}を修正）")

    if _has_applicable_evidence(evidence, revision_markers):
        tracked: List[str] = []
        if _has_applicable_evidence(evidence, ("before", "after", "before_after", "修正前", "修正後", "差分")):
            tracked.append("修正前後")
        if _has_applicable_evidence(evidence, ("reuse", "moved", "reflect", "implementation", "反映", "転用")):
            tracked.append("反映先")
        reason = _join_evidence_labels(tracked) or "判断履歴と修正内容"
        items.append(f"・修正履歴・改善管理（{reason}を記録）")

    if _has_confirmed_release_review(evidence_parts):
        items.append("・最終レビュー・公開判断（公開前の確認と承認を記録）")

    return items


def _build_applicable_business_list(
    source_text: str,
    scores: Dict[str, int] | None = None,
    data: Any = None,
    report_data: Any = None,
) -> str:
    items = _evidence_based_applicable_business_items(source_text, data, report_data)
    if not items:
        items = _applicable_business_items(source_text, scores)
    return "\n".join(items)


def _build_ai_use_scope_statement(
    scores: Dict[str, int],
    source_text: str,
    improve_text: str,
    weakness_text: str,
    report_data: Any = None,
) -> str:
    report_data = report_data if isinstance(report_data, dict) else {}
    context_parts: List[str] = [source_text, improve_text, weakness_text]
    for key in (
        "overall_comment",
        "strengths_text",
        "weaknesses_text",
        "improve_text",
        "responsibility_text",
        "risk_text",
    ):
        context_parts.append(_safe_text(report_data.get(key)))
    for key in ("axis_comment_blocks", "axis_comments"):
        axis_values = report_data.get(key)
        if isinstance(axis_values, dict):
            context_parts.extend(_safe_text(value) for value in axis_values.values())

    def axis_score(axis: str) -> int:
        return max(0, min(100, _safe_int(scores.get(axis), 0)))

    ranked_axes = sorted(AXIS_ORDER, key=lambda axis: (axis_score(axis), -AXIS_ORDER.index(axis)), reverse=True)
    primary_axis = ranked_axes[0] if ranked_axes else AXIS_ORDER[1]
    secondary_axis = ranked_axes[1] if len(ranked_axes) > 1 else AXIS_ORDER[2]
    limiting_axis = min(AXIS_ORDER, key=lambda axis: (axis_score(axis), AXIS_ORDER.index(axis)))
    total_score = sum(axis_score(axis) for axis in AXIS_ORDER)

    high_actions = {
        AXIS_ORDER[0]: "情報の流れを整理し、相手に伝わりやすい成果物へまとめる形でAIを活用しています",
        AXIS_ORDER[1]: "複数の案を比べ、採用する内容や進め方を判断する形でAIを活用しています",
        AXIS_ORDER[2]: "修正点を整理し、改善内容を成果物へ反映する形でAIを活用しています",
        AXIS_ORDER[3]: "AIの提案を目的に合わせて取捨選択する形で活用しています",
        AXIS_ORDER[4]: "決めた内容を成果物へ反映し、全体の流れを整える形でAIを活用しています",
    }
    high_support = {
        AXIS_ORDER[0]: "必要な情報を相手に伝わる順番へ整理しながら進めており",
        AXIS_ORDER[1]: "判断理由を残しながら意思決定を進めており",
        AXIS_ORDER[2]: "判断理由や修正履歴を残しながら改善を進めており",
        AXIS_ORDER[3]: "AIに任せきらず、自分の判断で内容を選んでおり",
        AXIS_ORDER[4]: "決めた内容を後から説明できる形で残しており",
    }
    improvement_focus = {
        AXIS_ORDER[0]: "情報の並べ方",
        AXIS_ORDER[1]: "比較した理由",
        AXIS_ORDER[2]: "修正履歴",
        AXIS_ORDER[3]: "採用する内容を選んだ理由",
        AXIS_ORDER[4]: "最後の確認",
    }

    if total_score >= 400:
        main_action = high_actions[AXIS_ORDER[1]]
        support_action = high_support[AXIS_ORDER[2]]
        candidate = (
            f"{main_action}。"
            f"{support_action}、結論に至るまでの判断経緯を振り返ることができます。"
            "AIの提案を比較し、必要な内容だけを選びながら成果物へ反映する進め方が取れています。"
        )
    elif total_score >= 300:
        focus = improvement_focus.get(limiting_axis, "判断理由")
        candidate = (
            "AIを使った情報整理や案の比較は行われています。"
            f"一方で、{focus}や修正経緯の残し方にはばらつきがあり、"
            "改善の流れを継続的に振り返れる状態までは至っていません。"
            "現状は、確認できた判断を評価しつつ、理由と反映先の記録を補う段階です。"
        )
    elif total_score >= 200:
        focus = improvement_focus.get(limiting_axis, "比較した理由")
        if focus == "修正履歴":
            focus = "判断履歴"
        candidate = (
            "AIを使った情報収集や案出しは見られます。"
            f"ただし、{focus}や修正履歴の記録が十分ではなく、"
            "人の判断が最終結果へどう反映されたかは読み取りにくい状態です。"
            "確認できた判断内容を残しながら、採用理由と見送った理由を補う必要があります。"
        )
    elif total_score >= 100:
        candidate = (
            "AIの利用は見られます。"
            "ただし、比較検討や採用する内容を選んだ理由の記録が少なく、"
            "人の判断過程を確認することは難しい状態です。"
            "まずは、何を採用し、何を見送り、どこを修正したかを短く残すことが必要です。"
        )
    else:
        candidate = (
            "AI利用の痕跡は見られます。"
            "ただし、判断理由や修正履歴などの情報が不足しており、"
            "AI活用の過程を評価するための材料が十分に確認できません。"
            "能力の高低を断定するより、評価に必要な記録を増やす段階です。"
        )

    fallback = (
        "AI利用の痕跡は見られます。"
        "ただし、判断理由や修正履歴などの情報が不足しています。"
        "まずは、AI案に対して何を選び、何を見送り、どこを直したのかを残すことが必要です。"
        "記録が増えるほど、AIをどの範囲で使い、人がどこで判断したのかを説明しやすくなります。"
    )

    forbidden = {
        "確認されました": "示されています",
        "評価されました": "扱えます",
        "分析の結果": "",
        "と考えられます": "です",
    }
    awkward_patterns = (
        "比較の比較",
        "構成の構成",
        "修正の改善",
        "整理を整理",
        "判断を判断",
        "品質を高め",
        "最適化",
        "アウトプット構成",
        "行動導線",
        "成立している",
        "保持されている",
        "として機能している",
        "確認可能な状態",
        "追跡可能な状態",
        "接続している",
    )
    for candidate_text in (candidate, fallback):
        statement = _humanize_transferable_prose(candidate_text)
        for before, after in forbidden.items():
            statement = statement.replace(before, after)
        for pattern in awkward_patterns:
            statement = statement.replace(pattern, "")
        if 110 <= len(statement) <= 190:
            return statement
        if len(statement) > 190:
            return statement[:190]
    statement = _humanize_transferable_prose(fallback)
    for before, after in forbidden.items():
        statement = statement.replace(before, after)
    for pattern in awkward_patterns:
        statement = statement.replace(pattern, "")
    return statement[:170]

def _build_page6_transparency_text(scores: Dict[str, int] | None = None) -> str:
    scores = scores or {}
    judgment = _safe_int(scores.get("判断プロセス"), 0)
    revision = _safe_int(scores.get("修正プロセス"), 0)
    consistency = _safe_int(scores.get("全体整合性"), 0)
    if min(judgment, revision, consistency) < 40:
        return (
            "判断履歴、修正履歴、反映経路の記録は限定的であり、"
            "なぜその構成になったかを説明するには記録が不足している。"
            "ただし、AI案への違和感、不要点、変更方針を示した記録は一部確認できる。"
            "第三者へ説明するには、判断理由、修正理由、反映箇所を追加で残す必要がある。"
            "透明性の評価は、確認できた判断と不足している記録の両方に基づく。"
            "採用した内容と見送った内容がそろうほど、利用過程は読み取りやすくなる。"
        )
    return (
        "判断履歴、修正履歴、反映経路は、ログとアウトプットの双方で一部確認できる。"
        "なぜその構成になったかは、記録が残っている範囲で説明材料になる。"
            "AI案をそのまま採用せず、人が選別した記録も評価材料になる。"
            "透明性の評価は、判断理由、修正理由、反映箇所を照合できる範囲に基づく。"
            "さらに採用理由と不採用理由がそろうほど、利用過程は第三者に伝わりやすくなる。"
            "確認できた材料と不足点を分けて示すことで、評価の根拠も明確になる。"
        )


def _build_page6_responsibility_structure() -> str:
    return "\n".join(
        [
            "処理主体：人",
            "AIの役割：案出し・情報整理",
            "最終決定：人が構成確定",
            "責任主体：人側で根拠保持",
        ]
    )


def _build_page6_responsibility_body(scores: Dict[str, int] | None = None) -> str:
    scores = scores or {}
    agency = _safe_int(scores.get("判断主体性"), 0)
    judgment = _safe_int(scores.get("判断プロセス"), 0)
    if agency < 60 or judgment < 40:
        return (
            "ログ上では、人による判断の記録が一部見られる。"
            "ただし、AI案の採否、修正方針、最終決定の理由を十分に示すほどの記録は不足している。"
            "それでも、不要点を示した発言や変更方針の記録は、AI任せではない利用の材料になる。"
            "責任構造を明確にするには、選んだ理由、見送った理由、成果物へ反映した箇所を残す必要がある。"
            "評価は、確認できた人の判断と、まだ不足している説明材料の両方から行う。"
        )
    return (
        "ログ上では、AI案の採否、修正方針、構成変更の各工程に人側の判断が残っている。"
        "生成情報は判断材料として使われ、最終構成や表示構造は、修正履歴と表示結果の関係を踏まえて確定されている。"
        "採用した内容だけでなく、見送った内容や修正した理由も責任構造を説明する材料になる。"
        "責任構造の評価は、採用内容、構成反映、表示結果の関係を確認できる範囲に基づく。"
    )


def _resolve_ai_capability_score(data: Dict[str, Any], report_data: Dict[str, Any], scores: Dict[str, int]) -> int:
    candidates = [
        data.get("ai_capability_score"),
        data.get("capability_score"),
        data.get("ai_score"),
        data.get("ai_utilization_score"),
        data.get("AI活用能力"),
        data.get("AI活用度"),
        report_data.get("ai_capability_score"),
        report_data.get("capability_score"),
        report_data.get("ai_score"),
        report_data.get("AI活用能力"),
        report_data.get("AI活用度"),
    ]
    for value in candidates:
        if value in (None, ""):
            continue
        match = re.search(r"\d{1,3}", str(value))
        if match:
            return max(0, min(100, _safe_int(match.group(0), 0)))
    return max(0, min(100, _safe_int(scores.get("成果物論理性"), 0)))


def _evidence_phrase(*texts: str) -> str:
    src = _clean_report_sentence("。".join(t for t in texts if t))
    terms: List[str] = []
    candidates = [
        "LP",
        "CTA",
        "有料導線",
        "行動導線",
        "視覚構成",
        "余白設計",
        "情報密度",
        "視線導線",
        "配置バランス",
        "強弱設計",
        "構成順",
        "見出し",
        "配置",
        "採用",
        "不採用",
        "比較",
        "修正",
    ]
    for term in candidates:
        if term in src and term not in terms:
            terms.append(term)
    if not any(t in terms for t in ("有料導線", "行動導線")) and "導線" in src:
        terms.append("導線")
    if not terms:
        return "記録が残っている範囲"
    return "、".join(terms[:3])


def _axis_analysis_parts(axis: str, source_text: str, improve_text: str, weakness_text: str) -> tuple[str, str, str, str]:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    evidence = _evidence_phrase(source_text, improve_text, weakness_text)
    if axis == AXIS_ORDER[0]:
        return (
            f"ログでは、{evidence}に関する比較と採否が確認される。",
            f"その判断は{target}の{structure}、本文順、{route}位置に反映されている。",
            f"この反映は、読み手が主張から{route}へ進む順序に影響している。",
            f"{structure}を選んだ理由が短い箇所は、配置意図を第三者が追いにくい。",
        )
    if axis == AXIS_ORDER[1]:
        return (
            f"ログでは、{evidence}をめぐる選択順と採否判断が確認される。",
            f"採用した判断は{target}の{structure}選択と{route}配置に反映されている。",
            f"この判断は、どの情報を先に読ませるかという選択品質に影響している。",
            "不採用理由の粒度がそろわない箇所は、選択基準の再現性が弱く見える。",
        )
    if axis == AXIS_ORDER[2]:
        return (
            f"ログでは、{evidence}に対する修正判断と再配置が確認される。",
            f"修正内容はページ本文の説明順、{structure}、{route}までの流れに反映されている。",
            f"この修正は、読み手が迷う箇所と離脱しやすい箇所に影響している。",
            "変更前後の差分説明が短い箇所は、修正意図の追跡が難しくなる。",
        )
    if axis == AXIS_ORDER[3]:
        return (
            f"ログでは、AI案を参照した後に{evidence}の採否が行われている。",
            f"最終採否はAI案の転記ではなく、人による{target}の構造決定に反映されている。",
            "この流れは、意思決定の所在がAIではなく人に残っていることに影響している。",
            "見送った案の理由が残らない箇所は、選別した根拠が伝わりにくい。",
        )
    return (
        f"ログ上の優先順位は、{evidence}として記録されている。",
        f"主要判断は{target}の本文順、{structure}、{route}配置に反映されている。",
        "この一致は、ログ上の判断と最終アウトプットの照合精度に影響している。",
        "提出前の反映確認が後段に寄る箇所は、判断と最終形の照合が弱くなる。",
    )


def _axis_evaluation_tail(axis: str, source_text: str, improve_text: str, weakness_text: str) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    evidence = _evidence_phrase(source_text, improve_text, weakness_text)
    if axis == AXIS_ORDER[0]:
        return (
            f"また、{evidence}の採否が{target}の説明順に残っているため、構造の妥当性を確認できる。"
            f"ただし、{structure}と{route}の対応理由が薄い部分は、評価根拠として読み取りに差が出る。"
        )
    if axis == AXIS_ORDER[1]:
        return (
            f"比較対象が{structure}と{route}に分かれているため、選択の質を追跡できる。"
            "ただし、採用と不採用の理由量に差がある部分は、判断基準の一貫性が弱く見える。"
        )
    if axis == AXIS_ORDER[2]:
        return (
            f"修正が{target}本文と{route}の流れに反映されており、修正過程の実在性を確認できる。"
            "ただし、変更前後の対応が短い部分は、どの判断で何が変わったかを追いにくい。"
        )
    if axis == AXIS_ORDER[3]:
        return (
            f"AI案を参照しつつ、{structure}と{route}の最終採否が人の判断として残っている。"
            "ただし、見送った案の扱いが薄い部分は、意思決定主体の説明力が弱く見える。"
        )
    return (
        f"ログ上の優先順位と{target}上の反映箇所が対応し、照合可能な範囲は明確である。"
        "ただし、反映確認が後段に寄る部分は、判断記録と最終形の一致度が弱く見える。"
    )


def _axis_shortage_sentence(axis: str, source_text: str, improve_text: str, weakness_text: str) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    if axis == AXIS_ORDER[0]:
        return f"ただし、{structure}と{route}を結びつけた理由が短い部分は、構成意図の読み取りが弱くなる。"
    if axis == AXIS_ORDER[1]:
        return "ただし、採用理由と不採用理由の量に差がある部分は、判断基準の一貫性が弱く見える。"
    if axis == AXIS_ORDER[2]:
        return "ただし、変更前後の対応が短い部分は、どの判断で何が変わったかを追いにくい。"
    if axis == AXIS_ORDER[3]:
        return f"ただし、見送った案の扱いが薄い部分は、{target}を人が決めた根拠が伝わりにくい。"
    return f"ただし、反映確認が後段に寄る部分は、{target}とログ判断の一致度が弱く見える。"


def _axis_impact_sentence(axis: str, source_text: str, improve_text: str, weakness_text: str) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    if axis == AXIS_ORDER[0]:
        return f"{structure}と{route}の接続を確認できる。"
    if axis == AXIS_ORDER[1]:
        return "選択した理由を追跡しやすい。"
    if axis == AXIS_ORDER[2]:
        return "変更の影響範囲を確認できる。"
    if axis == AXIS_ORDER[3]:
        return "判断主体の所在も明確に残っている。"
    return "評価者は一致箇所を追跡できる。"


def _axis_improvement_actions(axis: str) -> tuple[str, str]:
    if axis == AXIS_ORDER[0]:
        return (
            "次回は見出しごとの役割を一文で残す。",
            "CTAまたは有料導線を選んだ理由をアウトプット横に記録する。",
        )
    if axis == AXIS_ORDER[1]:
        return (
            "次回は構成案を比較する観点を先に固定する。",
            "採用理由と不採用理由を配置ごとに同じ粒度で残す。",
        )
    if axis == AXIS_ORDER[2]:
        return (
            "次回は本文、構成、導線の修正前後差分を一文で残す。",
            "変更した箇所と狙いを同じ行で対応させる。",
        )
    if axis == AXIS_ORDER[3]:
        return (
            "次回はAI案を採用しなかった理由も導線単位で残す。",
            "最終判断者としての決定理由を明示する。",
        )
    return (
        "次回は提出前に判断記録とLP上の反映箇所を照合する。",
        "反映されていない判断をチェック項目として残す。",
    )


def _fit_axis_comment_block(text: str) -> str:
    src = _sanitize_unicode_text(text)
    for token in FORBIDDEN_TERMS:
        src = src.replace(token, "")
    src = src.replace("成果物", "アウトプット")
    src = re.sub(r"\bartifact\b", "アウトプット", src, flags=re.IGNORECASE)
    src = re.sub(r"\braw\b", "入力内容", src, flags=re.IGNORECASE)
    src = re.sub(r"\bdebug\b", "", src, flags=re.IGNORECASE)
    src = re.sub(r"\b\d+\s*点\b", "", src)
    src = src.replace("不足点は、", "")
    src = src.replace("不足点は", "")
    src = src.replace("不明点は、", "")
    src = src.replace("不明点は", "")
    src = src.replace("\r\n", "\n").replace("\r", "\n")
    src = re.sub(r"\n{3,}", "\n\n", src)
    return src.strip()


def _compose_relation_analysis_text(source_text: str, improve_text: str, weakness_text: str) -> str:
    judgment = _axis_analysis_parts(AXIS_ORDER[1], source_text, improve_text, weakness_text)
    output = _axis_analysis_parts(AXIS_ORDER[0], source_text, improve_text, weakness_text)
    revision = _axis_analysis_parts(AXIS_ORDER[2], source_text, improve_text, weakness_text)
    return "\n".join(
        [
            "■思考とアウトプットの関係",
            "①思考プロセス",
            judgment[0],
            "比較、採否、修正の順序をアウトプットと照合できる。",
            "採用した案と見送った案の差もログ上に残っている。",
            "不要と判断した内容や方式変更の記録は、人がAI案を選別した根拠になる。",
            "判断が短い場合でも、どの方向へ進めるかを決めた発言は思考過程として扱える。",
            "②アウトプット",
            output[1],
            revision[1],
            "本文順と導線位置に判断結果が反映されている。",
            "修正方針が成果物の構成、表示順、導線へ移った箇所は評価材料になる。",
            "採用した内容が残り、見送った内容が削られているほど、対話と成果物の関係は明確になる。",
            "③因果関係",
            judgment[2],
            "判断内容、修正方針、採否が成果物上の要素と結び付くことで、点数の根拠が説明しやすくなる。",
            "一方で、理由が短い箇所は反映箇所との対応が弱く見える。",
        ]
    )


def _compose_visibility_analysis_text(source_text: str, improve_text: str, weakness_text: str) -> str:
    agency = _axis_analysis_parts(AXIS_ORDER[3], source_text, improve_text, weakness_text)
    consistency = _axis_analysis_parts(AXIS_ORDER[4], source_text, improve_text, weakness_text)
    judgment = _axis_analysis_parts(AXIS_ORDER[1], source_text, improve_text, weakness_text)
    return "\n".join(
        [
            "■どう見えるか",
            "①伝わるポイント",
            agency[2],
            "採否と反映の対応が残る箇所は、第三者も判断経路を追える。",
            "判断主体とアウトプットの接続が評価根拠になる。",
            "AI案をそのまま通さず、不要点や変更方針を人が示した部分は伝わりやすい。",
            "成果物側に反映された判断が分かるほど、読み手は評価理由を理解しやすくなる。",
            "②伝わりにくいポイント",
            consistency[3],
            judgment[3],
            "理由量がそろわない箇所は、読み手の確認負荷が上がる。",
            "採用した理由と見送った理由の差が薄い箇所では、判断の優先順位が伝わりにくい。",
            "修正した箇所と修正理由が離れている場合、成果物との対応も弱く見える。",
            "③評価につながるポイント",
            "ログ判断とアウトプット反映を同じ順序で照合できる。",
            "照合できる箇所が評価根拠として機能する。",
            "確認できた判断、修正、採否を成果物上の反映先と結び付けることで、評価の根拠が具体化する。",
        ]
    )


def _compose_improve_points_text(source_text: str, improve_text: str, weakness_text: str) -> str:
    judgment = _axis_analysis_parts(AXIS_ORDER[1], source_text, improve_text, weakness_text)
    output = _axis_analysis_parts(AXIS_ORDER[0], source_text, improve_text, weakness_text)
    consistency = _axis_analysis_parts(AXIS_ORDER[4], source_text, improve_text, weakness_text)
    return "\n".join(
        [
            "■改善ポイント",
            "①思考プロセスの改善点",
            judgment[3],
            "比較観点と採否理由を一対で残す必要がある。",
            "判断順を固定すると、後から選択品質を確認しやすい。",
            "何を採用し、何を見送ったかを同じ粒度で残すと、判断プロセスの根拠が強くなる。",
            "②アウトプットの改善点",
            output[3],
            "見出しごとに配置理由を一文で残す必要がある。",
            "本文、構成、導線の対応を同じ粒度で確認する。",
            "修正方針が成果物のどこへ反映されたかを残すと、評価者が変更意図を追いやすい。",
            "③因果関係の改善点",
            consistency[3],
            "判断記録と反映箇所を提出前に照合する必要がある。",
            "判断理由、修正理由、成果物上の反映先を並べることで、対話と完成形の因果関係が伝わる。",
        ]
    )


def _compose_next_action_text(source_text: str, improve_text: str, weakness_text: str) -> str:
    revision = _axis_analysis_parts(AXIS_ORDER[2], source_text, improve_text, weakness_text)
    consistency = _axis_analysis_parts(AXIS_ORDER[4], source_text, improve_text, weakness_text)
    return "\n".join(
        [
            "■次回へ活かすポイント",
            "①改善の意味",
            "判断、修正、反映を同じ粒度で残す。",
            "読み手がログからアウトプットまで追える状態を固定する。",
            "評価者が迷う箇所を提出前に減らす。",
            "判断した内容が成果物のどこへ移ったかを確認できると、次回の評価根拠も明確になる。",
            "②具体的なアクション",
            "・比較観点を先に固定する",
            "・修正前後の差分を一文で残す",
            "・判断記録と反映箇所を公開前に照合する",
            "・採用した案と不採用にした案を同じ形式で残す",
        ]
    )


def _axis_meaning_value(axis: str) -> tuple[str, str, str, str]:
    if axis == AXIS_ORDER[0]:
        return (
            "情報の順番が整い、読み手が要点へ自然に進める構成です。",
            "提案資料やLPでは、訴求の入口から行動導線までを一続きで見せる力になります。",
            "改善余地は、配置を選んだ意図が短くなりやすいところです。",
            "見出しごとに役割を一文添えると、初見でも流れを追いやすくなります。",
            "作り手の狙いが見えるほど、読み手は安心して次へ進めます。",
        )
    if axis == AXIS_ORDER[1]:
        return (
            "複数案を比べ、採用する案を自分の基準で選べています。",
            "会議や企画では、選択肢を整理して決め切る場面で効きます。",
            "改善余地は、採否の基準が場面ごとに細かく揺れやすいところです。",
            "先に比較観点を置くと、迷った時も同じ軸へ戻れます。",
            "理由が短く残るほど、後から見ても納得しやすい決定に変わります。",
        )
    if axis == AXIS_ORDER[2]:
        return (
            "一度で終わらせず、修正を重ねて完成度を上げられています。",
            "制作改善や運用改善では、試して直す進め方としてそのまま武器になります。",
            "改善余地は、変更ごとの狙いが途中で埋もれやすいところです。",
            "修正前後の差分を短く書くと、次の案件でも改善手順を再利用できます。",
            "直した理由まで残ると、改善がその場限りで終わりません。",
        )
    if axis == AXIS_ORDER[3]:
        return (
            "AI案を材料にしながら、最後の採否を自分で決められています。",
            "速く試しつつ、丸投げにしない距離感を保っています。",
            "改善余地は、不採用にした案の扱いが薄くなりやすいところです。",
            "見送った理由を一文で置くと、選別した根拠が残ります。",
            "AIを使うほど、この一手間が判断の信頼感になります。",
        )
    return (
        "決めた方針を最終アウトプットへ反映する流れは作れています。",
        "提出物として、考えた内容と仕上がりを結びつける力があります。",
        "改善余地は、細部の反映チェックが後回しになりやすいところです。",
        "公開前に決定事項を照合すると、仕上がりのぶれを抑えられます。",
        "最後の確認が習慣になると、安心して人に見せられる状態に近づきます。",
    )


def _compose_axis_comment_v2(
    axis: str,
    score: int,
    source_text: str,
    improve_text: str,
    weakness_text: str,
) -> str:
    markers = _context_markers(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    evidence = _evidence_phrase(source_text, improve_text, weakness_text)
    if axis == AXIS_ORDER[0]:
        lines = [
            f"{target}の論理性は、{structure}、本文順、{route}の接続で評価する。",
            f"ログでは、{evidence}を比較し、採用する順序を決めた記録が残る。",
            f"その判断は{target}の説明順と{route}位置に反映されている。",
            f"反映内容は、読み手が主張から{route}へ進む順序に影響している。",
            f"評価結論は、ログ判断と{target}構成の対応が追える点を重視する。",
        ]
    elif axis == AXIS_ORDER[1]:
        lines = [
            "判断プロセスは、選択順、採否理由、判断基準の残り方で評価する。",
            f"ログでは、{evidence}をめぐる比較と選択順が確認される。",
            f"採用した判断は、{target}の{structure}と{route}配置に反映されている。",
            "この反映は、どの情報を先に読ませるかという選択品質に影響している。",
            "評価結論は、選択理由と反映箇所の対応が明確な点を重視する。",
        ]
    elif axis == AXIS_ORDER[2]:
        lines = [
            "修正プロセスは、変更前後の差分、修正理由、反映範囲で評価する。",
            f"ログでは、{evidence}に対する修正判断と再配置が確認される。",
            f"修正は、本文順、{structure}、{route}までの流れに反映されている。",
            "この反映は、読み手が迷う箇所や離脱しやすい箇所の整理に影響している。",
            "評価結論は、修正意図と最終形の対応範囲に基づく。",
        ]
    elif axis == AXIS_ORDER[3]:
        lines = [
            "判断主体性は、AI案の扱い方と最終採否の所在で評価する。",
            f"ログでは、AI案参照後に{evidence}の採否を行った流れが残る。",
            f"最終採否はAI案の転記ではなく、人による{target}構造決定に反映されている。",
            "この流れは、意思決定の所在がAIではなく人に残ることに影響している。",
            "評価結論は、採否と反映の対応から人側の判断主体を重視する。",
        ]
    else:
        lines = [
            "全体整合性は、ログ上の判断と最終アウトプットの一致度で評価する。",
            f"ログ上の優先順位は、{evidence}に関する判断記録として残る。",
            (
                f"主要判断は、{target}の本文順、{structure}、{route}配置に反映されている。"
                if score >= 65
                else f"ただし、{target}側で照合できる本文や構造情報が限られ、反映確認は暫定的である。"
            ),
            (
                "この一致は、ログ判断と最終アウトプットの照合精度に影響している。"
                if score >= 65
                else "この制約により、ログ判断と最終アウトプットの一致度は控えめに評価している。"
            ),
            (
                "評価結論は、判断記録と最終形の対応範囲を重視する。"
                if score >= 65
                else "評価結論は、判断記録の質を認めつつ、取得できた範囲での暫定評価とする。"
            ),
        ]
    return "\n".join(lines)


def _build_structured_axis_text(
    *,
    axis: str,
    score: int,
    source_text: str,
    improve_text: str,
    weakness_text: str,
) -> str:
    """Generate the four required evaluation parts before layout fitting."""
    markers = _context_markers(source_text, improve_text, weakness_text)
    visual_artifact = _is_visual_artifact_context(source_text, improve_text, weakness_text)
    target = markers["target"]
    route = markers["route"]
    structure = markers["structure"]
    evidence = _evidence_phrase(source_text, improve_text, weakness_text)

    if axis == AXIS_ORDER[0]:
        if score < 50:
            viewpoint = f"アウトプットの論理性は、{structure}、本文順、{route}のつながりを確認する観点で評価する。"
            log_fact = f"ログ上で見られる材料は{evidence}に限られる。"
            reflection = f"{target}への反映は一部見られるが、判断と最終形の対応を十分に説明するには情報が不足している。"
            conclusion = "以上より、論理構造の成立を強みとして断定せず、記録が残っている範囲で評価する。"
        elif visual_artifact:
            viewpoint = "アウトプットの論理性は、視覚構成、情報密度、余白設計、視線誘導がつながっているかで評価する。"
            log_fact = f"ログ上では、{evidence}について比較し、画面上の優先順位を決めた記録が確認できる。"
            reflection = f"その判断は、{target}の配置バランス、強弱設計、視線誘導に反映されている。"
            conclusion = f"以上より、ログ判断と{target}の見た目の対応が追える点を評価する。"
        else:
            viewpoint = f"アウトプットの論理性は、{structure}、本文順、{route}がつながっているかで評価する。"
            log_fact = f"ログ上では、{evidence}について比較し、採用順を決めた記録が確認できる。"
            reflection = f"その判断は、{target}の説明順、見出し構成、{route}位置に反映されている。"
            conclusion = f"以上より、ログ判断と{target}構成の対応が追える点を評価する。"
    elif axis == AXIS_ORDER[1]:
        viewpoint = "判断プロセスは、選択順、採否理由、判断基準が記録として残るかで評価する。"
        if score < 40:
            log_fact = f"ログ上で見られる材料は{evidence}に限られ、比較と選択順の記録は十分ではない。"
            reflection = f"{target}の{structure}選択や{route}配置との対応も限定的である。"
            conclusion = "以上より、選択理由と反映箇所の対応関係を評価するには記録が不足している。"
        else:
            log_fact = f"ログ上では、{evidence}をめぐる比較と選択順が一部見られる。"
            reflection = f"採用した判断と、{target}の{structure}選択や{route}配置との対応は一部見られる。"
            conclusion = "以上より、記録が残っている判断範囲で評価する。"
    elif axis == AXIS_ORDER[2]:
        viewpoint = "修正プロセスは、変更前後の差分、修正理由、反映範囲の対応が確認できるかで評価する。"
        if score < 40:
            log_fact = f"ログ上で見られる修正材料は{evidence}に限られ、差分や修正理由は十分に残っていない。"
            reflection = f"{target}の本文順、{structure}、{route}へどう反映されたかは追いにくい。"
            conclusion = "以上より、修正意図と最終形の対応関係を評価するには記録が不足している。"
        else:
            log_fact = f"ログ上では、{evidence}に対する修正判断が一部見られる。"
            reflection = f"修正内容と{target}の本文順、{structure}、{route}との対応は記録が残る範囲に限られる。"
            conclusion = "以上より、残っている修正記録の範囲で評価する。"
    elif axis == AXIS_ORDER[3]:
        viewpoint = "判断主体性は、AI案を参照した後も最終採否を人が担っているかで評価する。"
        if score < 60:
            log_fact = f"ログ上で見られる材料は{evidence}に限られ、人の最終採否を十分に説明するには記録が不足している。"
            reflection = f"{target}の構造決定に人の判断がどう反映されたかは限定的である。"
            conclusion = "以上より、判断主体性は確認できた範囲に限定して評価する。"
        else:
            log_fact = f"ログ上では、AI案参照後に{evidence}の採否を行った流れが一部見られる。"
            reflection = f"最終採否は、人による{target}の構造決定に一部関係している。"
            conclusion = "以上より、採否と反映の対応は記録が残る範囲で判断主体を評価する。"
    else:
        viewpoint = (
            "全体整合性は、ログ上の判断と画面上の配置、強弱、視線誘導の一致度で評価する。"
            if visual_artifact
            else "全体整合性は、ログ上の判断と最終アウトプットの一致度で評価する。"
        )
        log_fact = f"ログ上では、{evidence}に関する優先順位と判断記録が確認できる。"
        if score >= 65:
            reflection = (
                f"主要判断は、{target}の配置バランス、視覚的優先順位、余白と強弱に反映されている。"
                if visual_artifact
                else f"主要判断は、{target}の本文順、{structure}、{route}配置に反映されている。"
            )
            conclusion = "以上より、判断記録と最終形の対応範囲を評価する。"
        else:
            reflection = (
                f"ただし、{target}側で照合できる配置や視覚階層が限られ、反映確認は暫定的である。"
                if visual_artifact
                else f"ただし、{target}側で照合できる本文や構造情報が限られ、反映確認は暫定的である。"
            )
            conclusion = "以上より、判断記録の質を認めつつ、取得できた範囲での暫定評価とする。"

    text = "".join([viewpoint, log_fact, reflection, conclusion])
    if score >= 60 and _display_width(text) < 260:
        text += (
            "この対応により、評価者はログ上の判断とアウトプット上の反映を同じ流れで確認できる。"
            "したがって、評価結論は記録された判断と最終形の対応範囲に基づく。"
        )
    return _fit_plain(text, 560, text)


def _compose_overall_summary_v2(
    scores: Dict[str, int],
    overall_comment: str,
    improve_text: str,
) -> str:
    top_axis = max(scores.items(), key=lambda x: x[1])[0] if scores else AXIS_ORDER[1]
    weak_axis = min(scores.items(), key=lambda x: x[1])[0] if scores else AXIS_ORDER[4]
    top_label = AXIS_LABEL_MAP.get(top_axis, "判断プロセス")
    weak_label = AXIS_LABEL_MAP.get(weak_axis, "全体整合性")
    fact = _first_fact_sentence(overall_comment, improve_text)
    if fact:
        fact = _humanize_fact_sentence(top_axis, fact)
    if not fact:
        fact = "ログ上で見られる判断や修正の記録をもとに評価しています。"
    total = sum(max(0, min(100, _safe_int(value))) for value in scores.values())
    eval_rate = _evaluation_rate(total)
    if eval_rate >= 80:
        text = (
            f"{fact}"
            f"{top_label}では確認できる根拠が比較的多く、AI任せではなく自分の基準で進めた記録が残っています。"
            f"{weak_label}は、記録の粒度をそろえることでさらに説明しやすくなります。"
        )
    elif eval_rate >= 60:
        text = (
            f"{fact}"
            f"{top_label}では判断や修正の材料が確認できます。"
            f"{weak_label}は、理由や反映経路を補うことでさらに伝わりやすくなります。"
        )
    elif eval_rate >= 45:
        text = (
            f"{fact}"
            f"{top_label}には評価できる材料が見られます。"
            f"一方で{weak_label}は、判断理由や修正経緯の記録をそろえる余地があります。"
        )
    else:
        text = (
            f"{fact}"
            f"{top_label}にも一部材料は見られます。"
            f"全体としては、判断理由や修正経緯を増やすことが次の改善点です。"
        )
    return _clean_report_sentence(text)


def _compose_strength_bullets_v2(scores: Dict[str, int]) -> str:
    rows = _strength_items(scores)[:3]
    if not rows:
        rows = [
            "複数案を比較して選ぶ力があります",
            "修正を積み上げながら、品質を上げられます",
            "AIを使っても、最後の判断を保てています",
        ]
    return "\n".join(f"・{row.rstrip('。')}。" for row in rows[:3])


def _compose_weakness_bullets_v2(scores: Dict[str, int]) -> str:
    weak_axis = min(scores.items(), key=lambda x: x[1])[0] if scores else AXIS_ORDER[4]
    sentence_map = {
        "成果物論理性": "判断とアウトプットの接続を強化することで、全体評価の安定性が向上します。",
        "判断プロセス": "比較観点と採否理由の記録を揃えることで、判断とアウトプットの接続がさらに安定します。",
        "修正プロセス": "修正理由を同じ形式で残すことで、判断とアウトプットの接続がさらに安定します。",
        "判断主体性": "選ばなかった理由を短く残すことで、判断とアウトプットの接続がさらに安定します。",
        "全体整合性": "最終反映の照合手順を固定することで、判断とアウトプットの接続がさらに安定します。",
    }
    sentence = sentence_map.get(weak_axis, "判断とアウトプットの接続を強化することで、全体評価の安定性が向上します。")
    return f"・{sentence.rstrip('。')}。"


def _score_badge(total_score: int) -> str:
    if total_score >= 470:
        return "S"
    if total_score >= 430:
        return "A"
    if total_score >= 380:
        return "B"
    if total_score >= 300:
        return "C"
    return "D"


def _dedupe_target_work(text: str) -> str:
    clean = _remove_internal_terms(text)
    if not clean:
        return ""
    clean = re.sub(r"\s+", " ", clean).strip()

    # 同文二重記載を最優先で抑止（例: "A A" / "A｜A"）
    m = re.match(r"^\s*(.+?)\s*(?:[｜|/]\s*|\s+)\1\s*$", clean)
    if m:
        clean = m.group(1).strip()

    # 区切りベースで重複除去
    parts = [p.strip() for p in re.split(r"[｜|/\n]+", clean) if p.strip()]
    unique: List[str] = []
    for part in parts:
        if part in unique:
            continue
        unique.append(part)
    if unique:
        merged = " ｜ ".join(unique)
        if len(merged) <= FIELD_LIMITS["target_work"]["chars"]:
            return merged
    return clean


def _strength_items(scores: Dict[str, int]) -> List[str]:
    ranking = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    sentence_map = {
        "成果物論理性": "判断した情報の優先順位がアウトプット構造に反映されており、説明時にも意図の再現性を保てています。",
        "判断プロセス": "比較観点と採否理由が連動して残っているため、重要判断の場面でも意思決定の根拠を共有できます。",
        "修正プロセス": "修正の狙いが段階ごとに接続されており、改善を一過性で終わらせず次回運用へ転用できています。",
        "判断主体性": "AI案を参照しつつ最終採否を自分で確定しているため、スピードと判断責任の両立が実務で機能しています。",
        "全体整合性": "ログ上の判断と最終成果物の対応が維持されており、提出後の説明でも因果関係を明確に示せます。",
    }
    items: List[str] = []
    for axis, _ in ranking:
        sentence = sentence_map.get(axis, "")
        if sentence and sentence not in items:
            items.append(sentence)
        if len(items) >= 3:
            break
    if len(items) < 3:
        items.extend(
            [
                "比較観点と採否理由が連動して残っているため、重要判断の場面でも意思決定の根拠を共有できます。",
                "修正の狙いが段階ごとに接続されており、改善を一過性で終わらせず次回運用へ転用できています。",
                "ログ上の判断と最終成果物の対応が維持されており、提出後の説明でも因果関係を明確に示せます。",
            ]
        )
    return items[:3]


def _weakness_items(report_data: Dict[str, Any], scores: Dict[str, int]) -> List[str]:
    text = _remove_internal_terms(
        _safe_text(report_data.get("weaknesses_text")) + " " + _safe_text(report_data.get("improve_text"))
    )
    items: List[str] = []
    if "QRコード連携" in text:
        items.append("共有導線の目的を添えると、見せる場面で相手が動きやすくなります")
    if "視覚設計" in text:
        items.append("見た目の意図を残すと、制作判断まで説明しやすくなります")
    if "未反映" in text:
        items.append("決めた内容を最後に照合すると、提出前の安心感が増します")
    if "根拠" in text:
        items.append("判断理由を短く残すと、後から自分の選択を見直しやすくなります")

    for axis, _ in sorted(scores.items(), key=lambda x: x[1]):
        candidate = {
            "成果物論理性": "訴求の流れを補うと、初見の相手にも価値が届きやすくなります",
            "判断プロセス": "優先順位を残すと、判断の速さと納得感を両立できます",
            "修正プロセス": "変更理由を揃えると、改善内容を次の案件にも活かせます",
            "判断主体性": "差し戻し理由を残すと、選別力をより明確に示せます",
            "全体整合性": "最終確認を固定すると、アウトプットを安心して提出できます",
        }.get(axis, "")
        if candidate and candidate not in items:
            items.append(candidate)
        if len(items) >= 3:
            break
    return items[:3]


def _improve_items(report_data: Dict[str, Any], scores: Dict[str, int]) -> List[str]:
    text = _remove_internal_terms(_safe_text(report_data.get("improve_text")))
    items: List[str] = []
    if "未反映" in text:
        items.append("公開前に決定事項と画面反映を照合する")
    if "根拠" in text:
        items.append("選んだ理由を1文で残し、後から見直せる形にする")
    if "QRコード連携" in text:
        items.append("共有導線の目的を先に書き、次の行動を明確にする")

    for axis, _ in sorted(scores.items(), key=lambda x: x[1]):
        candidate = {
            "成果物論理性": "主張と導線を並べ、読み手の次の行動を見直す",
            "判断プロセス": "比較観点を先に決め、選んだ理由を1文で残す",
            "修正プロセス": "変更の狙いを1文で残し、改善ログとして使う",
            "判断主体性": "選ばなかった理由を書き、AI案との違いを残す",
            "全体整合性": "公開前チェックを固定し、反映漏れを最後に確認する",
        }.get(axis, "")
        if candidate and candidate not in items:
            items.append(candidate)
        if len(items) >= 3:
            break

    return items[:3]


def _compose_improve_bullets(report_data: Dict[str, Any], scores: Dict[str, int]) -> str:
    """2P右下は、すぐ実行できる短い行動だけに限定する。"""
    items = _improve_items(report_data, scores)
    if not items:
        items = [
            "比較観点を先に決め、選んだ理由を1文で残す",
            "変更の狙いを1文で残し、改善ログとして使う",
            "公開前チェックを固定し、反映漏れを最後に確認する",
        ]
    fitted = "\n".join(f"・{item.rstrip('。')}" for item in items[:3])
    if not fitted.strip():
        fitted = (
            "・比較観点を先に決め、選んだ理由を1文で残す\n"
            "・変更の狙いを1文で残し、改善ログとして使う\n"
            "・公開前チェックを固定し、反映漏れを最後に確認する"
        )
    return fitted


def _compose_risk_body(report_data: Dict[str, Any], scores: Dict[str, int]) -> str:
    """AI活用リスクは、AI丸投げ有無と確認不足に絞る。"""
    source = _remove_internal_terms(
        " ".join(
            [
                _safe_text(report_data.get("risk_text")),
                _safe_text(report_data.get("weaknesses_text")),
                _safe_text(report_data.get("improve_text")),
            ]
        )
    )
    checkpoints: List[str] = []
    if "QR" in source:
        checkpoints.append("QRコード連携")
    if "視覚設計" in source:
        checkpoints.append("視覚設計")
    if "導線" in source:
        checkpoints.append("導線確認")
    checkpoints = list(dict.fromkeys(checkpoints))[:3]

    if checkpoints:
        target = "、".join(checkpoints)
        return (
            "AI案をそのまま採用する使い方にはなっていません。"
            f"注意点は、{target}など決めた要素が最終成果物で機能しているかです。"
            "提出前チェックに組み込めば、抜けや説明不足を早い段階で抑えられます。"
        )
    return (
        "AI案をそのまま採用する使い方にはなっていません。"
        "注意点は、選んだ理由と最終成果物が食い違わないようにすることです。"
        "提出前に照合手順を固定すれば、反映漏れと説明不足を早めに防げます。"
    )


def _build_report_payload(
    data: Dict[str, Any],
    report_data: Dict[str, Any],
    doc_id: str,
    target_period: str,
) -> Dict[str, str]:
    scores = _normalize_scores(data)
    total_score = _safe_int(data.get("total_score"), 0)
    evaluation_rate = _evaluation_rate(total_score)

    name = _safe_text(data.get("name"), "未設定")
    target_work = _safe_text(data.get("target_work"), "未設定")
    target_work_display = _safe_text(data.get("target_work_name"), target_work)
    issue_date = _short_date(_safe_text(data.get("issue_date"), datetime.now().strftime("%Y年%m月%d日")))
    source_context = data.get("evaluation_source", {})
    artifact_url = ""
    source_mode = ""
    if isinstance(source_context, dict):
        artifact_url = _safe_text(source_context.get("artifact_url"))
        source_mode = _safe_text(source_context.get("mode"))
    visual_only_report = source_mode in {"artifact_image_set", "screenshot_lp"}
    display_url = _display_url(artifact_url)

    overall_comment = _remove_internal_terms(_safe_text(report_data.get("overall_comment")))
    strengths_text = _remove_internal_terms(_safe_text(report_data.get("strengths_text")))
    weaknesses_text = _remove_internal_terms(_safe_text(report_data.get("weaknesses_text")))
    improve_text = _remove_internal_terms(_safe_text(report_data.get("improve_text")))
    aptitude_text = _remove_internal_terms(_safe_text(report_data.get("aptitude_text")))
    risk_text = _remove_internal_terms(_safe_text(report_data.get("risk_text")))
    responsibility_text = _remove_internal_terms(_safe_text(report_data.get("responsibility_text")))
    if responsibility_text.count("?") >= 3:
        responsibility_text = ""

    strengths_items = _strength_items(scores)
    weakness_items = _weakness_items(report_data, scores)
    improve_items = _improve_items(report_data, scores)
    page3_left_top = (
        "複数案を見比べ、修正しながら仕上げる力が表れています。"
        "AIを使っても、採用する内容を自分で選べる点が強みです。"
        "企画、編集、改善運用では、案出しの速さと品質判断を両立しやすくなります。"
        "作ったものを説明する場面でも、自分の言葉で扱える余地が広がります。"
    )

    axis_comments = report_data.get("axis_comments", {})
    top_axis = max(scores.items(), key=lambda x: x[1])[0] if scores else "判断プロセス"
    weak_axis = min(scores.items(), key=lambda x: x[1])[0] if scores else "全体整合性"
    top_axis_comment = ""
    weak_axis_comment = ""
    if isinstance(axis_comments, dict):
        top_axis_comment = _remove_internal_terms(_safe_text(axis_comments.get(top_axis)))
        weak_axis_comment = _remove_internal_terms(_safe_text(axis_comments.get(weak_axis)))

    deduped_target_work = _dedupe_target_work(_compact_target_work(target_work_display))
    analysis_source_text = "。".join(
        part
        for part in [
            overall_comment,
            strengths_text,
            weaknesses_text,
            improve_text,
            aptitude_text,
            risk_text,
            responsibility_text,
            top_axis_comment,
            weak_axis_comment,
        ]
        if part
    )
    relation_analysis_text = _fit_multiline_block(
        _compose_relation_analysis_text(analysis_source_text, improve_text, weaknesses_text),
        max_total_chars=FIELD_LIMITS["relation_analysis_text"]["chars"],
        max_lines=12,
        max_line_chars=40,
        fallback="■思考とアウトプットの関係\n①思考プロセス\nログで判断手順が確認される。\n②アウトプット\n判断結果がページ本文へ反映される。\n③因果関係\n判断記録と最終構成の対応範囲を評価する。",
    )
    visibility_analysis_text = _fit_multiline_block(
        _compose_visibility_analysis_text(analysis_source_text, improve_text, weaknesses_text),
        max_total_chars=FIELD_LIMITS["visibility_analysis_text"]["chars"],
        max_lines=12,
        max_line_chars=40,
            fallback="■どう見えるか\n①伝わるポイント\n判断根拠が本文に残る。\n②伝わりにくいポイント\n反映確認の記述が不足する。\n③評価につながるポイント\n判断と結果の接続が評価の根拠になる。",
    )
    relation_analysis_text = _normalize_text(relation_analysis_text)
    visibility_analysis_text = _normalize_text(visibility_analysis_text)
    improve_points_text = _force_page4_breaks(_fit_multiline_block(
        _compose_improve_points_text(analysis_source_text, improve_text, weaknesses_text),
        max_total_chars=FIELD_LIMITS["improve_points_text"]["chars"],
        max_lines=12,
        max_line_chars=40,
        fallback="■改善ポイント\n①思考プロセスの改善点\n採否理由の記録粒度をそろえる。\n②アウトプットの改善点\n修正意図と反映箇所を対応させる。\n③因果関係の改善点\n判断記録と最終反映の照合を固定する。",
    ))
    action_seed = _improve_items(report_data, scores)
    next_action_text = _force_page4_breaks(_fit_multiline_block(
        _compose_next_action_text(analysis_source_text, improve_text, weaknesses_text),
        max_total_chars=FIELD_LIMITS["next_action_text"]["chars"],
        max_lines=11,
        max_line_chars=40,
        fallback="■次回へ活かすポイント\n①改善の意味\n判断記録の統一で品質が上がる。\n②具体的なアクション\n・比較観点を先に固定する\n・反映確認を最終手順へ固定する",
    ))

    payload = {
        "target_work": _fit_plain(deduped_target_work, FIELD_LIMITS["target_work"]["chars"], "未設定"),
        "doc_id": _fit_plain(_display_doc_id(doc_id), FIELD_LIMITS["doc_id"]["chars"], _display_doc_id(doc_id)),
        "target_name": _fit_plain(name, FIELD_LIMITS["target_name"]["chars"], "未設定"),
        "overall_summary": _build_overall_summary(report_data, scores),
        "analysis_method": _build_analysis_method(report_data, scores),
        # 1P右側固定見出しを必ず表示（見出し欠落防止）
        "total_score": f"■ AI活用力総合評価　　{total_score} / 500",
        "overall_total_score": f"{total_score} / 500",
        "strengths_title": "■ あなたの強み",
        "strengths_bullets": "・"
        + _fit_bullets(
            "\n".join(strengths_items),
            max_lines=FIELD_LIMITS["strengths_bullets"]["lines"],
            max_line_chars=FIELD_LIMITS["strengths_bullets"]["line_chars"],
            max_total_chars=FIELD_LIMITS["strengths_bullets"]["chars"],
            fallback_items=strengths_items,
        ).lstrip("・"),
        "weaknesses_title": "■ 改善ポイント",
        "weaknesses_bullets": "・"
        + _fit_bullets(
            "\n".join(weakness_items),
            max_lines=FIELD_LIMITS["weaknesses_bullets"]["lines"],
            max_line_chars=FIELD_LIMITS["weaknesses_bullets"]["line_chars"],
            max_total_chars=FIELD_LIMITS["weaknesses_bullets"]["chars"],
            fallback_items=weakness_items,
        ).lstrip("・"),
        "meta_info": _fit_plain(issue_date, FIELD_LIMITS["meta_info"]["chars"], issue_date),
        "axis_output_logic_comment": _display_axis_comment(
            report_data,
            "成果物論理性",
            scores["成果物論理性"],
            "情報設計と訴求導線が整理され、アウトプットの主張が伝わります。",
        ),
        "axis_output_logic_score": f"{scores['成果物論理性']} / 100",
        "axis_judgment_comment": _display_axis_comment(
            report_data,
            "判断プロセス",
            scores["判断プロセス"],
            "比較・取捨選択・理由が揃い、判断の流れが明確です。",
        ),
        "axis_judgment_score": f"{scores['判断プロセス']} / 100",
        "axis_revision_comment": _display_axis_comment(
            report_data,
            "修正プロセス",
            scores["修正プロセス"],
            "段階的な修正が続き、改善の精度が保たれています。",
        ),
        "axis_revision_score": f"{scores['修正プロセス']} / 100",
        "axis_agency_comment": _display_axis_comment(
            report_data,
            "判断主体性",
            scores["判断主体性"],
            "最終判断を人が握り、取捨選択の主導権が維持されています。",
        ),
        "axis_agency_score": f"{scores['判断主体性']} / 100",
        "axis_consistency_comment": _display_axis_comment(
            report_data,
            "全体整合性",
            scores["全体整合性"],
            "ログ判断とアウトプット反映の対応は概ね保たれています。",
        ),
        "axis_consistency_score": f"{scores['全体整合性']} / 100",
        "improve_bullets": _compose_improve_bullets(report_data, scores),
        "responsibility_header": _fit_plain(
            "■ AI利用における責任構造\n\n処理主体：人\nAIの役割：情報生成支援\n最終決定：人\n責任主体：人",
            FIELD_LIMITS["responsibility_header"]["chars"],
            "",
        ),
        "responsibility_body": _fit_prose_full(
            "AIは候補出しと情報整理を補助する役割です。"
            "採用する内容、修正の方向、公開前の最終判断は自分で決めています。"
            "判断の主導権が残っているため、AI任せのアウトプットにはなっていません。"
            "最終的な説明責任も、人が引き受けられる構造です。"
            "ログとアウトプットの対応が残るため、第三者にも責任の所在を説明できます。",
            FIELD_LIMITS["responsibility_body"]["chars"],
            FIELD_LIMITS["responsibility_body"]["sentences"],
            "AIは整理を補助し、最終判断と責任は人が担います。",
            min_fill_ratio=MIN_FILL_RATIO.get("responsibility_body", 0.78),
            extra_sentences=FILLER_SENTENCES.get("responsibility_body"),
        ),
        "risk_bullets": _dedupe_lines_by_keywords(
            "■AI活用リスク評価\n"
            + _fit_bullets_full_sentence(
            risk_text + " " + weaknesses_text,
            max_lines=FIELD_LIMITS["risk_bullets"]["lines"],
            max_line_chars=FIELD_LIMITS["risk_bullets"]["line_chars"],
            max_total_chars=FIELD_LIMITS["risk_bullets"]["chars"],
            fallback=(
                "決めた内容が最後まで残らない場合、提出前に確認工程を入れる必要があります。"
                "理由の残し方に差があると、後から判断を見直しにくくなります。"
                "共有導線や視覚設計の意図を残すと、AI任せではない提案になります。"
            ),
            ),
            keywords=["未反映", "根拠記録", "ログ判断"],
        ),
        "aptitude_bullets": _fit_bullets(
            "",
            max_lines=FIELD_LIMITS["aptitude_bullets"]["lines"],
            max_line_chars=FIELD_LIMITS["aptitude_bullets"]["line_chars"],
            max_total_chars=FIELD_LIMITS["aptitude_bullets"]["chars"],
            fallback_items=_build_aptitude_short_items(aptitude_text),
        ),
        "page3_summary_bullets": _fit_bullets(
            "",
            max_lines=FIELD_LIMITS["page3_summary_bullets"]["lines"],
            max_line_chars=FIELD_LIMITS["page3_summary_bullets"]["line_chars"],
            max_total_chars=FIELD_LIMITS["page3_summary_bullets"]["chars"],
            fallback_items=_build_page3_summary_items(),
        ),
        "transparency_bullets": _fit_bullets(
            "",
            max_lines=FIELD_LIMITS["transparency_bullets"]["lines"],
            max_line_chars=FIELD_LIMITS["transparency_bullets"]["line_chars"],
            max_total_chars=FIELD_LIMITS["transparency_bullets"]["chars"],
            fallback_items=[
                "判断理由が残るため、後から経緯を追いやすくなります。",
                "修正前後の差分が見え、改善内容を読み取れます。",
                "AI案の採否を自分で扱ったことが伝わります。",
            ],
        ),
        "summary_text": _fit_dense_from_sources(
            sources=[
                page3_left_top,
                aptitude_text,
                _safe_text(report_data.get("overall_comment")),
                _safe_text(report_data.get("summary_text")),
            ],
            max_chars=FIELD_LIMITS["summary_text"]["chars"],
            max_sentences=FIELD_LIMITS["summary_text"]["sentences"],
            fallback=page3_left_top,
            min_fill_ratio=MIN_FILL_RATIO.get("summary_text", 0.7),
            extra_sentences=FILLER_SENTENCES.get("summary_text"),
        ),
        "usage_note": _fit_to_line_rule(
            "usage_note",
            sources=[_build_growth_note(report_data)],
            fallback=(
                "今後の伸びしろは、決めた内容を最後まで残し、判断理由を短く同じ形で記録することにあります。"
                "公開前の見直しを固定すると、提出物としての説得力が増します。"
            ),
        ),
        "relation_analysis_text": relation_analysis_text,
        "visibility_analysis_text": visibility_analysis_text,
        "improve_points_text": improve_points_text,
        "next_action_text": next_action_text,
    }
    axis_blocks = report_data.get("axis_comment_blocks", {})
    axis_comments = report_data.get("axis_comments", {})
    improve_src = _safe_text(report_data.get("improve_text"))
    weakness_src = _safe_text(report_data.get("weaknesses_text"))

    payload["overall_summary"] = _fit_to_line_rule(
        "overall_summary",
        sources=[_compose_overall_summary_v2(scores, _safe_text(report_data.get("overall_comment")), improve_src)],
        fallback=payload.get("overall_summary", ""),
    )
    payload["overall_summary"] = _integrate_strengths_into_overall(payload.get("overall_summary", ""))
    payload["strengths_title"] = ""
    payload["strengths_bullets"] = ""
    payload["weaknesses_bullets"] = _fit_bullets(
        _compose_weakness_bullets_v2(scores),
        max_lines=FIELD_LIMITS["weaknesses_bullets"]["lines"],
        max_line_chars=FIELD_LIMITS["weaknesses_bullets"]["line_chars"],
        max_total_chars=FIELD_LIMITS["weaknesses_bullets"]["chars"],
        fallback_items=weakness_items,
    )
    ai_capability_source = "。".join(
        part
        for part in [
            _safe_text(data.get("output_text")),
            weaknesses_text,
            improve_src,
            risk_text,
        ]
        if part
    )
    capability_score = _resolve_ai_capability_score(data, report_data, scores)
    payload["ai_capability_score"] = f"{capability_score} / 100"
    payload["ai_capability_evaluation"] = _build_ai_capability_evaluation(
        ai_capability_source,
        improve_src,
        weakness_src,
        capability_score,
        total_score,
    )
    payload["output_logic_evaluation"] = _build_output_logic_evaluation(
        ai_capability_source,
        improve_src,
        weakness_src,
        scores.get("成果物論理性", 0),
        total_score,
    )
    payload["judgment_process_evaluation"] = _build_judgment_process_evaluation(
        ai_capability_source,
        improve_src,
        weakness_src,
        scores.get("判断プロセス", 0),
        total_score,
    )
    payload["revision_process_evaluation"] = _build_revision_process_evaluation(
        ai_capability_source,
        improve_src,
        weakness_src,
        scores.get("修正プロセス", 0),
        total_score,
    )
    payload["agency_process_evaluation"] = _build_agency_process_evaluation(
        ai_capability_source,
        improve_src,
        weakness_src,
        scores.get("判断主体性", 0),
        total_score,
    )
    payload["consistency_process_evaluation"] = _build_consistency_process_evaluation(
        ai_capability_source,
        improve_src,
        weakness_src,
        scores.get("全体整合性", 0),
        total_score,
    )
    payload["thought_output_relation"] = _build_thought_output_relation(
        ai_capability_source,
        improve_src,
        weakness_src,
        scores,
    )
    payload["third_party_visibility"] = _build_third_party_visibility(
        ai_capability_source,
        improve_src,
        weakness_src,
        scores,
    )
    payload["applicable_domain_text"] = _build_applicable_domain_text(
        ai_capability_source,
        improve_src,
        weakness_src,
        scores,
    )
    payload["applicable_business_list"] = _build_applicable_business_list(
        ai_capability_source,
        scores,
        data,
        report_data,
    )
    payload["ai_use_scope_statement"] = _build_ai_use_scope_statement(
        scores,
        ai_capability_source,
        improve_src,
        weakness_src,
        report_data,
    )
    payload["page6_transparency_text"] = _build_page6_transparency_text(scores)
    payload["page6_responsibility_structure"] = _build_page6_responsibility_structure()
    payload["page6_responsibility_body"] = _build_page6_responsibility_body(scores)

    axis_payload_map = {
        AXIS_ORDER[0]: ("axis_output_logic_comment", "axis_output_logic_comment"),
        AXIS_ORDER[1]: ("axis_judgment_comment", "axis_judgment_comment"),
        AXIS_ORDER[2]: ("axis_revision_comment", "axis_revision_comment"),
        AXIS_ORDER[3]: ("axis_agency_comment", "axis_agency_comment"),
        AXIS_ORDER[4]: ("axis_consistency_comment", "axis_consistency_comment"),
    }
    for axis_key, (payload_key, limit_key) in axis_payload_map.items():
        src = ""
        if isinstance(axis_blocks, dict):
            src = _safe_text(axis_blocks.get(axis_key))
        if not src and isinstance(axis_comments, dict):
            src = _safe_text(axis_comments.get(axis_key))
        src = "。".join(
            part
            for part in [
                src,
                weaknesses_text,
                improve_src,
                risk_text,
            ]
            if part
        )
        composed = _build_structured_axis_text(
            axis=axis_key,
            score=scores.get(axis_key, 0),
            source_text=src,
            improve_text=improve_src,
            weakness_text=weakness_src,
        )
        payload[payload_key] = _fit_axis_comment_block(composed)

    aptitude_body = _single_line_prose(aptitude_text)
    if not aptitude_body:
        aptitude_body = _single_line_prose(" ".join(_build_aptitude_fallback_items()))
    payload["aptitude_bullets"] = aptitude_body
    summary_body = _fit_to_line_rule(
        "summary_text",
        sources=[
            page3_left_top,
            aptitude_text,
            overall_comment,
            strengths_text,
        ],
        fallback=page3_left_top,
    )
    if evaluation_rate < 45:
        summary_body = (
            "AI利用の記録と、人が判断に関わった痕跡は確認できます。"
            "現時点では、判断と修正の記録を増やすことで活用領域を明確にする段階です。"
            "\n"
            "確認できた材料として、AI案への違和感、不要点の指摘、修正方針の一部があります。"
            "採否理由、修正理由、反映箇所を残すことで、活用可能領域をより具体的に評価できます。"
        )
    elif evaluation_rate < 65:
        summary_body = (
            "AIを使っても、採用する内容を自分で選ぶ記録が確認できます。"
            "判断、修正、採否の材料も一部残っており、構成や導線に合わせて人が選別した流れが見られます。"
            "\n"
            "活用可能領域は評価できますが、判断理由、修正経緯、反映箇所をそろえるとさらに伝わります。"
            "確認できた判断は、次の改善や提案にも活用できる材料です。"
        )
    else:
        summary_body = (
            "AIを使っても、採用する内容を自分で選べる点が確認できます。"
            "比較検討、修正判断、採否判断がログ上に残り、成果物の構成や導線との対応も評価材料になります。"
            "\n"
            "活用可能領域は、確認できた判断と修正の範囲で評価できます。改善点は、判断理由と修正経緯の記録量をそろえることです。"
        )
    payload["summary_text"] = "■活用可能領域\n" + _single_line_prose(summary_body)

    if evaluation_rate < 45:
        risk_body = (
            "AI案に対して人が選んだ痕跡は確認できます。"
            "注意点は、何を見送り、なぜ選んだかの理由を残すことです。"
            "\n"
            "採否理由、修正理由、反映箇所を短く残すと、AI任せに見えるリスクを下げられます。"
        )
    elif evaluation_rate < 65:
        risk_body = (
            "AI案をそのまま採用していない箇所は確認できます。"
            "注意点は、決めた要素が最終アウトプットで確認できる形になっているかです。"
            "\n"
            "判断記録と反映箇所を対応させることで、説明不足のリスクを抑えられます。"
        )
    else:
        risk_body = (
            "AI案をそのまま採用していない箇所は確認できます。"
            "注意点は、決めた要素が最終アウトプットで確認できる形になっているかです。"
            "\n"
            "判断記録と反映箇所を対応させることで、AI任せに見えるリスクを下げられます。"
        )
    payload["risk_bullets"] = "■AI活用リスク評価\n" + _single_line_prose(risk_body)

    payload["responsibility_header"] = (
        "■ AI利用における責任構造\n"
        "AIは情報生成を補助し、採用内容、修正方向、公開前の最終判断は人が担う。"
        "そのため、処理の補助はAIにあっても、判断と責任の主体は利用者に残る。"
    )
    if evaluation_rate < 45:
        responsibility_body = (
            "採用する内容や修正方向に人の判断が関わった記録は一部見られます。"
            "AI案をそのまま通したのではなく、不要点や違和感を示した発言も評価材料になります。"
            "責任の所在をさらに明確にするには、判断理由や見送った理由を短く残すことが有効です。"
            "AI案をどのように選び、どこへ反映したかを残すと、成果物との関係まで説明しやすくなります。"
            "確認できた人の判断は、責任構造を示す土台になります。"
        )
    elif evaluation_rate < 65:
        responsibility_body = (
            "採用する内容や修正方向は、人が判断した記録として確認できます。"
            "AI任せではない使い方が見られ、採否、修正、反映先を人が扱った流れも一部残っています。"
            "今後は、選んだ理由、見送った理由、反映箇所をそろえることで責任の所在をさらに示しやすくなります。"
            "確認できた判断内容は評価材料になり、記録を増やすほど第三者にも説明しやすくなります。"
            "最終判断を人が担った範囲も伝わりやすくなります。"
        )
    else:
        responsibility_body = (
            "採用する内容、修正の方向、公開前の最終判断は自分で決めています。"
            "判断の主導権が残っているため、AI任せのアウトプットにはなっていません。"
            "ログとアウトプットの対応が残るため、第三者にも責任の所在を説明できます。"
            "比較した案、採用した内容、見送った内容が分かるほど、判断主体はより明確になります。"
            "生成結果は補助材料であり、アウトプットの責任主体は人に残ります。"
        )
    payload["responsibility_body"] = _single_line_prose(responsibility_body)

    if evaluation_rate < 45:
        transparency_body = (
            "AI案の採否や修正前後の差分は一部確認できます。"
            "不要点の指摘や変更方針も見られるため、AI案をそのまま採用しただけではないことは読み取れます。"
            "後から経緯をたどるには、判断理由、修正理由、反映箇所の情報を増やす必要があります。"
            "現時点では、確認できた利用過程を評価し、記録の追加を改善点とします。"
        )
    elif evaluation_rate < 65:
        transparency_body = (
            "AI案の採否や修正前後の差分は確認できます。"
            "判断理由と反映箇所も一部残っているため、利用過程を説明する材料があります。"
            "採用した内容、見送った内容、修正した内容がそろうほど、AI利用の透明性は高まります。"
            "さらに記録粒度をそろえると、第三者にも経緯を伝えやすくなります。"
        )
    else:
        transparency_body = (
            "AI活用の透明性は、判断理由、修正前後の差分、AI案の採否が残ることで成立します。"
            "後から経緯を確認できるため、単なる自動生成ではなく判断を伴う利用として説明できます。"
            "どの案を採用し、どの案を見送ったかが残る点も重要です。"
            "アウトプットに反映された判断を追えるため、第三者にも利用過程を示しやすくなります。"
        )
    payload["transparency_bullets"] = "■ AI活用の透明性\n" + _single_line_prose(transparency_body)

    payload["aptitude_bullets"] = _collapse_cjk_spacing(payload.get("aptitude_bullets", ""))
    payload["risk_bullets"] = _collapse_cjk_spacing(payload.get("risk_bullets", ""))
    payload["usage_note"] = _collapse_cjk_spacing(payload.get("usage_note", ""))
    payload["transparency_bullets"] = _collapse_cjk_spacing(payload.get("transparency_bullets", ""))
    if visual_only_report:
        for key, value in list(payload.items()):
            if isinstance(value, str):
                payload[key] = _rewrite_visual_artifact_report_text(value)
    if not payload.get("usage_note", "").lstrip().startswith("■"):
        payload["usage_note"] = "■ 続けると伸びるポイント\n" + payload.get("usage_note", "").lstrip()
    if not payload.get("transparency_bullets", "").lstrip().startswith("■"):
        payload["transparency_bullets"] = "■ AI活用の透明性\n" + payload.get("transparency_bullets", "").lstrip()
    for prose_key in (
        "overall_summary",
        "axis_output_logic_comment",
        "axis_judgment_comment",
        "axis_revision_comment",
        "axis_agency_comment",
        "axis_consistency_comment",
        "summary_text",
        "risk_bullets",
        "responsibility_body",
        "usage_note",
    ):
        payload[prose_key] = _indent_prose_lines(payload.get(prose_key, ""))
    payload["responsibility_body"] = _indent_prose_lines(payload.get("responsibility_body", ""))
    return payload


def build_report_payload(
    data: Dict[str, Any],
    report_data: Dict[str, Any],
    doc_id: str,
    target_period: str = "",
    canonical_evaluation_result: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build the canonical Japanese production report payload."""
    payload = _build_report_payload(
        data=data,
        report_data=report_data,
        doc_id=doc_id,
        target_period=target_period,
    )
    if canonical_evaluation_result:
        from engine.evidence_bound_prose import build_evidence_bound_prose

        evidence_prose = build_evidence_bound_prose(canonical_evaluation_result, language="ja")
        for key, value in evidence_prose.items():
            if not str(payload.get(key) or "").strip():
                payload[key] = value
    return payload


def _ensure_run_style(rpr: ET.Element, *, font_name: str = JP_FONT_FAMILY, size: str | None = None, bold: str | None = None) -> None:
    rpr.set("lang", "ja-JP")
    rpr.set("altLang", "ja-JP")
    if size is not None:
        rpr.set("sz", str(size))
    if bold is not None:
        rpr.set("b", str(bold))
    rpr.set("spc", "0")
    rpr.set("kern", "0")
    rpr.attrib.pop("kumimoji", None)
    for tag in ("latin", "ea", "cs"):
        child = rpr.find(f"a:{tag}", NS)
        if child is None:
            child = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
        child.set("typeface", font_name)


def _normalize_paragraph_style(shape: ET.Element) -> None:
    def _apply_font(rpr: ET.Element) -> None:
        _ensure_run_style(rpr)

    for paragraph in shape.findall(".//a:p", NS):
        ppr = paragraph.find("a:pPr", NS)
        if ppr is None:
            ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr")
        ppr.set("algn", "l")
        # 段落前後余白を同値にして、上下バランスを揃える
        for node in list(ppr):
            if node.tag in (f"{{{A_NS}}}spcBef", f"{{{A_NS}}}spcAft"):
                ppr.remove(node)
        spc_bef = ET.SubElement(ppr, f"{{{A_NS}}}spcBef")
        spc_bef_pts = ET.SubElement(spc_bef, f"{{{A_NS}}}spcPts")
        spc_bef_pts.set("val", "0")
        spc_aft = ET.SubElement(ppr, f"{{{A_NS}}}spcAft")
        spc_aft_pts = ET.SubElement(spc_aft, f"{{{A_NS}}}spcPts")
        spc_aft_pts.set("val", "0")
        for attr in ("fontAlgn", "eaLnBrk", "latinLnBrk", "hangingPunct"):
            if attr in ppr.attrib:
                del ppr.attrib[attr]

    for rpr in shape.findall(".//a:rPr", NS):
        _apply_font(rpr)

    for drpr in shape.findall(".//a:defRPr", NS):
        for attr in ("spc", "kern"):
            if attr in drpr.attrib:
                del drpr.attrib[attr]
        _apply_font(drpr)

    for erpr in shape.findall(".//a:endParaRPr", NS):
        _apply_font(erpr)


def _rewrite_shape_single_run(shape: ET.Element, text: str, *, font_name: str = JP_FONT_FAMILY) -> None:
    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        tx_body = ET.SubElement(shape, f"{{{PPT_NS}}}txBody")
        ET.SubElement(tx_body, f"{{{A_NS}}}bodyPr")
        ET.SubElement(tx_body, f"{{{A_NS}}}lstStyle")

    body_pr = tx_body.find("a:bodyPr", NS)
    lst_style = tx_body.find("a:lstStyle", NS)
    existing_rpr = shape.find(".//a:rPr", NS)
    size = existing_rpr.get("sz") if existing_rpr is not None and existing_rpr.get("sz") else None
    bold = existing_rpr.get("b") if existing_rpr is not None and existing_rpr.get("b") is not None else "0"
    existing_ppr = shape.find(".//a:pPr", NS)

    for child in list(tx_body):
        if child not in (body_pr, lst_style):
            tx_body.remove(child)

    paragraph = ET.SubElement(tx_body, f"{{{A_NS}}}p")
    ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr")
    if existing_ppr is not None:
        ppr.attrib.update(existing_ppr.attrib)
    ppr.set("algn", ppr.get("algn", "l"))
    for attr in ("fontAlgn", "eaLnBrk", "latinLnBrk", "hangingPunct"):
        ppr.attrib.pop(attr, None)

    run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
    rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
    _ensure_run_style(rpr, font_name=font_name, size=size, bold=bold)
    text_node = ET.SubElement(run, f"{{{A_NS}}}t")
    normalized = _normalize_replace_text(text)
    if normalized.startswith((" ", "　")) or normalized.endswith((" ", "　")):
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = normalized
    end = ET.SubElement(paragraph, f"{{{A_NS}}}endParaRPr")
    _ensure_run_style(end, font_name=font_name, size=size, bold=bold)


def _replace_shape_text(slide_xml: bytes, replacements: Dict[int, str], *, rewrite_single_run: bool = False) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)

    for shape_idx, new_text in replacements.items():
        if shape_idx <= 0 or shape_idx > len(shapes):
            continue

        shape = shapes[shape_idx - 1]
        if rewrite_single_run:
            _rewrite_shape_single_run(shape, new_text)
            continue

        text_nodes = shape.findall(".//a:t", NS)
        if not text_nodes:
            tx_body = shape.find("p:txBody", NS)
            if tx_body is None:
                tx_body = ET.SubElement(shape, f"{{{PPT_NS}}}txBody")
                ET.SubElement(tx_body, f"{{{A_NS}}}bodyPr")
                ET.SubElement(tx_body, f"{{{A_NS}}}lstStyle")
            paragraph = tx_body.find("a:p", NS)
            if paragraph is None:
                paragraph = ET.SubElement(tx_body, f"{{{A_NS}}}p")
            run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
            rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
            rpr.set("lang", "ja-JP")
            for tag in ("latin", "ea", "cs"):
                ft = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
                ft.set("typeface", JP_FONT_FAMILY)
            text_node = ET.SubElement(run, f"{{{A_NS}}}t")
            text_nodes = [text_node]
        if not text_nodes:
            continue

        text_nodes[0].text = _normalize_replace_text(new_text)
        for node in text_nodes[1:]:
            node.text = ""

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _set_score_runs(
    shape: ET.Element,
    score_value: int,
    *,
    main_size: int = 2000,
    suffix_size: int = 1300,
    suffix_text: str = "  / 100",
    font_name: str = JP_FONT_FAMILY,
    main_spacing: int = 0,
    suffix_spacing: int = 0,
    margin_left: str = "420000",
) -> None:
    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        return
    body_pr = tx_body.find("a:bodyPr", NS)
    if body_pr is not None:
        # スコア表示は行内配置がずれやすいため、textbox 内の上下基準を固定する。
        body_pr.set("anchor", "t")
        body_pr.set("anchorCtr", "0")
        body_pr.set("tIns", "0")
        body_pr.set("bIns", "0")
        body_pr.set("lIns", "0")
        body_pr.set("rIns", "0")
    paragraph = tx_body.find("a:p", NS)
    if paragraph is None:
        paragraph = ET.SubElement(tx_body, f"{{{A_NS}}}p")
    for child in list(paragraph):
        paragraph.remove(child)

    ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr")
    ppr.set("algn", "l")
    ppr.set("marL", margin_left)

    def _append_run(text: str, size: int, bold: bool = False, spacing: int = 0) -> None:
        run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
        rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
        rpr.set("lang", "ja-JP")
        rpr.set("sz", str(size))
        rpr.set("b", "1" if bold else "0")
        rpr.set("spc", str(spacing))
        rpr.set("kern", "0")
        for tag in ("latin", "ea", "cs"):
            ft = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
            ft.set("typeface", font_name)
        t = ET.SubElement(run, f"{{{A_NS}}}t")
        if text.startswith(" ") or text.endswith(" ") or "  " in text:
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text

    _append_run(str(score_value), main_size, False, main_spacing)
    _append_run(suffix_text, suffix_size, False, suffix_spacing)
    epr = ET.SubElement(paragraph, f"{{{A_NS}}}endParaRPr")
    epr.set("lang", "ja-JP")
    epr.set("sz", str(main_size))
    epr.set("b", "0")
    epr.set("spc", "0")
    epr.set("kern", "0")
    for tag in ("latin", "ea", "cs"):
        ft = ET.SubElement(epr, f"{{{A_NS}}}{tag}")
        ft.set("typeface", font_name)


def _style_axis_score_shapes(slide_xml: bytes, score_shape_indexes: List[int]) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    for shape_idx in score_shape_indexes:
        if shape_idx <= 0 or shape_idx > len(shapes):
            continue
        shape = shapes[shape_idx - 1]
        font_name = JP_FONT_FAMILY
        text_nodes = shape.findall(".//a:t", NS)
        raw_text = "".join((t.text or "") for t in text_nodes).strip()
        m = re.search(r"(\d{1,3})", raw_text)
        if not m:
            continue
        score_value = max(0, min(100, _safe_int(m.group(1), 0)))
        main_size = 1650
        suffix_size = 1150
        main_spacing = 0
        suffix_spacing = 0
        margin_left = "90000"
        if shape_idx == 6:
            margin_left = "90000"
        _set_score_runs(
            shape,
            score_value,
            main_size=main_size,
            suffix_size=suffix_size,
            suffix_text=" / 100",
            font_name=font_name,
            main_spacing=main_spacing,
            suffix_spacing=suffix_spacing,
            margin_left=margin_left,
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _style_slide2_body_fontsize(
    slide_xml: bytes,
    body_shape_indexes: List[int],
    size: int = 1050,
    line_spacing_pct: int = 92000,
) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    for shape_idx in body_shape_indexes:
        if shape_idx <= 0 or shape_idx > len(shapes):
            continue
        shape = shapes[shape_idx - 1]
        for rpr in shape.findall(".//a:rPr", NS):
            rpr.set("sz", str(size))
        for p in shape.findall(".//a:p", NS):
            ppr = p.find("a:pPr", NS)
            if ppr is None:
                ppr = ET.SubElement(p, f"{{{A_NS}}}pPr")
            for node in list(ppr):
                if node.tag == f"{{{A_NS}}}lnSpc":
                    ppr.remove(node)
            ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
            spc_pct = ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct")
            spc_pct.set("val", str(line_spacing_pct))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _style_slide2_body_paragraphs(
    slide_xml: bytes,
    body_shape_indexes: List[int],
    *,
    size: int = 1050,
    line_spacing_pct: int = 140000,
    paragraph_after_pts: int = 600,
) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    for shape_idx in body_shape_indexes:
        if shape_idx <= 0 or shape_idx > len(shapes):
            continue
        _rewrite_textbox_paragraphs(
            shapes[shape_idx - 1],
            font_size=size,
            line_spacing_pct=line_spacing_pct,
            paragraph_after_pts=paragraph_after_pts,
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _layout_slide2_heading_score_body(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    groups = [
        (4, 6, 5),
        (10, 12, 11),
        (13, 15, 14),
        (17, 19, 18),
        (20, 22, 21),
    ]
    for heading_idx, score_idx, body_idx in groups:
        if max(heading_idx, score_idx, body_idx) > len(shapes):
            continue
        heading_box = _get_shape_box(shapes[heading_idx - 1])
        score_box = _get_shape_box(shapes[score_idx - 1])
        body_box = _get_shape_box(shapes[body_idx - 1])
        if heading_box is None or score_box is None or body_box is None:
            continue
        hx, hy, hw, hh = heading_box
        _, _, sw, sh = score_box
        bx, _, bw, bh = body_box
        score_y = hy + hh + 20000
        body_y = score_y + sh + 20000
        _set_shape_box(shapes[score_idx - 1], hx + 90000, score_y, sw, sh)
        _set_shape_box(shapes[body_idx - 1], bx, body_y, bw, max(780000, bh - (body_y - body_box[1])))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _style_slide2_action_area(slide_xml: bytes, action_text: str) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    if len(shapes) < 23:
        return slide_xml
    heading_shape = shapes[22]
    for node in heading_shape.findall(".//a:t", NS):
        if "改善示唆" in (node.text or ""):
            node.text = (node.text or "").replace("改善示唆", "次のアクション")

    if len(shapes) < 24:
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    body_shape = shapes[23]
    tx_body = body_shape.find("p:txBody", NS)
    if tx_body is None:
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    body_pr = tx_body.find("a:bodyPr", NS)
    lst_style = tx_body.find("a:lstStyle", NS)
    for child in list(tx_body):
        if child not in (body_pr, lst_style):
            tx_body.remove(child)

    items = [line.strip().lstrip("・").strip() for line in action_text.splitlines() if line.strip()]
    if not items:
        items = [
            "比較観点を先に決め、選んだ理由を1文で残す",
            "変更の狙いを1文で残し、改善ログとして使う",
            "公開前チェックを固定し、反映漏れを最後に確認する",
        ]

    for item in items[:3]:
        p = ET.SubElement(tx_body, f"{{{A_NS}}}p")
        ppr = ET.SubElement(p, f"{{{A_NS}}}pPr")
        ppr.set("algn", "l")
        ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
        spc_pct = ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct")
        spc_pct.set("val", "92000")
        run = ET.SubElement(p, f"{{{A_NS}}}r")
        rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
        rpr.set("lang", "ja-JP")
        rpr.set("sz", "1200")
        rpr.set("b", "0")
        rpr.set("spc", "0")
        rpr.set("kern", "0")
        for tag in ("latin", "ea", "cs"):
            ft = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
            ft.set("typeface", "BIZ UDP明朝 Medium")
        t = ET.SubElement(run, f"{{{A_NS}}}t")
        t.text = f"・ {item}"
        epr = ET.SubElement(p, f"{{{A_NS}}}endParaRPr")
        epr.set("lang", "ja-JP")
        epr.set("sz", "1200")
        epr.set("spc", "0")
        for tag in ("latin", "ea", "cs"):
            ft = ET.SubElement(epr, f"{{{A_NS}}}{tag}")
            ft.set("typeface", "BIZ UDP明朝 Medium")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _style_slide1_target_work_fontsize(slide_xml: bytes, shape_idx: int = 5, size: int = 1050) -> bytes:
    """1ページ目の対象アウトプット値をラベル相当サイズに統一する。"""
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    if shape_idx <= 0 or shape_idx > len(shapes):
        return slide_xml
    shape = shapes[shape_idx - 1]
    for rpr in shape.findall(".//a:rPr", NS):
        rpr.set("sz", str(size))
        rpr.set("b", "0")
        rpr.set("spc", "0")
        rpr.set("kern", "0")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _style_slide1_target_work_fontsize_auto(slide_xml: bytes, target_work: str, size: int = 1050) -> bytes:
    """1P の対象アウトプット値を shape 自動検出でフォントサイズ統一する。"""
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    tw = _normalize_text(target_work)
    for shape in shapes:
        txt = "".join((t.text or "") for t in shape.findall(".//a:t", NS))
        if "対象アウトプット" in txt and (tw and tw in txt):
            for rpr in shape.findall(".//a:rPr", NS):
                rpr.set("sz", str(size))
                rpr.set("b", "0")
                rpr.set("spc", "0")
                rpr.set("kern", "0")
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    # fallback: 従来の固定indexを使う
    return _style_slide1_target_work_fontsize(slide_xml, shape_idx=5, size=size)


def _style_slide1_bullet_body_fontsize(
    slide_xml: bytes,
    body_shape_indexes: List[int],
    size: int = 1050,
) -> bytes:
    """1P右側の箇条書き本文だけを総評本文に近い見え方へ微調整する。"""
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    for shape_idx in body_shape_indexes:
        if shape_idx <= 0 or shape_idx > len(shapes):
            continue
        shape = shapes[shape_idx - 1]
        for rpr in shape.findall(".//a:rPr", NS):
            rpr.set("sz", str(size))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _shift_slide1_strength_area(slide_xml: bytes, delta_y: int = 220000) -> bytes:
    """1P右欄の総評本文と強み欄の間に、約1行分の余白を作る。"""
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    for shape_idx in (13, 14, 15, 16):
        if shape_idx <= 0 or shape_idx > len(shapes):
            continue
        off = shapes[shape_idx - 1].find("./p:spPr/a:xfrm/a:off", NS)
        if off is None:
            continue
        off.set("y", str(_safe_int(off.get("y"), 0) + delta_y))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _style_total_score_shape(slide_xml: bytes, shape_idx: int, score_value: int) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    if shape_idx <= 0 or shape_idx > len(shapes):
        return slide_xml
    shape = shapes[shape_idx - 1]
    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        return slide_xml
    paragraph = tx_body.find("a:p", NS)
    if paragraph is None:
        paragraph = ET.SubElement(tx_body, f"{{{A_NS}}}p")
    font_name = "BIZ UDP明朝 Medium"
    first_rpr = shape.find(".//a:rPr", NS)
    if first_rpr is not None:
        font_node = first_rpr.find("a:ea", NS) or first_rpr.find("a:latin", NS)
        if font_node is not None and font_node.get("typeface"):
            font_name = font_node.get("typeface")
    for child in list(paragraph):
        paragraph.remove(child)

    ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr")
    ppr.set("algn", "l")

    def _append_run(
        text: str,
        size: int,
        bold: bool = False,
        preserve_space: bool = False,
        spacing: int = 0,
    ) -> None:
        run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
        rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
        rpr.set("lang", "ja-JP")
        rpr.set("sz", str(size))
        rpr.set("b", "1" if bold else "0")
        rpr.set("spc", str(spacing))
        rpr.set("kern", "0")
        for tag in ("latin", "ea", "cs"):
            ft = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
            ft.set("typeface", font_name)
        t = ET.SubElement(run, f"{{{A_NS}}}t")
        if preserve_space or text.startswith(" ") or text.endswith(" ") or text.startswith("　") or text.endswith("　"):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        t.text = text

    _append_run("■ ", 1600, False, spacing=0, preserve_space=True)
    _append_run("AI", 1600, False, spacing=0)
    _append_run("活用能力総合評価　", 1600, False, spacing=0, preserve_space=True)
    _append_run("　  ", 1600, False, preserve_space=True)
    _append_run(str(score_value), 3200, False)
    _append_run(" / ", 2000, False)
    _append_run("500", 2000, False)
    epr = ET.SubElement(paragraph, f"{{{A_NS}}}endParaRPr")
    epr.set("lang", "ja-JP")
    for tag in ("latin", "ea", "cs"):
        ft = ET.SubElement(epr, f"{{{A_NS}}}{tag}")
        ft.set("typeface", font_name)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _style_total_score_shape_auto(slide_xml: bytes, score_value: int) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    target_idx = 0
    for i, shape in enumerate(shapes, 1):
        txt = "".join((t.text or "") for t in shape.findall(".//a:t", NS))
        if ("AI活用能力総合評価" in txt) or ("総合評価" in txt and "/ 500" in txt) or re.search(r"\d{1,3}\s*/\s*500", txt):
            target_idx = i
            break
    if target_idx <= 0:
        return slide_xml
    return _style_total_score_shape(slide_xml, target_idx, score_value)


def _replace_total_score_number(slide_xml: bytes, score_value: int) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    for shape in shapes:
        text_nodes = shape.findall(".//a:t", NS)
        combined = "".join((t.text or "") for t in text_nodes)
        if "総合評価" not in combined or not re.search(r"\d{1,3}\s*/\s*500", combined):
            continue
        for node in text_nodes:
            current = node.text or ""
            if re.fullmatch(r"\s*\d{1,3}\s*", current):
                prefix = current[: len(current) - len(current.lstrip())]
                suffix = current[len(current.rstrip()) :]
                node.text = f"{prefix}{score_value}{suffix}"
                return ET.tostring(root, encoding="utf-8", xml_declaration=True)
        replaced = False
        for node in text_nodes:
            current = node.text or ""
            new_text = re.sub(r"\d{1,3}", str(score_value), current, count=1)
            if new_text != current:
                node.text = new_text
                replaced = True
                break
        if replaced:
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    return slide_xml


def _style_analysis_method_body_auto(slide_xml: bytes, body_size: int = 1140, spacing: int = 0) -> bytes:
    """
    1ページ目左側「解析方法」ブロック全体のフォントサイズを統一する。
    """
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    target_shape = None
    for shape in shapes:
        txt = "".join((t.text or "") for t in shape.findall(".//a:t", NS))
        if "解析方法" in txt and "本解析は" in txt:
            target_shape = shape
            break
    if target_shape is None:
        return slide_xml

    paragraphs = target_shape.findall(".//a:p", NS)
    for p in paragraphs:
        p_text = "".join((t.text or "") for t in p.findall(".//a:t", NS))
        is_heading = "解析方法" in p_text and "■" in p_text
        size = 1100 if is_heading else body_size
        for rpr in p.findall(".//a:rPr", NS):
            rpr.set("sz", str(size))
            rpr.set("b", "0")
            rpr.set("spc", str(spacing))
            rpr.set("kern", "0")
        ppr = p.find("a:pPr", NS)
        if ppr is not None:
            def_rpr = ppr.find("a:defRPr", NS)
            if def_rpr is None:
                def_rpr = ET.SubElement(ppr, f"{{{A_NS}}}defRPr")
            def_rpr.set("sz", str(size))
            def_rpr.set("b", "0")
            def_rpr.set("spc", str(spacing))
            def_rpr.set("kern", "0")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _fix_slide1_analysis_method_line_spacing(slide_xml: bytes, line_spacing_pct: int = 125000) -> bytes:
    root = ET.fromstring(slide_xml)
    for shape in root.findall(".//p:sp", NS):
        txt = _shape_text(shape)
        if "解析方法" not in txt or "本解析は" not in txt:
            continue
        for p in shape.findall(".//a:p", NS):
            p_text = "".join((t.text or "") for t in p.findall(".//a:t", NS))
            if "本解析は" not in p_text:
                continue
            ppr = p.find("a:pPr", NS)
            if ppr is None:
                ppr = ET.SubElement(p, f"{{{A_NS}}}pPr")
            for node in list(ppr):
                if node.tag == f"{{{A_NS}}}lnSpc":
                    ppr.remove(node)
            ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
            ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct", {"val": str(line_spacing_pct)})
        break
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _strip_guide_styles(slide_xml: bytes) -> bytes:
    """
    開発時の色分けガイド（赤/緑）を正式版出力時に除去する。
    """
    root = ET.fromstring(slide_xml)

    # 強調ハイライトを除去（赤ガイド文字）
    for parent in root.iter():
        for child in list(parent):
            if child.tag == f"{{{A_NS}}}highlight":
                parent.remove(child)

    # 赤/緑のガイド枠線を非表示化
    for ln in root.findall(".//p:spPr/a:ln", NS):
        srgb_nodes = ln.findall(".//a:srgbClr", NS)
        has_guide_color = any(((n.get("val") or "").upper() in GUIDE_LINE_COLORS) for n in srgb_nodes)
        if not has_guide_color:
            continue
        for child in list(ln):
            ln.remove(child)
        ET.SubElement(ln, f"{{{A_NS}}}noFill")

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _shape_text(shape: ET.Element) -> str:
    return "".join((t.text or "") for t in shape.findall(".//a:t", NS))


def _shape_xfrm(shape: ET.Element) -> ET.Element | None:
    sp_pr = shape.find("p:spPr", NS)
    if sp_pr is None:
        return None
    xfrm = sp_pr.find("a:xfrm", NS)
    if xfrm is None:
        xfrm = ET.SubElement(sp_pr, f"{{{A_NS}}}xfrm")
    if xfrm.find("a:off", NS) is None:
        ET.SubElement(xfrm, f"{{{A_NS}}}off", {"x": "0", "y": "0"})
    if xfrm.find("a:ext", NS) is None:
        ET.SubElement(xfrm, f"{{{A_NS}}}ext", {"cx": "0", "cy": "0"})
    return xfrm


def _get_shape_box(shape: ET.Element) -> tuple[int, int, int, int] | None:
    xfrm = _shape_xfrm(shape)
    if xfrm is None:
        return None
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return None
    return (
        _safe_int(off.get("x"), 0),
        _safe_int(off.get("y"), 0),
        _safe_int(ext.get("cx"), 0),
        _safe_int(ext.get("cy"), 0),
    )


def _set_shape_box(shape: ET.Element, x: int, y: int, w: int, h: int) -> None:
    xfrm = _shape_xfrm(shape)
    if xfrm is None:
        return
    off = xfrm.find("a:off", NS)
    ext = xfrm.find("a:ext", NS)
    if off is None or ext is None:
        return
    off.set("x", str(max(0, int(x))))
    off.set("y", str(max(0, int(y))))
    ext.set("cx", str(max(0, int(w))))
    ext.set("cy", str(max(0, int(h))))


def _estimated_text_lines(text: str, *, line_width: float, min_lines: int = 1, max_lines: int = 12) -> int:
    clean = re.sub(r"\s+", "", _normalize_text(text))
    clean = re.sub(r"^■[^。]+", "", clean)
    width = max(1.0, _display_width(clean))
    return max(min_lines, min(max_lines, int((width + line_width - 1) // line_width)))


def _layout_stack(
    shapes: List[ET.Element],
    indexes: List[int],
    *,
    top: int,
    bottom: int,
    gap: int,
    min_heights: Dict[int, int],
    weights: Dict[int, int],
) -> None:
    available = max(0, bottom - top - gap * (len(indexes) - 1))
    base_total = sum(min_heights.get(i, 300000) for i in indexes)
    extra = max(0, available - base_total)
    weight_total = max(1, sum(weights.get(i, 1) for i in indexes))
    y = top
    for pos, idx in enumerate(indexes):
        if idx <= 0 or idx > len(shapes):
            continue
        shape = shapes[idx - 1]
        box = _get_shape_box(shape)
        if box is None:
            continue
        x, _, w, _ = box
        h = min_heights.get(idx, 300000) + int(extra * weights.get(idx, 1) / weight_total)
        if pos == len(indexes) - 1:
            h = max(min_heights.get(idx, 300000), bottom - y)
        _set_shape_box(shape, x, y, w, h)
        y += h + gap


def _optimize_slide3_layout(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    if len(shapes) < 13:
        return slide_xml

    # 新フォーマットでは3P右側に「AI活用の透明性」枠が追加され、
    # PowerPoint側で赤枠・横線・上下配分を調整済み。ここで旧3段レイアウトに
    # 再配置すると重なりが再発するため、新構成はテンプレート座標を尊重する。
    if len(shapes) >= 15:
        shape15_text = _shape_text(shapes[14])
        if "AI活用の透明性" in shape15_text:
            def _center_separator(line_idx: int, upper_idx: int, lower_idx: int, ratio: float = 0.5) -> None:
                if max(line_idx, upper_idx, lower_idx) > len(shapes):
                    return
                line_box = _get_shape_box(shapes[line_idx - 1])
                upper_box = _get_shape_box(shapes[upper_idx - 1])
                lower_box = _get_shape_box(shapes[lower_idx - 1])
                if line_box is None or upper_box is None or lower_box is None:
                    return
                x, _, w, h = line_box
                _, uy, _, uh = upper_box
                _, ly, _, _ = lower_box
                gap_top = uy + uh
                _set_shape_box(shapes[line_idx - 1], x, int(gap_top + (ly - gap_top) * ratio), w, h)

            def _set_gap_from_previous(idx: int, prev_idx: int, gap: int) -> None:
                if max(idx, prev_idx) > len(shapes):
                    return
                box = _get_shape_box(shapes[idx - 1])
                prev_box = _get_shape_box(shapes[prev_idx - 1])
                if box is None or prev_box is None:
                    return
                x, y, w, h = box
                _, py, _, ph = prev_box
                bottom = y + h
                new_y = py + ph + gap
                if new_y < bottom:
                    _set_shape_box(shapes[idx - 1], x, new_y, w, bottom - new_y)

            # 下段の本文と箇条書き、責任構造の固定欄と本文の間に1行分の余白を確保。
            _set_gap_from_previous(13, 10, 190000)
            _set_gap_from_previous(5, 4, 190000)
            # 区切り線は上下項目の真ん中に置く。
            _center_separator(8, 7, 15, 0.62)
            _center_separator(12, 9, 10)
            _center_separator(14, 15, 4, 0.62)
            return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    left_indexes = [11, 9, 10, 13]
    right_indexes = [7, 4, 5]
    left_boxes = [_get_shape_box(shapes[i - 1]) for i in left_indexes if i <= len(shapes)]
    right_boxes = [_get_shape_box(shapes[i - 1]) for i in right_indexes if i <= len(shapes)]
    left_boxes = [b for b in left_boxes if b is not None]
    right_boxes = [b for b in right_boxes if b is not None]
    if not left_boxes or not right_boxes:
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    left_top = min(y for _, y, _, _ in left_boxes)
    left_bottom = max(y + h for _, y, _, h in left_boxes)
    right_top = min(y for _, y, _, _ in right_boxes)
    right_bottom = max(y + h for _, y, _, h in right_boxes)

    # 3Pは列ごとに可変。ただし見出し下余白と区切り線の位置が崩れないよう、
    # 安全な比率を基準に再配分する。
    left_gap = 80000
    available_left = max(0, left_bottom - left_top - left_gap * 3)
    summary_h = int(available_left * 0.30)
    aptitude_h = int(available_left * 0.18)
    usage_h = int(available_left * 0.31)
    final_h = max(520000, available_left - summary_h - aptitude_h - usage_h)
    left_y = left_top
    for idx, h in ((11, summary_h), (9, aptitude_h), (10, usage_h), (13, final_h)):
        if idx <= len(shapes):
            box = _get_shape_box(shapes[idx - 1])
            if box is not None:
                x, _, w, _ = box
                _set_shape_box(shapes[idx - 1], x, left_y, w, h)
        left_y += h + left_gap

    # 右列: リスク量が少ない時は下線を1行分上げ、責任構造の固定欄と本文の余白を確保。
    right_gap = 190000
    risk_h = 1510000
    header_h = 1360000
    body_h = max(980000, right_bottom - right_top - risk_h - header_h - right_gap * 2)
    for idx, y, h in (
        (7, right_top, risk_h),
        (4, right_top + risk_h + right_gap, header_h),
        (5, right_top + risk_h + right_gap + header_h + right_gap, body_h),
    ):
        if idx <= len(shapes):
            box = _get_shape_box(shapes[idx - 1])
            if box is not None:
                x, _, w, _ = box
                _set_shape_box(shapes[idx - 1], x, y, w, h)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _dedupe_text_occurrence(slide_xml: bytes, text: str) -> bytes:
    target = _normalize_text(text)
    if not target:
        return slide_xml

    root = ET.fromstring(slide_xml)
    nodes = root.findall(".//a:t", NS)
    seen = 0
    for node in nodes:
        if _normalize_text(node.text or "") == target:
            seen += 1
            if seen >= 2:
                node.text = ""
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _ensure_report_column_read_order(slide_xml: bytes, slide_no: int) -> bytes:
    """PDF text extraction follows XML order, so force left column before right."""
    desired_orders = {
        3: [1, 2, 3, 4, 6, 5],
        4: [6, 1, 2, 3, 5, 4],
    }
    desired = desired_orders.get(slide_no)
    if not desired:
        return slide_xml

    root = ET.fromstring(slide_xml)
    sp_tree = root.find(".//p:cSld/p:spTree", NS)
    if sp_tree is None:
        return slide_xml

    shapes = sp_tree.findall("p:sp", NS)
    if len(shapes) < max(desired):
        return slide_xml

    ordered_targets = [shapes[idx - 1] for idx in desired if idx <= len(shapes)]
    target_ids = {id(shape) for shape in ordered_targets}
    insert_pos = None
    children = list(sp_tree)
    for pos, child in enumerate(children):
        if id(child) in target_ids:
            insert_pos = pos if insert_pos is None else min(insert_pos, pos)
            sp_tree.remove(child)

    if insert_pos is None:
        return slide_xml

    for offset, shape in enumerate(ordered_targets):
        sp_tree.insert(insert_pos + offset, shape)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _set_textbox_body_pr(tx_body: ET.Element) -> None:
    body_pr = tx_body.find("a:bodyPr", NS)
    if body_pr is None:
        body_pr = ET.Element(f"{{{A_NS}}}bodyPr")
        tx_body.insert(0, body_pr)
    body_pr.set("wrap", "square")
    body_pr.set("anchor", "t")
    body_pr.set("anchorCtr", "0")
    body_pr.set("tIns", "52000")
    body_pr.set("bIns", "52000")
    body_pr.set("lIns", "52000")
    body_pr.set("rIns", "52000")
    for child in list(body_pr):
        if child.tag in (
            f"{{{A_NS}}}noAutofit",
            f"{{{A_NS}}}normAutofit",
            f"{{{A_NS}}}spAutoFit",
        ):
            body_pr.remove(child)
    ET.SubElement(body_pr, f"{{{A_NS}}}noAutofit")


def _disable_textbox_autofit(tx_body: ET.Element) -> None:
    body_pr = tx_body.find("a:bodyPr", NS)
    if body_pr is None:
        body_pr = ET.Element(f"{{{A_NS}}}bodyPr")
        tx_body.insert(0, body_pr)
    for child in list(body_pr):
        if child.tag in (
            f"{{{A_NS}}}noAutofit",
            f"{{{A_NS}}}normAutofit",
            f"{{{A_NS}}}spAutoFit",
        ):
            body_pr.remove(child)
    ET.SubElement(body_pr, f"{{{A_NS}}}noAutofit")


def _force_japanese_font_and_spacing(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    design_markers = ("AI Visualization Report", "TLC imagine", "T L C imagine")
    for shape in root.findall(".//p:sp", NS):
        if any(marker in _shape_text(shape) for marker in design_markers):
            continue
        for ppr in shape.findall(".//a:pPr", NS):
            for attr in ("fontAlgn", "eaLnBrk", "latinLnBrk", "hangingPunct"):
                if attr in ppr.attrib:
                    del ppr.attrib[attr]
        for rpr in shape.findall(".//a:rPr", NS) + shape.findall(".//a:defRPr", NS) + shape.findall(".//a:endParaRPr", NS):
            rpr.set("lang", "ja-JP")
            rpr.set("spc", "0")
            rpr.set("kern", "0")
            rpr.attrib.pop("kumimoji", None)
            for tag in ("latin", "ea", "cs"):
                font = rpr.find(f"a:{tag}", NS)
                if font is None:
                    font = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
                font.set("typeface", JP_FONT_FAMILY)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _apply_brand_font_to_shape(shape: ET.Element) -> None:
    for run in shape.findall(".//a:r", NS):
        rpr = run.find("a:rPr", NS)
        if rpr is None:
            rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
        _set_brand_rpr(rpr)
    for rpr in shape.findall(".//a:defRPr", NS) + shape.findall(".//a:endParaRPr", NS):
        _set_brand_rpr(rpr)


def _apply_brand_font_only_to_shape(shape: ET.Element) -> None:
    for run in shape.findall(".//a:r", NS):
        rpr = run.find("a:rPr", NS)
        if rpr is None:
            rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
        _set_brand_font_only(rpr)
    for rpr in shape.findall(".//a:defRPr", NS) + shape.findall(".//a:endParaRPr", NS):
        _set_brand_font_only(rpr)


def _set_brand_rpr(rpr: ET.Element) -> None:
    rpr.set("spc", str(BRAND_CHAR_SPACING))
    for tag in ("latin", "ea", "cs"):
        font = rpr.find(f"a:{tag}", NS)
        if font is None:
            font = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
        font.set("typeface", BRAND_FONT_FAMILY)


def _set_brand_font_only(rpr: ET.Element, font_name: str = BRAND_FONT_FAMILY) -> None:
    for tag in ("latin", "ea", "cs"):
        font = rpr.find(f"a:{tag}", NS)
        if font is None:
            font = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
        font.set("typeface", font_name)


def _set_certificate_brand_style(rpr: ET.Element) -> None:
    rpr.set("sz", str(CERTIFICATE_BRAND_FONT_SIZE))
    rpr.set("spc", str(BRAND_CHAR_SPACING))
    _set_brand_font_only(rpr)


def _is_brand_text(text: str) -> bool:
    compact = re.sub(r"\s+", "", str(text or "")).lower()
    return any(marker in compact for marker in BRAND_TEXT_COMPACT_MARKERS)


def _apply_certificate_brand_font_to_shape(shape: ET.Element) -> None:
    touched = False
    for run in shape.findall(".//a:r", NS):
        run_text = "".join(t.text or "" for t in run.findall(".//a:t", NS))
        if not _is_brand_text(run_text):
            continue
        rpr = run.find("a:rPr", NS)
        if rpr is None:
            rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
        _set_certificate_brand_style(rpr)
        touched = True
    if touched:
        return
    for rpr in shape.findall(".//a:rPr", NS) + shape.findall(".//a:defRPr", NS) + shape.findall(".//a:endParaRPr", NS):
        _set_certificate_brand_style(rpr)


def _force_brand_font_and_spacing(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    for shape in root.findall(".//p:sp", NS):
        text = _shape_text(shape)
        if text and _is_brand_text(text):
            _apply_brand_font_only_to_shape(shape)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _normalize_slide1_body_runs(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    design_markers = ("AI Visualization Report", "TLC imagine", "T L C imagine")
    mixed_size_markers = ("/ 500", "/500")

    for shape in root.findall(".//p:sp", NS):
        text = _shape_text(shape)
        if not text or any(marker in text for marker in design_markers + mixed_size_markers):
            continue

        run_props = shape.findall(".//a:rPr", NS)
        if not run_props:
            continue
        base_size = next((rpr.get("sz") for rpr in run_props if rpr.get("sz")), None)
        if "総合評価" in text:
            base_size = None
        base_bold = next((rpr.get("b") for rpr in run_props if rpr.get("b") is not None), "0")
        for rpr in run_props + shape.findall(".//a:defRPr", NS) + shape.findall(".//a:endParaRPr", NS):
            rpr.set("lang", "ja-JP")
            rpr.set("altLang", "ja-JP")
            if base_size:
                rpr.set("sz", base_size)
            rpr.set("b", base_bold)
            rpr.set("spc", "0")
            rpr.set("kern", "0")
            rpr.attrib.pop("kumimoji", None)
            for tag in ("latin", "ea", "cs"):
                font = rpr.find(f"a:{tag}", NS)
                if font is None:
                    font = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
                font.set("typeface", JP_FONT_FAMILY)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _apply_slide1_finished_tracking(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    design_markers = ("AI Visualization Report", "TLC imagine", "T L C imagine")

    for shape_idx, shape in enumerate(root.findall(".//p:sp", NS), start=1):
        text = _shape_text(shape)
        if not text or any(marker in text for marker in design_markers):
            continue

        if shape_idx == 2 or text == "AI活用能力評価レポート":
            spacing = SLIDE1_TITLE_CHAR_SPACING
        elif shape_idx == 10 or "解析方法" in text:
            spacing = SLIDE1_BODY_CHAR_SPACING
        elif shape_idx == 11 or "総合評価" in text:
            spacing = SLIDE1_SCORE_LABEL_CHAR_SPACING
        elif shape_idx in (5, 7, 9, 13):
            spacing = SLIDE1_VALUE_CHAR_SPACING
        else:
            spacing = 0

        for rpr in shape.findall(".//a:rPr", NS) + shape.findall(".//a:defRPr", NS) + shape.findall(".//a:endParaRPr", NS):
            rpr.set("spc", str(spacing))
            rpr.set("kern", "0")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _keep_slide1_total_score_on_one_line(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    for shape in root.findall(".//p:sp", NS):
        text = _shape_text(shape)
        if "総合評価" not in text or not re.search(r"\d{1,3}\s*/\s*500", text):
            continue

        tx_body = shape.find("p:txBody", NS)
        body_pr = tx_body.find("a:bodyPr", NS) if tx_body is not None else None
        if body_pr is not None:
            body_pr.set("wrap", "none")
            body_pr.set("lIns", "0")
            body_pr.set("rIns", "0")

        xfrm = _shape_xfrm(shape)
        ext = xfrm.find("a:ext", NS) if xfrm is not None else None
        if ext is not None:
            current_width = _safe_int(ext.get("cx"), 0)
            ext.set("cx", str(max(current_width, 5600000)))

        for run in shape.findall(".//a:r", NS):
            rpr = run.find("a:rPr", NS)
            if rpr is not None:
                rpr.set("spc", "0")
                rpr.set("kern", "0")
        break
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _clear_shape_text(shape: ET.Element) -> None:
    for text_node in shape.findall(".//a:t", NS):
        text_node.text = ""


def _max_cnvpr_id(root: ET.Element) -> int:
    max_id = 1
    for node in root.findall(".//p:cNvPr", NS):
        max_id = max(max_id, _safe_int(node.get("id"), 1))
    return max_id


def _axis_prose_text(text: str) -> str:
    clean = _strip_list_markers_to_prose(text)
    if _display_width(clean) < 260:
        clean += (
            "この対応により、評価者はログ上の判断とアウトプット上の反映を同じ流れで確認できる。"
            "したがって、評価結論は記録された判断と最終形の対応範囲に基づく。"
        )
    return _fit_plain(clean, 560, clean)


def _axis_layout_lines(text: str) -> List[str]:
    clean = _axis_prose_text(text)
    if _display_width(clean) < 220:
        supplement = (
            "この対応により、評価者は判断と反映の接続を確認できる。"
            "評価結論は、記録された判断と最終形の対応範囲に基づく。"
        )
        clean += supplement
    return [clean]


def _layout_block_lines(text: str, *, max_chars: int, max_lines: int, max_line_chars: int) -> List[str]:
    clean = _single_line_prose(text)
    return [clean] if clean else []


STRUCTURED_EVALUATION_KEYS = {
    "ai_capability_evaluation",
    "output_logic_evaluation",
    "judgment_process_evaluation",
    "revision_process_evaluation",
    "agency_process_evaluation",
    "consistency_process_evaluation",
}

REPORT_BODY_CHAR_SPACING = 0
REPORT_BODY_LINE_SPACING = 148000
SLIDE1_TITLE_CHAR_SPACING = 300
SLIDE1_VALUE_CHAR_SPACING = 300
SLIDE1_BODY_CHAR_SPACING = 260
SLIDE1_SCORE_LABEL_CHAR_SPACING = 220


def _evaluation_block_layout_lines(text: str) -> List[str]:
    sections: Dict[str, List[str]] = {"①評価": [], "②因果関係": [], "③結論": []}
    current: str | None = None
    for raw in _normalize_text(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line in sections:
            current = line
            continue
        if current is not None:
            sections[current].append(line)

    lines: List[str] = []
    for heading in ("①評価", "②因果関係", "③結論"):
        body = _single_line_prose("".join(sections.get(heading, [])))
        lines.append(heading)
        if body:
            lines.append(body)
    return lines


def _append_textbox(
    sp_tree: ET.Element,
    *,
    shape_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    h: int,
    lines: List[str],
    font_size: int,
    bold: bool = False,
    color: str = "000000",
    line_spacing_pct: int = 125000,
) -> None:
    shape = ET.SubElement(sp_tree, f"{{{PPT_NS}}}sp")
    nv_sp_pr = ET.SubElement(shape, f"{{{PPT_NS}}}nvSpPr")
    ET.SubElement(nv_sp_pr, f"{{{PPT_NS}}}cNvPr", {"id": str(shape_id), "name": name})
    ET.SubElement(nv_sp_pr, f"{{{PPT_NS}}}cNvSpPr", {"txBox": "1"})
    ET.SubElement(nv_sp_pr, f"{{{PPT_NS}}}nvPr")

    sp_pr = ET.SubElement(shape, f"{{{PPT_NS}}}spPr")
    xfrm = ET.SubElement(sp_pr, f"{{{A_NS}}}xfrm")
    ET.SubElement(xfrm, f"{{{A_NS}}}off", {"x": str(x), "y": str(y)})
    ET.SubElement(xfrm, f"{{{A_NS}}}ext", {"cx": str(w), "cy": str(h)})
    prst_geom = ET.SubElement(sp_pr, f"{{{A_NS}}}prstGeom", {"prst": "rect"})
    ET.SubElement(prst_geom, f"{{{A_NS}}}avLst")
    ET.SubElement(sp_pr, f"{{{A_NS}}}noFill")
    line = ET.SubElement(sp_pr, f"{{{A_NS}}}ln")
    ET.SubElement(line, f"{{{A_NS}}}noFill")

    tx_body = ET.SubElement(shape, f"{{{PPT_NS}}}txBody")
    ET.SubElement(
        tx_body,
        f"{{{A_NS}}}bodyPr",
        {
            "wrap": "square",
            "anchor": "t",
            "anchorCtr": "0",
            "tIns": "0",
            "bIns": "0",
            "lIns": "0",
            "rIns": "0",
        },
    )
    ET.SubElement(tx_body, f"{{{A_NS}}}lstStyle")

    for line_text in lines:
        paragraph = ET.SubElement(tx_body, f"{{{A_NS}}}p")
        ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr", {"algn": "l"})
        ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
        ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct", {"val": str(line_spacing_pct)})
        run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
        rpr = ET.SubElement(
            run,
            f"{{{A_NS}}}rPr",
            {
                "lang": "ja-JP",
                "sz": str(font_size),
                "b": "1" if bold else "0",
                "spc": "0",
                "kern": "0",
            },
        )
        solid = ET.SubElement(rpr, f"{{{A_NS}}}solidFill")
        ET.SubElement(solid, f"{{{A_NS}}}srgbClr", {"val": color})
        for tag in ("latin", "ea", "cs"):
            ET.SubElement(rpr, f"{{{A_NS}}}{tag}", {"typeface": JP_FONT_FAMILY})
        text_node = ET.SubElement(run, f"{{{A_NS}}}t")
        text_node.text = line_text
        end = ET.SubElement(paragraph, f"{{{A_NS}}}endParaRPr", {"lang": "ja-JP", "sz": str(font_size)})
        for tag in ("latin", "ea", "cs"):
            ET.SubElement(end, f"{{{A_NS}}}{tag}", {"typeface": JP_FONT_FAMILY})


def _append_horizontal_rule(
    sp_tree: ET.Element,
    *,
    shape_id: int,
    name: str,
    x: int,
    y: int,
    w: int,
    color: str = "D9D9D9",
    width: int = 9000,
) -> None:
    shape = ET.SubElement(sp_tree, f"{{{PPT_NS}}}sp")
    nv_sp_pr = ET.SubElement(shape, f"{{{PPT_NS}}}nvSpPr")
    ET.SubElement(nv_sp_pr, f"{{{PPT_NS}}}cNvPr", {"id": str(shape_id), "name": name})
    ET.SubElement(nv_sp_pr, f"{{{PPT_NS}}}cNvSpPr")
    ET.SubElement(nv_sp_pr, f"{{{PPT_NS}}}nvPr")

    sp_pr = ET.SubElement(shape, f"{{{PPT_NS}}}spPr")
    xfrm = ET.SubElement(sp_pr, f"{{{A_NS}}}xfrm")
    ET.SubElement(xfrm, f"{{{A_NS}}}off", {"x": str(x), "y": str(y)})
    ET.SubElement(xfrm, f"{{{A_NS}}}ext", {"cx": str(w), "cy": "0"})
    prst_geom = ET.SubElement(sp_pr, f"{{{A_NS}}}prstGeom", {"prst": "line"})
    ET.SubElement(prst_geom, f"{{{A_NS}}}avLst")
    line = ET.SubElement(sp_pr, f"{{{A_NS}}}ln", {"w": str(width)})
    solid = ET.SubElement(line, f"{{{A_NS}}}solidFill")
    ET.SubElement(solid, f"{{{A_NS}}}srgbClr", {"val": color})


def _set_shape_lines(
    shape: ET.Element,
    lines: List[str],
    *,
    font_size: int,
    bold: bool = False,
    line_spacing_pct: int = 125000,
    char_spacing: int = 0,
    font_name: str = JP_FONT_FAMILY,
    preserve_body_pr: bool = False,
) -> None:
    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        return
    body_pr = tx_body.find("a:bodyPr", NS)
    lst_style = tx_body.find("a:lstStyle", NS)
    for child in list(tx_body):
        if child not in (body_pr, lst_style):
            tx_body.remove(child)
    if not preserve_body_pr:
        _set_textbox_body_pr(tx_body)
    else:
        _disable_textbox_autofit(tx_body)
    for line in lines:
        paragraph = ET.SubElement(tx_body, f"{{{A_NS}}}p")
        ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr", {"algn": "l"})
        ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
        ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct", {"val": str(line_spacing_pct)})
        run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
        rpr = ET.SubElement(
            run,
            f"{{{A_NS}}}rPr",
            {
                "lang": "ja-JP",
                "sz": str(font_size),
                "b": "1" if bold else "0",
                "spc": str(char_spacing),
                "kern": "0",
            },
        )
        for tag in ("latin", "ea", "cs"):
            ET.SubElement(rpr, f"{{{A_NS}}}{tag}", {"typeface": font_name})
        text_node = ET.SubElement(run, f"{{{A_NS}}}t")
        text_node.text = line
        end = ET.SubElement(paragraph, f"{{{A_NS}}}endParaRPr", {"lang": "ja-JP", "sz": str(font_size), "spc": str(char_spacing)})
        for tag in ("latin", "ea", "cs"):
            ET.SubElement(end, f"{{{A_NS}}}{tag}", {"typeface": font_name})


def _set_shape_paragraph(
    shape: ET.Element,
    text: str,
    *,
    font_size: int,
    bold: bool = False,
    line_spacing_pct: int = 140000,
    char_spacing: int = 0,
) -> None:
    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        return
    body_pr = tx_body.find("a:bodyPr", NS)
    lst_style = tx_body.find("a:lstStyle", NS)
    for child in list(tx_body):
        if child not in (body_pr, lst_style):
            tx_body.remove(child)
    _set_textbox_body_pr(tx_body)
    paragraph = ET.SubElement(tx_body, f"{{{A_NS}}}p")
    ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr", {"algn": "l"})
    ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
    ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct", {"val": str(line_spacing_pct)})
    run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
    rpr = ET.SubElement(
        run,
        f"{{{A_NS}}}rPr",
        {"lang": "ja-JP", "sz": str(font_size), "b": "1" if bold else "0", "spc": str(char_spacing), "kern": "0"},
    )
    for tag in ("latin", "ea", "cs"):
        ET.SubElement(rpr, f"{{{A_NS}}}{tag}", {"typeface": JP_FONT_FAMILY})
    text_node = ET.SubElement(run, f"{{{A_NS}}}t")
    text_node.text = _single_line_prose(text)
    end = ET.SubElement(paragraph, f"{{{A_NS}}}endParaRPr", {"lang": "ja-JP", "sz": str(font_size), "spc": str(char_spacing)})
    for tag in ("latin", "ea", "cs"):
        ET.SubElement(end, f"{{{A_NS}}}{tag}", {"typeface": JP_FONT_FAMILY})


def _set_axis_heading(shape: ET.Element, heading: str, score_text: str) -> None:
    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        return
    for rpr in shape.findall(".//a:rPr", NS) + shape.findall(".//a:endParaRPr", NS):
        rpr.attrib.pop("b", None)
    denominator = "500" if re.search(r"/\s*500", score_text or "") else "100"
    score_match = re.search(r"(\d{1,3})\s*/\s*(?:100|500)", score_text or "")
    score_value = score_match.group(1) if score_match else re.sub(r"\D", "", score_text or "")[:3]
    score_value = score_value or "0"

    runs = tx_body.findall(".//a:r", NS)
    text_nodes = [run.find("a:t", NS) for run in runs]
    if len(text_nodes) >= 5:
        text_nodes[0].text = heading.rstrip()
        text_nodes[1].text = score_value
        for node in text_nodes[2:]:
            node.text = ""
        text_nodes[4].text = f" / {denominator}"
        return

    existing = shape.findall(".//a:t", NS)
    if existing:
        existing[0].text = f"{heading.rstrip()}{score_value} / {denominator}"
        for node in existing[1:]:
            node.text = ""


def _render_detail_axis_groups(
    slide_xml: bytes,
    payload: Dict[str, str],
    axes: List[tuple[str, str, str]],
) -> bytes:
    root = ET.fromstring(slide_xml)
    sp_tree = root.find(".//p:cSld/p:spTree", NS)
    if sp_tree is None:
        return slide_xml
    groups = sp_tree.findall("p:grpSp", NS)
    for group, (heading, score_key, body_key) in zip(groups, axes):
        child_shapes = group.findall("./p:sp", NS)
        if len(child_shapes) < 2:
            continue
        if len(child_shapes) >= 3:
            heading_shape = child_shapes[0]
            body_shape = child_shapes[1]
            score_shape = child_shapes[2]
            detail_full_width = 9700000
            heading_box = _get_shape_box(heading_shape)
            if heading_box is not None:
                hx, hy, _, hh = heading_box
                _set_shape_box(heading_shape, hx, hy, detail_full_width, max(hh, 300000))
            body_box = _get_shape_box(body_shape)
            if body_box is not None:
                bx, by, _, bh = body_box
                _set_shape_box(body_shape, bx, by, detail_full_width, bh)
            score_box = _get_shape_box(score_shape)
            if score_box is not None:
                sx, sy, _, sh = score_box
                _set_shape_box(score_shape, sx, sy, detail_full_width, sh)
        else:
            body_shape = child_shapes[0]
            heading_shape = child_shapes[1]
            score_shape = None
            if body_key == "ai_capability_evaluation" and len(groups) > 1:
                right_shapes = groups[1].findall("./p:sp", NS)
                if right_shapes:
                    right_body_lines = _evaluation_block_layout_lines(payload.get("output_logic_evaluation", ""))
                    if right_body_lines:
                        _set_shape_lines(
                            right_shapes[0],
                            right_body_lines,
                            font_size=1200,
                            bold=False,
                            line_spacing_pct=REPORT_BODY_LINE_SPACING,
                            char_spacing=REPORT_BODY_CHAR_SPACING,
                            font_name="BIZ UDP明朝 Medium",
                            preserve_body_pr=True,
                        )
                    else:
                        _disable_textbox_autofit(right_shapes[0].find("p:txBody", NS))
                        for rpr in right_shapes[0].findall(".//a:rPr", NS) + right_shapes[0].findall(".//a:endParaRPr", NS):
                            rpr.set("sz", "1200")
                        for ppr in right_shapes[0].findall(".//a:pPr", NS):
                            ln_spc = ppr.find("a:lnSpc", NS)
                            if ln_spc is None:
                                ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
                            for child in list(ln_spc):
                                ln_spc.remove(child)
                            ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct", {"val": "140000"})
                if len(right_shapes) > 1:
                    right_heading_text = "".join((t.text or "") for t in right_shapes[1].findall(".//a:t", NS))
                    right_heading = re.sub(r"[0-9０-９]{1,3}\s*/\s*100.*$", "", right_heading_text)
                    right_score_text = _normalize_text(payload.get("axis_output_logic_score", ""))
                    if right_score_text:
                        _set_axis_heading(right_shapes[1], right_heading, right_score_text)
        score_text = _normalize_text(payload.get(score_key, ""))
        _set_axis_heading(heading_shape, heading, score_text)
        body_lines = (
            _evaluation_block_layout_lines(payload.get(body_key, ""))
            if body_key in STRUCTURED_EVALUATION_KEYS
            else _axis_layout_lines(payload.get(body_key, ""))
        )
        _set_shape_lines(
            body_shape,
            body_lines,
            font_size=1200,
            bold=False,
            line_spacing_pct=REPORT_BODY_LINE_SPACING if body_key in STRUCTURED_EVALUATION_KEYS else 140000,
            char_spacing=REPORT_BODY_CHAR_SPACING if body_key in STRUCTURED_EVALUATION_KEYS else 0,
            font_name="BIZ UDP明朝 Medium" if body_key in STRUCTURED_EVALUATION_KEYS else JP_FONT_FAMILY,
            preserve_body_pr=body_key in STRUCTURED_EVALUATION_KEYS,
        )
        if score_shape is not None:
            _set_shape_lines(score_shape, [""], font_size=1200, bold=False, line_spacing_pct=140000)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _clip_shape_text_lines(
    shape: ET.Element,
    *,
    max_lines: int,
    max_line_chars: int,
    font_size: int,
    line_spacing_pct: int = 125000,
    char_spacing: int = 0,
) -> None:
    raw_lines: List[str] = []
    for paragraph in shape.findall(".//a:p", NS):
        text = "".join((t.text or "") for t in paragraph.findall(".//a:t", NS)).strip()
        if text:
            raw_lines.append(text)
    if not raw_lines:
        return

    fitted: List[str] = []
    for raw in raw_lines:
        if len(fitted) >= max_lines:
            break
        if raw.startswith("■") or re.match(r"^[①②③④⑤]", raw):
            fitted.append(raw)
            continue
        parts = _fit_multiline_block(
            raw,
            max_total_chars=max_line_chars * 2,
            max_lines=2,
            max_line_chars=max_line_chars,
            fallback=raw,
        ).splitlines()
        for part in parts:
            if len(fitted) >= max_lines:
                break
            if part.strip():
                fitted.append(part.strip())

    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        return
    body_pr = tx_body.find("a:bodyPr", NS)
    lst_style = tx_body.find("a:lstStyle", NS)
    for child in list(tx_body):
        if child not in (body_pr, lst_style):
            tx_body.remove(child)
    _set_textbox_body_pr(tx_body)
    for line in fitted[:max_lines]:
        paragraph = ET.SubElement(tx_body, f"{{{A_NS}}}p")
        ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr", {"algn": "l"})
        ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
        ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct", {"val": str(line_spacing_pct)})
        run = ET.SubElement(paragraph, f"{{{A_NS}}}r")
        rpr = ET.SubElement(
            run,
            f"{{{A_NS}}}rPr",
            {
                "lang": "ja-JP",
                "sz": str(font_size),
                "b": "1" if line.startswith("■") else "0",
                "spc": str(char_spacing),
                "kern": "0",
            },
        )
        for tag in ("latin", "ea", "cs"):
            ET.SubElement(rpr, f"{{{A_NS}}}{tag}", {"typeface": JP_FONT_FAMILY})
        t = ET.SubElement(run, f"{{{A_NS}}}t")
        t.text = line
        ET.SubElement(paragraph, f"{{{A_NS}}}endParaRPr", {"lang": "ja-JP", "sz": str(font_size), "spc": str(char_spacing)})


def _fix_report_page3_layout(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    sp_tree = root.find(".//p:cSld/p:spTree", NS)
    shapes = root.findall(".//p:sp", NS)
    if sp_tree is not None and len(shapes) >= 6:
        try:
            sp_tree.remove(shapes[5])
        except ValueError:
            _clear_shape_text(shapes[5])
    if len(shapes) >= 1:
        _set_shape_box(shapes[0], 934153, 1512991, 4876958, 4680413)
        _clip_shape_text_lines(shapes[0], max_lines=12, max_line_chars=32, font_size=1100, line_spacing_pct=REPORT_BODY_LINE_SPACING, char_spacing=REPORT_BODY_CHAR_SPACING)
    if len(shapes) >= 5:
        _set_shape_box(shapes[4], 6233204, 1512992, 4876958, 4680412)
        _clip_shape_text_lines(shapes[4], max_lines=12, max_line_chars=32, font_size=1100, line_spacing_pct=REPORT_BODY_LINE_SPACING, char_spacing=REPORT_BODY_CHAR_SPACING)
    if sp_tree is not None:
        _append_textbox(
            sp_tree,
            shape_id=_max_cnvpr_id(root) + 1,
            name="page3 fixed title",
            x=896112,
            y=841248,
            w=6526750,
            h=330000,
            lines=["3　思考とアウトプットの関係分析"],
            font_size=2400,
            bold=False,
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _fix_report_page4_layout(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    sp_tree = root.find(".//p:cSld/p:spTree", NS)
    shapes = root.findall(".//p:sp", NS)
    for idx in (6, 9, 10, 12):
        if idx <= len(shapes):
            if sp_tree is not None and idx in (9, 10):
                try:
                    sp_tree.remove(shapes[idx - 1])
                    continue
                except ValueError:
                    pass
            _clear_shape_text(shapes[idx - 1])
    for idx in (4, 5, 7, 8):
        if idx <= len(shapes):
            _clip_shape_text_lines(shapes[idx - 1], max_lines=8, max_line_chars=34, font_size=1050, line_spacing_pct=REPORT_BODY_LINE_SPACING, char_spacing=REPORT_BODY_CHAR_SPACING)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _rewrite_textbox_paragraphs(
    shape: ET.Element,
    *,
    font_size: int = 1200,
    line_spacing_pct: int = 115000,
    paragraph_after_pts: int = 100,
    char_spacing: int = 0,
) -> int:
    tx_body = shape.find("p:txBody", NS)
    if tx_body is None:
        return 0

    paragraph_texts: List[str] = []
    for paragraph in tx_body.findall("a:p", NS):
        paragraph_texts.append("".join((t.text or "") for t in paragraph.findall(".//a:t", NS)).rstrip())
    text = "\n".join(paragraph_texts).strip()
    if not text:
        return 0

    body_pr = tx_body.find("a:bodyPr", NS)
    lst_style = tx_body.find("a:lstStyle", NS)
    for child in list(tx_body):
        if child not in (body_pr, lst_style):
            tx_body.remove(child)
    _set_textbox_body_pr(tx_body)

    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    for line in lines:
        p = ET.SubElement(tx_body, f"{{{A_NS}}}p")
        ppr = ET.SubElement(p, f"{{{A_NS}}}pPr")
        ppr.set("algn", "l")
        ln_spc = ET.SubElement(ppr, f"{{{A_NS}}}lnSpc")
        spc_pct = ET.SubElement(ln_spc, f"{{{A_NS}}}spcPct")
        spc_pct.set("val", str(line_spacing_pct))
        spc_aft = ET.SubElement(ppr, f"{{{A_NS}}}spcAft")
        spc_pts = ET.SubElement(spc_aft, f"{{{A_NS}}}spcPts")
        spc_pts.set("val", str(paragraph_after_pts if line else paragraph_after_pts // 2))

        run = ET.SubElement(p, f"{{{A_NS}}}r")
        rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
        rpr.set("lang", "ja-JP")
        rpr.set("sz", str(font_size))
        rpr.set("b", "1" if line.startswith("■") else "0")
        rpr.set("spc", str(char_spacing))
        rpr.set("kern", "0")
        for tag in ("latin", "ea", "cs"):
            ft = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
            ft.set("typeface", JP_FONT_FAMILY)
        t = ET.SubElement(run, f"{{{A_NS}}}t")
        t.text = line

        epr = ET.SubElement(p, f"{{{A_NS}}}endParaRPr")
        epr.set("lang", "ja-JP")
        epr.set("sz", str(font_size))
        epr.set("spc", str(char_spacing))

    return len([line for line in lines if line.strip()])


def _apply_readable_textbox_layout(
    slide_xml: bytes,
    shape_indexes: List[int],
    *,
    font_size: int = 1200,
    line_spacing_pct: int = 115000,
    paragraph_after_pts: int = 100,
    char_spacing: int = 0,
) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    for shape_idx in shape_indexes:
        if shape_idx <= 0 or shape_idx > len(shapes):
            continue
        shape = shapes[shape_idx - 1]
        line_count = _rewrite_textbox_paragraphs(
            shape,
            font_size=font_size,
            line_spacing_pct=line_spacing_pct,
            paragraph_after_pts=paragraph_after_pts,
            char_spacing=char_spacing,
        )
        box = _get_shape_box(shape)
        if box is None or line_count <= 0:
            continue
        x, y, w, h = box
        estimated = int(line_count * (font_size / 100.0) * 12700 * 1.62 + 260000)
        new_h = max(h, estimated)
        bottom_limit = 6300000
        for other_idx, other in enumerate(shapes, start=1):
            if other_idx == shape_idx:
                continue
            other_box = _get_shape_box(other)
            if other_box is None:
                continue
            ox, oy, ow, _ = other_box
            overlaps_x = max(x, ox) < min(x + w, ox + ow)
            if overlaps_x and oy > y:
                bottom_limit = min(bottom_limit, oy - 120000)
        if y + new_h > bottom_limit:
            new_h = max(900000, bottom_limit - y)
        _set_shape_box(shape, x, y, w, new_h)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _fix_slide1_strengths_layout(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    if len(shapes) >= 18:
        summary = shapes[16]
        title = shapes[17]
        title_box = _get_shape_box(title)
        box = _get_shape_box(summary)
        if title_box is not None and box is not None:
            tx, ty, tw, th = title_box
            _, _, w, _ = box
            _set_shape_box(summary, tx, ty + th + 90000, max(w, tw), 3300000)
        _set_shape_paragraph(
            summary,
            "".join((t.text or "") for t in summary.findall(".//a:t", NS)),
            font_size=1200,
            bold=False,
            line_spacing_pct=REPORT_BODY_LINE_SPACING,
            char_spacing=REPORT_BODY_CHAR_SPACING,
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _render_page5_prose_layout(slide_xml: bytes, payload: Dict[str, str]) -> bytes:
    root = ET.fromstring(slide_xml)
    sp_tree = root.find(".//p:cSld/p:spTree", NS)
    groups = sp_tree.findall("p:grpSp", NS) if sp_tree is not None else []
    def _page5_lines(value: str) -> List[str]:
        lines: List[str] = []
        for raw in _normalize_text(value).splitlines():
            line = raw.strip()
            if not line:
                continue
            lines.append(_single_line_prose(line))
        return lines

    if groups:
        left_shapes = groups[0].findall("./p:sp", NS)
        if left_shapes:
            left_lines = _page5_lines(payload.get("thought_output_relation", ""))
            if left_lines:
                _set_shape_lines(
                    left_shapes[0],
                    left_lines,
                    font_size=1200,
                    bold=False,
                    line_spacing_pct=REPORT_BODY_LINE_SPACING,
                    char_spacing=REPORT_BODY_CHAR_SPACING,
                    font_name="BIZ UDP明朝 Medium",
                    preserve_body_pr=True,
                )
        if len(groups) > 1:
            right_shapes = groups[1].findall("./p:sp", NS)
            if right_shapes:
                right_lines = _page5_lines(payload.get("third_party_visibility", ""))
                if right_lines:
                    _set_shape_lines(
                        right_shapes[0],
                        right_lines,
                        font_size=1200,
                        bold=False,
                        line_spacing_pct=REPORT_BODY_LINE_SPACING,
                        char_spacing=REPORT_BODY_CHAR_SPACING,
                        font_name="BIZ UDP明朝 Medium",
                        preserve_body_pr=True,
                    )
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)
    shapes = root.findall(".//p:sp", NS)
    for idx in (5, 7, 8, 11, 12):
        if idx <= len(shapes):
            _clear_shape_text(shapes[idx - 1])
    if len(shapes) >= 10:
        usage_items = payload.get("applicable_business_list", "").strip()
        if not usage_items:
            usage_items = payload.get("applicable_domain_text", "").strip()
        _set_shape_box(shapes[8], 930000, 1510000, 4970000, 1900000)
        _set_shape_lines(
            shapes[8],
            ["■活用可能領域"]
            + _layout_block_lines(usage_items, max_chars=210, max_lines=7, max_line_chars=38),
            font_size=1200,
            bold=False,
            line_spacing_pct=REPORT_BODY_LINE_SPACING,
            char_spacing=REPORT_BODY_CHAR_SPACING,
        )
        _set_shape_box(shapes[9], 930000, 5000000, 4970000, 900000)
        _set_shape_lines(
            shapes[9],
            ["■ AI活用リスク評価"]
            + _layout_block_lines(
                payload.get("risk_bullets", "").replace("■AI活用リスク評価", ""),
                max_chars=88,
                max_lines=3,
                max_line_chars=38,
            ),
            font_size=1200,
            bold=False,
            line_spacing_pct=REPORT_BODY_LINE_SPACING,
            char_spacing=REPORT_BODY_CHAR_SPACING,
        )
    if len(shapes) >= 12:
        _set_shape_box(shapes[11], 6280000, 1510000, 4970000, 1700000)
        _set_shape_lines(
            shapes[11],
            ["■ AI活用の透明性"]
            + _layout_block_lines(
                payload.get("transparency_bullets", "").replace("■ AI活用の透明性", ""),
                max_chars=210,
                max_lines=7,
                max_line_chars=38,
            ),
            font_size=1200,
            bold=False,
            line_spacing_pct=REPORT_BODY_LINE_SPACING,
            char_spacing=REPORT_BODY_CHAR_SPACING,
        )
    if len(shapes) >= 5:
        _set_shape_box(shapes[3], 6280000, 3340000, 4970000, 2600000)
        responsibility_lines = [
            line.strip()
            for line in payload.get("page6_responsibility_structure", "").splitlines()
            if line.strip()
        ]
        if not responsibility_lines:
            responsibility_lines = _layout_block_lines(
                payload.get("responsibility_header", "").replace("■ AI利用における責任構造", "")
                + payload.get("responsibility_body", ""),
                max_chars=145,
                max_lines=5,
                max_line_chars=38,
            )
        _set_shape_lines(
            shapes[3],
            ["■ AI利用における責任構造"] + responsibility_lines,
            font_size=1200,
            bold=False,
            line_spacing_pct=REPORT_BODY_LINE_SPACING,
            char_spacing=REPORT_BODY_CHAR_SPACING,
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _render_page6_applicable_domain(slide_xml: bytes, payload: Dict[str, str]) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:cSld/p:spTree/p:sp", NS)
    if len(shapes) >= 4:
        responsibility_header_xfrm = shapes[3].find(".//a:xfrm", NS)
        responsibility_header_off = (
            responsibility_header_xfrm.find("a:off", NS) if responsibility_header_xfrm is not None else None
        )
        if responsibility_header_off is not None:
            responsibility_header_off.set("y", "1320000")
        responsibility_lines = [
            line.strip()
            for line in payload.get("page6_responsibility_structure", "").splitlines()
            if line.strip()
        ]
        if responsibility_lines:
            _set_shape_lines(
                shapes[3],
                ["■ AI利用における責任構造", ""] + responsibility_lines,
                font_size=1200,
                bold=False,
                line_spacing_pct=REPORT_BODY_LINE_SPACING,
                char_spacing=REPORT_BODY_CHAR_SPACING,
                font_name="BIZ UDP明朝 Medium",
                preserve_body_pr=True,
            )
            responsibility_paragraphs = shapes[3].findall(".//a:p", NS)
            if len(responsibility_paragraphs) > 1:
                blank_spacing = responsibility_paragraphs[1].find(".//a:lnSpc/a:spcPct", NS)
                if blank_spacing is not None:
                    blank_spacing.set("val", "70000")
    if len(shapes) >= 5:
        responsibility_body_xfrm = shapes[4].find(".//a:xfrm", NS)
        responsibility_body_off = (
            responsibility_body_xfrm.find("a:off", NS) if responsibility_body_xfrm is not None else None
        )
        if responsibility_body_off is not None:
            responsibility_body_off.set("y", "2950000")
        responsibility_body = _normalize_text(payload.get("page6_responsibility_body", ""))
        if responsibility_body:
            _set_shape_lines(
                shapes[4],
                [responsibility_body],
                font_size=1200,
                bold=False,
                line_spacing_pct=REPORT_BODY_LINE_SPACING,
                char_spacing=REPORT_BODY_CHAR_SPACING,
                font_name="BIZ UDP明朝 Medium",
                preserve_body_pr=True,
            )
    if len(shapes) >= 7:
        business_xfrm = shapes[6].find(".//a:xfrm", NS)
        business_off = business_xfrm.find("a:off", NS) if business_xfrm is not None else None
        if business_off is not None:
            business_off.set("y", "2950000")
        business_lines = [
            line.strip()
            for line in payload.get("applicable_business_list", "").splitlines()
            if line.strip()
        ]
        if business_lines:
            _set_shape_lines(
                shapes[6],
                business_lines,
                font_size=1200,
                bold=False,
                line_spacing_pct=REPORT_BODY_LINE_SPACING,
                char_spacing=REPORT_BODY_CHAR_SPACING,
                font_name="BIZ UDP明朝 Medium",
                preserve_body_pr=True,
            )
        else:
            _clear_shape_text(shapes[6])
    if len(shapes) >= 8:
        body = _normalize_text(payload.get("applicable_domain_text", ""))
        if body:
            _set_shape_lines(
                shapes[7],
                ["■活用可能領域", body],
                font_size=1200,
                bold=False,
                line_spacing_pct=REPORT_BODY_LINE_SPACING,
                char_spacing=REPORT_BODY_CHAR_SPACING,
                font_name="BIZ UDP明朝 Medium",
                preserve_body_pr=True,
            )
    if len(shapes) >= 10:
        transparency_line_xfrm = shapes[8].find(".//a:xfrm", NS)
        transparency_line_off = (
            transparency_line_xfrm.find("a:off", NS) if transparency_line_xfrm is not None else None
        )
        if transparency_line_off is not None:
            transparency_line_off.set("y", "4023477")
        transparency_text_xfrm = shapes[9].find(".//a:xfrm", NS)
        transparency_text_off = (
            transparency_text_xfrm.find("a:off", NS) if transparency_text_xfrm is not None else None
        )
        if transparency_text_off is not None:
            transparency_text_off.set("y", "4158492")
        transparency_body = _normalize_text(payload.get("page6_transparency_text", ""))
        if transparency_body:
            _set_shape_lines(
                shapes[9],
                ["■ AI活用の透明性", transparency_body],
                font_size=1200,
                bold=False,
                line_spacing_pct=REPORT_BODY_LINE_SPACING,
                char_spacing=REPORT_BODY_CHAR_SPACING,
                font_name="BIZ UDP明朝 Medium",
                preserve_body_pr=True,
            )
    sp_tree = root.find(".//p:cSld/p:spTree", NS)
    ai_scope_statement = _normalize_text(payload.get("ai_use_scope_statement", ""))
    if sp_tree is not None and ai_scope_statement:
        existing_ids = [
            _safe_int(shape_id.get("id"), 0)
            for shape_id in sp_tree.findall(".//p:cNvPr", NS)
        ]
        shape_id = max(existing_ids + [1000]) + 1
        _append_horizontal_rule(
            sp_tree,
            shape_id=shape_id,
            name="AI use scope rule",
            x=6280000,
            y=4685000,
            w=4970000,
        )
        _append_textbox(
            sp_tree,
            shape_id=shape_id + 1,
            name="AI use scope statement",
            x=6280000,
            y=4765000,
            w=4970000,
            h=1180000,
            lines=["\u25a0 AI\u3092\u3069\u3053\u307e\u3067\u6d3b\u7528\u3067\u304d\u308b\u304b"]
            + [
                line.replace("アウトプット", "成果物")
                for line in _layout_block_lines(ai_scope_statement, max_chars=180, max_lines=5, max_line_chars=34)
            ],
            font_size=1200,
            bold=False,
            line_spacing_pct=REPORT_BODY_LINE_SPACING,
        )
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _remove_slide3_detail_title(slide_xml: bytes) -> bytes:
    root = ET.fromstring(slide_xml)
    shapes = root.findall(".//p:sp", NS)
    for shape in shapes:
        text = "".join((t.text or "") for t in shape.findall(".//a:t", NS))
        if "詳細分析" in text:
            _clear_shape_text(shape)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _populate_template(template_path: Path, output_pptx: Path, payload: Dict[str, str]) -> None:
    sanitized_payload: Dict[str, str] = {}
    for k, v in payload.items():
        base = _sanitize_unicode_text(v)
        if k in FIXED_PAYLOAD_KEYS or k in LINE_RULES:
            sv = base
        else:
            sv = _naturalize_generated_text(base)
        if _is_mojibake_text(sv):
            sv = ""
        # 商品品質要件: ASCII ? を残さない
        sv = sv.replace("?", "？")
        sanitized_payload[k] = sv

    bad_keys = [k for k, v in sanitized_payload.items() if "?" in v]
    if bad_keys:
        raise ValueError(f"文字化け検査に失敗しました（'?' 残存）: {', '.join(bad_keys)}")

    slide_replacements: Dict[str, Dict[int, str]] = {}
    for slide_no, mapping in SLIDE_SHAPE_MAP.items():
        slide_name = f"ppt/slides/slide{slide_no}.xml"
        replacements: Dict[int, str] = {}
        for shape_idx, payload_key in mapping.items():
            if payload_key not in sanitized_payload:
                continue
            value = _normalize_text(sanitized_payload.get(payload_key, ""))
            # 空文字はテンプレ既定文言を消さない
            if not value:
                continue
            replacements[shape_idx] = value
        slide_replacements[slide_name] = replacements

    with zipfile.ZipFile(template_path, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}

    for slide_name, replacements in slide_replacements.items():
        if slide_name not in entries:
            continue
        updated = entries[slide_name]
        if replacements and not slide_name.endswith(("slide2.xml", "slide3.xml")):
            updated = _replace_shape_text(updated, replacements, rewrite_single_run=slide_name.endswith("slide1.xml"))
            if slide_name.endswith("slide1.xml"):
                updated = _dedupe_text_occurrence(updated, sanitized_payload.get("target_work", ""))
                total_match = re.search(r"(\d{1,3})\s*/\s*500", sanitized_payload.get("total_score", ""))
                if total_match:
                    updated = _replace_total_score_number(updated, _safe_int(total_match.group(1), 0))
                updated = _fix_slide1_strengths_layout(updated)
        if slide_name.endswith("slide2.xml"):
            updated = _render_detail_axis_groups(
                updated,
                sanitized_payload,
                [
                    ("■ＡＩ活用総合：", "overall_total_score", "ai_capability_evaluation"),
                ],
            )
        if slide_name.endswith("slide4.xml"):
            updated = _render_detail_axis_groups(
                updated,
                sanitized_payload,
                [
                    ("■判断の主体性：", "axis_agency_score", "agency_process_evaluation"),
                    ("■全体整合性 ：", "axis_consistency_score", "consistency_process_evaluation"),
                ],
            )
        if slide_name.endswith("slide3.xml"):
            updated = _render_detail_axis_groups(
                updated,
                sanitized_payload,
                [
                    ("■ 判断プロセス ：", "axis_judgment_score", "judgment_process_evaluation"),
                    ("■ 修正プロセス ：", "axis_revision_score", "revision_process_evaluation"),
                ],
            )
            updated = _remove_slide3_detail_title(updated)
        if slide_name.endswith("slide5.xml"):
            updated = _render_page5_prose_layout(updated, sanitized_payload)
            updated = _apply_readable_textbox_layout(
                updated,
                [4, 5, 9, 10, 12],
                font_size=1200,
                line_spacing_pct=REPORT_BODY_LINE_SPACING,
                paragraph_after_pts=0,
                char_spacing=REPORT_BODY_CHAR_SPACING,
            )
        if slide_name.endswith("slide6.xml"):
            updated = _render_page6_applicable_domain(updated, sanitized_payload)
        if slide_name.endswith(("slide1.xml", "slide2.xml", "slide3.xml", "slide4.xml", "slide5.xml", "slide6.xml")):
            updated = _force_japanese_font_and_spacing(updated)
        if slide_name.endswith("slide1.xml"):
            updated = _normalize_slide1_body_runs(updated)
            updated = _apply_slide1_finished_tracking(updated)
            updated = _keep_slide1_total_score_on_one_line(updated)
            updated = _fix_slide1_analysis_method_line_spacing(updated)
        if slide_name.endswith(("slide1.xml", "slide2.xml", "slide3.xml", "slide4.xml", "slide5.xml", "slide6.xml")):
            updated = _force_brand_font_and_spacing(updated)
        updated = _strip_guide_styles(updated)
        entries[slide_name] = updated

    for entry_name in list(entries):
        if not entry_name.startswith(("ppt/slideLayouts/", "ppt/slideMasters/")) or not entry_name.endswith(".xml"):
            continue
        entries[entry_name] = _force_brand_font_and_spacing(entries[entry_name])

    with zipfile.ZipFile(output_pptx, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, content in entries.items():
            zout.writestr(name, content)


def _resolve_template_path() -> Path:
    checked_paths: List[str] = []

    def _candidate_paths(path_text: str) -> List[Path]:
        raw_path = Path(path_text).expanduser()
        if raw_path.is_absolute():
            return [raw_path]
        return [
            Path.cwd() / raw_path,
            APP_DIR / raw_path,
            PROJECT_ROOT / raw_path,
        ]

    for candidate in DEFAULT_TEMPLATE_CANDIDATES:
        path_text = str(candidate or "").strip()
        if not path_text:
            continue
        for path in _candidate_paths(path_text):
            resolved = path.resolve()
            checked_paths.append(str(resolved))
            if resolved.exists() and resolved.suffix.lower() == ".pptx":
                return resolved
    raise FileNotFoundError(
        "PowerPointテンプレートが見つかりません。"
        "AI_REPORT_TEMPLATE_PATH またはリポジトリ内テンプレート(app/template_new.pptx, tmp/ui_reference.pptx)を確認してください。"
        f" checked={checked_paths}"
    )


def _set_first_text(run: ET.Element, value: str) -> None:
    text_el = run.find("a:t", NS)
    if text_el is not None:
        text_el.text = value


CERTIFICATE_TEXT_BOXES = {
    "詳細レポート": (6098492, 3913000, 1689558, 284560),
    "総合スコア": (1238250, 3362441, 3675350, 523220),
    "発行日": (760000, 4058300, 4153599, 338554),
    "ID No.": (971106, 4830000, 3942494, 338554),
    "対象者": (1028424, 5092000, 3885176, 400110),
    "Certified by": (6143272, 5660000, 1600000, 530978),
}
CERTIFICATE_QR_BOX = (6242825, 4272637, 1260000, 1260000)
CERTIFICATE_QR_TARGET_DPI = 600
CERTIFICATE_QR_QUIET_ZONE_RATIO = 0.12
DEFAULT_SLIDE_SIZE_EMU = (12192000, 6858000)
CERTIFICATE_FONT_FAMILY = "Noto Serif CJK JP"
CERTIFICATE_SHORT_REPORT_BASE_URL = "https://www.tokyolastcraftsmen.com/r"


def _set_run_font(run: ET.Element, font_name: str, *, spacing: int | None = 0) -> None:
    rpr = run.find("a:rPr", NS)
    if rpr is None:
        rpr = ET.SubElement(run, f"{{{A_NS}}}rPr")
    rpr.set("lang", "ja-JP")
    rpr.set("altLang", "ja-JP")
    rpr.attrib.pop("b", None)
    rpr.attrib.pop("kumimoji", None)
    if spacing is not None:
        rpr.set("spc", str(spacing))
    for tag in ("latin", "ea", "cs"):
        font = rpr.find(f"a:{tag}", NS)
        if font is None:
            font = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
        font.set("typeface", font_name)


def _set_rpr_font(rpr: ET.Element, font_name: str, *, spacing: int | None = None) -> None:
    rpr.set("lang", "ja-JP")
    rpr.set("altLang", "ja-JP")
    rpr.attrib.pop("b", None)
    rpr.attrib.pop("kumimoji", None)
    if spacing is not None:
        rpr.set("spc", str(spacing))
    for tag in ("latin", "ea", "cs"):
        font = rpr.find(f"a:{tag}", NS)
        if font is None:
            font = ET.SubElement(rpr, f"{{{A_NS}}}{tag}")
        font.set("typeface", font_name)


def _style_certificate_text(shape: ET.Element, text: str) -> None:
    if any(marker in text for marker in BRAND_TEXT_MARKERS):
        _apply_certificate_brand_font_to_shape(shape)
        return
    for run in shape.findall(".//a:r", NS):
        _set_run_font(run, CERTIFICATE_FONT_FAMILY, spacing=None)
    for rpr in shape.findall(".//a:endParaRPr", NS) + shape.findall(".//a:defRPr", NS):
        _set_rpr_font(rpr, CERTIFICATE_FONT_FAMILY)


def _set_paragraph_alignment(shape: ET.Element, align: str) -> None:
    for paragraph in shape.findall(".//a:p", NS):
        ppr = paragraph.find("a:pPr", NS)
        if ppr is None:
            ppr = ET.SubElement(paragraph, f"{{{A_NS}}}pPr")
        ppr.set("algn", align)


def _normalize_qr_target_path(target: str) -> str:
    normalized = target.replace("\\", "/")
    if normalized.startswith("../"):
        normalized = "ppt/" + normalized[3:]
    elif not normalized.startswith("ppt/"):
        normalized = "ppt/slides/" + normalized
    parts: List[str] = []
    for part in normalized.split("/"):
        if part in {"", "."}:
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _certificate_short_report_url(doc_id: str) -> str:
    safe_id = str(doc_id or "").strip().strip("/")
    return f"{CERTIFICATE_SHORT_REPORT_BASE_URL}/{safe_id}"


def _certificate_qr_display_inches() -> float:
    return max(0.1, CERTIFICATE_QR_BOX[2] / 914400.0)


def _log_qr_png_state(label: str, image_bytes: bytes, *, doc_id: str = "", media_name: str = "", shape_box: tuple[int, int, int, int] | None = None) -> None:
    try:
        from PIL import Image
    except Exception:
        LOGGER.info(
            "%s doc_id=%s media=%s bytes=%s shape_box=%s pil=unavailable",
            label,
            doc_id,
            media_name,
            len(image_bytes or b""),
            shape_box,
        )
        return

    try:
        image = Image.open(BytesIO(image_bytes))
        rgb = image.convert("RGB")
        colors = rgb.getcolors(maxcolors=256)
        color_count = len(colors) if colors is not None else "over_256"
        LOGGER.info(
            "%s doc_id=%s media=%s bytes=%s size=%sx%s mode=%s colors=%s shape_box=%s",
            label,
            doc_id,
            media_name,
            len(image_bytes or b""),
            image.width,
            image.height,
            image.mode,
            color_count,
            shape_box,
        )
    except Exception:
        LOGGER.error("CERTIFICATE_QR_INSPECTION_FAILED category=validation")


def _save_certificate_qr_debug_png(doc_id: str, image_bytes: bytes) -> Path:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(doc_id or "").strip() or "certificate")
    debug_path = OUTPUT_DIR / f"{safe_id}_certificate_qr.png"
    debug_path.write_bytes(image_bytes)
    LOGGER.info("CERTIFICATE_QR_SINGLE_PNG_SAVED")
    return debug_path


def _certificate_qr_media_name(doc_id: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(doc_id or "").strip() or "certificate")
    return f"ppt/media/{safe_id}_certificate_qr_direct.png"


def _relationship_target_from_media_name(media_name: str) -> str:
    normalized = media_name.replace("\\", "/")
    if normalized.startswith("ppt/media/"):
        return f"../media/{normalized.split('/')[-1]}"
    return normalized


def _pptx_slide_size_emu(pptx_path: Path) -> tuple[int, int]:
    try:
        with zipfile.ZipFile(pptx_path, "r") as zin:
            root = ET.fromstring(zin.read("ppt/presentation.xml"))
        sld_sz = root.find(f".//{{{PPT_NS}}}sldSz")
        if sld_sz is not None:
            width = _safe_int(sld_sz.get("cx"), 0)
            height = _safe_int(sld_sz.get("cy"), 0)
            if width > 0 and height > 0:
                return width, height
    except Exception:
        LOGGER.error("CERTIFICATE_QR_PDF_SLIDE_SIZE_READ_FAILED category=storage")
    return DEFAULT_SLIDE_SIZE_EMU


def _build_certificate_qr_png(doc_id: str) -> bytes:
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_H
        from PIL import Image
    except Exception:
        LOGGER.error("CERTIFICATE_QR_GENERATE_IMPORT_FAILED category=dependency")
        return b""

    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_H,
            box_size=64,
            border=4,
        )
        qr_url = _certificate_short_report_url(doc_id)
        qr.add_data(qr_url)
        qr.make(fit=True)
        qr_body = qr.make_image(fill_color="#000000", back_color="#ffffff").convert("1")
        nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
        module_count = len(qr.get_matrix())
        target_pixels = max(1, round(_certificate_qr_display_inches() * CERTIFICATE_QR_TARGET_DPI))
        module_pixels = max(8, round(target_pixels / module_count))
        qr_size = module_count * module_pixels
        image = qr_body.resize((qr_size, qr_size), nearest)
        output = BytesIO()
        actual_dpi = qr_size / _certificate_qr_display_inches()
        image.convert("RGB").save(output, format="PNG", optimize=False, compress_level=0, dpi=(actual_dpi, actual_dpi))
        image_bytes = output.getvalue()
        LOGGER.info(
            "CERTIFICATE_QR_GENERATED doc_id=%s url=%s version=%s error_correction=H border_modules=4 size=%sx%s module_count=%s module_pixels=%s dpi=%.2f",
            doc_id,
            qr_url,
            qr.version,
            image.width,
            image.height,
            module_count,
            module_pixels,
            actual_dpi,
        )
        _log_qr_png_state("CERTIFICATE_QR_SINGLE_PNG_GENERATED", image_bytes, doc_id=doc_id)
        _save_certificate_qr_debug_png(doc_id, image_bytes)
        return image_bytes
    except Exception:
        LOGGER.error("CERTIFICATE_QR_GENERATE_FAILED category=rendering")
        return b""


def _enhance_qr_png(image_bytes: bytes) -> bytes:
    try:
        from PIL import Image
    except Exception:
        return image_bytes

    try:
        source = Image.open(BytesIO(image_bytes)).convert("RGBA")
        white = Image.new("RGBA", source.size, (255, 255, 255, 255))
        white.alpha_composite(source)
        gray = white.convert("L")
        bw = gray.point(lambda px: 0 if px < 128 else 255, mode="1")
        black_bbox = bw.convert("L").point(lambda px: 255 if px == 0 else 0).getbbox()
        if black_bbox is None:
            return image_bytes

        target_pixels = max(1, round(_certificate_qr_display_inches() * CERTIFICATE_QR_TARGET_DPI))
        scale = max(1, int((target_pixels + max(bw.size) - 1) / max(bw.size)))
        nearest = getattr(getattr(Image, "Resampling", Image), "NEAREST")
        canvas_size = (bw.width * scale, bw.height * scale)
        quiet_zone = max(1, int(min(canvas_size) * CERTIFICATE_QR_QUIET_ZONE_RATIO))
        max_qr_size = (
            max(1, canvas_size[0] - quiet_zone * 2),
            max(1, canvas_size[1] - quiet_zone * 2),
        )
        qr_body = bw.crop(black_bbox)
        qr_body = qr_body.resize(max_qr_size, nearest)

        canvas = Image.new("1", canvas_size, 1)
        offset = ((canvas_size[0] - qr_body.width) // 2, (canvas_size[1] - qr_body.height) // 2)
        canvas.paste(qr_body, offset)
        output = BytesIO()
        actual_dpi = canvas.width / _certificate_qr_display_inches()
        canvas.convert("RGB").save(output, format="PNG", optimize=False, compress_level=0, dpi=(actual_dpi, actual_dpi))
        return output.getvalue()
    except Exception:
        return image_bytes


def _prepare_qr_picture_xml(pic: ET.Element, rel_id: str) -> None:
    _set_shape_box(pic, *CERTIFICATE_QR_BOX)
    blip = pic.find(".//a:blip", NS)
    if blip is not None:
        blip.set(f"{{{R_NS}}}embed", rel_id)
        blip.set("cstate", "none")
        ext_lst = blip.find("a:extLst", NS)
        if ext_lst is None:
            ext_lst = ET.SubElement(blip, f"{{{A_NS}}}extLst")
        use_local_dpi = None
        for ext in ext_lst.findall("a:ext", NS):
            use_local_dpi = ext.find(f"{{{A14_NS}}}useLocalDpi")
            if use_local_dpi is not None:
                break
        if use_local_dpi is None:
            ext = ET.SubElement(ext_lst, f"{{{A_NS}}}ext")
            ext.set("uri", "{28A0092B-C50C-407E-A947-70E740481C1C}")
            use_local_dpi = ET.SubElement(ext, f"{{{A14_NS}}}useLocalDpi")
        use_local_dpi.set("val", "1")

    blip_fill = pic.find("p:blipFill", NS)
    if blip_fill is not None:
        for src_rect in list(blip_fill.findall("a:srcRect", NS)):
            blip_fill.remove(src_rect)
        for tile in list(blip_fill.findall("a:tile", NS)):
            blip_fill.remove(tile)
        stretch = blip_fill.find("a:stretch", NS)
        if stretch is None:
            stretch = ET.SubElement(blip_fill, f"{{{A_NS}}}stretch")
        for child in list(stretch):
            stretch.remove(child)
        ET.SubElement(stretch, f"{{{A_NS}}}fillRect")

    pic_locks = pic.find(".//a:picLocks", NS)
    if pic_locks is not None:
        pic_locks.set("noChangeAspect", "1")


def _enhance_certificate_qr_media(entries: Dict[str, bytes], root: ET.Element, doc_id: str) -> None:
    rels_name = "ppt/slides/_rels/slide1.xml.rels"
    if rels_name not in entries:
        LOGGER.error("CERTIFICATE_QR_PPTX_RELS_MISSING rels=%s", rels_name)
        return

    rel_root = ET.fromstring(entries[rels_name])
    rel_targets = {rel.get("Id"): rel.get("Target") for rel in rel_root}
    direct_media_name = _certificate_qr_media_name(doc_id)
    direct_target = _relationship_target_from_media_name(direct_media_name)
    generated_qr = _build_certificate_qr_png(doc_id)
    if not generated_qr:
        LOGGER.error("CERTIFICATE_QR_DIRECT_MEDIA_GENERATE_FAILED doc_id=%s", doc_id)
        return
    entries[direct_media_name] = generated_qr
    replaced = False
    for pic in root.findall(".//p:pic", NS):
        box = _get_shape_box(pic)
        if box is None:
            continue
        _, _, w, h = box
        if w >= 2500000 or h >= 2500000:
            continue
        blip = pic.find(".//a:blip", NS)
        rel_id = blip.get(f"{{{R_NS}}}embed") if blip is not None else None
        target = rel_targets.get(rel_id or "")
        if not target:
            LOGGER.info("CERTIFICATE_QR_PPTX_CANDIDATE_SKIPPED reason=no_target rel_id=%s shape_box=%s", rel_id, box)
            continue
        old_media_name = _normalize_qr_target_path(target)
        if old_media_name in entries:
            _log_qr_png_state("CERTIFICATE_QR_PPTX_ORIGINAL_MEDIA", entries[old_media_name], doc_id=doc_id, media_name=old_media_name, shape_box=box)
        if old_media_name in entries and old_media_name.lower().endswith(".png"):
            for rel in rel_root:
                if rel.get("Id") == rel_id:
                    rel.set("Target", direct_target)
                    break
            _prepare_qr_picture_xml(pic, rel_id or "")
            _log_qr_png_state("CERTIFICATE_QR_PPTX_DIRECT_MEDIA", entries[direct_media_name], doc_id=doc_id, media_name=direct_media_name, shape_box=CERTIFICATE_QR_BOX)
            LOGGER.info(
                "CERTIFICATE_QR_PPTX_DIRECT_PLACED old_media=%s new_media=%s rel_id=%s target=%s shape_box=%s useLocalDpi=1",
                old_media_name,
                direct_media_name,
                rel_id,
                direct_target,
                CERTIFICATE_QR_BOX,
            )
            replaced = True
        else:
            LOGGER.info("CERTIFICATE_QR_PPTX_CANDIDATE_SKIPPED reason=unsupported_media media=%s shape_box=%s", old_media_name, box)
    if not replaced:
        LOGGER.error("CERTIFICATE_QR_PPTX_MEDIA_NOT_REPLACED doc_id=%s", doc_id)
    else:
        entries[rels_name] = ET.tostring(rel_root, encoding="utf-8", xml_declaration=True)


def _fix_certificate_layout(root: ET.Element) -> None:
    for shape in root.findall(".//p:sp", NS):
        text = _shape_text(shape)
        _style_certificate_text(shape, text)
        for marker, box in CERTIFICATE_TEXT_BOXES.items():
            if marker in text:
                _set_shape_box(shape, *box)
                if marker in {"総合スコア", "発行日", "ID No.", "対象者"}:
                    _set_paragraph_alignment(shape, "r")
                break

    for pic in root.findall(".//p:pic", NS):
        box = _get_shape_box(pic)
        if box is None:
            continue
        _, _, w, h = box
        if w < 2500000 and h < 2500000:
            _set_shape_box(pic, *CERTIFICATE_QR_BOX)


def _replace_certificate_values(template_path: Path, output_pptx: Path, total_score: int, issue_date: str, id_no: str, user_name: str) -> None:
    with zipfile.ZipFile(template_path, "r") as zin:
        entries = {name: zin.read(name) for name in zin.namelist()}

    slide_name = "ppt/slides/slide1.xml"
    root = ET.fromstring(entries[slide_name])
    for shape in root.findall(".//p:sp", NS):
        full_text = "".join((t.text or "") for t in shape.findall(".//a:t", NS))
        runs = shape.findall(".//a:r", NS)
        if not runs:
            continue

        if "総合スコア" in full_text:
            values = ["総合スコア　", str(total_score), " ", "/", " 500"]
            for idx, run in enumerate(runs):
                _set_first_text(run, values[idx] if idx < len(values) else "")
        elif full_text.startswith("発行日"):
            year = issue_date[:4]
            rest = issue_date[4:]
            values = ["発行日　", year, rest]
            for idx, run in enumerate(runs):
                _set_first_text(run, values[idx] if idx < len(values) else "")
        elif full_text.startswith("ID No."):
            for idx, run in enumerate(runs):
                _set_first_text(run, f"ID No. {id_no}" if idx == 0 else "")
        elif full_text.startswith("対象者"):
            values = ["対象者", "　", f"　{user_name}"]
            for idx, run in enumerate(runs):
                _set_first_text(run, values[idx] if idx < len(values) else "")

    _fix_certificate_layout(root)
    _enhance_certificate_qr_media(entries, root, id_no)

    entries[slide_name] = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    with zipfile.ZipFile(output_pptx, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, content in entries.items():
            compress_type = zipfile.ZIP_STORED if name == _certificate_qr_media_name(id_no) else zipfile.ZIP_DEFLATED
            zout.writestr(name, content, compress_type=compress_type)
    LOGGER.info("CERTIFICATE_QR_PPTX_WRITTEN")


def _remove_report_extra_slide(pptx_path: Path) -> None:
    """レポートは4ページ固定。壊れた旧3ページ目を出力から除外する。"""
    try:
        from pptx import Presentation  # type: ignore
    except Exception:
        return

    prs = Presentation(str(pptx_path))
    if len(prs.slides) <= 4:
        return
    slide_id_list = prs.slides._sldIdLst  # type: ignore[attr-defined]
    slide_id = slide_id_list[2]
    rel_id = slide_id.rId
    prs.part.drop_rel(rel_id)
    slide_id_list.remove(slide_id)
    prs.save(str(pptx_path))


def _find_libreoffice() -> str:
    candidates = [
        os.getenv("LIBREOFFICE_PATH", ""),
        shutil.which("soffice") or "",
        shutil.which("libreoffice") or "",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return ""


def _prepare_libreoffice_fonts() -> None:
    """Make bundled fonts visible to LibreOffice in cloud/headless runs."""
    font_dir = Path.home() / ".local" / "share" / "fonts" / "ai_visualizer"
    font_dir.mkdir(parents=True, exist_ok=True)

    for font_path in list(APP_DIR.glob("Orbitron*.ttf")) + list(APP_DIR.glob("BIZ-UDMinchoM.ttc")):
        target = font_dir / font_path.name
        if not target.exists() or target.stat().st_size != font_path.stat().st_size:
            shutil.copy2(font_path, target)

    # Make local Windows fonts available to LibreOffice's fontconfig path.
    for source in (
        Path(r"C:\Windows\Fonts\BIZ-UDMinchoM.ttc"),
        Path(r"C:\Windows\Fonts\yumindb.ttf"),
        Path(r"C:\Windows\Fonts\yumin.ttf"),
    ):
        if source.exists():
            target = font_dir / source.name
            if not target.exists() or target.stat().st_size != source.stat().st_size:
                shutil.copy2(source, target)

    fc_cache = shutil.which("fc-cache")
    if fc_cache:
        subprocess.run([fc_cache, "-f", str(font_dir)], check=False, capture_output=True, text=True, timeout=30)


def _export_pdf_via_libreoffice(pptx_path: Path, pdf_path: Path) -> bool:
    soffice = _find_libreoffice()
    if not soffice:
        return False
    _prepare_libreoffice_fonts()

    pptx_abs = Path(pptx_path).resolve()
    pdf_abs = Path(pdf_path).resolve()
    out_dir = pdf_abs.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--nologo",
            "--nofirststartwizard",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(pptx_abs),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    converted = out_dir / f"{pptx_abs.stem}.pdf"
    if result.returncode == 0 and converted.exists():
        if converted.resolve() != pdf_abs:
            if pdf_abs.exists():
                pdf_abs.unlink()
            converted.replace(pdf_abs)
        return pdf_abs.exists()
    return False


def _export_pdf_or_empty(pptx_path: Path, pdf_path: Path) -> str:
    if _export_pdf_via_libreoffice(pptx_path, pdf_path) and pdf_path.exists():
        return str(pdf_path.resolve())
    return ""


def _append_cumulative_analysis_slide(pptx_path: Path, cumulative_analysis: Dict[str, Any]) -> None:
    if not isinstance(cumulative_analysis, dict) or not cumulative_analysis.get("enabled"):
        return
    try:
        from pptx import Presentation  # type: ignore
        from pptx.dml.color import RGBColor  # type: ignore
        from pptx.util import Inches, Pt  # type: ignore
    except Exception:
        LOGGER.error("CUMULATIVE_SLIDE_IMPORT_FAILED category=dependency")
        return

    try:
        prs = Presentation(str(pptx_path))
        blank_layout = prs.slide_layouts[6] if len(prs.slide_layouts) > 6 else prs.slide_layouts[0]
        slide = prs.slides.add_slide(blank_layout)

        def add_box(x: float, y: float, w: float, h: float, text: str, *, size: int = 11, bold: bool = False) -> None:
            box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
            frame = box.text_frame
            frame.clear()
            frame.word_wrap = True
            p = frame.paragraphs[0]
            run = p.add_run()
            run.text = str(text or "")
            run.font.name = "BIZ UDP明朝 Medium"
            run.font.size = Pt(size)
            run.font.bold = bold
            run.font.color.rgb = RGBColor(28, 31, 38)

        axis_trends = cumulative_analysis.get("5項目スコアの推移", {})
        if not isinstance(axis_trends, dict):
            axis_trends = {}
        axis_lines = "\n".join(
            f"{axis}：{axis_trends.get(axis, '')}"
            for axis in AXIS_ORDER
            if str(axis_trends.get(axis, "") or "").strip()
        )

        add_box(0.72, 0.45, 10.4, 0.45, "AI活用の成長と再現性", size=22, bold=True)
        add_box(0.78, 1.05, 10.2, 0.35, f"解析回数：{int(cumulative_analysis.get('record_count', 0) or 0)}回", size=11)
        add_box(0.78, 1.55, 4.95, 0.55, "総合スコアの推移", size=13, bold=True)
        add_box(0.78, 2.02, 4.95, 0.55, str(cumulative_analysis.get("総合スコアの推移", "")), size=18, bold=True)
        add_box(6.05, 1.55, 5.2, 0.55, "5項目スコアの推移", size=13, bold=True)
        add_box(6.05, 2.02, 5.2, 1.65, axis_lines, size=10)
        add_box(0.78, 2.95, 4.95, 0.45, "成長コメント", size=13, bold=True)
        add_box(0.78, 3.35, 4.95, 1.15, str(cumulative_analysis.get("成長コメント", "")), size=11)
        add_box(6.05, 3.85, 5.2, 0.45, "再現性コメント", size=13, bold=True)
        add_box(6.05, 4.25, 5.2, 1.0, str(cumulative_analysis.get("再現性コメント", "")), size=11)
        add_box(0.78, 4.85, 4.95, 0.45, "次回の確認ポイント", size=13, bold=True)
        add_box(0.78, 5.25, 10.45, 0.75, str(cumulative_analysis.get("次回の確認ポイント", "")), size=11)

        prs.save(str(pptx_path))
        LOGGER.info("CUMULATIVE_SLIDE_APPENDED")
    except Exception:
        LOGGER.error("CUMULATIVE_SLIDE_APPEND_FAILED category=rendering")


def _draw_certificate_qr_directly_on_pdf(pdf_path: Path, pptx_path: Path, doc_id: str) -> bool:
    if not pdf_path.exists():
        LOGGER.error("CERTIFICATE_QR_PDF_DIRECT_SKIP reason=pdf_missing")
        return False

    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception:
        LOGGER.error("CERTIFICATE_QR_PDF_DIRECT_IMPORT_FAILED category=dependency")
        return False

    qr_bytes = _build_certificate_qr_png(doc_id)
    if not qr_bytes:
        LOGGER.error("CERTIFICATE_QR_PDF_DIRECT_SKIP reason=qr_generate_failed doc_id=%s", doc_id)
        return False

    try:
        reader = PdfReader(BytesIO(pdf_path.read_bytes()))
        if not reader.pages:
            LOGGER.error("CERTIFICATE_QR_PDF_DIRECT_SKIP reason=no_pages")
            return False

        first_page = reader.pages[0]
        page_width = float(first_page.mediabox.width)
        page_height = float(first_page.mediabox.height)
        slide_width, slide_height = _pptx_slide_size_emu(pptx_path)
        qr_x, qr_y, qr_w, qr_h = CERTIFICATE_QR_BOX

        x_pt = qr_x / slide_width * page_width
        y_pt = page_height - ((qr_y + qr_h) / slide_height * page_height)
        w_pt = qr_w / slide_width * page_width
        h_pt = qr_h / slide_height * page_height
        side_pt = min(w_pt, h_pt)
        x_pt += (w_pt - side_pt) / 2
        y_pt += (h_pt - side_pt) / 2

        overlay_buffer = BytesIO()
        c = canvas.Canvas(overlay_buffer, pagesize=(page_width, page_height))
        c.setFillColorRGB(1, 1, 1)
        c.rect(x_pt, y_pt, side_pt, side_pt, stroke=0, fill=1)
        c.drawImage(
            ImageReader(BytesIO(qr_bytes)),
            x_pt,
            y_pt,
            width=side_pt,
            height=side_pt,
            mask=None,
            preserveAspectRatio=True,
            anchor="c",
        )
        c.save()
        overlay_buffer.seek(0)

        overlay_reader = PdfReader(overlay_buffer)
        first_page.merge_page(overlay_reader.pages[0])
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        output_pdf = BytesIO()
        writer.write(output_pdf)
        pdf_path.write_bytes(output_pdf.getvalue())
        LOGGER.info("CERTIFICATE_QR_PDF_DIRECT_SUCCESS")
        return True
    except Exception:
        LOGGER.error("CERTIFICATE_QR_PDF_DIRECT_FAILED category=rendering")
        return False


def generate_report_from_payload(
    payload: Dict[str, Any],
    report_data: Dict[str, Any],
    doc_id: str,
) -> str:
    """Render a canonical payload with the existing Japanese production design."""
    template_path = _resolve_template_path()
    report_pptx_path = OUTPUT_DIR / f"{doc_id}_report.pptx"
    report_pdf_path = OUTPUT_DIR / f"{doc_id}_report.pdf"

    if TEMPLATE_CLONE_ONLY:
        shutil.copyfile(template_path, report_pptx_path)
        return _export_pdf_or_empty(report_pptx_path, report_pdf_path)

    _populate_template(template_path, report_pptx_path, payload)
    _append_cumulative_analysis_slide(report_pptx_path, report_data.get("cumulative_analysis", {}))
    return _export_pdf_or_empty(report_pptx_path, report_pdf_path)


def generate_report(
    data: Dict[str, Any],
    report_data: Dict[str, Any],
    doc_id: str,
    target_period: str = "",
) -> str:
    payload = build_report_payload(
        data=data,
        report_data=report_data,
        doc_id=doc_id,
        target_period=target_period,
    )
    return generate_report_from_payload(
        payload=payload,
        report_data=report_data,
        doc_id=doc_id,
    )


def _resolve_certificate_template_path() -> Path:
    checked_paths: List[str] = []

    def _candidate_paths(path_text: str) -> List[Path]:
        raw_path = Path(path_text).expanduser()
        if raw_path.is_absolute():
            return [raw_path]
        return [
            Path.cwd() / raw_path,
            APP_DIR / raw_path,
            PROJECT_ROOT / raw_path,
        ]

    candidates = [
        os.getenv("AI_CERTIFICATE_TEMPLATE_PATH", ""),
        "app/certificate_template.pptx",
        str(APP_DIR / "certificate_template.pptx"),
    ]
    for candidate in candidates:
        path_text = str(candidate or "").strip()
        if not path_text:
            continue
        for path_candidate in _candidate_paths(path_text):
            resolved = path_candidate.resolve()
            checked_paths.append(str(resolved))
            if resolved.exists() and resolved.suffix.lower() == ".pptx":
                return resolved
    raise FileNotFoundError(
        "Certificate PowerPoint template was not found. "
        "Check AI_CERTIFICATE_TEMPLATE_PATH or app/certificate_template.pptx."
        f" checked={checked_paths}"
    )


def generate_certificate(data: Dict[str, Any], doc_id: str, target_period: str = "") -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_doc_id = str(doc_id or "").strip() or datetime.now().strftime("TLC-%Y%m%d-001")
    certificate_pptx_path = OUTPUT_DIR / f"{safe_doc_id}_certificate.pptx"
    certificate_pdf_path = OUTPUT_DIR / f"{safe_doc_id}_certificate.pdf"

    user_name = str(data.get("user_name", "") or "").strip()
    if not user_name:
        raise ValueError("User name is required")
    try:
        total_score = int(data.get("total_score", 0) or 0)
    except Exception:
        total_score = 0
    total_score = max(0, min(500, total_score))

    issue_date = datetime.now().strftime("%Y\u5e74%m\u6708%d\u65e5")
    id_no = safe_doc_id
    cert_template = _resolve_certificate_template_path()

    _replace_certificate_values(
        cert_template,
        certificate_pptx_path,
        total_score,
        issue_date,
        id_no,
        user_name,
    )
    exported_pdf = _export_pdf_or_empty(certificate_pptx_path, certificate_pdf_path)
    direct_pdf_qr = False
    if exported_pdf:
        direct_pdf_qr = _draw_certificate_qr_directly_on_pdf(Path(exported_pdf), certificate_pptx_path, safe_doc_id)
    LOGGER.info(
        "CERTIFICATE_QR_PDF_EXPORT pdf_exists=%s direct_pdf_qr=%s",
        bool(exported_pdf and Path(exported_pdf).exists()),
        direct_pdf_qr,
    )
    return exported_pdf
