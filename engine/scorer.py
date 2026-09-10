# C:\Users\TokyoLastCraftsmen\ai_visualizer_app\engine\scorer.py

import math
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List


AXIS_ORDER = [
    "成果物論理性",
    "判断プロセス",
    "修正プロセス",
    "判断主体性",
    "全体整合性",
]

STOPWORDS = {
    "する", "した", "して", "いる", "ある", "ない", "なる", "もの", "こと", "これ", "それ",
    "ため", "よう", "ので", "から", "まで", "です", "ます", "でした", "ました", "という",
    "また", "でも", "ただ", "なら", "より", "へ", "を", "に", "が", "は", "と", "で",
    "やる", "いい", "よい", "OK", "ok", "了解", "AI", "ai", "人", "ユーザー",
}

REASON_PATTERNS = [
    r"理由", r"なぜ", r"ため", r"ので", r"から", r"狙い", r"意図", r"目的",
    r"伝わりやすい", r"自然", r"強い", r"弱い", r"危険", r"ズレ", r"筋",
    r"(?i)\bbecause\b", r"(?i)\bsince\b", r"(?i)\bso that\b", r"(?i)\bthe point is\b",
    r"(?i)\b(?:feels?|sounds?)\b", r"(?i)\b(?:clearer|clearest|shorter|works better|important)\b",
]

STRUCTURE_PATTERNS = [
    r"構造", r"構成", r"順番", r"並び順", r"見出し", r"項目", r"流れ",
    r"導線", r"配置", r"ラベル", r"名称", r"用語", r"UI", r"HERO", r"CTA",
    r"(?i)\b(?:structure|section|headline|heading|paragraph|button|call[- ]to[- ]action|cta|hero|layout|order)\b",
    r"(?i)\bline above\b", r"(?i)\bwording\b",
]

LOGIC_PATTERNS = [
    r"理由", r"したがって", r"そのため", r"一方", r"ただし", r"つまり",
    r"まず", r"次に", r"最後に", r"結論", r"前提", r"条件", r"目的", r"根拠",
    r"(?i)\bbecause\b", r"(?i)\bhowever\b", r"(?i)\bbut\b", r"(?i)\binstead\b",
    r"(?i)\bfirst\b", r"(?i)\bfinal\b", r"(?i)\bthe point is\b", r"(?i)\bshould\b",
]

PAGE_MARKERS = [
    "SOURCE_URL:",
    "PAGE_EVALUATION_READY:",
    "FETCH_MODE:",
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
    "CTA_BUTTONS:",
    "LINK_TEXTS:",
    "ARIA_LABELS:",
    "BODY:",
    "TEXT:",
    "SECTIONS:",
    "LP_HERO_SCORE:",
    "LP_CTA_SCORE:",
    "LP_FLOW_SCORE:",
    "ARTIFACT_SET_MODE:",
    "ARTIFACT_TEXT[",
    "ARTIFACT_IMAGE_ROLE:",
]

CONTENT_MARKERS = [
    "PAGE_EVALUATION_READY:",
    "PAGE_TITLE:",
    "H1:",
    "H2:",
    "H3:",
    "CTA_BUTTONS:",
    "LINK_TEXTS:",
    "ARIA_LABELS:",
    "BODY:",
    "TEXT:",
    "SECTIONS:",
    "LP_HERO_SCORE:",
    "LP_CTA_SCORE:",
    "LP_FLOW_SCORE:",
    "ARTIFACT_SET_MODE:",
    "ARTIFACT_TEXT[",
    "ARTIFACT_IMAGE_ROLE:",
]

ARTIFACT_HINTS = [
    "品名・説明:",
    "対象URL:",
    "文章成果物:",
    "ARTIFACT_SET_MODE:",
    "ARTIFACT_TEXT[",
    "ARTIFACT_IMAGE_ROLE:",
]

LP_HINTS = [
    "LP", "ランディング", "CTA", "HERO", "導線",
    "料金", "比較", "申込", "申し込み", "無料", "有料",
    "証明", "レポート", "診断", "強み", "課題", "選ばせる",
]

URL_EVAL_ORDER = [
    "文章構造",
    "訴求力",
    "AI活用度",
]

TARGET_CLARITY_WORDS = [
    "あなた", "向け", "対象", "こんな方", "こんな人", "ペルソナ",
    "採用担当", "経営者", "担当者", "個人", "法人",
]

BENEFIT_WORDS = [
    "できる", "わかる", "伝わる", "見える", "可視化", "改善",
    "解決", "成果", "効率", "証明", "最適", "強み", "課題",
]

CTA_WORDS = [
    "CTA", "申し込み", "申込", "今すぐ", "相談", "問い合わせ",
    "診断", "資料請求", "無料", "ダウンロード", "始める", "確認",
]

ANXIETY_RELIEF_WORDS = [
    "安心", "不安", "初めて", "はじめて", "無料", "簡単",
    "手軽", "サポート", "FAQ", "よくある質問", "リスク", "失敗",
]

TRUST_WORDS = [
    "実績", "事例", "導入", "お客様", "会社", "運営",
    "プロフィール", "比較", "料金", "証明", "レポート", "レビュー",
]

ACTION_REASON_WORDS = [
    "今すぐ", "無料", "限定", "先着", "診断", "相談",
    "確認", "始める", "申し込み", "比較", "メリット",
]

PAGE_CONTEXT_RULES = [
    ("有料導線LP", ["有料導線", "販売LP", "訴求LP", "セールスLP"]),
    ("LP", ["lp", "ランディング", "landing page"]),
    ("使い方ページ", ["使い方", "利用方法", "ご利用方法", "how to", "ガイド", "手順"]),
    ("入力フォームページ", ["入力フォーム", "申込フォーム", "申し込みフォーム", "エントリー", "フォーム"]),
    ("サービス紹介ページ", ["サービス紹介", "サービスページ", "紹介ページ"]),
    ("採用ページ", ["採用ページ", "採用", "recruit"]),
    ("記事ページ", ["記事", "ブログ", "コラム"]),
    ("コーポレートページ", ["会社概要", "コーポレート", "企業情報", "about"]),
]

TARGET_DESIGN_WORDS = [
    "ターゲット", "誰向け", "向け", "主語", "あなた",
    "読者", "対象", "ペルソナ", "採用担当", "経営者",
]

ISSUE_ORGANIZATION_WORDS = [
    "論点", "整理", "優先", "順番", "構造",
    "導線", "見出し", "分類", "章立て", "筋",
]

STEP_TOPIC_RULES = [
    ("hero_primary", ["HERO", "Hero", "ヒーロー", "問い", "止める構造", "ヒーローコピー"]),
    ("hero_follow", ["HERO下", "Hero下", "直下", "時代背景", "主語", "問題提起"]),
    ("problem", ["PROBLEM", "違和感", "残らない", "共有されない"]),
    ("qr", ["QR", "読み取るだけ", "見せれば分かる"]),
    ("proof_message", ["評価", "証明", "伝わる", "共有", "見える化", "想像させる"]),
    ("ad_flow", ["フック", "診断", "自己認識", "広告構造"]),
    ("classification_structure", ["分類ゾーン", "分類セクション", "5分類", "自分はどこ", "位置認識", "自己認識導線"]),
    ("classification_title", ["分類タイトル", "カテゴリー", "レベル"]),
    ("classification_label", ["分類ラベル", "依存", "主導", "任せる", "速める", "借りる", "つくる", "導く"]),
    ("classification_copy", ["分類説明文", "一言コメント", "状態を示す文章", "工程説明"]),
    ("visual_style", ["見た目", "余白", "ミニマル", "Apple", "高級感", "装飾", "背景", "静けさ", "UI"]),
    ("cta", ["CTA", "現在地を確認する", "スコアを確認する", "命令", "確認系"]),
    ("page_role", ["売るページ", "理解させて", "教育型", "納得型", "行動させる", "入力の質"]),
    ("flow", ["見える化までの流れ", "使い方ページ", "ログ抽出", "折りたたみ", "手順", "導線", "アプリ"]),
    ("trust", ["β版", "フッター", "問い合わせ", "利用規約", "プライバシー", "運営情報"]),
    ("identity", ["TLC", "運営者名", "所在地", "事務所", "アトリエ", "法人"]),
    ("device", ["スマホ", "PC"]),
    ("report_preview", ["レポート画像", "拡大表示", "Lightbox", "モーダル"]),
    ("completion_phase", ["未完成", "完成度", "細部調整", "細部改善", "大改修"]),
    ("decision_stance", ["最終決定", "自分で行う", "AI案は参考"]),
]


def score(analysis: Dict[str, Any], output_text: str = "") -> Dict[str, Any]:
    analysis = analysis if isinstance(analysis, dict) else {}

    structured_steps = analysis.get("structured_steps", []) or []
    decisions = analysis.get("decisions", []) or []
    revisions = analysis.get("revisions", []) or []
    adoptions = analysis.get("adoptions", []) or []
    structure_decisions = analysis.get("structure_decisions", []) or []
    step_profile = analysis.get("step_profile", {}) if isinstance(analysis.get("step_profile", {}), dict) else {}
    log_source_profile = analysis.get("log_source_profile", {}) if isinstance(analysis.get("log_source_profile", {}), dict) else {}

    if not decisions and not revisions and not adoptions and structured_steps:
        decisions, revisions, adoptions, structure_decisions = _rebuild_collections_from_steps(structured_steps)

    compression_result = _compress_duplicate_step_bundle(
        structured_steps,
        source_structure_decisions=structure_decisions,
    )
    if compression_result["compressed_steps"]:
        structured_steps = compression_result["compressed_steps"]
        decisions = compression_result["decisions"]
        revisions = compression_result["revisions"]
        adoptions = compression_result["adoptions"]
        structure_decisions = compression_result["structure_decisions"]

    log_text = _safe_text(analysis.get("log_text", ""))
    analysis_output_text = _safe_text(analysis.get("output_text", ""))
    analysis_actual_output_text = _safe_text(analysis.get("actual_output_text", ""))
    analysis_page_output_text = _safe_text(analysis.get("page_output_text", ""))
    analysis_context_text = _safe_text(analysis.get("artifact_context_text", ""))
    output_text = _safe_text(output_text)

    merged_output = _build_scoring_output_text(
        provided_output=output_text,
        analyzed_output=analysis_output_text,
        actual_output=analysis_actual_output_text,
        page_output=analysis_page_output_text,
        context_output=analysis_context_text,
    )
    artifact_type = _classify_artifact_type(merged_output, analysis_context_text)
    artifact_match = _measure_final_artifact_match(
        structured_steps,
        analysis_actual_output_text or merged_output,
    )
    visual_input_mode = _normalize_visual_input_mode(analysis.get("visual_input_mode", {}), merged_output)

    url_structure_detail = _score_url_structure(merged_output)
    url_appeal_detail = _score_url_appeal(merged_output)
    judgment_agency = _score_judgment_agency(
        structured_steps,
        decisions,
        adoptions,
        step_profile=step_profile,
        log_source_profile=log_source_profile,
    )
    judgment_process = _score_judgment_process(
        structured_steps,
        decisions,
        adoptions,
        step_profile=step_profile,
        log_source_profile=log_source_profile,
    )
    revision_process = _score_revision_process(
        structured_steps,
        revisions,
        structure_decisions,
        step_profile=step_profile,
        log_source_profile=log_source_profile,
    )
    output_logic = _score_output_logic(
        merged_output,
        log_text,
        structured_steps,
        decisions,
        revisions,
        adoptions,
        structure_decisions,
        url_structure_detail,
        url_appeal_detail,
        visual_input_mode,
        step_profile=step_profile,
        artifact_type=artifact_type,
        artifact_match=artifact_match,
    )
    overall_consistency = _score_overall_consistency(
        structured_steps=structured_steps,
        decisions=decisions,
        revisions=revisions,
        adoptions=adoptions,
        structure_decisions=structure_decisions,
        output_text=merged_output,
        log_text=log_text,
        url_structure_detail=url_structure_detail,
        url_appeal_detail=url_appeal_detail,
        visual_input_mode=visual_input_mode,
        step_profile=step_profile,
        artifact_type=artifact_type,
        artifact_match=artifact_match,
    )

    scores = {
        AXIS_ORDER[0]: output_logic["score"],
        AXIS_ORDER[1]: judgment_process["score"],
        AXIS_ORDER[2]: revision_process["score"],
        AXIS_ORDER[3]: judgment_agency["score"],
        AXIS_ORDER[4]: overall_consistency["score"],
    }

    total_score = int(sum(scores.values()))

    axis_details = {
        AXIS_ORDER[0]: output_logic,
        AXIS_ORDER[1]: judgment_process,
        AXIS_ORDER[2]: revision_process,
        AXIS_ORDER[3]: judgment_agency,
        AXIS_ORDER[4]: overall_consistency,
    }

    trace_summary = _build_trace_summary(
        decisions=decisions,
        revisions=revisions,
        adoptions=adoptions,
        structure_decisions=structure_decisions,
        raw_counts=compression_result["raw_counts"],
    )
    unclassified_comment = _build_unclassified_comment(scores, merged_output)
    url_evaluation = _build_url_evaluation(
        output_text=merged_output,
        log_text=log_text,
        structured_steps=structured_steps,
        decisions=decisions,
        revisions=revisions,
        adoptions=adoptions,
        structure_decisions=structure_decisions,
        judgment_process=judgment_process,
        revision_process=revision_process,
        judgment_agency=judgment_agency,
        overall_consistency=overall_consistency,
    )
    visual_evaluation = analysis.get("visual_evaluation", {})
    if not isinstance(visual_evaluation, dict):
        visual_evaluation = {}
    if (not visual_evaluation or not visual_evaluation.get("enabled")) and visual_input_mode.get("enabled"):
        visual_evaluation = _build_screenshot_visual_evaluation(merged_output, visual_input_mode)

    return {
        "scores": scores,
        "total_score": total_score,
        "axis_details": axis_details,
        "trace_summary": trace_summary,
        "compression_summary": compression_result["summary"],
        "unclassified_comment": unclassified_comment,
        "url_evaluation": url_evaluation,
        "visual_evaluation": visual_evaluation,
        "log": log_text,
        "output": merged_output,
        "step_profile": step_profile,
        "artifact_type": artifact_type,
        "artifact_match": artifact_match,
    }


def _build_scoring_output_text(
    *,
    provided_output: str,
    analyzed_output: str,
    actual_output: str,
    page_output: str,
    context_output: str,
) -> str:
    parts: List[str] = []

    for text_part in [actual_output, page_output]:
        clean_part = _safe_text(text_part)
        _append_distinct_artifact(parts, clean_part)

    for text_part in [provided_output, analyzed_output]:
        stripped_part = _strip_supporting_context_lines(text_part)
        _append_distinct_artifact(parts, stripped_part)

    if not parts:
        fallback = _safe_text(context_output) or _safe_text(provided_output) or _safe_text(analyzed_output)
        if fallback:
            parts.append(fallback)

    return "\n\n".join(parts).strip()


def _append_distinct_artifact(parts: List[str], candidate: str) -> None:
    candidate = _safe_text(candidate)
    if not candidate:
        return

    normalized_candidate = _normalize_artifact_identity(candidate)
    compact_candidate = _compact_artifact_identity(candidate)
    if not normalized_candidate:
        return

    for existing in parts:
        normalized_existing = _normalize_artifact_identity(existing)
        compact_existing = _compact_artifact_identity(existing)
        if normalized_candidate == normalized_existing:
            return
        # Analyzer output can contain the same artifact followed by metadata.
        # Treat that as one artifact, while preserving genuinely different
        # Files/URL/Text artifacts.
        shorter = min(len(compact_candidate), len(compact_existing))
        if shorter >= 200 and (
            compact_candidate in compact_existing
            or compact_existing in compact_candidate
        ):
            return

    parts.append(candidate)


def _normalize_artifact_identity(text: str) -> str:
    normalized_lines = [
        line.rstrip()
        for line in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    normalized = "\n".join(normalized_lines).strip()
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", normalized)


def _compact_artifact_identity(text: str) -> str:
    return re.sub(r"\s+", " ", _normalize_artifact_identity(text)).strip()


def _classify_artifact_type(output_text: str, context_text: str = "") -> str:
    text = "\n".join(filter(None, [_safe_text(context_text), _safe_text(output_text)]))
    if _is_lp_like(text):
        return "landing_page"

    lowered = text.lower()
    heading_count = _count_document_headings(output_text)
    type_patterns = [
        ("product_specification", [
            r"\bproduct\s+specification\b", r"\bfunctional\s+specification\b",
            r"\brequirements?\s+specification\b", r"\bspecification\b",
            r"製品仕様書", r"機能仕様書", r"要件定義書", r"仕様書",
        ]),
        ("improvement_plan", [
            r"\bimprovement\s+plan\b", r"\bimplementation\s+plan\b",
            r"\baction\s+plan\b", r"改善計画", r"実装計画", r"実行計画",
        ]),
        ("proposal", [
            r"\bproposal\b", r"\brecommendation\b", r"提案書", r"提案", r"推奨案",
        ]),
        ("report", [
            r"\breport\b", r"\bfindings\b", r"\banalysis\s+summary\b",
            r"報告書", r"調査結果", r"分析結果",
        ]),
    ]
    for artifact_type, patterns in type_patterns:
        if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns):
            return artifact_type

    if heading_count >= 3:
        return "general_document"
    if heading_count >= 1 or len(_safe_text(output_text)) >= 500:
        return "structured_text"
    return "unknown"


def _count_document_headings(text: str) -> int:
    count = 0
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line or len(line) > 180:
            continue
        if re.match(r"^(?:#{1,6}\s+|\d+(?:\.\d+)*[.)]?\s+|[IVXLC]+[.)]\s+)", line, re.IGNORECASE):
            count += 1
            continue
        if re.match(r"^(?:第[一二三四五六七八九十0-9]+[章節部]|【.+】)", line):
            count += 1
            continue
        letters = re.sub(r"[^A-Za-z]", "", line)
        if len(letters) >= 5 and letters.upper() == letters:
            count += 1
    return count


def _measure_final_artifact_match(
    structured_steps: List[Dict[str, Any]],
    submitted_output: str,
) -> Dict[str, Any]:
    submitted = _safe_text(submitted_output)
    if not submitted:
        return {
            "status": "not_available",
            "ratio": 0.0,
            "source_step_id": 0,
            "candidate_chars": 0,
            "submitted_chars": 0,
        }

    approval_patterns = [
        r"\bapprove(?:d)?\b.+\b(?:as\s+)?final\b",
        r"\breject\s+further\s+changes?\b",
        r"\bno\s+further\s+revisions?\s+(?:is|are)\s+required\b",
        r"\b(?:use|choose)\s+the\s+current\s+version\s+as\s+final\b",
        r"\bkeep\s+the\s+current\s+version\b",
        r"\buse\s+this\s+final\s+structure\b",
        r"最終(?:版|成果物).*(?:承認|採用)",
        r"(?:この|現行の).*(?:最終版|完成版).*(?:採用|承認)",
        r"追加修正は不要",
    ]
    candidates: List[tuple[int, str]] = []
    for step in structured_steps:
        if not isinstance(step, dict):
            continue
        user_evidence = "\n".join([
            _safe_text(step.get("raw", "")),
            _safe_text(step.get("judgment", "")),
            _safe_text(step.get("adoption", "")),
        ])
        assistant_context = _safe_text(step.get("assistant_context", ""))
        if len(assistant_context) < 80:
            continue
        if any(re.search(pattern, user_evidence, flags=re.IGNORECASE | re.DOTALL) for pattern in approval_patterns):
            candidates.append((_safe_int(step.get("step_id", 0)), assistant_context))

    if not candidates:
        return {
            "status": "not_found",
            "ratio": 0.0,
            "source_step_id": 0,
            "candidate_chars": 0,
            "submitted_chars": len(submitted),
        }

    source_step_id, candidate = candidates[-1]
    exact_candidate = candidate.replace("\r\n", "\n").replace("\r", "\n").strip()
    exact_submitted = submitted.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized_candidate = _normalize_artifact_identity(candidate)
    normalized_submitted = _normalize_artifact_identity(submitted)
    ratio = SequenceMatcher(None, normalized_candidate, normalized_submitted).ratio()

    if exact_candidate == exact_submitted:
        status = "exact"
        ratio = 1.0
    elif normalized_candidate == normalized_submitted:
        status = "normalized"
        ratio = 1.0
    elif ratio >= 0.35:
        status = "partial"
    else:
        status = "mismatch"

    return {
        "status": status,
        "ratio": round(float(ratio), 4),
        "source_step_id": source_step_id,
        "candidate_chars": len(candidate),
        "submitted_chars": len(submitted),
    }


