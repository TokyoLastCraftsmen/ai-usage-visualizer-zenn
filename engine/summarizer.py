import re
from typing import Any, Dict, List

AXIS_ORDER = [
    "成果物論理性",
    "判断プロセス",
    "修正プロセス",
    "判断主体性",
    "全体整合性",
]

AXIS_ALIASES = {
    "謌先棡迚ｩ隲也炊諤ｧ": "成果物論理性",
    "蛻､譁ｭ繝励Ο繧ｻ繧ｹ": "判断プロセス",
    "菫ｮ豁｣繝励Ο繧ｻ繧ｹ": "修正プロセス",
    "蛻､譁ｭ荳ｻ菴捺ｧ": "判断主体性",
    "蜈ｨ菴捺紛蜷域ｧ": "全体整合性",
}

TERM_MAP = {
    "classification_copy": "分類導線",
    "classification_structure": "分類構成",
    "classification_title": "分類見出し",
    "classification_label": "分類ラベル",
    "classification": "分類導線",
    "qr": "QRコード連携",
    "qr_flow": "QRコード連携",
    "visual_style": "視覚設計",
    "hero": "冒頭訴求",
    "hero_primary": "冒頭訴求",
    "hero_follow": "冒頭訴求",
    "cta": "行動導線",
    "flow": "導線設計",
}

FORBIDDEN_WORDS = [
    "PAGE_TITLE",
    "SOURCE_URL",
    "URL_FETCH_FAILED",
    "H1",
    "H2",
    "H3",
    "CTA_BUTTONS",
    "SECTIONS",
    "FETCH_MODE",
    "HERO",
    "LP_",
    "SCREENSHOT_",
]

AXIS_VIEWPOINT = {
    "成果物論理性": "成果物側では",
    "判断プロセス": "意思決定面では",
    "修正プロセス": "改善運用面では",
    "判断主体性": "主体性の観点では",
    "全体整合性": "反映整合の観点では",
}

AXIS_FOCUS = {
    "成果物論理性": "情報設計と訴求導線",
    "判断プロセス": "比較検討と理由の明確さ",
    "修正プロセス": "修正の段階性と改善精度",
    "判断主体性": "最終判断の保持と選別の厳密さ",
    "全体整合性": "ログ判断と成果物反映の一致率",
}

VISUAL_AXIS_FOCUS = {
    "成果物論理性": "視覚構成、情報密度、視線誘導",
    "全体整合性": "ログ判断と画面上の配置、強弱、視線誘導の一致率",
}


