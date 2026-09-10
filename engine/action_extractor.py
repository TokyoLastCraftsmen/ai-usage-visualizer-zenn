"""Deterministic auxiliary action extraction, independent of the scorer."""

from __future__ import annotations

import re
from typing import Any


_ROLE_RE = re.compile(
    r"(?im)^(?:\s*(?:(?P<number>\d+)\.\s*)?(?P<role>user|human|assistant|ai)\s*:\s?"
    r"|\s*---\s*(?:(?P<delim_number>\d+)\.\s*)?(?P<delim_role>user|human|assistant|ai)\s*---\s*(?:\r?\n|$))"
)


def _user_messages(conversation_log: str) -> list[tuple[str, str]]:
    text = str(conversation_log or "")
    markers = list(_ROLE_RE.finditer(text))
    messages: list[tuple[str, str]] = []
    user_number = 0
    for index, marker in enumerate(markers):
        role = (marker.group("role") or marker.group("delim_role") or "").lower()
        if role not in {"user", "human"}:
            continue
        user_number += 1
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        messages.append((f"user-{user_number}", text[marker.end():end]))
    return messages


def _contains(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def _polarity(text: str, positive: tuple[str, ...], negative: tuple[str, ...]) -> str | None:
    if _contains(text, negative):
        return "negative"
    if _contains(text, positive):
        return "positive"
    return None


def _before_after(text: str) -> tuple[str, str]:
    before = re.search(r"(?:before|\u5909\u66f4\u524d)\s*[:\uff1a]?\s*(.+?)(?=(?:after|\u5909\u66f4\u5f8c)\s*[:\uff1a]|$)", text, re.I | re.S)
    after = re.search(r"(?:after|\u5909\u66f4\u5f8c)\s*[:\uff1a]?\s*(.+)$", text, re.I | re.S)
    if before or after:
        return (before.group(1).strip() if before else "", after.group(1).strip() if after else "")
    transition = re.search(r".{1,120}?\u3092(.{1,120}?)\u304b\u3089\s*(.{1,120}?)(?:\u3078|\u306b)\s*(?:\u5909\u66f4|\u4fee\u6b63|\u5dee\u3057\u66ff\u3048)", text)
    if transition:
        return transition.group(1).strip(), transition.group(2).strip()
    transition = re.search(r"(.{1,120}?)\u304b\u3089\s*(.{1,120}?)(?:\u3078|\u306b)\s*(?:\u5909\u66f4|\u4fee\u6b63|\u5dee\u3057\u66ff\u3048)", text)
    if transition:
        return transition.group(1).strip(), transition.group(2).strip()
    transition = re.search(r"from\s+(.{1,120}?)\s+to\s+(.{1,120}?)(?=\s+(?:because|since)|[.!?]|$)", text, re.I)
    return (transition.group(1).strip(), transition.group(2).strip()) if transition else ("", "")


def _target(text: str, action_type: str) -> str:
    if action_type == "revision":
        target_match = re.search(r"(.{1,120}?)\u3092.{1,120}?\u304b\u3089.{1,120}?(?:\u3078|\u306b)\s*\u5909\u66f4", text)
        if target_match:
            return target_match.group(1).strip()
    patterns = {
        "comparison": r"((?:A\u6848|A)\s*(?:\u3068|and)\s*(?:B\u6848|B))",
        "rejection": r"([A-Za-z0-9\u3041-\u9fff]{1,20}?)(?=\s*(?:\u306f|\u3092)\s*(?:\u63a1\u7528\u3057\u306a\u3044|\u4e0d\u63a1\u7528|\u5374\u4e0b|\u4f7f\u308f\u306a\u3044|do not adopt|don't adopt|not adopt|reject))",
        "adoption": r"([A-Za-z0-9\u3041-\u9fff]{1,20}?)(?=\s*(?:\u3092)?\s*(?:\u63a1\u7528\u3059\u308b|\u63a1\u7528\u3057\u305f|\u9078\u3076\u3053\u3068\u306b\u3057\u305f|\u9078\u3076|adopt(?:ed|ing)?|accept(?:ed|ing)?|keep))",
        "revision": r"((?:[A-Za-z0-9\u3041-\u9fff]{1,80})?)(?=\u304b\u3089\s*[^\u3002\uff01\uff1f]{1,80}(?:\u3078|\u306b)\s*\u5909\u66f4)|((?:[A-Za-z0-9\u3041-\u9fff]{1,80})?)(?=\s*(?:\u3092)?\s*(?:\u5909\u66f4\u3057\u305f|\u5909\u66f4\u3059\u308b|\u4fee\u6b63\u3057\u305f|\u4fee\u6b63\u3059\u308b))",
        "priority_change": r"(?:\u88c5\u98fe\u306e\u591a\u3055\u3088\u308a\u3082\s*)(.+?)(?=\s*\u3092?\s*\u4e0a\u4f4d\u306b\u7f6e\u304f|\s*priority)",
        "policy_change": r"(?:\u307e\u305f\u3001)?\s*(.+?\u65b9\u91dd)(?=\s*(?:\u3092)?\s*\u5909\u66f4|\s*policy)",
        "reason": r"((?:[A-Za-z0-9\u3041-\u9fff]{1,80})(?:\u7406\u7531|reason|rationale|purpose))",
    }
    pattern = patterns.get(action_type)
    if pattern:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            for group in match.groups():
                if group and group.strip():
                    return group.strip().rstrip("\u3002\uff01\uff1f.!?")
    return text.strip().rstrip("\u3002\uff01\uff1f.!?")


def _make(message_id: str, number: int, raw: str, evidence: str, kind: str, polarity: str, before: str, after: str, reason: str) -> dict[str, Any]:
    return {
        "message_id": message_id,
        "action_id": f"{message_id}-action-{number}",
        "type": kind,
        "polarity": polarity,
        "target": _target(evidence, kind),
        "evidence": evidence,
        "before": before,
        "after": after,
        "reason": reason,
        "raw_message": raw,
    }


def _segments(raw: str) -> list[str]:
    sentences = re.split(r"(?<=[\u3002\uff01\uff1f.!?\uff1b;])\s*|\n+", raw)
    segments: list[str] = []
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # English compound decisions use commas/but as action boundaries.
        if re.search(r"[A-Za-z]", sentence):
            segments.extend(re.sub(r"^(?:but|while)\s+", "", part.strip(), flags=re.I) for part in re.split(r",\s*|\s+(?:but|while)\s+", sentence) if part.strip())
        else:
            segments.append(sentence)
    return segments


def _reason_text(text: str) -> str:
    explicit_reason = re.search(r"(?:\u7406\u7531\u306f|\u306a\u305c\u306a\u3089|\u305d\u306e\u7406\u7531\u3068\u3057\u3066)\s*(?![\u3001\u3002])\S+", text)
    causal_reason = re.search(r"(?:\u304b\u3089\u3067\u3042\u308b|\u304b\u3089\u3067\u3059|because|reason|rationale|purpose)", text, re.I)
    if explicit_reason or causal_reason:
        return text
    return ""


def _comparison_evidence(text: str) -> str:
    if re.search(r"(?:A\u6848|A)\s*(?:\u3068|and)\s*(?:B\u6848|B)\s*(?:\u3092|\u306e)?\s*(?:\u6bd4\u8f03(?:\u3059\u308b|\u3057\u305f|\u691c\u8a0e\u3059\u308b)?|\u6bd4\u3079\u308b|compare|comparison|compare\s+and)", text, re.I):
        return text
    if re.search(r"compare\s+(?:option\s+)?[A-Za-z0-9]+\s+and\s+(?:option\s+)?[A-Za-z0-9]+", text, re.I):
        return text
    return ""


def _adoption_matches(text: str) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    rejection = re.compile(r"(?:\u63a1\u7528\u3057\u306a\u3044|\u4e0d\u63a1\u7528|\u5374\u4e0b(?:\u3059\u308b|\u3057\u305f)?|\u4f7f\u308f\u306a\u3044|do not adopt|don't adopt|not adopt|reject(?:ed|ing)?)", re.I)
    adoption = re.compile(r"(?:\u63a1\u7528\u3059\u308b|\u63a1\u7528\u3057\u305f|\u9078\u3076\u3053\u3068\u306b\u3057\u305f|\u9078\u3076|\u9078\u3093\u3060|adopt(?:ed|ing)?|accept(?:ed|ing)?|keep)", re.I)
    rejection_matches = list(rejection.finditer(text))
    for match in rejection_matches:
        if re.match(r"\s*(?:\u7406\u7531|reason)", text[match.end():], re.I):
            continue
        matches.append(("rejection", match.group(0)))
    for match in adoption.finditer(text):
        if any(rej.start() <= match.start() < rej.end() for rej in rejection_matches):
            continue
        if re.match(r"\s*(?:\u7406\u7531|reason)", text[match.end():], re.I):
            continue
        matches.append(("adoption", match.group(0)))
    return matches


def _revision_evidence(text: str) -> str:
    # Past-tense noun modifiers such as "変更した見出し" are descriptions,
    # not new revision actions.
    if re.search(r"(?:\u5909\u66f4\u3057\u305f|\u4fee\u6b63\u3057\u305f)\s*(?:\u898b\u51fa\u3057|\u7b87\u6240|\u5185\u5bb9)|\u5909\u66f4\u5f8c\u306e\u753b\u9762", text):
        return ""
    if re.search(r"(?:\u304b\u3089\s*[^\u3002\uff01\uff1f]{1,80}(?:\u3078|\u306b)\s*)?(?:\u5909\u66f4\u3059\u308b|\u5909\u66f4\u3057\u305f|\u4fee\u6b63\u3059\u308b|\u4fee\u6b63\u3057\u305f|\u8ffd\u52a0\u3059\u308b|\u524a\u9664\u3059\u308b|\u5dee\u3057\u66ff\u3048\u308b|change|revise|update|replace)|from\s+.{1,120}?\s+to\s+.{1,120}", text, re.I):
        return text
    return ""


def extract_actions(conversation_log: str) -> list[dict[str, Any]]:
    """Extract explicit actions from USER messages; ordinary chat returns []."""
    actions: list[dict[str, Any]] = []
    for message_id, raw in _user_messages(conversation_log):
        number = 1
        priority_action: tuple[str, str] | None = None
        policy_action: tuple[str, str] | None = None
        for evidence in _segments(raw):
            before, after = _before_after(evidence)
            reason = _reason_text(evidence)
            priority_hit = bool(re.search(r"\u512a\u5148\u9806\u4f4d\u3092\u5909\u66f4|\u512a\u5148\u3059\u308b|\u4e0a\u4f4d\u306b\u7f6e\u304f|priority", evidence))
            policy_hit = bool(re.search(r"\u65b9\u91dd\u3092\u5909\u66f4|\u65b9\u91dd\u8ee2\u63db|policy", evidence))

            for kind, _ in _adoption_matches(evidence):
                polarity = "negative" if kind == "rejection" else "positive"
                action_reason = reason
                actions.append(_make(message_id, number, raw, evidence, kind, polarity, before, after, action_reason))
                number += 1

            revision = _revision_evidence(evidence)
            explicit_transition = bool(re.search(r"\u304b\u3089\s*[^\u3002\uff01\uff1f]{1,80}(?:\u3078|\u306b)\s*\u5909\u66f4", evidence))
            if revision and not policy_hit and (not priority_hit or explicit_transition):
                rev_before, rev_after = _before_after(revision)
                actions.append(_make(message_id, number, raw, revision, "revision", "positive", rev_before, rev_after, reason))
                number += 1

            if _comparison_evidence(evidence):
                actions.append(_make(message_id, number, raw, evidence, "comparison", "neutral", before, after, reason))
                number += 1

            if reason and not _adoption_matches(evidence) and not revision:
                actions.append(_make(message_id, number, raw, evidence, "reason", "neutral", before, after, reason))
                number += 1

            if priority_hit:
                priority_action = (evidence, reason)
            if policy_hit:
                policy_action = (evidence, reason)

        if priority_action:
            priority_evidence, priority_reason = priority_action
            actions.append(_make(message_id, number, raw, priority_evidence, "priority_change", "neutral", "", "", priority_reason))
            number += 1
        if policy_action:
            policy_evidence, policy_reason = policy_action
            actions.append(_make(message_id, number, raw, policy_evidence, "policy_change", "neutral", "", "", policy_reason))
            number += 1
    return actions


__all__ = ["extract_actions"]