def _strip_supporting_context_lines(text: str) -> str:
    rows: List[str] = []
    capture_output = False

    for raw_line in str(text or "").splitlines():
        line = _safe_text(raw_line)
        if not line:
            continue

        if line.startswith("文章成果物:"):
            capture_output = True
            tail = line.replace("文章成果物:", "", 1).strip()
            if tail:
                rows.append(tail)
            continue

        if capture_output:
            rows.append(line)
            continue

        if line.startswith("LP_") or line.startswith((
            "ARTIFACT_SET_MODE:",
            "ARTIFACT_SET_ROLE:",
            "ARTIFACT_SET_ITEM_COUNT:",
            "ARTIFACT_SET_TYPES:",
            "ARTIFACT_FILE_COUNTS:",
            "ARTIFACT_IMAGE_ROLE:",
            "ARTIFACT_IMAGE_COUNT:",
            "ARTIFACT_IMAGE_FILES:",
            "ARTIFACT_EMBEDDED_MEDIA_COUNT:",
            "ARTIFACT_TEXT_EXTRACTION_READY:",
            "ARTIFACT_TEXT[",
            "PAGE_TITLE:",
            "PAGE_EVALUATION_READY:",
            "META:",
            "H1:",
            "H2:",
            "H3:",
            "SECTIONS:",
            "BODY:",
            "TEXT:",
            "CTA_BUTTONS:",
            "LINK_TEXTS:",
            "ARIA_LABELS:",
            "SOURCE_URL:",
            "対象URL:",
            "URL_FETCH_FAILED:",
        )):
            rows.append(line)

    return "\n".join(rows).strip()


def _has_substantive_output_core(text: str) -> bool:
    txt = _safe_text(text)
    if not txt:
        return False
    if any(marker in txt for marker in CONTENT_MARKERS):
        return True
    return len(_extract_keywords(txt)) >= 12


def _measure_decision_reflection(
    output_text: str,
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
) -> float:
    output_keywords = set(_extract_keywords(output_text))
    if not output_keywords:
        return 0.0

    reflected = 0
    total = 0
    for item in decisions[:4] + revisions[:4] + adoptions[:4]:
        text = _safe_text(item.get("text", "")) if isinstance(item, dict) else ""
        if not text:
            continue
        keywords = set(_extract_keywords(text))
        if not keywords:
            continue
        total += 1
        overlap = keywords & output_keywords
        if overlap and (len(overlap) / max(1, len(keywords)) >= 0.2 or len(overlap) >= 2):
            reflected += 1

    if total == 0:
        return 0.0
    return reflected / total


def _measure_page_structure_reflection(
    output_text: str,
    structured_steps: List[Dict[str, Any]],
) -> float:
    txt = _safe_text(output_text)
    if not txt or not structured_steps:
        return 0.0

    page_zone = _build_page_zone(_get_page_context(txt), include_body=True)
    if not page_zone:
        return 0.0

    rule_map = {
        "hero_primary": ["問い", "証明", "できますか", "活用できている"],
        "hero_follow": ["当たり前", "証明する方法", "評価する基準", "残らない"],
        "problem": ["残らない", "共有されない", "違和感", "評価基準"],
        "qr": ["qr", "読み取る", "見せれば分かる", "伝わる"],
        "classification_structure": ["カテゴリー", "分類", "どこにいますか", "現在地"],
        "classification_label": ["依存", "効率化", "補助", "共創", "主導", "任せる", "速める", "借りる", "つくる", "導く"],
        "visual_style": ["余白", "ミニマル", "apple", "静けさ", "高級感"],
        "cta": ["確認", "診断", "スコア", "始める", "申し込み", "現在地を確認"],
        "trust": ["β版", "問い合わせ", "利用規約", "プライバシー", "運営"],
    }

    matched = 0
    total = 0
    lowered_page_zone = page_zone.lower()

    for step in structured_steps:
        topics = _extract_step_topics(step)
        if not topics:
            continue
        for topic in topics:
            if topic not in rule_map:
                continue
            total += 1
            keywords = rule_map[topic]
            if any(keyword.lower() in lowered_page_zone for keyword in keywords):
                matched += 1

    if total == 0:
        return 0.0
    return matched / total