def _safe(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _safe_int(v: Any) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def summarize(scored: Dict[str, Any], scores: Dict[str, int]) -> Dict[str, Any]:
    scored = scored if isinstance(scored, dict) else {}
    scores = _normalize_scores(scores if isinstance(scores, dict) else {})

    if not scores:
        scores = _normalize_scores(scored.get("scores", {}))

    axis_details = _normalize_axis_details(scored.get("axis_details", {}))
    evaluation_source = scored.get("evaluation_source", {})
    source_mode = _safe(evaluation_source.get("mode")) if isinstance(evaluation_source, dict) else ""
    visual_artifact_mode = source_mode in {"artifact_image_set", "screenshot_lp"}

    total_score = _safe_int(scored.get("total_score", 0))
    if total_score == 0:
        total_score = sum(_safe_int(scores.get(k, 0)) for k in AXIS_ORDER)

    axis_comment_blocks: Dict[str, str] = {}
    axis_comments: Dict[str, str] = {}

    for axis in AXIS_ORDER:
        detail = axis_details.get(axis, {})
        axis_comment_blocks[axis] = _build_axis_comment_block(axis, detail, visual_artifact_mode=visual_artifact_mode)
        axis_comments[axis] = _build_short_comment(axis, detail)

    overall_comment = _build_overall_comment(total_score, axis_comments, axis_details, scores)
    strengths_text = _build_strengths_text(axis_comments, axis_details, scores)
    weaknesses_text = _build_weaknesses_text(axis_comments, axis_details, scores)
    improve_text = _build_improve_text(axis_comments, axis_details, scores)
    risk_text = _build_risk_text(axis_details, scores)
    aptitude_text = _build_aptitude_text(scores, axis_details)
    responsibility_text = _build_responsibility_text(scores, axis_details)
    summary_text = _build_summary_text(overall_comment, strengths_text, improve_text, risk_text)

    url_evaluation = scored.get("url_evaluation", {})
    if not isinstance(url_evaluation, dict):
        url_evaluation = {}

    visual_evaluation = scored.get("visual_evaluation", {})
    if not isinstance(visual_evaluation, dict):
        visual_evaluation = {}

    return {
        "overall_comment": overall_comment,
        "axis_comments": axis_comments,
        "axis_comment_blocks": axis_comment_blocks,
        "strengths_text": strengths_text,
        "weaknesses_text": weaknesses_text,
        "improve_text": improve_text,
        "risk_text": risk_text,
        "aptitude_text": aptitude_text,
        "responsibility_text": responsibility_text,
        "summary_text": summary_text,
        "url_evaluation": url_evaluation,
        "url_evaluation_block": _build_url_evaluation_block(url_evaluation),
        "visual_evaluation": visual_evaluation,
        "visual_evaluation_block": _build_visual_evaluation_block(visual_evaluation),
        "trace_summary": _safe(scored.get("trace_summary", "")),
        "compression_summary": _safe(scored.get("compression_summary", "")),
        "unclassified_comment": _humanize_terms(_safe(scored.get("unclassified_comment", ""))),
    }


def _normalize_scores(scores: Dict[str, Any]) -> Dict[str, int]:
    result: Dict[str, int] = {}
    if not isinstance(scores, dict):
        return result

    for raw_key, raw_value in scores.items():
        axis = AXIS_ALIASES.get(_safe(raw_key), _safe(raw_key))
        if axis in AXIS_ORDER:
            result[axis] = _safe_int(raw_value)

    return result


def _normalize_axis_details(axis_details: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(axis_details, dict):
        return {}

    normalized: Dict[str, Dict[str, Any]] = {}
    for raw_key, detail in axis_details.items():
        axis = AXIS_ALIASES.get(_safe(raw_key), _safe(raw_key))
        if axis not in AXIS_ORDER:
            continue
        if not isinstance(detail, dict):
            detail = {}
        normalized[axis] = detail
    return normalized


def _build_axis_comment_block(axis: str, detail: Dict[str, Any], visual_artifact_mode: bool = False) -> str:
    reasons = _prepare_fragments(detail.get("reasons", []))
    evidence = _prepare_fragments(detail.get("evidence", []))
    risks = _prepare_fragments(detail.get("risk_flags", []))
    score = _safe_int(detail.get("score", 0))
    viewpoint = AXIS_VIEWPOINT.get(axis, "評価観点では")
    focus = VISUAL_AXIS_FOCUS.get(axis, AXIS_FOCUS.get(axis, axis)) if visual_artifact_mode else AXIS_FOCUS.get(axis, axis)

    risk_seed = risks[0] if risks else ""
    if score >= 58:
        positive_seed = reasons[0] if reasons else (evidence[0] if evidence else "")
        support_seed = reasons[1] if len(reasons) > 1 else (evidence[1] if len(evidence) > 1 else "")
    else:
        # Low-score comments should not turn partial findings into strengths.
        positive_seed = evidence[0] if evidence else ""
        support_seed = ""

    sentences: List[str] = []
    if score >= 86:
        sentences.append(f"{viewpoint}{focus}が高い水準で成立しており、判断結果に再現性があります。")
    elif score >= 72:
        sentences.append(f"{viewpoint}{focus}は実務運用に耐える水準ですが、根拠の明文化でさらに安定します。")
    elif score >= 58:
        sentences.append(f"{viewpoint}{focus}は成立しつつあるものの、品質のばらつきが残っています。")
    else:
        sentences.append(f"{viewpoint}{focus}の成立条件が不足し、評価上の弱点が明確に残っています。")

    if risk_seed:
        sentences.append(_ensure_sentence(risk_seed, prefix="改善に向けては、"))
    if positive_seed:
        prefix = "確認できた範囲として、" if score < 58 else "確認できた根拠として、"
        sentences.append(_ensure_sentence(positive_seed, prefix=prefix))
    if support_seed and support_seed != positive_seed:
        sentences.append(_ensure_sentence(support_seed, prefix="加えて、"))

    text = " ".join(x for x in sentences if x).strip()
    return _fit_length(text, min_len=90, max_len=150)


def _build_short_comment(axis: str, detail: Dict[str, Any]) -> str:
    evidence = _prepare_fragments(detail.get("evidence", []))
    reasons = _prepare_fragments(detail.get("reasons", []))
    risks = _prepare_fragments(detail.get("risk_flags", []))
    score = _safe_int(detail.get("score", 0))

    primary = reasons[0] if reasons else ""
    risk = risks[0] if risks else ""
    focus = AXIS_FOCUS.get(axis, axis)

    sentences: List[str] = []
    if score < 58:
        if risk:
            sentences.append(_ensure_sentence(risk))
        elif evidence:
            sentences.append(_ensure_sentence(evidence[0], prefix="確認できた範囲は、"))
        else:
            sentences.append(_ensure_sentence(f"{focus}は記録が不足している状態です"))
    elif primary:
        sentences.append(_ensure_sentence(primary))
    else:
        if score >= 85:
            sentences.append(_ensure_sentence(f"{focus}が高い水準で成立しています"))
        elif score >= 70:
            sentences.append(_ensure_sentence(f"{focus}は実務運用に耐える水準です"))
        else:
            sentences.append(_ensure_sentence(f"{focus}は改善余地が残る状態です"))

    if risk and score >= 58:
        sentences.append(_ensure_sentence(risk, prefix="今後は、"))
    elif score < 70 and not risk:
        sentences.append("根拠として残る情報を増やす必要があります。")

    return _fit_length(" ".join(sentences[:2]).strip(), min_len=60, max_len=125)


def _build_overall_comment(
    total_score: int,
    axis_comments: Dict[str, str],
    axis_details: Dict[str, Any],
    scores: Dict[str, int],
) -> str:
    ranked_axes = sorted(AXIS_ORDER, key=lambda axis: _safe_int(scores.get(axis, 0)), reverse=True)
    strongest = ranked_axes[0] if ranked_axes else ""
    weakest = ranked_axes[-1] if ranked_axes else ""

    parts = [f"総合点は {total_score} / 500 です。"]

    strong_reason = _first_reason(axis_details.get(strongest, {}))
    weak_risk = _first_risk(axis_details.get(weakest, {}))

    strongest_score = _safe_int(scores.get(strongest, 0)) if strongest else 0
    if strongest and total_score < 300:
        if strong_reason:
            parts.append(f"相対的に点数が高い項目は{strongest}で、{_clean_fragment(strong_reason)}")
        else:
            parts.append(f"相対的に点数が高い項目は{strongest}ですが、総合評価として高評価と断定できる段階ではありません。")
    elif strongest and strongest_score >= 70:
        strong_sentence = strong_reason or axis_comments.get(strongest, "") or "主要判断の根拠が整理され、再現性ある評価につながっています。"
        parts.append(f"強みは{strongest}で、{_clean_fragment(strong_sentence)}")
    elif strongest:
        parts.append(f"相対的に点数が高い項目は{strongest}ですが、高評価として断定できる段階ではありません。")
    if weakest and weakest != strongest:
        if weak_risk:
            parts.append(f"一方で{weakest}は、{weak_risk}")
        else:
            parts.append(f"一方で{weakest}は、反映根拠を補うことで評価の安定性を高められます。")

    if total_score >= 350:
        parts.append("総合的には、対話ログと成果物の対応づけは一定程度確認できます。今後は未反映判断の圧縮と根拠の明文化により、説明の安定性を高められます。")
    else:
        parts.append("総合的には、対話ログから読み取れる判断や修正の根拠が限られています。現時点では、記録が残っている内容と不足している内容を分けて扱う必要があります。")
    return _fit_length(" ".join(parts).strip(), min_len=180, max_len=250)


def _build_strengths_text(
    axis_comments: Dict[str, str],
    axis_details: Dict[str, Any],
    scores: Dict[str, int],
) -> str:
    ranked_axes = sorted(AXIS_ORDER, key=lambda axis: _safe_int(scores.get(axis, 0)), reverse=True)
    bullets: List[str] = []
    for axis in ranked_axes:
        if _safe_int(scores.get(axis, 0)) < 70:
            continue
        seed = _first_reason(axis_details.get(axis, {})) or _trim_sentence(axis_comments.get(axis, ""))
        if not seed:
            continue
        line = _fit_length(f"・{axis}：{_clean_fragment(seed)}", min_len=32, max_len=56)
        if line not in bullets:
            bullets.append(line)
        if len(bullets) >= 3:
            break
    return "\n".join(bullets)


def _build_weaknesses_text(
    axis_comments: Dict[str, str],
    axis_details: Dict[str, Any],
    scores: Dict[str, int],
) -> str:
    ranked_axes = sorted(AXIS_ORDER, key=lambda axis: _safe_int(scores.get(axis, 0)))
    bullets: List[str] = []
    for axis in ranked_axes:
        seed = _first_risk(axis_details.get(axis, {}))
        if not seed:
            seed = f"{axis}では、判断根拠と成果反映の対応づけを明文化すると評価の安定性が向上します。"
        line = _fit_length(f"・{axis}：{_clean_fragment(seed)}", min_len=32, max_len=56)
        if line not in bullets:
            bullets.append(line)
        if len(bullets) >= 3:
            break
    return "\n".join(bullets)


def _build_improve_text(
    axis_comments: Dict[str, str],
    axis_details: Dict[str, Any],
    scores: Dict[str, int],
) -> str:
    ranked_axes = sorted(AXIS_ORDER, key=lambda axis: _safe_int(scores.get(axis, 0)))
    fragments: List[str] = []
    for axis in ranked_axes[:3]:
        risk = _first_risk(axis_details.get(axis, {}))
        if risk:
            fragments.append(f"{axis}では、{_clean_fragment(risk)}")
        else:
            fragments.append(f"{axis}では、判断の根拠と成果反映の対応を明文化すると評価の説得力が高まります。")
    text = " ".join(_ensure_sentence(x) for x in fragments if x)
    text = f"{text} 改善は「未反映判断の解消」「理由記録の粒度統一」「成果物への反映確認」の順で進めると、短期間でも評価上昇につながります。"
    return _fit_length(text, min_len=100, max_len=180)


def _build_risk_text(axis_details: Dict[str, Any], scores: Dict[str, int]) -> str:
    ranked_axes = sorted(AXIS_ORDER, key=lambda axis: _safe_int(scores.get(axis, 0)))
    fragments: List[str] = []
    for axis in ranked_axes[:3]:
        risk = _first_risk(axis_details.get(axis, {}))
        if risk:
            fragments.append(f"{axis}においては、{_clean_fragment(risk)}")
    if not fragments:
        fragments.append("重大なリスクは限定的ですが、判断根拠の記録粒度を揃えることで再現性をさらに高められます。")
    text = " ".join(_ensure_sentence(x) for x in fragments if x)
    return _fit_length(text, min_len=100, max_len=180)


def _build_aptitude_text(scores: Dict[str, int], axis_details: Dict[str, Any]) -> str:
    ranked_axes = sorted(AXIS_ORDER, key=lambda axis: _safe_int(scores.get(axis, 0)), reverse=True)
    top_axes = ranked_axes[:2]
    top_score = _safe_int(scores.get(top_axes[0], 0)) if top_axes else 0
    if top_score >= 70:
        body = (
            f"{'・'.join(top_axes)}の評価が相対的に高く、確認できた範囲では要件整理や判断記録に強みがあります。"
            "ただし、活用可能領域は実際に残っている判断根拠と修正記録の範囲で判断する必要があります。"
        )
    else:
        weak = _first_risk(axis_details.get(ranked_axes[-1], {})) if ranked_axes else ""
        body = (
            f"現時点では、高い適性として断定できる項目は限定的です。"
            f"{_clean_fragment(weak) if weak else '判断理由や修正履歴の記録を増やすことで、活用可能領域をより正確に評価できます。'}"
        )
    return _fit_length(body, min_len=100, max_len=180)


def _build_responsibility_text(scores: Dict[str, int], axis_details: Dict[str, Any]) -> str:
    agency = _safe_int(scores.get("判断主体性", 0))
    coherence = _safe_int(scores.get("全体整合性", 0))
    if agency >= 70:
        body = (
            f"判断主体性は {agency} 点で、人が最終判断を担った記録が一定程度確認できます。"
            f"一方、全体整合性は {coherence} 点であり、意思決定の記録を成果物へ対応付ける運用を強める余地があります。"
        )
    else:
        agency_risk = _first_risk(axis_details.get("判断主体性", {}))
        body = (
            f"判断主体性は {agency} 点で、最終判断の所在を十分に説明するには記録が不足しています。"
            f"{_clean_fragment(agency_risk) if agency_risk else 'AI案に対して人が何を選び、何を見送ったかを残す必要があります。'}"
        )
    return _fit_length(body, min_len=100, max_len=180)


def _build_summary_text(
    overall_comment: str,
    strengths_text: str,
    improve_text: str,
    risk_text: str,
) -> str:
    fragments: List[str] = []
    for candidate in [overall_comment, improve_text, risk_text]:
        clean = _clean_fragment(candidate)
        if clean and clean not in fragments:
            fragments.append(clean)
    return _fit_length(" ".join(_ensure_sentence(x) for x in fragments), min_len=140, max_len=220)


def _build_url_evaluation_block(url_evaluation: Dict[str, Any]) -> str:
    if not isinstance(url_evaluation, dict) or not url_evaluation.get("enabled"):
        return ""

    scores = url_evaluation.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}

    lines = [
        f"文章構造: {_safe_int(scores.get('文章構造', 0))}",
        f"訴求力: {_safe_int(scores.get('訴求力', 0))}",
        f"AI活用度: {_safe_int(scores.get('AI活用度', 0))}",
        f"総合: {_safe_int(url_evaluation.get('total_score', 0))}",
    ]

    comment = _humanize_terms(_safe(url_evaluation.get("comment", "")))
    if comment:
        lines.append("")
        lines.append(comment)

    return "\n".join(lines).strip()


def _build_visual_evaluation_block(visual_evaluation: Dict[str, Any]) -> str:
    if not isinstance(visual_evaluation, dict):
        return ""

    scores = visual_evaluation.get("scores", {})
    if not isinstance(scores, dict):
        scores = {}

    lines: List[str] = []

    if visual_evaluation.get("enabled"):
        lines.extend([
            f"第一印象: {_safe_int(scores.get('第一印象', 0))}",
            f"視線導線: {_safe_int(scores.get('視線導線', 0))}",
            f"余白設計: {_safe_int(scores.get('余白設計', 0))}",
            f"信頼感: {_safe_int(scores.get('信頼感', 0))}",
            f"CTA視認性: {_safe_int(scores.get('CTA視認性', 0))}",
            f"情報密度: {_safe_int(scores.get('情報密度', 0))}",
            f"スマホ閲覧性: {_safe_int(scores.get('スマホ閲覧性', 0))}",
            f"離脱リスク: {_safe_int(scores.get('離脱リスク', 0))}",
            f"総合: {_safe_int(visual_evaluation.get('total_score', 0))}",
        ])
        comment = _humanize_terms(_safe(visual_evaluation.get("comment", "")))
        if comment:
            lines.append("")
            lines.append(comment)
        summary = _humanize_terms(_safe(visual_evaluation.get("summary", "")))
        if summary:
            lines.append(summary)
    else:
        message = _humanize_terms(_safe(visual_evaluation.get("message", "")))
        if message:
            lines.append(message)

    return "\n".join(lines).strip()


def _prepare_fragments(value: Any) -> List[str]:
    result: List[str] = []
    for item in _to_list(value):
        clean = _clean_fragment(item)
        if clean and _is_usable_fragment(clean) and clean not in result:
            result.append(clean)
    return result


def _first_reason(detail: Any) -> str:
    if not isinstance(detail, dict):
        return ""
    reasons = _prepare_fragments(detail.get("reasons", []))
    if reasons:
        return _ensure_sentence(reasons[0])
    evidence = _prepare_fragments(detail.get("evidence", []))
    if evidence:
        return _ensure_sentence(evidence[0])
    return ""


def _first_risk(detail: Any) -> str:
    if not isinstance(detail, dict):
        return ""
    risks = _prepare_fragments(detail.get("risk_flags", []))
    if risks:
        return _ensure_sentence(risks[0])
    return ""


def _clean_fragment(text: str) -> str:
    clean = _humanize_terms(_safe(text))
    before_after_placeholder = "__BEFORE_AFTER__"
    clean = re.sub(r"(?:before\s*/\s*after)+", before_after_placeholder, clean, flags=re.IGNORECASE)
    clean = re.sub(r"(?<!before/after)の変化と反映箇所", "before/afterの変化と反映箇所", clean)
    clean = re.sub(r"(?<!before/after)の差分、試行結果", "before/afterの差分、試行結果", clean)
    clean = re.sub(r"^スコア[:：].*$", "", clean)
    clean = re.sub(r"^(根拠|評価理由|改善余地)[:：]?\s*", "", clean)
    clean = clean.replace("URL取得が未完了のため、この軸は評価保留です", "")
    clean = clean.replace("評価保留: URL取得完了後に再評価", "")
    clean = re.sub(r"変更前\s*[:：]?", "", clean)
    clean = re.sub(r"変更後\s*[:：]?", "", clean)
    clean = clean.strip("・ ")
    clean = re.sub(r"\s*/\s*", "、", clean)
    clean = clean.replace(before_after_placeholder, "before/after")
    clean = re.sub(r"\s*→\s*", "→", clean)
    clean = re.sub(r"\s+", " ", clean)
    clean = re.sub(r"(before/after){2,}", "before/after", clean)
    clean = re.sub(r"、{2,}", "、", clean)
    clean = re.sub(r"・{2,}", "・", clean)
    clean = re.sub(r"・\s*、|、\s*・", "、", clean)
    clean = re.sub(r"^\s*[、・]+", "", clean)
    clean = clean.replace("[", "").replace("]", "").replace("'", "")
    for term in FORBIDDEN_WORDS:
        clean = re.sub(re.escape(term), "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^[:：、。・\-\s]+", "", clean)
    clean = re.sub(r"[:：]\s*$", "", clean)
    clean = re.sub(r"根拠として\s*、?\s*$", "", clean)
    clean = re.sub(r"確認できた根拠として\s*、?\s*$", "", clean)
    return clean.strip()


def _humanize_terms(text: str) -> str:
    value = _safe(text)
    if not value:
        return ""
    before_after_placeholder = "__BEFORE_AFTER__"
    value = re.sub(r"(?:before\s*/\s*after)+", before_after_placeholder, value, flags=re.IGNORECASE)
    for key, label in TERM_MAP.items():
        value = re.sub(rf"\b{re.escape(key)}\b", label, value)
    value = value.replace(",", "、")
    value = re.sub(r"\s*、\s*", "、", value)
    value = re.sub(r"\s*/\s*", "、", value)
    value = value.replace(before_after_placeholder, "before/after")
    return value.strip()


def _ensure_sentence(text: str, prefix: str = "") -> str:
    clean = _clean_fragment(text)
    if not clean:
        return ""
    sentence = f"{prefix}{clean}".strip()
    if sentence[-1] not in "。.!?！？":
        sentence += "。"
    return sentence


def _trim_sentence(text: str) -> str:
    clean = _safe(text).rstrip("。")
    if not clean:
        return ""
    return f"{clean}。"


def _to_list(v: Any) -> List[str]:
    if isinstance(v, list):
        return [str(x) for x in v if str(x).strip()]
    if isinstance(v, str) and v.strip():
        return [v.strip()]
    return []


def _fit_length(text: str, min_len: int, max_len: int) -> str:
    clean = re.sub(r"\s+", " ", _safe(text))
    if not clean:
        return ""
    if len(clean) > max_len:
        clean = clean[:max_len].rstrip(" 、。")
        if clean and clean[-1] not in "。.!?！？":
            clean += "。"
    return clean[:max_len].strip()


def _is_usable_fragment(text: str) -> bool:
    t = _safe(text)
    if not t:
        return False
    if len(t) < 8:
        return False
    if not re.search(r"[ぁ-んァ-ヶ一-龠A-Za-z0-9]", t):
        return False
    if re.match(r"^(が|を|に|で|と|は|も|、|。|:|：)", t):
        return False
    if re.search(r"(取得されており|確認できます)$", t) and len(t) < 18:
        return False
    return True