def _rebuild_collections_from_steps(
    structured_steps: List[Dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    decisions: List[Dict[str, Any]] = []
    revisions: List[Dict[str, Any]] = []
    adoptions: List[Dict[str, Any]] = []
    structure_decisions: List[Dict[str, Any]] = []

    for idx, step in enumerate(structured_steps, start=1):
        if not isinstance(step, dict):
            continue

        judgment = _safe_text(step.get("judgment", ""))
        revision = _safe_text(step.get("revision", ""))
        adoption = _safe_text(step.get("adoption", ""))
        reason = _safe_text(step.get("reason", ""))

        if judgment:
            decisions.append({
                "step_id": step.get("step_id", idx),
                "text": judgment,
                "reason": reason,
            })

        if revision:
            revisions.append({
                "step_id": step.get("step_id", idx),
                "text": revision,
                "reason": reason,
                "before_after": step.get("before_after", {}) if isinstance(step.get("before_after", {}), dict) else {},
            })

        if adoption:
            adoptions.append({
                "step_id": step.get("step_id", idx),
                "text": adoption,
                "reason": reason,
            })

        combined = "\n".join([x for x in [judgment, revision, adoption] if _safe_text(x)]).strip()
        if combined and _looks_like_structure_decision(combined):
            structure_decisions.append({
                "step_id": step.get("step_id", idx),
                "text": combined,
                "reason": reason,
            })

    return decisions, revisions, adoptions, structure_decisions


def _compress_duplicate_step_bundle(
    structured_steps: List[Dict[str, Any]],
    source_structure_decisions: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    raw_counts = {
        "steps": len([step for step in structured_steps if isinstance(step, dict)]),
        "decisions": 0,
        "revisions": 0,
        "adoptions": 0,
        "structure_decisions": 0,
    }

    if not structured_steps:
        return {
            "compressed_steps": [],
            "decisions": [],
            "revisions": [],
            "adoptions": [],
            "structure_decisions": [],
            "summary": "",
            "raw_counts": raw_counts,
        }

    raw_decisions, raw_revisions, raw_adoptions, rebuilt_structure_decisions = _rebuild_collections_from_steps(structured_steps)
    raw_structure_decisions = (
        [item for item in (source_structure_decisions or []) if isinstance(item, dict)]
        if source_structure_decisions
        else rebuilt_structure_decisions
    )
    raw_counts["decisions"] = len(raw_decisions)
    raw_counts["revisions"] = len(raw_revisions)
    raw_counts["adoptions"] = len(raw_adoptions)
    raw_counts["structure_decisions"] = len(raw_structure_decisions)

    unique_steps: List[Dict[str, Any]] = []
    step_groups: List[List[Dict[str, Any]]] = []

    for step in structured_steps:
        if not isinstance(step, dict):
            continue
        if not _step_has_content(step):
            continue

        matched_index = -1
        matched_score = 0.0

        for idx, existing_step in enumerate(unique_steps):
            similarity = _step_similarity(step, existing_step)
            if similarity > matched_score:
                matched_score = similarity
                matched_index = idx

        if matched_index >= 0 and _should_merge_step(step, unique_steps[matched_index], matched_score):
            unique_steps[matched_index] = _merge_step_pair(unique_steps[matched_index], step)
            step_groups[matched_index].append(step)
        else:
            unique_steps.append(dict(step))
            step_groups.append([step])

    compressed_steps: List[Dict[str, Any]] = []
    merged_group_count = 0

    for idx, step in enumerate(unique_steps, start=1):
        normalized_step = dict(step)
        original_step_id = _safe_int(step.get("step_id", idx)) or idx
        normalized_step["source_step_id"] = original_step_id
        normalized_step["step_id"] = idx

        group = step_groups[idx - 1]
        source_step_ids = [
            _safe_int(item.get("step_id", 0)) for item in group if isinstance(item, dict)
        ]
        if len(group) > 1:
            merged_group_count += 1
            normalized_step["compressed_count"] = len(group)
            normalized_step["compressed_from_step_ids"] = source_step_ids

        compressed_steps.append(normalized_step)

    decisions, revisions, adoptions, rebuilt_compressed_structure = _rebuild_collections_from_steps(compressed_steps)
    structure_decisions = _remap_structure_decisions(
        raw_structure_decisions,
        compressed_steps,
    ) if source_structure_decisions else rebuilt_compressed_structure
    duplicate_count = max(0, raw_counts["steps"] - len(compressed_steps))

    summary = ""
    if duplicate_count > 0:
        summary = (
            f"重複Stepを {duplicate_count} 件圧縮し、"
            f"{raw_counts['steps']}件 -> {len(compressed_steps)}件 で採点"
        )
    elif raw_counts["steps"] > 0:
        summary = f"重複圧縮なしで {raw_counts['steps']}件 を採点"

    return {
        "compressed_steps": compressed_steps,
        "decisions": decisions,
        "revisions": revisions,
        "adoptions": adoptions,
        "structure_decisions": structure_decisions,
        "summary": summary,
        "raw_counts": raw_counts,
        "merged_group_count": merged_group_count,
    }


def _step_has_content(step: Dict[str, Any]) -> bool:
    return any(
        _safe_text(step.get(field, ""))
        for field in ["judgment", "revision", "adoption", "reason", "raw"]
    )


def _step_similarity(a: Dict[str, Any], b: Dict[str, Any]) -> float:
    core_a = _build_step_core_text(a)
    core_b = _build_step_core_text(b)
    reason_a = _safe_text(a.get("reason", ""))
    reason_b = _safe_text(b.get("reason", ""))

    core_similarity = _text_similarity(core_a, core_b)
    judgment_similarity = _text_similarity(a.get("judgment", ""), b.get("judgment", ""))
    revision_similarity = _text_similarity(a.get("revision", ""), b.get("revision", ""))
    adoption_similarity = _text_similarity(a.get("adoption", ""), b.get("adoption", ""))
    reason_similarity = _text_similarity(reason_a, reason_b)

    similarity = (
        core_similarity * 0.45
        + judgment_similarity * 0.20
        + revision_similarity * 0.15
        + adoption_similarity * 0.10
        + reason_similarity * 0.10
    )

    if _shared_keyword_count(core_a, core_b) >= 4:
        similarity += 0.08
    if _shared_keyword_count(reason_a, reason_b) >= 3:
        similarity += 0.04
    if _shared_topic_count(a, b) >= 2:
        similarity += 0.06

    return min(1.0, similarity)


def _should_merge_step(a: Dict[str, Any], b: Dict[str, Any], similarity: float) -> bool:
    source_a = _step_source_identity(a)
    source_b = _step_source_identity(b)
    if source_a and source_b and source_a != source_b:
        return False

    core_a = _build_step_core_text(a)
    core_b = _build_step_core_text(b)
    core_similarity = _text_similarity(core_a, core_b)
    judgment_similarity = _text_similarity(a.get("judgment", ""), b.get("judgment", ""))
    revision_similarity = _text_similarity(a.get("revision", ""), b.get("revision", ""))
    adoption_similarity = _text_similarity(a.get("adoption", ""), b.get("adoption", ""))
    reason_similarity = _text_similarity(a.get("reason", ""), b.get("reason", ""))
    shared_core_keywords = _shared_keyword_count(core_a, core_b)
    shared_topics = _shared_topic_count(a, b)

    if judgment_similarity >= 0.88:
        return True
    if core_similarity >= 0.82:
        return True
    if similarity >= 0.72:
        return True
    if shared_topics >= 1 and judgment_similarity >= 0.64:
        return True
    if shared_topics >= 1 and similarity >= 0.58:
        return True
    if shared_topics >= 2 and max(revision_similarity, adoption_similarity, reason_similarity) >= 0.42:
        return True
    if similarity >= 0.58 and shared_core_keywords >= 4:
        return True

    return False


def _step_source_identity(step: Dict[str, Any]) -> tuple[int, int] | None:
    block_id = _safe_int(step.get("log_block_id", 0))
    block_step_index = _safe_int(step.get("log_block_step_index", 0))
    if block_id > 0:
        return block_id, max(0, block_step_index)
    return None


def _remap_structure_decisions(
    source_items: List[Dict[str, Any]],
    compressed_steps: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    source_to_compressed: Dict[int, int] = {}
    for step in compressed_steps:
        compressed_id = _safe_int(step.get("step_id", 0))
        source_ids = step.get("compressed_from_step_ids", [])
        if not isinstance(source_ids, list) or not source_ids:
            source_ids = [step.get("source_step_id", compressed_id)]
        for source_id in source_ids:
            source_id = _safe_int(source_id)
            if source_id > 0:
                source_to_compressed[source_id] = compressed_id

    result: List[Dict[str, Any]] = []
    seen = set()
    for item in source_items:
        if not isinstance(item, dict):
            continue
        text = _safe_text(item.get("text", ""))
        if not text:
            continue
        source_id = _safe_int(item.get("step_id", 0))
        mapped_id = source_to_compressed.get(source_id, source_id)
        key = (mapped_id, _normalize_similarity_text(text))
        if key in seen:
            continue
        seen.add(key)
        normalized_item = dict(item)
        normalized_item["source_step_id"] = source_id
        normalized_item["step_id"] = mapped_id
        result.append(normalized_item)
    return result


def _merge_step_pair(base: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)

    for field in ["judgment", "revision", "adoption", "reason", "raw"]:
        merged[field] = _choose_richer_text(base.get(field, ""), incoming.get(field, ""))

    base_before_after = base.get("before_after", {}) if isinstance(base.get("before_after", {}), dict) else {}
    incoming_before_after = incoming.get("before_after", {}) if isinstance(incoming.get("before_after", {}), dict) else {}
    merged["before_after"] = {
        "before": _choose_richer_text(base_before_after.get("before", ""), incoming_before_after.get("before", "")),
        "after": _choose_richer_text(base_before_after.get("after", ""), incoming_before_after.get("after", "")),
    }

    return merged


def _choose_richer_text(a: Any, b: Any) -> str:
    text_a = _safe_text(a)
    text_b = _safe_text(b)

    if not text_a:
        return text_b
    if not text_b:
        return text_a

    score_a = _text_richness_score(text_a)
    score_b = _text_richness_score(text_b)

    return text_a if score_a >= score_b else text_b


def _text_richness_score(text: str) -> int:
    clean_text = _safe_text(text)
    return len(set(_extract_keywords(clean_text))) * 10 + len(clean_text)


def _build_step_core_text(step: Dict[str, Any]) -> str:
    return "\n".join([
        _safe_text(step.get("judgment", "")),
        _safe_text(step.get("revision", "")),
        _safe_text(step.get("adoption", "")),
    ]).strip()


def _text_similarity(a: Any, b: Any) -> float:
    text_a = _safe_text(a)
    text_b = _safe_text(b)

    if not text_a or not text_b:
        return 0.0

    normalized_a = _normalize_similarity_text(text_a)
    normalized_b = _normalize_similarity_text(text_b)

    if normalized_a == normalized_b:
        return 1.0

    if normalized_a and normalized_b and (normalized_a in normalized_b or normalized_b in normalized_a):
        return 0.92

    sequence_ratio = SequenceMatcher(None, normalized_a, normalized_b).ratio() if normalized_a and normalized_b else 0.0

    tokens_a = set(_extract_keywords(text_a))
    tokens_b = set(_extract_keywords(text_b))
    if not tokens_a or not tokens_b:
        return sequence_ratio

    overlap = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    containment = overlap / max(1, min(len(tokens_a), len(tokens_b)))
    jaccard = overlap / max(1, union)

    return max(jaccard, containment * 0.9, sequence_ratio)


def _normalize_similarity_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", _safe_text(text))
    normalized = re.sub(r"[【】\[\]（）()「」『』・/,:：\-—_]", "", normalized)
    return normalized


def _extract_step_topics(step: Dict[str, Any]) -> set[str]:
    if not isinstance(step, dict):
        return set()

    combined = "\n".join([
        _safe_text(step.get("judgment", "")),
        _safe_text(step.get("revision", "")),
        _safe_text(step.get("adoption", "")),
        _safe_text(step.get("reason", "")),
    ])

    topics: set[str] = set()
    for label, words in STEP_TOPIC_RULES:
        if any(word in combined for word in words):
            topics.add(label)

    return topics


def _shared_topic_count(a: Dict[str, Any], b: Dict[str, Any]) -> int:
    return len(_extract_step_topics(a) & _extract_step_topics(b))


def _shared_keyword_count(a: Any, b: Any) -> int:
    return len(set(_extract_keywords(a)) & set(_extract_keywords(b)))


def _normalized_from_hybrid(
    *,
    base_score: float = 80.0,
    plus_points: float = 0.0,
    minus_points: float = 0.0,
    floor: float = 0.0,
    hard_cap: float = 100.0,
) -> float:
    score = base_score + plus_points - minus_points
    score = max(floor, min(hard_cap, score))
    return max(0.0, min(1.0, score / 100.0))


def _is_structured_extraction_without_quote(log_source_profile: Dict[str, Any] | None) -> bool:
    profile = log_source_profile if isinstance(log_source_profile, dict) else {}
    return bool(profile.get("is_structured_extraction_log")) and not bool(profile.get("has_source_quote"))


def _score_judgment_agency(
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    step_profile: Dict[str, Any] | None = None,
    log_source_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    step_profile = step_profile if isinstance(step_profile, dict) else {}
    is_structured_extraction = _is_structured_extraction_without_quote(log_source_profile)
    human_decision_ratio = _measure_human_decision_ratio(structured_steps)
    ai_delegation_ratio = _measure_ai_delegation_ratio(structured_steps)
    human_override_ratio = _measure_human_override_ratio(structured_steps)
    reason_linked_ratio = _measure_reason_linked_ratio(structured_steps)
    user_decision_ratio = float(step_profile.get("user_decision_ratio", 0.0) or 0.0)
    if is_structured_extraction:
        human_override_ratio *= 0.65
        reason_linked_ratio *= 0.70
        user_decision_ratio *= 0.85
    unresolved_judgment_count = _safe_int(step_profile.get("unresolved_judgment_count", 0))
    step_count = max(1, _safe_int(step_profile.get("step_count", len(structured_steps))))
    plus_points = 0.0
    minus_points = 0.0

    if human_decision_ratio >= 0.75:
        plus_points += 6.0
    elif human_decision_ratio >= 0.60:
        plus_points += 3.0
    else:
        minus_points += 10.0

    if reason_linked_ratio >= 0.60:
        plus_points += 5.0
    elif reason_linked_ratio < 0.35:
        minus_points += 10.0

    if human_override_ratio >= 0.25:
        plus_points += 4.0
    elif human_override_ratio <= 0.05:
        minus_points += 8.0

    if ai_delegation_ratio <= 0.10:
        plus_points += 4.0
    elif ai_delegation_ratio >= 0.35:
        minus_points += 12.0
    elif ai_delegation_ratio >= 0.20:
        minus_points += 6.0

    plus_points += human_decision_ratio * 4.0 + human_override_ratio * 3.0
    plus_points += user_decision_ratio * 3.0
    minus_points += max(0.0, 0.45 - reason_linked_ratio) * 14.0
    minus_points += ai_delegation_ratio * 6.0
    minus_points += min(10.0, (unresolved_judgment_count / step_count) * 12.0)

    hard_cap = 90.0
    if (
        human_decision_ratio >= 0.90
        and reason_linked_ratio >= 0.75
        and human_override_ratio >= 0.35
        and ai_delegation_ratio <= 0.05
        and user_decision_ratio >= 0.80
    ):
        hard_cap = 94.0
    if is_structured_extraction:
        hard_cap = min(hard_cap, 82.0)

    normalized = _normalized_from_hybrid(
        base_score=80.0,
        plus_points=plus_points,
        minus_points=minus_points,
        floor=8.0,
        hard_cap=hard_cap,
    )

    reasons: List[str] = []
    evidence: List[str] = []
    risk_flags: List[str] = []

    if human_decision_ratio >= 0.75:
        reasons.append("人が最終判断を握っている比率が高く、主導権が保たれています")
    elif human_decision_ratio >= 0.50:
        reasons.append("人判断は確認できますが、明示の濃淡があります")
    else:
        risk_flags.append("人判断の比率が低く、主導権が見えにくい状態です")

    if human_override_ratio >= 0.25:
        reasons.append("AI提案をそのまま通さず、選別や差し戻しが確認できます")
    elif human_override_ratio == 0:
        risk_flags.append("AI提案への選別痕跡が薄く、主体性評価が伸びにくい状態です")

    if reason_linked_ratio >= 0.55:
        reasons.append("判断理由も残っており、主体性が記録として裏づけられています")
    elif reason_linked_ratio < 0.30:
        risk_flags.append("判断理由の明示が少なく、主体性の根拠が弱い状態です")

    if ai_delegation_ratio >= 0.35:
        risk_flags.append("AI提案をそのまま採用したと読める箇所が一定数あります")
    if is_structured_extraction:
        risk_flags.append("整形済みログ中心のため、元発言引用がない判断理由は限定的に扱っています")

    for step in structured_steps:
        judgment = _safe_text(step.get("judgment", ""))
        adoption = _safe_text(step.get("adoption", ""))
        if judgment and len(evidence) < 3:
            evidence.append(judgment)
        if adoption and len(evidence) < 5:
            evidence.append(adoption)

    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _has_before_after_signal(text: str) -> bool:
    value = _safe_text(text)
    if not value:
        return False
    return bool(
        re.search(r"before\s*/\s*after", value, flags=re.IGNORECASE)
        or re.search(r"\bbefore\s*(?:and|&|,|、)\s*after\b", value, flags=re.IGNORECASE)
        or "ビフォーアフター" in value
        or "変更前後" in value
        or "変更前" in value
        or "変更後" in value
        or "→" in value
    )


def _measure_before_after_marker_ratio(structured_steps: List[Dict[str, Any]]) -> float:
    revision_steps = [
        step for step in structured_steps
        if isinstance(step, dict) and _safe_text(step.get("revision", ""))
    ]
    if not revision_steps:
        return 0.0
    matched = 0
    for step in revision_steps:
        before_after = step.get("before_after", {}) if isinstance(step.get("before_after", {}), dict) else {}
        if (
            (_safe_text(before_after.get("before", "")) and _safe_text(before_after.get("after", "")))
            or _has_before_after_signal(_safe_text(step.get("revision", "")))
            or _has_before_after_signal(_safe_text(step.get("reason", "")))
        ):
            matched += 1
    return matched / max(1, len(revision_steps))


def _score_judgment_process(
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    step_profile: Dict[str, Any] | None = None,
    log_source_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    step_profile = step_profile if isinstance(step_profile, dict) else {}
    is_structured_extraction = _is_structured_extraction_without_quote(log_source_profile)
    coverage = _measure_judgment_coverage(structured_steps)
    quality = _measure_judgment_quality(structured_steps)
    tradeoff_score = _measure_tradeoff_signal(structured_steps)
    comparison_depth = _measure_comparison_depth(structured_steps)
    reason_linked_ratio = _measure_reason_linked_ratio(structured_steps)
    step_count = len(structured_steps)
    before_after_ratio = float(step_profile.get("before_after_ratio", 0.0) or 0.0)
    before_after_ratio = max(before_after_ratio, _measure_before_after_marker_ratio(structured_steps))
    adoption_ratio = float(step_profile.get("adoption_ratio", 0.0) or 0.0)
    reason_density = float(step_profile.get("reason_density", 0.0) or 0.0)
    unresolved_judgment_count = _safe_int(step_profile.get("unresolved_judgment_count", 0))
    if is_structured_extraction:
        reason_linked_ratio *= 0.65
        before_after_ratio *= 0.55
        adoption_ratio *= 0.75
        reason_density *= 0.70

    plus_points = 0.0
    minus_points = 0.0

    plus_points += coverage * 7.0
    plus_points += quality * 6.0
    plus_points += tradeoff_score * 5.0
    plus_points += comparison_depth * 5.0

    if coverage >= 0.75:
        plus_points += 5.0
    elif coverage < 0.55:
        minus_points += 15.0

    if quality >= 0.70:
        plus_points += 6.0
    elif quality < 0.45:
        minus_points += 12.0

    if tradeoff_score >= 0.50:
        plus_points += 4.0
    elif tradeoff_score < 0.30:
        minus_points += 8.0

    if comparison_depth >= 0.55:
        plus_points += 4.0
    elif comparison_depth < 0.35:
        minus_points += 10.0

    if reason_linked_ratio >= 0.60:
        plus_points += 4.0
    elif reason_linked_ratio < 0.40:
        minus_points += 8.0

    if before_after_ratio >= 0.45:
        plus_points += 4.0
    if adoption_ratio >= 0.45:
        plus_points += 3.0
    if reason_density >= 0.55:
        plus_points += 3.0

    minus_points += min(12.0, (unresolved_judgment_count / max(1, step_count)) * 16.0)

    if step_count >= 8:
        plus_points += 3.0
    elif step_count <= 3:
        minus_points += 6.0

    hard_cap = 90.0
    if (
        coverage >= 0.90
        and quality >= 0.80
        and tradeoff_score >= 0.60
        and comparison_depth >= 0.65
        and reason_linked_ratio >= 0.70
        and before_after_ratio >= 0.50
        and adoption_ratio >= 0.50
    ):
        hard_cap = 94.0
    if is_structured_extraction:
        hard_cap = min(hard_cap, 82.0)

    normalized = _normalized_from_hybrid(
        base_score=80.0,
        plus_points=plus_points,
        minus_points=minus_points,
        floor=10.0,
        hard_cap=hard_cap,
    )

    reasons: List[str] = []
    evidence: List[str] = []
    risk_flags: List[str] = []

    if coverage >= 0.80:
        reasons.append("比較・採否・理由が揃っており、判断の流れを追えます")
    elif coverage >= 0.55:
        reasons.append("判断記録はありますが、比較や採否の密度にばらつきがあります")
    else:
        risk_flags.append("判断の流れを追うための記録が不足しています")

    if quality >= 0.70 and tradeoff_score >= 0.50:
        reasons.append("比較語・理由・逆接・採否明示があり、判断の筋が見えます")
    elif quality >= 0.45:
        reasons.append("理由は確認できますが、比較の筋をさらに明示できる余地があります")
    else:
        risk_flags.append("比較や採否を支える表現が少なく、質評価が伸びにくい状態です")

    if comparison_depth < 0.35:
        risk_flags.append("複数案比較や優先順位変更の記録が少なく、高得点化しにくい状態です")
    if is_structured_extraction:
        risk_flags.append("整形済みログ中心のため、変更前後や理由の補完情報は限定的に扱っています")

    for step in structured_steps:
        judgment = _safe_text(step.get("judgment", ""))
        reason = _safe_text(step.get("reason", ""))
        adoption = _safe_text(step.get("adoption", ""))
        if judgment and len(evidence) < 3:
            evidence.append(judgment)
        if adoption and len(evidence) < 4:
            evidence.append(adoption)
        if reason and len(evidence) < 5:
            evidence.append(reason)

    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _score_revision_process(
    structured_steps: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
    step_profile: Dict[str, Any] | None = None,
    log_source_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    step_profile = step_profile if isinstance(step_profile, dict) else {}
    is_structured_extraction = _is_structured_extraction_without_quote(log_source_profile)
    stage_info = _detect_revision_stage(structured_steps, revisions, structure_decisions)
    stage = stage_info["stage"]
    quality = _measure_revision_stage_quality(structured_steps, revisions, structure_decisions, stage_info)
    duplicate_ratio = _measure_duplicate_revision_ratio(revisions)
    revision_policy_signals = _extract_revision_policy_signals(structured_steps)
    before_after_ratio = float(step_profile.get("before_after_ratio", 0.0) or 0.0)
    if stage_info["revision_count"]:
        before_after_ratio = max(
            before_after_ratio,
            stage_info["before_after_count"] / max(1, stage_info["revision_count"]),
        )
    reason_density = float(step_profile.get("reason_density", 0.0) or 0.0)
    continuity_ratio = float(step_profile.get("continuity_ratio", 0.0) or 0.0)
    unresolved_judgment_count = _safe_int(step_profile.get("unresolved_judgment_count", 0))
    step_count = max(1, _safe_int(step_profile.get("step_count", len(structured_steps))))
    if is_structured_extraction:
        quality *= 0.82
        before_after_ratio *= 0.55
        reason_density *= 0.70

    stage_base = {
        0: 32.0,
        1: 46.0,
        2: 58.0,
        3: 70.0,
        4: 80.0,
        5: 88.0,
    }[stage]

    plus_points = quality * 12.0
    minus_points = 0.0
    if stage < 2:
        minus_points += 18.0
    if stage_info["reason_linked_count"] == 0:
        minus_points += 10.0
    if stage_info["before_after_count"] == 0:
        minus_points += 12.0
    if stage >= 3 and stage_info["judgment_linked_count"] == 0:
        minus_points += 6.0
    if stage >= 4 and stage_info["structure_support_count"] == 0:
        minus_points += 8.0
    if stage_info["revision_count"] <= 1:
        minus_points += 8.0
    minus_points += duplicate_ratio * 14.0
    if before_after_ratio < 0.35:
        minus_points += 8.0
    if reason_density < 0.45:
        minus_points += 8.0
    if continuity_ratio >= 0.50:
        plus_points += 3.0
    elif continuity_ratio < 0.25:
        minus_points += 5.0
    minus_points += min(8.0, (unresolved_judgment_count / step_count) * 10.0)

    hard_cap = 92.0 if stage >= 5 else 88.0
    if (
        stage >= 5
        and quality >= 0.80
        and duplicate_ratio < 0.20
        and stage_info["before_after_count"] >= 2
        and stage_info["reason_linked_count"] >= 2
        and reason_density >= 0.60
    ):
        hard_cap = 94.0
    if is_structured_extraction:
        hard_cap = min(hard_cap, 78.0)

    limited_floor = 6.0
    if revision_policy_signals and stage < 2:
        limited_floor = min(35.0, 20.0 + len(revision_policy_signals) * 4.0)

    normalized = _normalized_from_hybrid(
        base_score=stage_base,
        plus_points=plus_points,
        minus_points=minus_points,
        floor=limited_floor,
        hard_cap=hard_cap,
    )

    reasons: List[str] = []
    evidence: List[str] = []
    risk_flags: List[str] = []

    stage_labels = {
        0: "修正記録がほとんど確認できません",
        1: "単発修正はありますが、改善の段階性はまだ弱いです",
        2: "before / after を含む修正があり、変更点を追えます",
        3: "理由付き修正があり、意図を伴った改善になっています",
        4: "構造修正まで進んでおり、表層調整に留まっていません",
        5: "複数回修正・before/after・理由・構造修正・採否接続が揃い、判断連動の改善として成立しています",
    }

    if stage >= 1:
        reasons.append(stage_labels[stage])
    else:
        risk_flags.append(stage_labels[stage])

    if revision_policy_signals and stage < 2:
        reasons.append("削除・削減・戻しなどの修正方針判断は見られます")
        risk_flags.append("ただし、変更前後や段階的な修正履歴は不足しています")

    if stage_info["reason_linked_count"] == 0 and stage >= 2:
        risk_flags.append("修正は見えますが、理由の明示が不足しています")
    if stage_info["before_after_count"] == 0 and stage >= 1:
        risk_flags.append("変更前後の追跡が弱く、改善精度の判定が伸びにくい状態です")
    if is_structured_extraction:
        risk_flags.append("整形済みログ中心のため、変更前後や理由の補完情報は限定的に扱っています")

    for item in revisions:
        text = _safe_text(item.get("text", ""))
        if text and len(evidence) < 3:
            evidence.append(text)
        reason = _safe_text(item.get("reason", ""))
        if reason and len(evidence) < 5:
            evidence.append(reason)
    for text in revision_policy_signals:
        if text and len(evidence) < 5:
            evidence.append(text)

    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _score_output_logic(
    output_text: str,
    log_text: str,
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
    url_structure_detail: Dict[str, Any] = None,
    url_appeal_detail: Dict[str, Any] = None,
    visual_input_mode: Dict[str, Any] = None,
    step_profile: Dict[str, Any] | None = None,
    artifact_type: str = "landing_page",
    artifact_match: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    step_profile = step_profile if isinstance(step_profile, dict) else {}
    txt = _safe_text(output_text)
    if not txt:
        return _build_axis_result(
            0.0,
            ["アウトプットが入力されていないため評価できません。"],
            [],
            ["アウトプット不足"],
        )

    clean_txt = _remove_noise_lines(txt)
    visual_input_mode = _normalize_visual_input_mode(visual_input_mode or {}, clean_txt)
    if artifact_type != "landing_page" and not visual_input_mode.get("enabled"):
        return _score_general_document_logic(
            clean_txt,
            structured_steps,
            decisions,
            revisions,
            adoptions,
            structure_decisions,
            step_profile=step_profile,
            artifact_type=artifact_type,
            artifact_match=artifact_match,
        )

    coverage_info = _measure_output_requirement_coverage(clean_txt)
    h1_body_consistency = _measure_h1_body_consistency(_get_page_context(clean_txt))
    cta_structure_score = _measure_cta_structure_coherence(_get_page_context(clean_txt))
    fetch_score = _measure_page_fetch(clean_txt)
    qr_bonus = 0.08 if _extract_prefixed_bool(clean_txt, "QR_PRESENT:") else 0.0
    decision_reflection = _measure_decision_reflection(clean_txt, decisions, revisions, adoptions)
    structure_reflection = _measure_page_structure_reflection(clean_txt, structured_steps)
    has_high_quality_step_log = bool(step_profile.get("has_high_quality_step_log", False))
    step_quality_score = float(step_profile.get("step_quality_score", 0.0) or 0.0)
    unresolved_judgment_count = _safe_int(step_profile.get("unresolved_judgment_count", 0))
    step_count = max(1, _safe_int(step_profile.get("step_count", len(structured_steps))))

    plus_points = 0.0
    minus_points = 0.0
    plus_points += coverage_info["required_coverage"] * 16.0
    plus_points += coverage_info["bonus_coverage"] * 8.0
    plus_points += h1_body_consistency * 5.0
    plus_points += cta_structure_score * 5.0
    plus_points += decision_reflection * 8.0
    plus_points += structure_reflection * 8.0
    plus_points += qr_bonus * 25.0
    plus_points += fetch_score * 3.0

    missing_count = 4 - sum(
        [
            coverage_info["has_h1"],
            coverage_info["has_body"],
            coverage_info["has_cta"],
            coverage_info["has_sections"],
        ]
    )
    minus_points += missing_count * 9.0
    if decision_reflection < 0.35:
        minus_points += 12.0
    if structure_reflection < 0.30 and len(structured_steps) >= 4:
        minus_points += 10.0
    if h1_body_consistency < 0.35 and coverage_info["has_h1"] and coverage_info["has_body"]:
        minus_points += 8.0
    if cta_structure_score < 0.35 and coverage_info["has_cta"]:
        minus_points += 6.0
    if fetch_score <= 0.10 and not visual_input_mode:
        minus_points += 8.0
    minus_points += min(8.0, (unresolved_judgment_count / step_count) * 10.0)
    if has_high_quality_step_log and decision_reflection >= 0.45 and structure_reflection >= 0.45:
        plus_points += 5.0
    if step_quality_score >= 0.70 and decision_reflection >= 0.50:
        plus_points += 2.0
    elif has_high_quality_step_log and (decision_reflection < 0.35 or structure_reflection < 0.35):
        minus_points += 6.0

    normalized = _normalized_from_hybrid(
        base_score=80.0,
        plus_points=plus_points,
        minus_points=minus_points,
        floor=5.0,
        hard_cap=95.0,
    )
    visual_lp_signal = _measure_lp_visual_signal(log_text, clean_txt, visual_input_mode)

    if visual_input_mode.get("enabled"):
        visual_score = (
            visual_lp_signal["normalized"] * 0.45
            + visual_lp_signal["flow"] * 0.20
            + visual_lp_signal["cta"] * 0.15
            + visual_lp_signal["whitespace"] * 0.10
            + (1.0 - visual_lp_signal["dropoff_risk"]) * 0.10
        )
        visual_floor = _normalized_from_hybrid(
            base_score=55.0,
            plus_points=visual_score * 35.0,
            minus_points=max(0.0, visual_lp_signal["dropoff_risk"] - 0.45) * 20.0,
            floor=42.0,
            hard_cap=92.0,
        )
        normalized = max(normalized, visual_floor)

    if (
        coverage_info["required_coverage"] >= 0.98
        and coverage_info["bonus_coverage"] >= 0.92
        and h1_body_consistency >= 0.88
        and cta_structure_score >= 0.85
        and decision_reflection >= 0.78
        and structure_reflection >= 0.75
        and fetch_score >= 0.90
        and _extract_prefixed_bool(clean_txt, "QR_PRESENT:")
    ):
        normalized = max(normalized, 0.96)

    reasons: List[str] = []
    evidence: List[str] = []
    risk_flags: List[str] = []

    if coverage_info["has_h1"]:
        reasons.append("H1が取得されており、成果物の主訴求を確認できます")
    if coverage_info["has_body"]:
        reasons.append("BODY本文が取得されており、ページ内容を直接評価できます")
    if coverage_info["has_cta"]:
        reasons.append("CTA文言が取得されており、行動導線を成果物根拠として扱えます")
    if coverage_info["has_sections"]:
        reasons.append("SECTIONSからLPの構造順序を追えます")
    if h1_body_consistency >= 0.60:
        reasons.append("H1と本文の主題がつながっており、訴求の軸がぶれていません")
    if _extract_prefixed_bool(clean_txt, "QR_PRESENT:"):
        reasons.append("QR導線が取得されており、体験導線の構造も確認できます")
    if decision_reflection >= 0.60:
        reasons.append("ログ判断が成果物テキストに反映され、設計意図の接続が確認できます")
    if structure_reflection >= 0.55:
        reasons.append("構造判断がページ構成に反映されており、情報設計の再現性があります")

    if not coverage_info["has_h1"] and not visual_input_mode.get("enabled"):
        risk_flags.append("H1が取得できておらず、主訴求の確認が弱い状態です")
    if not coverage_info["has_body"] and not visual_input_mode.get("enabled"):
        risk_flags.append("本文取得が不足しており、成果物実体の評価が伸びにくい状態です")
    if not coverage_info["has_cta"] and not visual_input_mode.get("enabled"):
        risk_flags.append("CTA文言が不足しており、LP導線の評価が限定されます")
    if not coverage_info["has_sections"] and not visual_input_mode.get("enabled"):
        risk_flags.append("セクション構造が不足しており、情報設計の評価が限定されます")
    if decision_reflection < 0.40 and len(decisions) + len(revisions) + len(adoptions) >= 5:
        risk_flags.append("ログ判断に対する成果物反映が弱く、接続根拠の補強が必要です")
    if structure_reflection < 0.35 and len(structured_steps) >= 4:
        risk_flags.append("構造方針の反映率が低く、成果物論理性が伸びにくい状態です")
    if has_high_quality_step_log and (decision_reflection < 0.40 or structure_reflection < 0.40):
        risk_flags.append("高品質Stepログに対し成果物反映が追いついておらず、減点対象になっています")

    if visual_input_mode.get("enabled"):
        reasons.append("画像・スクショを成果物本体として統合し、構成の完成度を評価しています")
        if visual_lp_signal["hero"] >= 0.60:
            reasons.append("Hero訴求が明確で、最初の視線停止点が設計されています")
        if visual_lp_signal["flow"] >= 0.60:
            reasons.append("Hero→課題提起→信頼提示→CTAの情報導線が自然です")
        if visual_lp_signal["cta"] >= 0.55:
            reasons.append("CTA配置が確認でき、行動転換の導線を確保しています")
        if visual_lp_signal["whitespace"] >= 0.55:
            reasons.append("余白バランスが整い、スマホ閲覧でも読みやすさを保てています")
        if visual_lp_signal["info_density"] <= 0.62:
            reasons.append("情報密度が過密すぎず、CTA到達までの負荷を抑えています")
        if visual_lp_signal["flow"] < 0.45:
            risk_flags.append("スクショ全体での情報導線が弱く、中盤の離脱リスクが残ります")
        if visual_lp_signal["trust"] < 0.40:
            risk_flags.append("信頼要素の配置根拠が薄く、訴求の裏付け強化余地があります")
        if visual_lp_signal["cta"] < 0.45:
            risk_flags.append("CTAの視認性が弱く、申込み導線で迷うリスクがあります")
        if visual_lp_signal["dropoff_risk"] >= 0.55:
            risk_flags.append("離脱リスクが高く、ファーストビューか中盤導線の再配置が必要です")

    evidence.extend(_extract_output_evidence_priority(clean_txt, prefer_artifact_context=False))
    if visual_input_mode.get("enabled"):
        image_files = visual_input_mode.get("image_files", []) or []
        if image_files:
            evidence.insert(0, f"画像成果物: 全{visual_input_mode.get('image_count', len(image_files))}枚")
            evidence.append(f"画像一覧: {' / '.join(image_files)}")
        evidence.append(f"画像枚数: {visual_input_mode.get('image_count', 0)}")
        if visual_lp_signal.get("flow_stages"):
            evidence.append(f"LPステージ: {' / '.join(visual_lp_signal['flow_stages'][:5])}")
        if visual_lp_signal.get("cta_positions"):
            evidence.append(f"CTA位置: {' / '.join(visual_lp_signal['cta_positions'][:4])}")

    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _score_general_document_logic(
    output_text: str,
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
    *,
    step_profile: Dict[str, Any],
    artifact_type: str,
    artifact_match: Dict[str, Any] | None,
) -> Dict[str, Any]:
    features = _measure_general_document_features(output_text)
    decision_reflection = _measure_general_decision_reflection(
        output_text,
        decisions,
        revisions,
        adoptions,
    )
    structure_reflection = _measure_general_structure_reflection(
        output_text,
        structure_decisions,
    )
    artifact_match = artifact_match if isinstance(artifact_match, dict) else {}
    if artifact_match.get("status") in {"exact", "normalized", "partial"}:
        decision_reflection = (
            decision_reflection * 0.80
            + float(artifact_match.get("ratio", 0.0) or 0.0) * 0.20
        )

    required_coverage = sum([
        features["has_title"],
        features["has_purpose"],
        features["has_headings"],
        features["has_conclusion"],
    ]) / 4.0
    bonus_coverage = sum([
        features["has_selection"],
        features["has_rejection"],
        features["has_revision"],
        features["has_implementation_order"],
        features["has_acceptance_criteria"],
        features["has_reasoning"],
    ]) / 6.0
    title_consistency = features["title_consistency"]
    sequence_score = features["sequence_score"]
    unresolved_judgment_count = _safe_int(step_profile.get("unresolved_judgment_count", 0))
    step_count = max(1, _safe_int(step_profile.get("step_count", len(structured_steps))))
    has_high_quality_step_log = bool(step_profile.get("has_high_quality_step_log", False))
    step_quality_score = float(step_profile.get("step_quality_score", 0.0) or 0.0)

    plus_points = 0.0
    minus_points = 0.0
    # Reuse the established Output Logic weighting. Only the evidence adapter
    # changes from LP fields to document fields.
    plus_points += required_coverage * 16.0
    plus_points += bonus_coverage * 8.0
    plus_points += title_consistency * 5.0
    plus_points += sequence_score * 5.0
    plus_points += decision_reflection * 8.0
    plus_points += structure_reflection * 8.0

    missing_count = 4 - sum([
        features["has_title"],
        features["has_purpose"],
        features["has_headings"],
        features["has_conclusion"],
    ])
    minus_points += missing_count * 9.0
    if decision_reflection < 0.35:
        minus_points += 12.0
    if structure_reflection < 0.30 and len(structured_steps) >= 4:
        minus_points += 10.0
    if title_consistency < 0.25 and features["has_title"]:
        minus_points += 8.0
    if sequence_score < 0.35 and features["heading_count"] >= 3:
        minus_points += 6.0
    minus_points += min(8.0, (unresolved_judgment_count / step_count) * 10.0)
    if has_high_quality_step_log and decision_reflection >= 0.45 and structure_reflection >= 0.45:
        plus_points += 5.0
    if step_quality_score >= 0.70 and decision_reflection >= 0.50:
        plus_points += 2.0
    elif has_high_quality_step_log and (decision_reflection < 0.35 or structure_reflection < 0.35):
        minus_points += 6.0

    normalized = _normalized_from_hybrid(
        base_score=80.0,
        plus_points=plus_points,
        minus_points=minus_points,
        floor=5.0,
        hard_cap=95.0,
    )

    reasons: List[str] = []
    risk_flags: List[str] = []
    if features["has_title"]:
        reasons.append("成果物のタイトルが明示され、文書の主題を確認できます")
    if features["has_purpose"]:
        reasons.append("目的が明示され、後続セクションの判断基準につながっています")
    if features["has_headings"]:
        reasons.append("見出し・番号構造があり、情報の階層と順序を追えます")
    if features["has_selection"] and features["has_rejection"]:
        reasons.append("採用内容と不採用案が区別され、選択理由を追跡できます")
    if features["has_implementation_order"] and features["has_acceptance_criteria"]:
        reasons.append("実装順と受入条件が示され、実行可能性を確認できます")
    if decision_reflection >= 0.60:
        reasons.append("ログ上の判断・修正が成果物本文へ反映されています")
    if structure_reflection >= 0.55:
        reasons.append("構造判断が文書の見出しやセクションへ反映されています")

    if not features["has_title"]:
        risk_flags.append("明確なタイトルを確認できません")
    if not features["has_purpose"]:
        risk_flags.append("目的の明示が弱く、判断基準を追いにくい状態です")
    if not features["has_headings"]:
        risk_flags.append("見出し・番号構造が不足し、文書構造を追いにくい状態です")
    if not features["has_conclusion"]:
        risk_flags.append("最終結論または推奨内容が明確ではありません")
    if decision_reflection < 0.40 and len(decisions) + len(revisions) + len(adoptions) >= 5:
        risk_flags.append("ログ判断と成果物本文の対応が弱い状態です")

    evidence = [f"成果物種別: {artifact_type}"]
    evidence.extend(_extract_output_evidence_priority(output_text, prefer_artifact_context=False))
    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _measure_general_document_features(text: str) -> Dict[str, Any]:
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    first_line = lines[0] if lines else ""
    has_title = bool(
        first_line
        and len(first_line) <= 180
        and not re.match(r"^(?:[-*•]|\d+[.)]\s)", first_line)
    )
    heading_count = _count_document_headings(text)
    has_headings = heading_count >= 2
    pattern_groups = {
        "has_purpose": [r"\b(?:objective|purpose|goal|scope)\b", r"目的", r"背景"],
        "has_selection": [r"\b(?:selected|selection|choose|chosen|adopt(?:ed|ion)?)\b", r"採用", r"選択"],
        "has_rejection": [r"\b(?:reject(?:ed|ion)?|not\s+adopted|discard(?:ed)?)\b", r"不採用", r"却下"],
        "has_revision": [r"\b(?:revision|revised|change(?:d|s)?|replace(?:d)?)\b", r"修正", r"変更", r"差し替え"],
        "has_implementation_order": [
            r"\b(?:implementation|execution)\s+(?:order|sequence|steps?)\b",
            r"\bphase\s+\d+\b", r"実装順", r"実行順", r"手順",
        ],
        "has_acceptance_criteria": [
            r"\bacceptance\s+criteria\b", r"\bvalidation\s+(?:rule|condition|criteria)\b",
            r"受入条件", r"検証条件",
        ],
        "has_conclusion": [r"\b(?:conclusion|final\s+recommendation|recommendation)\b", r"結論", r"最終方針", r"推奨"],
        "has_reasoning": [r"\b(?:because|reason|rationale|therefore|so that)\b", r"理由", r"根拠", r"ため"],
    }
    lowered = text.lower()
    flags = {
        name: any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns)
        for name, patterns in pattern_groups.items()
    }
    title_consistency = _measure_text_alignment(first_line, "\n".join(lines[1:])) if len(lines) > 1 else 0.0
    sequence_patterns = [
        pattern_groups["has_purpose"],
        pattern_groups["has_selection"] + pattern_groups["has_rejection"],
        pattern_groups["has_revision"],
        pattern_groups["has_implementation_order"],
        pattern_groups["has_acceptance_criteria"],
        pattern_groups["has_conclusion"],
    ]
    positions = []
    for patterns in sequence_patterns:
        matches = [
            match.start()
            for pattern in patterns
            for match in [re.search(pattern, lowered, flags=re.IGNORECASE)]
            if match
        ]
        if matches:
            positions.append(min(matches))
    if len(positions) < 2:
        sequence_score = 0.0
    else:
        ordered_pairs = sum(1 for left, right in zip(positions, positions[1:]) if left < right)
        sequence_score = ordered_pairs / max(1, len(positions) - 1)
    return {
        "has_title": has_title,
        "has_headings": has_headings,
        "heading_count": heading_count,
        "title_consistency": title_consistency,
        "sequence_score": sequence_score,
        **flags,
    }


def _measure_general_decision_reflection(
    output_text: str,
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
) -> float:
    return _measure_evidence_reflection(
        output_text,
        decisions + revisions + adoptions,
    )


def _measure_general_structure_reflection(
    output_text: str,
    structure_decisions: List[Dict[str, Any]],
) -> float:
    return _measure_evidence_reflection(output_text, structure_decisions)


def _measure_evidence_reflection(
    output_text: str,
    evidence_items: List[Dict[str, Any]],
) -> float:
    output_keywords = set(_extract_meaningful_match_keywords(output_text))
    if not output_keywords:
        return 0.0
    reflected = 0
    total = 0
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        text = _safe_text(item.get("text", ""))
        keywords = set(_extract_meaningful_match_keywords(text))
        if not keywords:
            continue
        total += 1
        overlap = keywords & output_keywords
        if len(overlap) >= 2 or len(overlap) / max(1, len(keywords)) >= 0.20:
            reflected += 1
    return reflected / total if total else 0.0


def _score_overall_consistency(
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
    output_text: str,
    log_text: str,
    url_structure_detail: Dict[str, Any] = None,
    url_appeal_detail: Dict[str, Any] = None,
    visual_input_mode: Dict[str, Any] = None,
    step_profile: Dict[str, Any] | None = None,
    artifact_type: str = "landing_page",
    artifact_match: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    step_profile = step_profile if isinstance(step_profile, dict) else {}
    clean_output = _remove_noise_lines(output_text)
    match_info = _measure_log_output_match_rate(
        structured_steps,
        clean_output,
        artifact_type=artifact_type,
    )
    artifact_match = artifact_match if isinstance(artifact_match, dict) else {}
    if artifact_type != "landing_page" and artifact_match.get("status") in {"exact", "normalized", "partial"}:
        match_info["match_rate"] = (
            float(match_info.get("match_rate", 0.0) or 0.0) * 0.75
            + float(artifact_match.get("ratio", 0.0) or 0.0) * 0.25
        )
    target_count = len(match_info["matched_topics"]) + len(match_info["unmatched_topics"])
    unmatched_ratio = len(match_info["unmatched_topics"]) / max(1, target_count)
    page_fetch_score = _measure_page_fetch(clean_output)
    page_evaluation_ready = _extract_prefixed_line(clean_output, "PAGE_EVALUATION_READY:").strip().lower() == "yes"
    has_url_context = (
        "SOURCE_URL:" in clean_output
        or "対象URL:" in clean_output
        or "http://" in clean_output
        or "https://" in clean_output
    )
    extracted_text_chars = _extract_prefixed_int(clean_output, "EXTRACTED_TEXT_CHARS:")
    partial_fetch = bool(0 < extracted_text_chars < 700)
    fetch_limited = bool(
        has_url_context
        and not page_evaluation_ready
        and (_has_url_fetch_failure(clean_output) or page_fetch_score < 0.50 or partial_fetch)
    )
    unresolved_judgment_count = _safe_int(step_profile.get("unresolved_judgment_count", 0))
    step_count = max(1, _safe_int(step_profile.get("step_count", len(structured_steps))))
    has_high_quality_step_log = bool(step_profile.get("has_high_quality_step_log", False))
    step_quality_score = float(step_profile.get("step_quality_score", 0.0) or 0.0)

    plus_points = 0.0
    minus_points = 0.0
    plus_points += match_info["match_rate"] * 18.0
    if page_evaluation_ready and page_fetch_score >= 0.60:
        plus_points += 5.0
    if fetch_limited:
        # URL/本文取得が弱い場合、未反映ではなく照合不能として扱う。
        # ログ側の品質まで過剰に落とさないため、match_rate由来の強い減点は避ける。
        plus_points += 2.0 if has_high_quality_step_log else 0.0
    elif match_info["match_rate"] >= 0.75:
        plus_points += 6.0
    elif match_info["match_rate"] < 0.50:
        minus_points += 14.0
    elif match_info["match_rate"] < 0.65:
        minus_points += 8.0

    if fetch_limited:
        pass
    elif target_count >= 4 and unmatched_ratio >= 0.40:
        minus_points += 14.0
    elif target_count >= 3 and unmatched_ratio >= 0.25:
        minus_points += 8.0

    minus_points += match_info["conflict_penalty"] * 60.0
    if match_info["conflict_topics"]:
        minus_points += min(8.0, len(match_info["conflict_topics"]) * 3.0)
    minus_points += min(10.0, (unresolved_judgment_count / step_count) * 12.0)
    if has_high_quality_step_log and unmatched_ratio >= 0.30 and not fetch_limited:
        minus_points += 6.0
    if has_high_quality_step_log and match_info["match_rate"] >= 0.65 and unmatched_ratio <= 0.25:
        plus_points += 3.0
    if step_quality_score >= 0.72 and match_info["match_rate"] >= 0.60:
        plus_points += 2.0
    if has_high_quality_step_log and target_count >= 5:
        plus_points += 1.0

    hard_cap = 95.0
    if fetch_limited:
        hard_cap = min(hard_cap, 76.0)
    elif page_evaluation_ready and page_fetch_score >= 0.60:
        if target_count >= 4 and match_info["match_rate"] < 0.50:
            hard_cap = min(hard_cap, 82.0)
        elif target_count >= 4 and match_info["match_rate"] < 0.65:
            hard_cap = min(hard_cap, 86.0)
    elif target_count >= 4:
        if match_info["match_rate"] < 0.50:
            hard_cap = min(hard_cap, 66.0)
        elif match_info["match_rate"] < 0.65:
            hard_cap = min(hard_cap, 74.0)
        elif match_info["match_rate"] < 0.80:
            hard_cap = min(hard_cap, 84.0)
    if target_count >= 3 and unmatched_ratio >= 0.40 and not fetch_limited:
        hard_cap = min(hard_cap, 78.0)
    if has_high_quality_step_log and unmatched_ratio >= 0.30 and not fetch_limited:
        hard_cap = min(hard_cap, 82.0)

    normalized = _normalized_from_hybrid(
        base_score=80.0,
        plus_points=plus_points,
        minus_points=minus_points,
        floor=6.0,
        hard_cap=hard_cap,
    )
    if fetch_limited and (has_high_quality_step_log or len(structure_decisions) >= 2):
        normalized = max(normalized, 0.70)
    if page_evaluation_ready and page_fetch_score >= 0.60 and (has_high_quality_step_log or len(structure_decisions) >= 2):
        normalized = max(normalized, 0.72)
    visual_input_mode = _normalize_visual_input_mode(visual_input_mode or {}, clean_output)
    visual_lp_signal = _measure_lp_visual_signal(log_text, clean_output, visual_input_mode)

    reasons: List[str] = []
    evidence: List[str] = []
    risk_flags: List[str] = []

    if match_info["matched_topics"]:
        reasons.append("ログで決めた内容が成果物に反映されています")
    if artifact_type != "landing_page" and artifact_match.get("status") == "exact":
        reasons.append("ログで最終承認された成果物と提出成果物が完全一致しています")
    elif artifact_type != "landing_page" and artifact_match.get("status") == "normalized":
        reasons.append("ログで最終承認された成果物と提出成果物が空白正規化後に一致しています")
    elif artifact_type != "landing_page" and artifact_match.get("status") == "partial":
        reasons.append("ログ上の最終成果物が提出成果物へ部分的に反映されています")
    if "hero_primary" in match_info["matched_topics"] or "hero_follow" in match_info["matched_topics"]:
        reasons.append("HEROまわりの判断がH1や本文に反映されています")
    if "cta" in match_info["matched_topics"]:
        reasons.append("CTA判断がボタン文言や導線に反映されています")
    if "qr" in match_info["matched_topics"]:
        reasons.append("QR導線の判断が成果物に残っています")
    if (
        "classification_structure" in match_info["matched_topics"]
        or "classification_title" in match_info["matched_topics"]
        or "classification_label" in match_info["matched_topics"]
        or "classification_copy" in match_info["matched_topics"]
    ):
        reasons.append("分類構造の判断がページ構成に反映されています")
    if "visual_style" in match_info["matched_topics"]:
        reasons.append("ミニマル設計の判断が成果物の見せ方に反映されています")

    if page_evaluation_ready:
        reasons.append("URL取得したページ本文、見出し、行動導線を成果物として照合しています")
    if fetch_limited:
        risk_flags.append("URLまたは本文取得が不完全なため、成果物反映の照合は暫定評価です")
    elif match_info["match_rate"] >= 0.75:
        reasons.append("反映可能な判断の大半が成果物側で確認できます")
    elif match_info["match_rate"] >= 0.50:
        reasons.append("主要判断は反映されていますが、一部はつながりが弱いです")
    else:
        risk_flags.append("ログ判断と成果物の一致率がまだ低い状態です")

    if match_info["unmatched_topics"] and not fetch_limited:
        risk_flags.append(f"未反映の判断があります: {', '.join(match_info['unmatched_topics'][:3])}")
    if artifact_type != "landing_page" and artifact_match.get("status") == "mismatch":
        risk_flags.append("ログで最終承認された成果物と提出成果物が一致していません")
    if match_info["conflict_topics"]:
        risk_flags.append(f"判断と逆向きに見える箇所があります: {', '.join(match_info['conflict_topics'][:3])}")

    if visual_input_mode.get("enabled"):
        topic_reflection = len(match_info["matched_topics"]) / max(1, target_count)
        screenshot_continuity = min(1.0, float(visual_input_mode.get("image_count", 0)) / 3.0)
        log_density = min(1.0, len(structured_steps) / 18.0)
        visual_match = (
            topic_reflection * 0.40
            + visual_lp_signal["normalized"] * 0.35
            + screenshot_continuity * 0.15
            + log_density * 0.10
        )
        visual_floor = _normalized_from_hybrid(
            base_score=56.0,
            plus_points=visual_match * 34.0,
            minus_points=max(0.0, 0.45 - topic_reflection) * 20.0 + visual_lp_signal["dropoff_risk"] * 6.0,
            floor=45.0,
            hard_cap=90.0,
        )
        normalized = max(normalized, visual_floor)

        reasons.append("画像・スクショ全体を成果物本体として扱い、ログ判断との反映整合を評価しています")
        if visual_lp_signal["whitespace"] >= 0.55:
            reasons.append("余白と情報密度のバランスが保たれ、ページ全体のトーンが安定しています")
        if topic_reflection >= 0.55:
            reasons.append("主要判断の反映率が高く、構成方針が途中でぶれていません")
        if topic_reflection < 0.40:
            risk_flags.append("主要判断の反映率が低く、スクショ間の接続根拠が不足しています")
        if visual_lp_signal["dropoff_risk"] >= 0.55:
            risk_flags.append("離脱リスクが高く、スクショ接続の導線補強が必要です")
        if visual_lp_signal["trust"] < 0.40:
            risk_flags.append("信頼導線が弱く、終盤CTAでの転換率低下が懸念されます")

    if target_count >= 3 and unmatched_ratio >= 0.35 and not fetch_limited:
        risk_flags.append("未反映判断の比率が高く、全体整合性の上振れを抑制しています")

    evidence.extend(match_info["evidence"][:5])
    if visual_input_mode.get("enabled"):
        image_files = visual_input_mode.get("image_files", []) or []
        if image_files:
            evidence.insert(0, f"画像成果物: 全{visual_input_mode.get('image_count', len(image_files))}枚")
            evidence.append(f"画像一覧: {' / '.join(image_files)}")
        evidence.append(f"画像統合評価: {visual_input_mode.get('image_count', 0)}枚")

    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _normalize_visual_input_mode(visual_input_mode: Any, output_text: str) -> Dict[str, Any]:
    source = visual_input_mode if isinstance(visual_input_mode, dict) else {}
    text = _safe_text(output_text)

    explicit_count = _safe_int(source.get("image_count", 0))
    marker_count = _extract_prefixed_int(text, "SCREENSHOT_COUNT:")
    marker_mode = _extract_prefixed_line(text, "VISUAL_MODE:").strip().lower()

    file_names = source.get("image_files", []) if isinstance(source.get("image_files", []), list) else []
    if not file_names:
        marker_files = _extract_prefixed_line(text, "SCREENSHOT_FILES:")
        if marker_files:
            file_names = [part.strip() for part in marker_files.split("/") if part.strip()]

    if marker_count <= 0:
        marker_count = len([
            line for line in text.splitlines()
            if re.search(r"^-\s+.*\.(png|jpg|jpeg|webp|bmp|gif)\s*$", line, re.IGNORECASE)
            or ("スクショ_" in line and line.strip().startswith("-"))
        ])

    image_count = max(explicit_count, marker_count, len(file_names))
    marker_enabled = marker_mode in {"lp_ui_screenshot", "web_lp_screenshot", "artifact_image_set"}
    enabled = bool(source.get("enabled")) or marker_enabled or image_count >= 1
    mode = _safe_text(source.get("mode", "")).strip().lower()
    if mode not in {"lp_ui_screenshot", "web_lp_screenshot", "artifact_image_set"}:
        mode = marker_mode if marker_mode in {"lp_ui_screenshot", "web_lp_screenshot", "artifact_image_set"} else ("artifact_image_set" if enabled else "default")

    return {
        "enabled": enabled,
        "mode": mode,
        "image_count": image_count,
        "image_files": [str(name).strip() for name in file_names if str(name).strip()],
    }


def _extract_lp_visual_metrics(text: str) -> Dict[str, Any]:
    txt = _safe_text(text)
    if not txt:
        return {"enabled": False}

    hero = _extract_prefixed_float(txt, "LP_HERO_SCORE:")
    cta = _extract_prefixed_float(txt, "LP_CTA_SCORE:")
    flow = _extract_prefixed_float(txt, "LP_FLOW_SCORE:")
    trust = _extract_prefixed_float(txt, "LP_TRUST_SCORE:")
    whitespace = _extract_prefixed_float(txt, "LP_WHITESPACE_SCORE:")
    info_density = _extract_prefixed_float(txt, "LP_INFO_DENSITY:")
    info_density_score = _extract_prefixed_float(txt, "LP_INFO_DENSITY_SCORE:")
    mobile = _extract_prefixed_float(txt, "LP_MOBILE_SCORE:")
    dropoff = _extract_prefixed_float(txt, "LP_DROPOFF_RISK:")
    overall = _extract_prefixed_float(txt, "LP_OVERALL_SCORE:")

    has_marker = any([
        "LP_HERO_SCORE:" in txt,
        "LP_CTA_SCORE:" in txt,
        "LP_FLOW_SCORE:" in txt,
        "LP_TRUST_SCORE:" in txt,
        "LP_WHITESPACE_SCORE:" in txt,
    ])
    if not has_marker:
        return {"enabled": False}

    if overall <= 0:
        overall = max(0.0, min(
            1.0,
            hero * 0.20
            + cta * 0.22
            + flow * 0.23
            + trust * 0.14
            + whitespace * 0.09
            + info_density_score * 0.12,
        ))

    return {
        "enabled": True,
        "hero": max(0.0, min(1.0, hero)),
        "cta": max(0.0, min(1.0, cta)),
        "flow": max(0.0, min(1.0, flow)),
        "trust": max(0.0, min(1.0, trust)),
        "whitespace": max(0.0, min(1.0, whitespace)),
        "info_density": max(0.0, min(1.0, info_density)),
        "info_density_score": max(0.0, min(1.0, info_density_score)),
        "mobile": max(0.0, min(1.0, mobile)),
        "dropoff_risk": max(0.0, min(1.0, dropoff)),
        "overall": max(0.0, min(1.0, overall)),
        "flow_stages": _extract_prefixed_segments(txt, "LP_FLOW_STAGES:"),
        "cta_positions": _extract_prefixed_segments(txt, "LP_CTA_POSITIONS:"),
        "ocr_engine": _extract_prefixed_line(txt, "LP_OCR_ENGINE:"),
        "ocr_blocks": _extract_prefixed_int(txt, "LP_OCR_BLOCK_COUNT:"),
    }


def _measure_lp_visual_signal(log_text: str, output_text: str, visual_input_mode: Dict[str, Any]) -> Dict[str, float]:
    lp_metrics = _extract_lp_visual_metrics(output_text)
    if lp_metrics.get("enabled"):
        return {
            "normalized": lp_metrics.get("overall", 0.0),
            "hero": lp_metrics.get("hero", 0.0),
            "cta": lp_metrics.get("cta", 0.0),
            "flow": lp_metrics.get("flow", 0.0),
            "trust": lp_metrics.get("trust", 0.0),
            "unity": lp_metrics.get("whitespace", 0.0),
            "whitespace": lp_metrics.get("whitespace", 0.0),
            "info_density": lp_metrics.get("info_density", 0.0),
            "mobile": lp_metrics.get("mobile", 0.0),
            "dropoff_risk": lp_metrics.get("dropoff_risk", 0.0),
            "flow_stages": lp_metrics.get("flow_stages", []),
            "cta_positions": lp_metrics.get("cta_positions", []),
        }

    merged = f"{_safe_text(log_text)}\n{_safe_text(output_text)}"
    hero_score = _keyword_coverage(merged, ["HERO", "Hero", "問い", "冒頭", "主訴求", "証明できますか"], full_hit_count=3)
    cta_score = _keyword_coverage(merged, ["CTA", "確認する", "無料", "申し込み", "行動導線", "ボタン"], full_hit_count=3)
    flow_score = _keyword_coverage(merged, ["導線", "流れ", "順番", "構成", "課題提起", "解決", "分類"], full_hit_count=4)
    trust_score = _keyword_coverage(merged, ["信頼", "実績", "問い合わせ", "利用規約", "プライバシー", "運営"], full_hit_count=3)
    unity_score = _keyword_coverage(merged, ["統一", "一貫", "余白", "ミニマル", "静けさ", "世界観"], full_hit_count=3)
    whitespace_score = _keyword_coverage(merged, ["余白", "視線", "密度", "詰め込み", "レイアウト"], full_hit_count=3)

    screenshot_bonus = min(1.0, float(_safe_int(visual_input_mode.get("image_count", 0))) / 4.0)
    normalized = (
        hero_score * 0.20
        + cta_score * 0.18
        + flow_score * 0.24
        + trust_score * 0.14
        + unity_score * 0.16
        + whitespace_score * 0.08
    )
    normalized = min(1.0, normalized + screenshot_bonus * 0.08)

    return {
        "normalized": normalized,
        "hero": hero_score,
        "cta": cta_score,
        "flow": flow_score,
        "trust": trust_score,
        "unity": unity_score,
        "whitespace": whitespace_score,
        "info_density": max(0.0, min(1.0, 1.0 - abs(whitespace_score - 0.55))),
        "mobile": max(0.0, min(1.0, (flow_score * 0.55 + whitespace_score * 0.45))),
        "dropoff_risk": max(0.0, min(1.0, 0.55 * (1.0 - flow_score) + 0.45 * (1.0 - cta_score))),
        "flow_stages": [],
        "cta_positions": [],
    }


def _detect_revision_stage(
    structured_steps: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
) -> Dict[str, Any]:
    revision_count = len([r for r in revisions if _safe_text(r.get("text", ""))])
    reason_linked_count = len([
        step for step in structured_steps
        if _safe_text(step.get("revision", "")) and _safe_text(step.get("reason", ""))
    ])
    before_after_count = 0
    for revision in revisions:
        before_after = revision.get("before_after", {}) or {}
        before_text = _safe_text(before_after.get("before", "")) if isinstance(before_after, dict) else ""
        after_text = _safe_text(before_after.get("after", "")) if isinstance(before_after, dict) else ""
        revision_text = _safe_text(revision.get("text", ""))
        if (
            (before_text and after_text)
            or _has_before_after_signal(revision_text)
        ):
            before_after_count += 1
    structure_support_count = len([s for s in structure_decisions if _safe_text(s.get("text", ""))])
    judgment_linked_count = len([
        step for step in structured_steps
        if _safe_text(step.get("judgment", "")) and _safe_text(step.get("revision", ""))
    ])
    adoption_linked_count = len([
        step for step in structured_steps
        if _safe_text(step.get("revision", "")) and _safe_text(step.get("adoption", ""))
    ])

    stage = 0
    if revision_count >= 1:
        stage = 1
    if revision_count >= 1 and before_after_count >= 1:
        stage = 2
    if revision_count >= 1 and before_after_count >= 1 and reason_linked_count >= 1:
        stage = 3
    if revision_count >= 2 and before_after_count >= 1 and reason_linked_count >= 1 and structure_support_count >= 1:
        stage = 4
    if revision_count >= 2 and before_after_count >= 2 and reason_linked_count >= 1 and structure_support_count >= 1 and adoption_linked_count >= 1:
        stage = 5

    return {
        "stage": stage,
        "revision_count": revision_count,
        "reason_linked_count": reason_linked_count,
        "before_after_count": before_after_count,
        "structure_support_count": structure_support_count,
        "judgment_linked_count": judgment_linked_count,
        "adoption_linked_count": adoption_linked_count,
    }


def _measure_revision_stage_quality(
    structured_steps: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
    stage_info: Dict[str, Any],
) -> float:
    revision_count = stage_info.get("revision_count", 0)
    reason_linked_count = stage_info.get("reason_linked_count", 0)
    before_after_count = stage_info.get("before_after_count", 0)
    structure_support_count = stage_info.get("structure_support_count", 0)
    judgment_linked_count = stage_info.get("judgment_linked_count", 0)
    adoption_linked_count = stage_info.get("adoption_linked_count", 0)
    if revision_count <= 0:
        return 0.0
    revision_depth = min(1.0, revision_count / 6.0)
    before_after_strength = min(1.0, before_after_count / max(1.0, revision_count))
    reason_strength = min(1.0, reason_linked_count / max(1.0, revision_count))
    structure_strength = min(1.0, structure_support_count / max(1.0, revision_count))
    judgment_strength = min(1.0, judgment_linked_count / max(1.0, revision_count))
    adoption_strength = min(1.0, adoption_linked_count / max(1.0, revision_count))

    quality = (
        revision_depth * 0.22
        + before_after_strength * 0.24
        + reason_strength * 0.24
        + structure_strength * 0.14
        + judgment_strength * 0.08
        + adoption_strength * 0.08
    )
    return max(0.0, min(1.0, quality))


def _extract_revision_policy_signals(structured_steps: List[Dict[str, Any]]) -> List[str]:
    signals: List[str] = []
    patterns = [
        r"修正|変更|戻す|元に戻す|戻そう|直す|調整|差し替え|簡素化",
        r"削除|追加|外す|削る|減らす|少なくする|増やす",
        r"いらん|いらない|不要|使わない|やめる|多すぎる",
        r"保存.*(?:いらん|不要|やめる|変更|方式)",
        r"(?:重要ログ|ログ).*(?:いらん|不要|多すぎ|減らす|少なく)",
    ]

    for step in structured_steps:
        if not isinstance(step, dict):
            continue
        fields = _dedupe([
            _safe_text(step.get("revision", "")),
            _safe_text(step.get("adoption", "")),
            _safe_text(step.get("judgment", "")),
        ])
        combined = "\n".join(fields).strip()
        if not combined:
            continue
        if any(re.search(pattern, combined) for pattern in patterns):
            signals.append(combined)

    return _dedupe(signals)[:5]


def _measure_duplicate_revision_ratio(revisions: List[Dict[str, Any]]) -> float:
    cleaned: List[str] = []
    for revision in revisions:
        text = _safe_text(revision.get("text", "")) if isinstance(revision, dict) else ""
        if not text:
            continue
        normalized = re.sub(r"\s+", "", text).lower()
        if normalized:
            cleaned.append(normalized)
    if len(cleaned) <= 1:
        return 0.0
    counts: Dict[str, int] = {}
    for item in cleaned:
        counts[item] = counts.get(item, 0) + 1
    duplicate_count = sum(max(0, count - 1) for count in counts.values())
    return max(0.0, min(1.0, duplicate_count / max(1, len(cleaned))))


def _measure_human_decision_ratio(structured_steps: List[Dict[str, Any]]) -> float:
    total = max(1, len(structured_steps))
    human_marked = len([
        step for step in structured_steps
        if _safe_text(step.get("judgment", "")) or _safe_text(step.get("adoption", "")) or _safe_text(step.get("reason", ""))
    ])
    return min(1.0, human_marked / total)


def _measure_ai_delegation_ratio(structured_steps: List[Dict[str, Any]]) -> float:
    total = max(1, len(structured_steps))
    ai_delegate_count = 0
    for step in structured_steps:
        combined = "\n".join([
            _safe_text(step.get("judgment", "")),
            _safe_text(step.get("revision", "")),
            _safe_text(step.get("adoption", "")),
            _safe_text(step.get("reason", "")),
        ])
        if re.search(r"(AI案そのまま|そのまま採用|AI任せ|任せる|丸投げ|そのままでいい)", combined):
            ai_delegate_count += 1
    return min(1.0, ai_delegate_count / total)


def _measure_human_override_ratio(structured_steps: List[Dict[str, Any]]) -> float:
    total = max(1, len(structured_steps))
    override_count = 0
    for step in structured_steps:
        combined = "\n".join([
            _safe_text(step.get("judgment", "")),
            _safe_text(step.get("revision", "")),
            _safe_text(step.get("adoption", "")),
        ])
        if re.search(
            r"(却下|不採用|違う|こっち|このまま|そのまま|維持|残す|削除|別表現|変更|"
            r"いらん|いらない|不要|使わない|意味(?:が)?ない|仕方ない|多すぎる|減らす|削る|戻す|元に戻す|戻そう)",
            combined,
        ):
            override_count += 1
    return min(1.0, override_count / total)


def _measure_reason_linked_ratio(structured_steps: List[Dict[str, Any]]) -> float:
    total = max(1, len(structured_steps))
    linked = len([
        step for step in structured_steps
        if (_safe_text(step.get("judgment", "")) or _safe_text(step.get("adoption", "")))
        and _safe_text(step.get("reason", ""))
    ])
    return min(1.0, linked / total)


def _measure_judgment_coverage(structured_steps: List[Dict[str, Any]]) -> float:
    if not structured_steps:
        return 0.0
    has_judgment = any(_safe_text(step.get("judgment", "")) for step in structured_steps)
    has_compare = any(_contains_any(_safe_text(step.get("judgment", "")), [r"比較", r"一方", r"より", r"ではなく", r"案"]) for step in structured_steps)
    has_adoption = any(_safe_text(step.get("adoption", "")) for step in structured_steps)
    has_reason = any(_safe_text(step.get("reason", "")) or _contains_any(_safe_text(step.get("judgment", "")), REASON_PATTERNS) for step in structured_steps)
    covered = sum([has_judgment, has_compare, has_adoption, has_reason])
    return covered / 4.0


def _measure_judgment_quality(structured_steps: List[Dict[str, Any]]) -> float:
    combined = "\n".join([
        "\n".join([
            _safe_text(step.get("judgment", "")),
            _safe_text(step.get("adoption", "")),
            _safe_text(step.get("reason", "")),
        ])
        for step in structured_steps
    ])
    combined = _remove_work_report_scoring_noise(combined)
    if not combined.strip():
        return 0.0

    comparison_score = _binary_or_weak_signal(
        combined,
        strong_pattern=r"(比較|一方|ではなく|より|案|こっち|違う)",
        weak_pattern=r"(そっち|した方がいい|の方がいい)",
    )
    reason_score = _binary_or_weak_signal(
        combined,
        strong_pattern=r"(理由|ため|ので|から|狙い|意図|目的)",
        weak_pattern=r"(仕方ない|意味がない|多すぎる|甘くして|厳しくして)",
    )
    contrast_score = _binary_or_weak_signal(
        combined,
        strong_pattern=r"(ただし|一方|でも|しかし|ではなく)",
        weak_pattern=r"(方向転換|変える|変更|戻す|切り替える)",
    )
    adoption_score = _binary_or_weak_signal(
        combined,
        strong_pattern=r"(採用|不採用|却下|維持|残す|削除|このまま|そのまま)",
        weak_pattern=r"(いらん|いらない|不要|使わない|やめる|削る|外す|これでいい|これでいく)",
    )
    return (comparison_score + reason_score + contrast_score + adoption_score) / 4.0


def _measure_tradeoff_signal(structured_steps: List[Dict[str, Any]]) -> float:
    combined = "\n".join([
        "\n".join([
            _safe_text(step.get("judgment", "")),
            _safe_text(step.get("adoption", "")),
            _safe_text(step.get("reason", "")),
        ])
        for step in structured_steps
    ])
    combined = _remove_work_report_scoring_noise(combined)
    if not combined.strip():
        return 0.0
    signal_count = 0
    if re.search(r"(優先|優先順位|先に|後に|こっち)", combined):
        signal_count += 1
    elif re.search(r"(した方がいい|の方がいい|そっち|これでいい|これでいく)", combined):
        signal_count += 0.4
    if re.search(r"(一方|ただし|でも|しかし|ではなく)", combined):
        signal_count += 1
    elif re.search(r"(方向転換|変える|変更|戻す|切り替える)", combined):
        signal_count += 0.4
    if re.search(r"(却下|不採用|違う|こっち|維持|そのまま)", combined):
        signal_count += 1
    elif re.search(r"(いらん|いらない|不要|使わない|やめる|削る|外す|仕方ない)", combined):
        signal_count += 0.4
    return min(1.0, signal_count / 3.0)


def _measure_comparison_depth(structured_steps: List[Dict[str, Any]]) -> float:
    combined = "\n".join([
        "\n".join([
            _safe_text(step.get("judgment", "")),
            _safe_text(step.get("revision", "")),
            _safe_text(step.get("adoption", "")),
        ])
        for step in structured_steps
    ])
    combined = _remove_work_report_scoring_noise(combined)
    if not combined.strip():
        return 0.0
    score = 0.0
    if re.search(r"(比較|案|A案|B案|複数案|こっち)", combined):
        score += 0.35
    elif re.search(r"(した方がいい|の方がいい|そっち)", combined):
        score += 0.15
    if re.search(r"(不採用|却下|違う|ではなく)", combined):
        score += 0.25
    elif re.search(r"(いらん|いらない|不要|使わない|やめる|外す|削る)", combined):
        score += 0.12
    if re.search(r"(こっち|このまま|維持|残す|別表現)", combined):
        score += 0.20
    elif re.search(r"(これでいい|これでいく|変える|変更|戻す|切り替える)", combined):
        score += 0.10
    if re.search(r"(優先|優先順位|トレードオフ|バランス)", combined):
        score += 0.20
    elif re.search(r"(方向転換|甘くして|厳しくして|多すぎる)", combined):
        score += 0.10
    return min(1.0, score)


def _binary_or_weak_signal(text: str, strong_pattern: str, weak_pattern: str) -> float:
    if re.search(strong_pattern, text):
        return 1.0
    if re.search(weak_pattern, text):
        return 0.35
    return 0.0


def _remove_work_report_scoring_noise(text: str) -> str:
    lines: List[str] = []
    for line in _safe_text(text).splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.search(r"^(作成|変更|修正|追加|実装|確認)しました", stripped):
            continue
        if re.search(r"^(確認結果|変更内容|実装内容|作成ファイル|変更ファイル)", stripped):
            continue
        if re.search(r"(manifest\.json|popup\.js|content\.js)", stripped, flags=re.IGNORECASE):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _measure_output_requirement_coverage(text: str) -> Dict[str, Any]:
    context = _get_page_context(text)
    h1 = _safe_text(context.get("h1", ""))
    body_parts = [_safe_text(item) for item in context.get("body", []) if _safe_text(item)]
    cta_buttons = _safe_text(context.get("cta_buttons", ""))
    sections = [_safe_text(item) for item in context.get("sections", []) if _safe_text(item)]
    fetch_mode = _extract_prefixed_line(text, "FETCH_MODE:").lower()
    qr_present = _extract_prefixed_bool(text, "QR_PRESENT:")

    has_h1 = bool(h1)
    has_body = bool(body_parts)
    has_cta = bool(cta_buttons)
    has_sections = bool(sections)

    required_coverage = sum([has_h1, has_body, has_cta, has_sections]) / 4.0

    body_count_bonus = min(1.0, len(body_parts) / 5.0)
    section_count_bonus = min(1.0, len(sections) / 5.0)
    qr_bonus = 1.0 if qr_present else 0.0
    fetch_bonus = 1.0 if fetch_mode == "rendered" else 0.7 if fetch_mode == "static" else 0.0
    bonus_coverage = (body_count_bonus + section_count_bonus + qr_bonus + fetch_bonus) / 4.0

    return {
        "required_coverage": required_coverage,
        "bonus_coverage": bonus_coverage,
        "has_h1": has_h1,
        "has_body": has_body,
        "has_cta": has_cta,
        "has_sections": has_sections,
    }


def _measure_h1_body_consistency(context: Dict[str, Any]) -> float:
    h1 = _safe_text(context.get("h1", ""))
    body = " ".join([_safe_text(item) for item in context.get("body", []) if _safe_text(item)])
    if not h1 or not body:
        return 0.0
    return _measure_text_alignment(h1, body)


def _measure_cta_structure_coherence(context: Dict[str, Any]) -> float:
    sections = " ".join([_safe_text(item) for item in context.get("sections", []) if _safe_text(item)])
    cta_buttons = _safe_text(context.get("cta_buttons", ""))
    body = " ".join([_safe_text(item) for item in context.get("body", []) if _safe_text(item)])
    if not cta_buttons:
        return 0.0
    return min(1.0, _measure_text_alignment(cta_buttons, sections + " " + body) + 0.15)


def _measure_log_output_match_rate(
    structured_steps: List[Dict[str, Any]],
    output_text: str,
    artifact_type: str = "landing_page",
) -> Dict[str, Any]:
    if artifact_type != "landing_page":
        return _measure_general_log_output_match_rate(structured_steps, output_text)

    reflectable_topics = {
        "hero_primary", "hero_follow", "cta", "qr",
        "classification_structure", "classification_title", "classification_label", "classification_copy",
        "flow", "visual_style",
    }
    context = _get_page_context(output_text)
    page_zone = _build_page_zone(context, include_body=True)
    page_topics = _extract_output_topics(page_zone)

    target_topics = set()
    evidence: List[str] = []
    for step in structured_steps:
        topics = _extract_step_topics(step) & reflectable_topics
        if topics:
            target_topics.update(topics)
            for field in ("judgment", "adoption", "revision"):
                text = _safe_text(step.get(field, ""))
                if text and len(evidence) < 5:
                    evidence.append(text)

    if not target_topics:
        return {
            "match_rate": 0.0,
            "conflict_penalty": 0.0,
            "matched_topics": [],
            "unmatched_topics": [],
            "conflict_topics": [],
            "evidence": evidence,
        }

    topic_groups = {
        "hero": {"hero_primary", "hero_follow"},
        "cta": {"cta"},
        "qr": {"qr"},
        "classification": {"classification_structure", "classification_title", "classification_label", "classification_copy"},
        "flow": {"flow"},
        "visual_style": {"visual_style"},
    }
    group_weights = {
        "hero": 1.2,
        "cta": 1.0,
        "qr": 0.9,
        "classification": 1.0,
        "flow": 0.8,
        "visual_style": 0.6,
    }

    matched_topics = sorted(target_topics & page_topics)
    unmatched_topics = sorted(target_topics - page_topics)
    conflict_topics = _detect_conflict_topics(structured_steps, output_text)
    target_weight = 0.0
    matched_weight = 0.0
    for group_name, group_topics in topic_groups.items():
        if target_topics & group_topics:
            target_weight += group_weights[group_name]
            if page_topics & group_topics:
                matched_weight += group_weights[group_name]
    match_rate = matched_weight / max(1.0, target_weight)
    conflict_penalty = min(0.20, len(conflict_topics) * 0.05)

    return {
        "match_rate": match_rate,
        "conflict_penalty": conflict_penalty,
        "matched_topics": matched_topics,
        "unmatched_topics": unmatched_topics,
        "conflict_topics": conflict_topics,
        "evidence": evidence,
    }


def _measure_general_log_output_match_rate(
    structured_steps: List[Dict[str, Any]],
    output_text: str,
) -> Dict[str, Any]:
    output_keywords = set(_extract_meaningful_match_keywords(output_text))
    matched_topics: List[str] = []
    unmatched_topics: List[str] = []
    evidence: List[str] = []
    reflected_ratios: List[float] = []

    for index, step in enumerate(structured_steps, start=1):
        if not isinstance(step, dict):
            continue
        source_id = (
            _safe_int(step.get("source_step_id", 0))
            or _safe_int(step.get("step_id", index))
            or index
        )
        evidence_text = "\n".join([
            _safe_text(step.get("judgment", "")),
            _safe_text(step.get("revision", "")),
            _safe_text(step.get("adoption", "")),
        ])
        keywords = set(_extract_meaningful_match_keywords(evidence_text))
        if not keywords:
            continue
        overlap = keywords & output_keywords
        ratio = len(overlap) / max(1, len(keywords))
        reflected = len(overlap) >= 2 or ratio >= 0.20
        label = f"step_{source_id}"
        reflected_ratios.append(min(1.0, ratio))
        if reflected:
            matched_topics.append(label)
            if len(evidence) < 5:
                evidence.append(evidence_text)
        else:
            unmatched_topics.append(label)

    match_rate = (
        len(matched_topics) / max(1, len(matched_topics) + len(unmatched_topics))
        if matched_topics or unmatched_topics
        else 0.0
    )
    conflict_topics = _detect_conflict_topics(structured_steps, output_text)
    return {
        "match_rate": match_rate,
        "conflict_penalty": min(0.20, len(conflict_topics) * 0.05),
        "matched_topics": matched_topics,
        "unmatched_topics": unmatched_topics,
        "conflict_topics": conflict_topics,
        "evidence": evidence,
        "mean_keyword_ratio": (
            sum(reflected_ratios) / len(reflected_ratios)
            if reflected_ratios
            else 0.0
        ),
    }


GENERIC_MATCH_STOPWORDS = {
    "decision", "revision", "selection", "reason", "before", "after",
    "choose", "chosen", "use", "used", "using", "keep", "kept", "make",
    "made", "change", "changed", "replace", "replaced", "should", "would",
    "could", "this", "that", "these", "those", "with", "from", "into",
    "when", "where", "which", "their", "there", "then", "than", "only",
    "final", "current", "version", "user", "users", "output", "input",
    "判断", "修正", "採否", "理由", "変更前", "変更後", "成果物",
}


def _extract_meaningful_match_keywords(text: str) -> List[str]:
    result: List[str] = []
    for keyword in _extract_keywords(text):
        normalized = keyword.lower()
        if normalized in GENERIC_MATCH_STOPWORDS:
            continue
        if len(normalized) < 3 and re.fullmatch(r"[a-z0-9_]+", normalized):
            continue
        result.append(normalized)
    return result


def _extract_output_topics(page_zone: str) -> set[str]:
    text = _safe_text(page_zone)
    topics = set()
    if not text:
        return topics
    for label, words in STEP_TOPIC_RULES:
        if any(word in text for word in words):
            topics.add(label)
    if re.search(r"(現在地を確認する|自分のスコアを確認する|自分のAI活用を確認する|AI活用を見える化する|AI時代の人間診断|AI相棒診断)", text):
        topics.add("cta")
    if re.search(r"(証明できますか|AIを活用できていると証明できますか|[?？])", text):
        topics.add("hero_primary")
        topics.add("hero_follow")
    if re.search(r"(QR|読み取るだけ|見せれば分かる)", text):
        topics.add("qr")
    if "qr_present: yes" in text.lower():
        topics.add("qr")
    if re.search(r"(レベル|カテゴリー|依存|効率化|補助|共創|主導)", text):
        topics.add("classification_structure")
        topics.add("classification_title")
        topics.add("classification_label")
    if re.search(r"(現在地|スコア|見える化|レポート|無料)", text):
        topics.add("flow")
    if re.search(r"(余白|ミニマル|Apple|高級感|静けさ)", text):
        topics.add("visual_style")
    return topics


def _detect_conflict_topics(structured_steps: List[Dict[str, Any]], output_text: str) -> List[str]:
    text = _safe_text(output_text)
    conflicts: List[str] = []
    combined_steps = "\n".join([
        "\n".join([
            _safe_text(step.get("judgment", "")),
            _safe_text(step.get("adoption", "")),
            _safe_text(step.get("revision", "")),
        ])
        for step in structured_steps
    ])
    if "不採用" in combined_steps and re.search(r"(機能説明|共有・連携・出力)", text):
        conflicts.append("cta")
    if re.search(r"(説明しない|説明を捨てる)", combined_steps) and re.search(r"(長文説明|詳細説明)", text):
        conflicts.append("flow")
    return conflicts

def _has_url_fetch_failure(text: str) -> bool:
    txt = _safe_text(text)
    return "URL_FETCH_FAILED:" in txt


def _count_structure_evidence(structure_decisions: List[Dict[str, Any]]) -> int:
    return len([item for item in structure_decisions if _safe_text(item.get("text", ""))])


def _compute_provisional_output_floor(
    output_text: str,
    log_text: str,
    structure_decisions: List[Dict[str, Any]],
) -> float:
    txt = _safe_text(output_text)
    if not txt:
        return 0.0

    has_url = ("http://" in txt or "https://" in txt or "対象URL:" in txt or "SOURCE_URL:" in txt)
    structure_count = _count_structure_evidence(structure_decisions)
    lp_hint_score = _measure_lp_hints(txt)
    alignment_score = _measure_text_alignment(log_text, txt)
    fetch_failed = _has_url_fetch_failure(txt)
    has_substantive_output = _has_substantive_output_core(txt)

    if structure_count < 1 or (not has_url and not has_substantive_output):
        return 0.0

    base_floor = 0.34
    if has_substantive_output:
        base_floor = 0.46
    page_fetch_score = _measure_page_fetch(txt)
    content_quality_score = _measure_content_quality(txt)
    url_structure_score = _detail_normalized(_score_url_structure(txt))
    if structure_count >= 2:
        base_floor += 0.08
    if structure_count >= 4:
        base_floor += 0.06

    base_floor += min(0.05, lp_hint_score * 0.06)
    base_floor += min(0.06, alignment_score * 0.10)
    base_floor += min(0.08, page_fetch_score * 0.10)
    base_floor += min(0.08, content_quality_score * 0.10)
    base_floor += min(0.06, url_structure_score * 0.08)

    if fetch_failed and has_substantive_output:
        base_floor += 0.02

    return min(0.78, base_floor)

def _compute_provisional_consistency_floor(
    output_text: str,
    log_text: str,
    structured_steps: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
) -> float:
    txt = _safe_text(output_text)
    if not txt:
        return 0.0

    has_url = ("http://" in txt or "https://" in txt or "対象URL:" in txt or "SOURCE_URL:" in txt)
    structure_count = _count_structure_evidence(structure_decisions)
    has_substantive_output = _has_substantive_output_core(txt)
    if structure_count < 2 or (not has_url and not has_substantive_output):
        return 0.0

    total_steps = max(1, len(structured_steps))
    reason_density = len([s for s in structured_steps if _safe_text(s.get("reason", ""))]) / total_steps
    filled_ratio = len([
        s for s in structured_steps
        if any([
            _safe_text(s.get("judgment", "")),
            _safe_text(s.get("revision", "")),
            _safe_text(s.get("adoption", "")),
            _safe_text(s.get("reason", "")),
        ])
    ]) / total_steps
    alignment_score = _measure_text_alignment(log_text, txt)
    lp_hint_score = _measure_lp_hints(txt)
    page_fetch_score = _measure_page_fetch(txt)
    content_quality_score = _measure_content_quality(txt)
    url_structure_score = _detail_normalized(_score_url_structure(txt))
    page_structure_reflection_score = _measure_page_structure_reflection(txt, structured_steps)
    fetch_failed = _has_url_fetch_failure(txt)

    if filled_ratio < 0.6 or reason_density < 0.5:
        return 0.0

    floor = 0.50
    if has_substantive_output:
        floor = 0.60
    if structure_count >= 4:
        floor += 0.06

    floor += min(0.04, reason_density * 0.05)
    floor += min(0.04, filled_ratio * 0.05)
    floor += min(0.03, lp_hint_score * 0.04)
    floor += min(0.04, alignment_score * 0.08)
    floor += min(0.04, page_fetch_score * 0.06)
    floor += min(0.04, content_quality_score * 0.06)
    floor += min(0.04, url_structure_score * 0.06)
    floor += min(0.05, page_structure_reflection_score * 0.08)

    if fetch_failed and has_substantive_output:
        floor += 0.01

    return min(0.85, floor)

def _build_url_evaluation(
    output_text: str,
    log_text: str,
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
    judgment_process: Dict[str, Any],
    revision_process: Dict[str, Any],
    judgment_agency: Dict[str, Any],
    overall_consistency: Dict[str, Any],
) -> Dict[str, Any]:
    clean_output = _remove_noise_lines(output_text)
    if not _has_page_context(clean_output):
        return {}

    page_context_label = _get_page_context_label(clean_output)

    structure_detail = _score_url_structure(clean_output)
    appeal_detail = _score_url_appeal(clean_output)
    ai_util_detail = _score_url_ai_utilization(
        log_text=log_text,
        output_text=clean_output,
        structured_steps=structured_steps,
        decisions=decisions,
        revisions=revisions,
        adoptions=adoptions,
        structure_decisions=structure_decisions,
        judgment_process=judgment_process,
        revision_process=revision_process,
        judgment_agency=judgment_agency,
        overall_consistency=overall_consistency,
    )

    scores = {
        "文章構造": structure_detail["score"],
        "訴求力": appeal_detail["score"],
        "AI活用度": ai_util_detail["score"],
    }
    total_score = round(sum(scores.values()) / max(1, len(scores)))

    return {
        "enabled": True,
        "title": _build_page_evaluation_title(page_context_label),
        "page_context_label": page_context_label,
        "scores": scores,
        "total_score": total_score,
        "comment": _build_url_evaluation_comment(scores, page_context_label),
        "details": {
            "文章構造": structure_detail,
            "訴求力": appeal_detail,
            "AI活用度": ai_util_detail,
        },
    }


def _build_screenshot_visual_evaluation(output_text: str, visual_input_mode: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _extract_lp_visual_metrics(output_text)
    if not metrics.get("enabled"):
        if visual_input_mode.get("enabled"):
            return {
                "enabled": False,
                "status": "missing_lp_markers",
                "message": "画像LP解析マーカーが不足しているため、見た目査定を確定できませんでした。",
            }
        return {}

    hero_score = int(round(max(0.0, min(1.0, metrics.get("hero", 0.0))) * 100))
    cta_score = int(round(max(0.0, min(1.0, metrics.get("cta", 0.0))) * 100))
    flow_score = int(round(max(0.0, min(1.0, metrics.get("flow", 0.0))) * 100))
    trust_score = int(round(max(0.0, min(1.0, metrics.get("trust", 0.0))) * 100))
    whitespace_score = int(round(max(0.0, min(1.0, metrics.get("whitespace", 0.0))) * 100))
    density_score = int(round(max(0.0, min(1.0, metrics.get("info_density_score", 0.0))) * 100))
    mobile_score = int(round(max(0.0, min(1.0, metrics.get("mobile", 0.0))) * 100))
    dropoff_risk = int(round(max(0.0, min(1.0, metrics.get("dropoff_risk", 0.0))) * 100))
    total_score = int(round(max(0.0, min(1.0, metrics.get("overall", 0.0))) * 100))

    strengths: List[str] = []
    risks: List[str] = []

    if hero_score >= 62:
        strengths.append("Heroが強く、ファーストビューで止まる構図を作れています。")
    if flow_score >= 60:
        strengths.append("視線導線が自然で、上から下まで読み進めやすい構成です。")
    if cta_score >= 60:
        strengths.append("CTA視認性が高く、行動導線が分かりやすい状態です。")
    if whitespace_score >= 58:
        strengths.append("余白バランスが安定しており、情報過密を抑えています。")
    if trust_score >= 55:
        strengths.append("信頼導線が入り、CTA直前の不安低減に寄与しています。")

    if hero_score < 45:
        risks.append("Hero訴求が弱く、ファーストビュー離脱の懸念があります。")
    if flow_score < 45:
        risks.append("視線導線が途切れやすく、中盤離脱リスクが高めです。")
    if cta_score < 45:
        risks.append("CTA位置が弱く、申込み導線で迷う可能性があります。")
    if density_score < 45:
        risks.append("情報密度の偏りがあり、スマホ閲覧時の読み負荷が高い状態です。")
    if trust_score < 40:
        risks.append("信頼要素が薄く、CTA着地時の不安解消が不足しています。")

    comment = (
        f"Hero {hero_score} / CTA {cta_score} / 視線導線 {flow_score} を中心に、"
        f"余白・情報密度・信頼導線を実画像で評価しました。"
    )
    summary = (
        f"スマホ閲覧性 {mobile_score}、離脱リスク {dropoff_risk}。"
        "画面構成・視覚導線・情報密度の観点で確認した結果です。"
    )

    return {
        "enabled": True,
        "status": "ok",
        "source": "screenshot_lp_analysis",
        "scores": {
            "第一印象": int(round(hero_score * 0.55 + flow_score * 0.45)),
            "視線導線": flow_score,
            "余白設計": whitespace_score,
            "信頼感": trust_score,
            "CTA視認性": cta_score,
            "情報密度": density_score,
            "スマホ閲覧性": mobile_score,
            "離脱リスク": dropoff_risk,
        },
        "total_score": total_score,
        "comment": comment,
        "summary": summary,
        "strengths": strengths[:5],
        "risks": risks[:5],
    }


def _score_url_structure(output_text: str) -> Dict[str, Any]:
    structure_score = _measure_output_structure(output_text)
    page_fetch_score = _measure_page_fetch(output_text)
    target_score = _measure_target_clarity(output_text)
    benefit_score = _measure_benefit_clarity(output_text)
    cta_flow_score = _measure_cta_flow(output_text)
    conciseness_score = _measure_conciseness(output_text)

    normalized = min(
        1.0,
        structure_score * 0.22
        + page_fetch_score * 0.12
        + target_score * 0.18
        + benefit_score * 0.18
        + cta_flow_score * 0.20
        + conciseness_score * 0.10
    )

    reasons: List[str] = []
    risk_flags: List[str] = []

    if structure_score >= 0.7:
        reasons.append("見出しとセクションの骨組みが整理されている")
    elif structure_score < 0.4:
        risk_flags.append("見出しやセクションの整理が弱く、読み筋が分かりにくい")

    if target_score >= 0.6:
        reasons.append("誰向けのページかが比較的つかみやすい")
    elif target_score < 0.4:
        risk_flags.append("対象読者の定義が弱く、刺さる相手がぼやけやすい")

    if benefit_score >= 0.6:
        reasons.append("ベネフィットが言語化されている")
    elif benefit_score < 0.4:
        risk_flags.append("価値訴求が抽象的で、読む理由が弱い")

    if cta_flow_score >= 0.6:
        reasons.append("CTAまでの流れが見えやすい")
    elif cta_flow_score < 0.4:
        risk_flags.append("CTAに至る導線が弱く、行動につながりにくい")

    evidence = _extract_output_evidence_priority(output_text)

    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _score_url_appeal(output_text: str) -> Dict[str, Any]:
    first_view_score = _measure_first_view_clarity(output_text)
    curiosity_score = _measure_curiosity(output_text)
    anxiety_relief_score = _measure_anxiety_relief(output_text)
    trust_score = _measure_trust(output_text)
    action_reason_score = _measure_action_reason(output_text)

    normalized = min(
        1.0,
        first_view_score * 0.24
        + curiosity_score * 0.14
        + anxiety_relief_score * 0.18
        + trust_score * 0.22
        + action_reason_score * 0.22
    )

    reasons: List[str] = []
    risk_flags: List[str] = []

    if first_view_score >= 0.7:
        reasons.append("ファーストビューで意味が伝わりやすい")
    elif first_view_score < 0.4:
        risk_flags.append("ファーストビューで何のページか伝わりにくい")

    if curiosity_score >= 0.5:
        reasons.append("続きを読みたくなる引きがある")
    elif curiosity_score < 0.3:
        risk_flags.append("読み進めたくなる引きが弱い")

    if anxiety_relief_score >= 0.5:
        reasons.append("不安解消につながる要素が含まれている")
    elif anxiety_relief_score < 0.35:
        risk_flags.append("不安解消の材料が少なく、離脱要因が残りやすい")

    if trust_score >= 0.5:
        reasons.append("信頼材料が一定程度そろっている")
    elif trust_score < 0.35:
        risk_flags.append("信頼の裏付けが薄く、比較検討で不利になりやすい")

    if action_reason_score >= 0.5:
        reasons.append("行動する理由が示されている")
    elif action_reason_score < 0.35:
        risk_flags.append("今動く理由が薄く、CVにつながりにくい")

    evidence = _extract_output_evidence_priority(output_text)

    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _score_url_ai_utilization(
    log_text: str,
    output_text: str,
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
    judgment_process: Dict[str, Any],
    revision_process: Dict[str, Any],
    judgment_agency: Dict[str, Any],
    overall_consistency: Dict[str, Any],
) -> Dict[str, Any]:
    human_judgment_score = _detail_normalized(judgment_agency)
    revision_intent_score = _detail_normalized(revision_process)
    target_design_score = _measure_target_design(log_text, output_text)
    issue_organization_score = _measure_issue_organization(log_text, structured_steps, structure_decisions)
    craftsmanship_score = _measure_ai_craftsmanship(
        structured_steps=structured_steps,
        decisions=decisions,
        revisions=revisions,
        adoptions=adoptions,
        judgment_process=judgment_process,
        overall_consistency=overall_consistency,
    )

    normalized = min(
        1.0,
        human_judgment_score * 0.28
        + revision_intent_score * 0.22
        + target_design_score * 0.16
        + issue_organization_score * 0.16
        + craftsmanship_score * 0.18
    )

    reasons: List[str] = []
    risk_flags: List[str] = []
    evidence = _extract_process_evidence(decisions, revisions, adoptions, structure_decisions)

    if human_judgment_score >= 0.7:
        reasons.append("AI提案に対する人判断が明確に残っている")
    elif human_judgment_score < 0.4:
        risk_flags.append("人判断の痕跡が薄く、AI任せに見えやすい")

    if revision_intent_score >= 0.6:
        reasons.append("修正意図が言語化されている")
    elif revision_intent_score < 0.4:
        risk_flags.append("修正の意図が見えづらく、改善の筋が弱い")

    if target_design_score >= 0.5:
        reasons.append("ターゲット設計の視点が入っている")
    elif target_design_score < 0.35:
        risk_flags.append("ターゲット設計の痕跡が弱く、誰向けかの調整が見えにくい")

    if issue_organization_score >= 0.5:
        reasons.append("論点整理や構造整理の跡が確認できる")
    elif issue_organization_score < 0.35:
        risk_flags.append("論点整理の形跡が弱く、場当たり修正に見えやすい")

    if craftsmanship_score >= 0.6:
        reasons.append("AI生成物をそのまま出さず、仕上げた痕跡がある")
    elif craftsmanship_score < 0.4:
        risk_flags.append("仕上げの磨き込みが弱く、AI依存に見えやすい")

    return _build_axis_result(normalized, reasons, evidence, risk_flags)


def _build_url_evaluation_comment(scores: Dict[str, int], page_context_label: str = "") -> str:
    strongest_axis = max(URL_EVAL_ORDER, key=lambda key: _safe_int(scores.get(key, 0)))
    weakest_axis = min(URL_EVAL_ORDER, key=lambda key: _safe_int(scores.get(key, 0)))

    strength_phrases = {
        "文章構造": "構造は優秀です",
        "訴求力": "訴求の立ち上がりは強いです",
        "AI活用度": "AI活用の人判断は明確です",
    }
    weakness_phrases = {
        "文章構造": "構造整理に改善余地があり、読み筋の補強余地があります",
        "訴求力": "訴求導線が弱く、CV改善余地があります",
        "AI活用度": "AI活用の根拠が見えにくく、独自性の補強余地があります",
    }

    prefix = ""
    clean_label = _safe_text(page_context_label)
    if clean_label and clean_label != "ページ":
        prefix = f"{clean_label}として見ると、"

    if all(_safe_int(scores.get(axis, 0)) >= 80 for axis in URL_EVAL_ORDER):
        return f"{prefix}構造・訴求・AI活用の3面で高水準です。"

    return f"{prefix}{strength_phrases[strongest_axis]}。{weakness_phrases[weakest_axis]}。"


def _build_trace_summary(
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
    raw_counts: Dict[str, Any] | None = None,
) -> str:
    summary = (
        f"判断 {len(decisions)}件 / "
        f"修正 {len(revisions)}件 / "
        f"採否 {len(adoptions)}件 / "
        f"構造決定 {len(structure_decisions)}件 を抽出"
    )

    if isinstance(raw_counts, dict):
        raw_decisions = _safe_int(raw_counts.get("decisions", 0))
        raw_revisions = _safe_int(raw_counts.get("revisions", 0))
        raw_adoptions = _safe_int(raw_counts.get("adoptions", 0))
        raw_structure = _safe_int(raw_counts.get("structure_decisions", 0))

        if (
            raw_decisions > len(decisions)
            or raw_revisions > len(revisions)
            or raw_adoptions > len(adoptions)
            or raw_structure > len(structure_decisions)
        ):
            summary += (
                f"（圧縮前: 判断 {raw_decisions}件 / "
                f"修正 {raw_revisions}件 / "
                f"採否 {raw_adoptions}件 / "
                f"構造決定 {raw_structure}件）"
            )

    return summary


def _build_unclassified_comment(scores: Dict[str, int], output_text: str) -> str:
    low_axes = [axis for axis, score_value in scores.items() if _safe_int(score_value) < 40]
    txt = _safe_text(output_text)

    has_url = ("http://" in txt or "https://" in txt or "対象URL:" in txt)
    has_title = "PAGE_TITLE:" in txt
    has_h1 = "H1:" in txt
    has_body = "BODY:" in txt
    has_sections = "SECTIONS:" in txt
    has_page_data = any(marker in txt for marker in PAGE_MARKERS)
    is_lp_like = _is_lp_like(txt)
    has_visual_artifact = any(
        marker in txt
        for marker in [
            "ARTIFACT_IMAGE_ROLE:",
            "VISUAL_MODE: artifact_image_set",
            "SCREENSHOT_COUNT:",
            "画像成果物",
            "視覚構成",
            "余白設計",
            "情報密度",
        ]
    )

    if has_url and not has_page_data:
        return "ページ本文取得が不足している可能性があり、成果物評価は暫定値です。"

    if has_visual_artifact and not has_url and not low_axes:
        return "スクリーンショット上の視覚構成、余白、情報密度を含め、評価の土台は成立しています。"

    if is_lp_like and has_title and has_h1 and has_body and has_sections and not low_axes:
        return "LP本文と構造情報の取得を含め、評価の土台は成立しています。"

    if has_title and has_h1 and has_body and has_sections and not low_axes:
        return "成果物本文と構造情報の取得を含め、評価の土台は成立しています。"

    if has_title and has_h1 and has_body and not low_axes:
        return "成果物本文の取得を含め、評価の土台は成立しています。"

    if not low_axes:
        return "大きな欠落は少なく、評価の土台は成立しています。"

    return " / ".join([f"{axis}に改善余地あり" for axis in low_axes[:3]])


def _measure_output_structure(text: str) -> float:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return 0.0

    heading_count = 0
    bullet_count = 0
    content_heading_count = 0

    for line in lines:
        if line.endswith("：") or line.endswith(":") or re.match(r"^[#■【\[]", line):
            heading_count += 1
        if re.match(r"^[・\-—―\*●○①②③④⑤]", line):
            bullet_count += 1
        if line.startswith(("PAGE_TITLE:", "H1:", "BODY:", "TEXT:", "SECTIONS:")):
            content_heading_count += 1

    line_count = len(lines)

    score = 0.0
    if heading_count >= 1:
        score += 0.18
    if heading_count >= 3:
        score += 0.10
    if bullet_count >= 1:
        score += 0.08
    if line_count >= 5:
        score += 0.10
    if line_count >= 10:
        score += 0.10
    if content_heading_count >= 2:
        score += 0.18
    if content_heading_count >= 3:
        score += 0.10
    if content_heading_count >= 4:
        score += 0.10

    h1_count = _extract_prefixed_int(text, "H1_COUNT:")
    h2_count = _extract_prefixed_int(text, "H2_COUNT:")
    h3_count = _extract_prefixed_int(text, "H3_COUNT:")
    section_count = _extract_prefixed_int(text, "SECTION_COUNT:")
    cta_count = _extract_prefixed_int(text, "CTA_COUNT:")
    if h1_count >= 1:
        score += 0.10
    if h2_count >= 2:
        score += 0.10
    if h3_count >= 2:
        score += 0.06
    if section_count >= 3:
        score += 0.12
    if section_count >= 6:
        score += 0.10
    if cta_count >= 1:
        score += 0.08
    if "CTA_BUTTONS:" in text and cta_count == 0:
        score += 0.04
    if _extract_prefixed_bool(text, "FAQ_PRESENT:"):
        score += 0.04
    if _extract_prefixed_bool(text, "FORM_PRESENT:"):
        score += 0.05
    if _extract_prefixed_bool(text, "QR_PRESENT:"):
        score += 0.05

    if _is_lp_like(text):
        sections = _extract_prefixed_line(text, "SECTIONS:")
        if sections:
            section_parts = [p.strip() for p in sections.split("/") if p.strip()]
            if len(section_parts) >= 2:
                score += 0.08
            if len(section_parts) >= 4:
                score += 0.08

    return min(1.0, score)


def _measure_logic_markers(text: str) -> float:
    if not _safe_text(text):
        return 0.0

    hits = 0
    for pattern in LOGIC_PATTERNS:
        hits += len(re.findall(pattern, text))

    if hits >= 8:
        return 1.0
    if hits >= 5:
        return 0.75
    if hits >= 3:
        return 0.50
    if hits >= 1:
        return 0.25
    return 0.0


def _measure_text_alignment(a: str, b: str) -> float:
    a_tokens = set(_extract_keywords(a))
    b_tokens = set(_extract_keywords(b))

    if not a_tokens or not b_tokens:
        return 0.0

    overlap = a_tokens & b_tokens
    union = a_tokens | b_tokens
    return min(1.0, len(overlap) / max(1, len(union)) * 3.0)


def _measure_structure_reflection(output_text: str, structure_decisions: List[Dict[str, Any]]) -> float:
    if not structure_decisions:
        return 0.0

    output_keywords = set(_extract_keywords(output_text))
    if not output_keywords:
        return 0.0

    reflected = 0
    total = 0

    for item in structure_decisions:
        text = _safe_text(item.get("text", ""))
        keywords = set(_extract_keywords(text))
        if not keywords:
            continue
        total += 1
        if keywords & output_keywords:
            reflected += 1

    if total == 0:
        return 0.0

    return reflected / total


def _measure_page_fetch(text: str) -> float:
    txt = _safe_text(text)
    if not txt:
        return 0.0

    fetch_mode = _extract_prefixed_line(txt, "FETCH_MODE:")
    evaluation_ready = _extract_prefixed_line(txt, "PAGE_EVALUATION_READY:").strip().lower() == "yes"
    raw_html_chars = _extract_prefixed_int(txt, "RAW_HTML_CHARS:")
    rendered_html_chars = _extract_prefixed_int(txt, "RENDERED_HTML_CHARS:")
    extracted_text_chars = _extract_prefixed_int(txt, "EXTRACTED_TEXT_CHARS:")
    section_count = _extract_prefixed_int(txt, "SECTION_COUNT:")
    heading_count = (
        _extract_prefixed_int(txt, "H1_COUNT:")
        + _extract_prefixed_int(txt, "H2_COUNT:")
        + _extract_prefixed_int(txt, "H3_COUNT:")
    )
    cta_count = _extract_prefixed_int(txt, "CTA_COUNT:")
    link_count = _extract_prefixed_int(txt, "LINK_TEXT_COUNT:")
    aria_label_count = _extract_prefixed_int(txt, "ARIA_LABEL_COUNT:")

    if "URL_FETCH_FAILED:" in txt and ("対象URL:" in txt or "http://" in txt or "https://" in txt):
        return 0.32

    if fetch_mode == "rendered":
        score = 0.68 if evaluation_ready else 0.62
        if rendered_html_chars >= 40000:
            score += 0.10
        if extracted_text_chars >= 1200:
            score += 0.10
        if heading_count >= 4:
            score += 0.08
        if section_count >= 4:
            score += 0.06
        if cta_count >= 1:
            score += 0.04
        if link_count >= 3:
            score += 0.04
        if aria_label_count >= 1:
            score += 0.02
        return min(1.0, score)

    if fetch_mode == "static":
        score = 0.58 if evaluation_ready else 0.40
        if raw_html_chars >= 20000:
            score += 0.08
        if extracted_text_chars >= 1000:
            score += 0.10
        if heading_count >= 4:
            score += 0.08
        if section_count >= 4:
            score += 0.06
        if cta_count >= 1:
            score += 0.04
        if link_count >= 3:
            score += 0.04
        if aria_label_count >= 1:
            score += 0.02
        return min(0.94 if evaluation_ready else 0.88, score)

    found = sum(1 for marker in PAGE_MARKERS if marker in txt)
    content_found = sum(1 for marker in CONTENT_MARKERS if marker in txt)

    if found >= 6 and content_found >= 4:
        return 1.0
    if found >= 5 and content_found >= 3:
        return 0.92
    if found >= 4 and content_found >= 2:
        return 0.82
    if found >= 3 and content_found >= 1:
        return 0.72
    if found >= 1:
        return 0.40
    if "対象URL:" in txt or "http://" in txt or "https://" in txt:
        return 0.20
    return 0.0


def _measure_output_volume(text: str) -> float:
    txt = _safe_text(text)
    n = len(txt)

    if n >= 2500:
        return 1.0
    if n >= 1500:
        return 0.85
    if n >= 800:
        return 0.65
    if n >= 350:
        return 0.45
    if n >= 100:
        return 0.25
    return 0.0


def _measure_lp_hints(text: str) -> float:
    txt = _safe_text(text)
    if not txt:
        return 0.0

    hit = sum(1 for word in LP_HINTS if word in txt)

    if hit >= 8:
        return 1.0
    if hit >= 5:
        return 0.75
    if hit >= 3:
        return 0.45
    if hit >= 1:
        return 0.20
    return 0.0


def _measure_artifact_context(text: str) -> float:
    txt = _safe_text(text)
    if not txt:
        return 0.0

    hit = sum(1 for marker in ARTIFACT_HINTS if marker in txt)

    if hit >= 3:
        return 0.45
    if hit >= 2:
        return 0.30
    if hit >= 1:
        return 0.15
    return 0.0

def _measure_content_quality(text: str) -> float:
    txt = _safe_text(text)
    if not txt:
        return 0.0

    score = 0.0

    page_title = _extract_prefixed_line(txt, "PAGE_TITLE:")
    h1 = _extract_prefixed_line(txt, "H1:")
    body = _extract_prefixed_line(txt, "BODY:")
    text_block = _extract_prefixed_line(txt, "TEXT:")
    sections = _extract_prefixed_line(txt, "SECTIONS:")
    cta_buttons = _extract_prefixed_line(txt, "CTA_BUTTONS:")
    extracted_text_chars = _extract_prefixed_int(txt, "EXTRACTED_TEXT_CHARS:")
    section_count = _extract_prefixed_int(txt, "SECTION_COUNT:")
    h2_count = _extract_prefixed_int(txt, "H2_COUNT:")
    h3_count = _extract_prefixed_int(txt, "H3_COUNT:")
    cta_count = _extract_prefixed_int(txt, "CTA_COUNT:")

    if page_title:
        score += 0.16
    if h1:
        score += 0.16
    if body:
        score += 0.20
        body_parts = [p.strip() for p in body.split("/") if p.strip()]
        if len(body_parts) >= 3:
            score += 0.08
        if len(body_parts) >= 6:
            score += 0.06
    elif text_block:
        score += 0.14

    if sections:
        score += 0.14
        section_parts = [p.strip() for p in sections.split("/") if p.strip()]
        if len(section_parts) >= 3:
            score += 0.08
        if len(section_parts) >= 5:
            score += 0.06

    if body and len(body) >= 80:
        score += 0.08
    if body and len(body) >= 160:
        score += 0.08
    if extracted_text_chars >= 1000:
        score += 0.10
    if section_count >= 4:
        score += 0.10
    if h2_count >= 3:
        score += 0.08
    if h3_count >= 2:
        score += 0.05
    if cta_count >= 1 or cta_buttons:
        score += 0.08

    if _is_lp_like(txt) and sections:
        score += 0.06

    return min(1.0, score)


def _measure_lp_bonus(text: str) -> float:
    txt = _safe_text(text)
    if not txt:
        return 0.0

    if not _is_lp_like(txt):
        return 0.0

    score = 0.0
    sections = _extract_prefixed_line(txt, "SECTIONS:")
    h1 = _extract_prefixed_line(txt, "H1:")
    body = _extract_prefixed_line(txt, "BODY:")

    if h1:
        score += 0.25
    if body:
        score += 0.20
    if sections:
        score += 0.25
        section_parts = [p.strip() for p in sections.split("/") if p.strip()]
        if len(section_parts) >= 3:
            score += 0.15
        if len(section_parts) >= 5:
            score += 0.15

    lp_words = sum(1 for word in LP_HINTS if word in txt)
    if lp_words >= 3:
        score += 0.10
    if lp_words >= 6:
        score += 0.10

    return min(1.0, score)


def _build_page_evaluation_title(page_context_label: str) -> str:
    label = _safe_text(page_context_label)
    if not label:
        return "ページ評価レポート"
    if label.endswith("レポート"):
        return label
    return f"{label}評価レポート"


def _get_page_context_label(text: str) -> str:
    txt = _safe_text(text)
    if not txt:
        return "ページ"

    explicit_desc = _extract_prefixed_line(txt, "簡単な説明:")
    if explicit_desc:
        explicit_label = _classify_page_context(explicit_desc)
        if explicit_label:
            return explicit_label

    artifact_desc = _extract_prefixed_line(txt, "品名・説明:")
    if artifact_desc:
        artifact_label = _classify_page_context(artifact_desc)
        if artifact_label:
            return artifact_label

    auto_zone = "\n".join([
        _extract_prefixed_line(txt, "PAGE_TITLE:"),
        _extract_prefixed_line(txt, "H1:"),
        _extract_prefixed_line(txt, "META:"),
        _extract_prefixed_line(txt, "SECTIONS:"),
        _extract_prefixed_line(txt, "BODY:"),
    ]).strip()
    auto_label = _classify_page_context(auto_zone)
    if auto_label:
        return auto_label

    if _is_lp_like(txt):
        return "LP"

    return "ページ"


def _classify_page_context(text: str) -> str:
    normalized = _safe_text(text).lower()
    if not normalized:
        return ""

    for label, keywords in PAGE_CONTEXT_RULES:
        if any(keyword.lower() in normalized for keyword in keywords):
            return label

    return ""


def _has_page_context(text: str) -> bool:
    txt = _safe_text(text)
    if not txt:
        return False
    return any(marker in txt for marker in PAGE_MARKERS) or "http://" in txt or "https://" in txt or "対象URL:" in txt


def _extract_prefixed_segments(text: str, prefix: str) -> List[str]:
    raw = _extract_prefixed_line(text, prefix)
    if not raw:
        return []
    return [segment.strip() for segment in raw.split("/") if segment.strip()]


def _get_page_context(text: str) -> Dict[str, Any]:
    return {
        "evaluation_ready": _extract_prefixed_line(text, "PAGE_EVALUATION_READY:"),
        "page_title": _extract_prefixed_line(text, "PAGE_TITLE:"),
        "meta": _extract_prefixed_line(text, "META:"),
        "h1": _extract_prefixed_line(text, "H1:"),
        "h2": _extract_prefixed_segments(text, "H2:"),
        "h3": _extract_prefixed_segments(text, "H3:"),
        "sections": _extract_prefixed_segments(text, "SECTIONS:"),
        "body": _extract_prefixed_segments(text, "BODY:"),
        "cta_buttons": _extract_prefixed_line(text, "CTA_BUTTONS:"),
        "link_texts": _extract_prefixed_line(text, "LINK_TEXTS:"),
        "aria_labels": _extract_prefixed_line(text, "ARIA_LABELS:"),
        "text": _extract_prefixed_line(text, "TEXT:"),
    }


def _build_page_zone(context: Dict[str, Any], include_body: bool = True) -> str:
    segments: List[str] = []

    for key in ["page_title", "meta", "h1"]:
        value = _safe_text(context.get(key, ""))
        if value:
            segments.append(value)

    segments.extend(context.get("h2", [])[:4])
    segments.extend(context.get("h3", [])[:4])
    segments.extend(context.get("sections", [])[:4])

    if include_body:
        segments.extend(context.get("body", [])[:4])
        cta_buttons = _safe_text(context.get("cta_buttons", ""))
        if cta_buttons:
            segments.extend([part.strip() for part in cta_buttons.split("/") if part.strip()][:4])
        link_texts = _safe_text(context.get("link_texts", ""))
        if link_texts:
            segments.extend([part.strip() for part in link_texts.split("/") if part.strip()][:5])
        aria_labels = _safe_text(context.get("aria_labels", ""))
        if aria_labels:
            segments.extend([part.strip() for part in aria_labels.split("/") if part.strip()][:4])
        text_block = _safe_text(context.get("text", ""))
        if text_block:
            segments.append(text_block[:1200])

    return " / ".join(_safe_text(segment) for segment in segments if _safe_text(segment))


def _keyword_coverage(text: str, words: List[str], full_hit_count: int = 4) -> float:
    txt = _safe_text(text)
    if not txt:
        return 0.0
    hits = sum(1 for word in words if word in txt)
    return min(1.0, hits / max(1, full_hit_count))


def _measure_target_clarity(text: str) -> float:
    context = _get_page_context(text)
    headline_zone = _build_page_zone(context, include_body=False)
    full_zone = _build_page_zone(context, include_body=True)

    explicit_target = 1.0 if re.search(r"(こんな方|こんな人|向け|対象|あなた)", headline_zone) else 0.0
    headline_score = _keyword_coverage(headline_zone, TARGET_CLARITY_WORDS, 3)
    full_score = _keyword_coverage(full_zone, TARGET_CLARITY_WORDS, 4)

    return min(1.0, headline_score * 0.5 + full_score * 0.25 + explicit_target * 0.25)


def _measure_benefit_clarity(text: str) -> float:
    context = _get_page_context(text)
    headline_zone = _build_page_zone(context, include_body=False)
    full_zone = _build_page_zone(context, include_body=True)

    headline_score = _keyword_coverage(headline_zone, BENEFIT_WORDS, 3)
    full_score = _keyword_coverage(full_zone, BENEFIT_WORDS, 5)
    explicit_value = 1.0 if re.search(r"(できる|わかる|伝わる|見える|解決|改善)", headline_zone) else 0.0

    return min(1.0, headline_score * 0.45 + full_score * 0.35 + explicit_value * 0.20)


def _measure_cta_flow(text: str) -> float:
    context = _get_page_context(text)
    full_zone = _build_page_zone(context, include_body=True)
    cta_score = _keyword_coverage(full_zone, CTA_WORDS, 3)
    cta_buttons_score = 1.0 if _safe_text(context.get("cta_buttons", "")) else 0.0
    section_count_score = min(1.0, len(context.get("sections", [])) / 4)
    has_core_flow = 1.0 if _safe_text(context.get("h1", "")) and len(context.get("body", [])) >= 2 else 0.0

    return min(1.0, cta_score * 0.35 + cta_buttons_score * 0.15 + section_count_score * 0.25 + has_core_flow * 0.25)


def _measure_conciseness(text: str) -> float:
    context = _get_page_context(text)
    headline = " ".join([_safe_text(context.get("page_title", "")), _safe_text(context.get("h1", ""))]).strip()
    body_parts = context.get("body", [])
    long_body_count = len([part for part in body_parts if len(_safe_text(part)) >= 140])
    score = 1.0

    if len(headline) >= 80:
        score -= 0.20
    if len(headline) >= 120:
        score -= 0.15
    if long_body_count >= 4:
        score -= 0.20
    if len(body_parts) >= 10:
        score -= 0.10

    return max(0.0, min(1.0, score))


def _measure_first_view_clarity(text: str) -> float:
    context = _get_page_context(text)
    headline_zone = _build_page_zone(context, include_body=False)
    has_title = 1.0 if _safe_text(context.get("page_title", "")) else 0.0
    has_h1 = 1.0 if _safe_text(context.get("h1", "")) else 0.0
    benefit_score = _keyword_coverage(headline_zone, BENEFIT_WORDS, 3)
    target_score = _keyword_coverage(headline_zone, TARGET_CLARITY_WORDS, 3)

    return min(1.0, has_title * 0.20 + has_h1 * 0.20 + benefit_score * 0.30 + target_score * 0.30)


def _measure_curiosity(text: str) -> float:
    context = _get_page_context(text)
    headline_zone = _build_page_zone(context, include_body=False)
    question_bonus = 1.0 if re.search(r"[?？]", headline_zone) else 0.0
    curiosity_words = ["なぜ", "まだ", "もし", "あなた", "見えていない", "本当に", "できていますか"]
    curiosity_score = _keyword_coverage(headline_zone, curiosity_words, 3)
    contrast_bonus = 1.0 if re.search(r"(でも|しかし|一方|なのに)", headline_zone) else 0.0

    return min(1.0, curiosity_score * 0.55 + question_bonus * 0.25 + contrast_bonus * 0.20)


def _measure_anxiety_relief(text: str) -> float:
    return _keyword_coverage(_build_page_zone(_get_page_context(text), include_body=True), ANXIETY_RELIEF_WORDS, 4)


def _measure_trust(text: str) -> float:
    return _keyword_coverage(_build_page_zone(_get_page_context(text), include_body=True), TRUST_WORDS, 4)


def _measure_action_reason(text: str) -> float:
    full_zone = _build_page_zone(_get_page_context(text), include_body=True)
    action_score = _keyword_coverage(full_zone, ACTION_REASON_WORDS, 4)
    explicit_reason = 1.0 if re.search(r"(理由|メリット|得られる|変わる|改善)", full_zone) else 0.0
    return min(1.0, action_score * 0.75 + explicit_reason * 0.25)


def _detail_normalized(detail: Dict[str, Any]) -> float:
    if not isinstance(detail, dict):
        return 0.0
    try:
        return max(0.0, min(1.0, float(detail.get("normalized", 0.0) or 0.0)))
    except Exception:
        return 0.0


def _measure_target_design(log_text: str, output_text: str) -> float:
    combined = "\n".join([_safe_text(log_text), _safe_text(output_text)]).strip()
    if not combined:
        return 0.0

    keyword_score = _keyword_coverage(combined, TARGET_DESIGN_WORDS, 4)
    explicit_score = 1.0 if re.search(r"(ターゲット|誰向け|ペルソナ|主語)", combined) else 0.0

    return min(1.0, keyword_score * 0.70 + explicit_score * 0.30)


def _measure_issue_organization(
    log_text: str,
    structured_steps: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
) -> float:
    total_steps = max(1, len(structured_steps))
    structure_ratio = len(structure_decisions) / total_steps
    reason_ratio = len([step for step in structured_steps if _safe_text(step.get("reason", ""))]) / total_steps
    keyword_score = _keyword_coverage(log_text, ISSUE_ORGANIZATION_WORDS, 4)

    return min(1.0, structure_ratio * 0.45 + reason_ratio * 0.35 + keyword_score * 0.20)


def _measure_ai_craftsmanship(
    structured_steps: List[Dict[str, Any]],
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    judgment_process: Dict[str, Any],
    overall_consistency: Dict[str, Any],
) -> float:
    total_steps = max(1, len(structured_steps))
    linked_steps = len([
        step for step in structured_steps
        if _safe_text(step.get("reason", "")) and (
            _safe_text(step.get("judgment", "")) or _safe_text(step.get("revision", "")) or _safe_text(step.get("adoption", ""))
        )
    ]) / total_steps
    adoption_ratio = len(adoptions) / total_steps
    revision_ratio = len(revisions) / total_steps
    decision_ratio = len(decisions) / total_steps

    return min(
        1.0,
        linked_steps * 0.35
        + adoption_ratio * 0.15
        + revision_ratio * 0.15
        + decision_ratio * 0.10
        + _detail_normalized(judgment_process) * 0.10
        + _detail_normalized(overall_consistency) * 0.15
    )


def _extract_process_evidence(
    decisions: List[Dict[str, Any]],
    revisions: List[Dict[str, Any]],
    adoptions: List[Dict[str, Any]],
    structure_decisions: List[Dict[str, Any]],
) -> List[str]:
    evidence: List[str] = []
    for item in decisions[:1] + revisions[:1] + adoptions[:1] + structure_decisions[:1]:
        text = _safe_text(item.get("text", "")) if isinstance(item, dict) else ""
        if text:
            evidence.append(text)
    return _dedupe(evidence)[:4]


def _extract_output_evidence_priority(text: str, prefer_artifact_context: bool = True) -> List[str]:
    txt = _safe_text(text)
    result: List[str] = []

    page_title = _extract_prefixed_line(txt, "PAGE_TITLE:")
    h1 = _extract_prefixed_line(txt, "H1:")
    h2 = _extract_prefixed_line(txt, "H2:")
    h3 = _extract_prefixed_line(txt, "H3:")
    body = _extract_prefixed_line(txt, "BODY:")
    text_block = _extract_prefixed_line(txt, "TEXT:")
    sections = _extract_prefixed_line(txt, "SECTIONS:")
    cta_buttons = _extract_prefixed_line(txt, "CTA_BUTTONS:")
    lp_headings = _extract_prefixed_line(txt, "LP_HEADINGS:")
    lp_cta_texts = _extract_prefixed_line(txt, "LP_CTA_TEXTS:")
    lp_flow_stages = _extract_prefixed_line(txt, "LP_FLOW_STAGES:")
    lp_cta_positions = _extract_prefixed_line(txt, "LP_CTA_POSITIONS:")
    source_url = _extract_prefixed_line(txt, "SOURCE_URL:")
    target_url = _extract_prefixed_line(txt, "対象URL:")
    artifact_desc = _extract_prefixed_line(txt, "品名・説明:")
    artifact_set_types = _extract_prefixed_line(txt, "ARTIFACT_SET_TYPES:")
    artifact_image_files = _extract_prefixed_line(txt, "ARTIFACT_IMAGE_FILES:")
    artifact_text_line = next(
        (_safe_text(line) for line in txt.splitlines() if _safe_text(line).startswith("ARTIFACT_TEXT[")),
        "",
    )

    if artifact_set_types:
        result.append(f"成果物セット: {artifact_set_types}")
    if artifact_image_files and len(result) < 5:
        result.append(f"画像成果物: {artifact_image_files}")
    if artifact_text_line and len(result) < 5:
        result.append(artifact_text_line[:220])

    if page_title and not _looks_like_noise_text(page_title):
        result.append(f"PAGE_TITLE: {page_title}")
    if h1 and not _looks_like_noise_text(h1):
        result.append(f"H1: {h1}")
    if h2:
        h2_parts = [p.strip() for p in h2.split("/") if p.strip()]
        for part in h2_parts[:2]:
            if not _looks_like_noise_text(part):
                result.append(f"H2: {part}")
    if h3 and len(result) < 5:
        h3_parts = [p.strip() for p in h3.split("/") if p.strip()]
        for part in h3_parts[:1]:
            if not _looks_like_noise_text(part):
                result.append(f"H3: {part}")

    if sections:
        section_parts = [p.strip() for p in sections.split("/") if p.strip()]
        for part in section_parts[:2]:
            if not _looks_like_noise_text(part):
                result.append(f"SECTIONS: {part}")

    if body:
        body_parts = [p.strip() for p in body.split("/") if p.strip()]
        for part in body_parts[:3]:
            if not _looks_like_noise_text(part):
                result.append(f"BODY: {part}")
    elif text_block and not _looks_like_noise_text(text_block):
        result.append(f"TEXT: {text_block}")

    if cta_buttons and len(result) < 5:
        cta_parts = [p.strip() for p in cta_buttons.split("/") if p.strip()]
        for part in cta_parts[:2]:
            if not _looks_like_noise_text(part):
                result.append(f"CTA: {part}")
    if lp_headings and len(result) < 5:
        result.append(f"LP_HEADINGS: {lp_headings}")
    if lp_cta_texts and len(result) < 5:
        result.append(f"LP_CTA_TEXTS: {lp_cta_texts}")
    if lp_flow_stages and len(result) < 5:
        result.append(f"LP_FLOW_STAGES: {lp_flow_stages}")
    if lp_cta_positions and len(result) < 5:
        result.append(f"LP_CTA_POSITIONS: {lp_cta_positions}")

    if not result:
        plain_lines = []
        for line in txt.splitlines():
            clean = _safe_text(line)
            if not clean:
                continue
            if clean.startswith(("品名:", "簡単な説明:", "品名・説明:", "対象URL:", "追加ファイル数:", "- ", "SOURCE_URL:", "URL_FETCH_FAILED:")):
                continue
            plain_lines.append(clean)
        manual_excerpt = " / ".join(plain_lines[:2]).strip()
        if manual_excerpt:
            result.append(f"OUTPUT: {manual_excerpt[:180]}")

    if source_url and len(result) < 4:
        result.append(f"SOURCE_URL: {source_url}")
    if target_url and len(result) < 4 and not source_url:
        result.append(f"対象URL: {target_url}")
    if artifact_desc and prefer_artifact_context and not result:
        result.append(f"品名・説明: {artifact_desc}")

    return _dedupe(result)[:5]

def _extract_prefixed_line(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.replace(prefix, "", 1).strip()
    return ""


def _extract_prefixed_int(text: str, prefix: str) -> int:
    raw = _extract_prefixed_line(text, prefix)
    try:
        return int(raw or 0)
    except Exception:
        return 0


def _extract_prefixed_float(text: str, prefix: str) -> float:
    raw = _extract_prefixed_line(text, prefix)
    try:
        return float(raw or 0.0)
    except Exception:
        return 0.0


def _extract_prefixed_bool(text: str, prefix: str) -> bool:
    raw = _extract_prefixed_line(text, prefix).lower()
    return raw in {"yes", "true", "1"}


def _looks_like_noise_text(text: str) -> bool:
    t = _safe_text(text)
    if not t:
        return True
    if t in {"---", "#", "##", "###"}:
        return True
    if t.startswith("©"):
        return True
    if "All Rights Reserved" in t:
        return True
    return False


def _remove_noise_lines(text: str) -> str:
    rows = []
    for line in str(text).splitlines():
        c = _safe_text(line)
        if not c:
            continue
        if _looks_like_noise_text(c):
            continue
        rows.append(c)
    return "\n".join(rows)


def _extract_keywords(text: str) -> List[str]:
    if not _safe_text(text):
        return []

    text = text.replace("→", " ").replace("・", " ").replace("/", " ")
    tokens = re.findall(r"[A-Za-z0-9_]+|[一-龥ぁ-んァ-ヴー]{2,}", text)

    filtered: List[str] = []
    for token in tokens:
        token = token.strip()
        if len(token) < 2:
            continue
        if token in STOPWORDS:
            continue
        filtered.append(token)

    return filtered


def _is_lp_like(text: str) -> bool:
    txt = _safe_text(text)
    if not txt:
        return False

    if "LP_HERO_SCORE:" in txt and "SCREENSHOT_COUNT:" in txt:
        return True

    lp_hits = sum(1 for word in LP_HINTS if word in txt)
    has_url = ("http://" in txt or "https://" in txt or "対象URL:" in txt)
    has_h1 = "H1:" in txt
    has_body = "BODY:" in txt
    has_sections = "SECTIONS:" in txt

    if has_h1 and has_body and has_sections:
        return True
    if has_url and lp_hits >= 2:
        return True
    if lp_hits >= 4:
        return True
    return False


def _looks_like_structure_decision(text: str) -> bool:
    return _contains_any(text, STRUCTURE_PATTERNS)


def _build_axis_result(
    normalized: float,
    reasons: List[str],
    evidence: List[str],
    risk_flags: List[str],
) -> Dict[str, Any]:
    normalized = max(0.0, min(1.0, normalized))
    score_value = math.floor(normalized * 100)

    return {
        "score": score_value,
        "normalized": round(normalized, 4),
        "reasons": _dedupe([_safe_text(r) for r in reasons if _safe_text(r)])[:4],
        "evidence": _dedupe([_safe_text(e) for e in evidence if _safe_text(e)])[:5],
        "risk_flags": _dedupe([_safe_text(r) for r in risk_flags if _safe_text(r)])[:4],
    }


def _contains_any(text: str, patterns: List[str]) -> bool:
    text = _safe_text(text)
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in patterns)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return "\n".join(str(v) for v in value if v is not None).strip()
    return str(value).strip()


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
