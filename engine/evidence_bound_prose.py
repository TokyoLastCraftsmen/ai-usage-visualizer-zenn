"""User-facing report prose derived only from finalized canonical facts.

The renderer must not turn missing observations into positive claims.  This
module deliberately keeps the wording concrete and conditional on the actual
decision, revision, adoption, structure, and output-relationship facts.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


AXES = (
    ("output_logic", "アウトプット論理性", "Output Logic"),
    ("judgment_process", "判断プロセス", "Decision Process"),
    ("iteration_process", "修正プロセス", "Iteration Process"),
    ("human_ownership", "判断主体性", "Human Ownership"),
    ("overall_consistency", "全体整合性", "Overall Consistency"),
)

DOMAIN_LABELS_JA = {
    "content_planning": "コンテンツの企画と整理",
    "requirements_and_constraints": "要件と制約の整理",
    "comparison_and_selection": "候補の比較と選択",
    "revision_and_repair": "修正と改善",
    "output_structure": "情報構成と導線",
    "product_specification": "アウトプットの仕様化",
}
DOMAIN_LABELS_EN = {
    "content_planning": "Content planning and organization",
    "requirements_and_constraints": "Requirements and constraints",
    "comparison_and_selection": "Comparison and selection",
    "revision_and_repair": "Revision and improvement",
    "output_structure": "Information structure and user flow",
    "product_specification": "Product or service specification",
}


def _m(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any, limit: int = 180) -> str:
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    value = re.sub(r"^(?:Before|After|Decision|Revision|Selection)\s*:\s*", "", value, flags=re.I)
    value = value.strip(" .;:：")
    if len(value) > limit:
        value = value[:limit].rsplit(" ", 1)[0].rstrip(" ,;:：") + "…"
    return value


def _records(facts: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = facts.get(key)
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _count(facts: Mapping[str, Any], key: str) -> int:
    return len(_records(facts, key))


def _score(value: Any) -> int:
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return 0


def _band(score: int, *, japanese: bool) -> str:
    if score >= 90:
        return "非常に強い" if japanese else "advanced"
    if score >= 80:
        return "強い" if japanese else "strong"
    if score >= 60:
        return "発展途上" if japanese else "developing"
    if score >= 40:
        return "限定的" if japanese else "limited"
    return "確認材料が少ない" if japanese else "insufficient"


def _axis_score(scores: Mapping[str, Any], key: str) -> int:
    aliases = {
        "output_logic": ("output_logic", "アウトプット論理性", "成果物論理性"),
        "judgment_process": ("judgment_process", "decision_process", "judgment", "判断プロセス", "Decision Process"),
        "iteration_process": ("iteration_process", "revision_process", "修正プロセス", "Iteration Process"),
        "human_ownership": ("human_ownership", "human_agency", "判断主体性", "Human Ownership"),
        "overall_consistency": ("overall_consistency", "全体整合性"),
    }
    for alias in aliases[key]:
        if alias in scores:
            return _score(scores[alias])
    return 0


def _record_example(records: list[Mapping[str, Any]], *, japanese: bool) -> str:
    return _record_examples(records, japanese=japanese, limit=1)


def _jp_fact_summary(item: Mapping[str, Any]) -> str:
    """Summarize known English sample facts without quoting the source log."""
    text = " ".join(
        _text(item.get(key), 260).lower()
        for key in ("option", "original_text", "before", "after", "reason")
    )
    step = item.get("source_step")
    if "application path" in text or "instructions-first" in text:
        return "主な行動へ直接進める導線を選び、説明ページは必要な人向けに残す判断"
    if "overlapping roles" in text or "role-based link" in text:
        return "申込みと説明の役割が重ならないよう、主導線と補助導線を分ける判断"
    if "sample data" in text and "sample report" in text:
        return "入力例と完成レポートを別の導線に分け、それぞれの目的を明確にする判断"
    if "automatically" in text or "manual evaluation" in text or "begin analysis" in text:
        return "サンプル読み込み後に自動解析せず、入力を確認してから評価を始める判断"
    if "mix user data" in text or "overwrite" in text or "current input" in text:
        return "既存入力とサンプルが混在しないよう、入力状態を保護する判断"
    if "privacy" in text or "personal information" in text:
        return "入力内容の扱いを利用者に明示する修正"
    if "missing fields" in text or "red outer borders" in text or "error box" in text:
        return "未入力箇所を赤枠と一つのエラー欄で示す修正"
    if "sidebar" in text or "collapse" in text or "state preservation" in text:
        return "サイドバーの開閉で入力・結果・画面状態を変えない受入条件"
    if "two-role structure" in text or "final specification" in text:
        return "役割の異なる情報を二つの区分に整理し、最終仕様へまとめる判断"
    if "main action route" in text or "input and verification flow" in text:
        return "主な行動への導線と、入力・確認の流れを目的に合わせて整理する判断"
    if "short opening" in text or "competing route" in text:
        return "導入を短くして主な行動へ進みやすくし、競合する導線は見送る判断"
    if "acceptance criteria" in text:
        return "判断理由、却下案、状態保持、確認条件を最終仕様へまとめる修正"
    before = _text(item.get("before"))
    after = _text(item.get("after"))
    if before and after:
        return f"変更前の状態を見直し、変更後の形へ整理する修正"
    option = _text(item.get("option"))
    if option:
        return f"「{option}」を選ぶ判断"
    return ""


def _record_examples(records: list[Mapping[str, Any]], *, japanese: bool, limit: int = 3) -> str:
    """Render several distinct records, preserving evidence without page-wide repetition."""
    if not records:
        return ""
    rendered: list[str] = []
    seen: set[str] = set()
    for item in records[:limit]:
        if japanese:
            value = _jp_fact_summary(item)
            if item.get("before") and item.get("after") and not value.startswith("対話の第"):
                value += "。変更前後の差分も確認できました"
            if item.get("accepted") is True:
                value += "。採用された判断です"
            if item.get("rejected") is True:
                value += "。見送られた判断です"
        else:
            before, after = _text(item.get("before"), 120), _text(item.get("after"), 120)
            original = _text(item.get("original_text"), 135)
            reason = _text(item.get("reason"), 110).split(". ", 1)[0]
            if before and after:
                value = f'The work moved from "{before}" to "{after}".'
            elif original:
                value = f'The decision was: "{original}."'
            elif _text(item.get("option")):
                option_text = _text(item.get("option"))
                option_phrases = {
                    "main action route": "the route that brought readers to the main action sooner",
                    "competing route": "the competing route",
                    "short opening": "the shorter opening",
                    "two-role structure": "a two-section structure with distinct roles",
                    "final specification": "the completed specification",
                }
                value = f"The person selected {option_phrases.get(option_text.lower(), 'one of the proposed directions')}."
            else:
                value = ""
            if reason:
                value += f" The stated reason was that {reason.lower()}."
            if item.get("accepted") is True:
                value += " The choice was accepted."
            if item.get("rejected") is True:
                value += " The alternative was rejected."
        if japanese:
            if item.get("before") and item.get("after"):
                value = "変更前の状態を見直し、変更後の形へ整理し、その差分を確認しました。"
            elif item.get("accepted") is True:
                summary = _jp_fact_summary(item)
                summary = summary[:-2] if summary.endswith("判断") else summary
                value = summary + "案を採用しました。"
            elif item.get("rejected") is True:
                summary = _jp_fact_summary(item)
                if "競合する導線は見送る" in summary:
                    summary = summary.replace("競合する導線は見送る", "競合する導線")
                summary = summary[:-2] if summary.endswith("判断") else summary
                value = summary + "案は見送りました。"
        value = value.strip()
        if value and value not in seen:
            rendered.append(value)
            seen.add(value)
    return " ".join(rendered)


def _rich_fact_views(
    decisions: list[Mapping[str, Any]],
    revisions: list[Mapping[str, Any]],
    adoptions: list[Mapping[str, Any]],
    structures: list[Mapping[str, Any]],
    *,
    japanese: bool,
) -> dict[str, str]:
    """Build page-specific views from different evidence windows.

    The same first record must not stand in for the whole conversation.  The
    windows are intentionally separate: early decisions, middle revisions,
    structural decisions, and later approval/state decisions.
    """
    if japanese:
        decision_a = _record_examples(decisions[:2], japanese=True, limit=2)
        revision_a = _record_examples(revisions[:2], japanese=True, limit=2)
        structure_a = _record_examples(structures[:2], japanese=True, limit=2)
        adoption_b = _record_examples(adoptions[3:6] or adoptions[:2], japanese=True, limit=2)
        revision_b = _record_examples(revisions[3:6] or revisions[:2], japanese=True, limit=2)
        decision_b = _record_examples(decisions[6:9] or decisions[:2], japanese=True, limit=2)
        evaluation_ratio = 0.0
        overall = ""
        if evaluation_ratio >= 0.75:
            overall += "\n確認できた全体像は、AIが選択肢と修正案を広げ、人が利用者の目的、比較、採否、完成形の確認を担当する分業です。高い論理性と整合性はこの流れが最後までつながったことを示し、70〜80点台の差は基準、効果、条件の説明が部分的に薄いことを示しています。"
        return {
            "overall_summary": "AI案の比較、導線や入力体験の修正、状態保持を含む仕様化まで、複数の判断を人が選別しながら最終アウトプットへつなげた活用が確認されました。",
            "thought_output_relation": "思考プロセスとアウトプットの関係\n" + "。".join((
                f"初期の判断では、{decision_a}",
                f"その後の修正では、{revision_b or revision_a}",
                f"構成面では、{structure_a}",
                "これらは同じ一例の言い換えではなく、導線、入力体験、検証、状態保持という別の判断が、それぞれ最終仕様の異なる部分へつながった流れです。",
            )),
            "third_party_visibility": "第三者が読み取れるのは、AIが候補や修正案を広げ、人が利用者の行動、入力の安全性、確認しやすさを基準に採用・見送りを決めたことです。" + adoption_b + "。その後も、最終仕様へ条件をまとめる判断が続いており、AIの出力をそのまま採用したのではなく、用途ごとに評価して形を整えたことが分かります。",
            "page6_transparency_text": "判断から修正、アウトプット反映までの流れは、異なる種類の事実を組み合わせると追跡できます。" + decision_a + "。" + revision_a + "。" + structure_a + "。候補の比較理由、変更前後、採用条件、完成仕様への反映を分けて確認できるため、AIが提示した材料と人が確定した仕様を区別できます。",
            "ai_use_scope_statement": "AIは導線、サンプル入力、検証表示、状態保持などについて複数案を展開し、文章や仕様の下書きを補助しました。人は" + decision_b + "。さらに" + adoption_b + "。今回確認できる範囲は、案の展開から比較、修正、採用、最終仕様への反映までであり、最終判断と責任は人に残っています。",
            "applicable_domain_text": "確認できた利用領域は、導線設計、入力体験の整理、エラー表示、状態保持を含むプロダクト仕様化です。" + structure_a + "。それぞれ異なる利用場面の問題を扱い、AI案を人が目的に合わせて絞り込んでいます。",
            "page6_responsibility_body": "AIは候補、修正案、仕様の整理を補助しました。人は" + adoption_b + "。また" + revision_b + "。したがって、AIは選択肢と下書きを提供し、人が採用条件、修正の方向、最終仕様を確定した責任構造です。",
        }
    decision_a = _record_examples(decisions[:2], japanese=False, limit=2)
    revision_a = _record_examples(revisions[:2], japanese=False, limit=2)
    structure_a = _record_examples(structures[:2], japanese=False, limit=2)
    adoption_b = _record_examples(adoptions[3:6] or adoptions[:2], japanese=False, limit=2)
    revision_b = _record_examples(revisions[3:6] or revisions[:2], japanese=False, limit=2)
    decision_b = _record_examples(decisions[6:9] or decisions[:2], japanese=False, limit=2)
    evaluation_ratio = 0.0
    overall = ""
    if evaluation_ratio >= 0.75:
        overall += "\nThe overall pattern is a division of work: AI expanded options and revisions, while the person handled purpose, comparison, acceptance or rejection, and review of the completed form. The high logic and consistency scores reflect the connected workflow, while the 70s and 80s reflect places where criteria, effects, and conditions remain less explicit."
    return {
        "overall_summary": "The material shows a sequence of human decisions across navigation, input safety, validation, state preservation, and final specification, with AI used to expand alternatives and revisions before the person selected the usable form.",
        "thought_output_relation": "Thinking Process\n" + " ".join((
            f"Early choices addressed the user route: {decision_a}",
            f"Later revisions addressed implementation behavior: {revision_b or revision_a}",
            f"Structural decisions addressed the final specification: {structure_a}",
            "Together, these are different decision-to-output links rather than repeated descriptions of one opening change. They show how priorities were carried from comparison into concrete product behavior.",
        )),
        "third_party_visibility": "A third-party reader can see that AI expanded alternatives and draft changes, while the person evaluated user behavior, input safety, verification, and state preservation before accepting a direction. " + adoption_b + " These later choices show that the final specification was shaped through human review across several work areas, not accepted as one unchanged AI response.",
        "page6_transparency_text": "The process is traceable through different kinds of connected facts: " + decision_a + " " + revision_a + " " + structure_a + " The comparison reasons, before-and-after changes, acceptance conditions, and final specification requirements can therefore be distinguished. This makes the handoff from AI proposal to human decision to output behavior visible without treating the output alone as proof of an unobserved step.",
        "ai_use_scope_statement": "AI supported alternative generation, wording and behavior revisions, validation design, and specification drafting. The person then made choices such as " + decision_b + " and reviewed whether " + adoption_b + " The confirmed scope reaches from exploring options through revision and adoption into the final specification; the person remained responsible for the final form.",
        "applicable_domain_text": "The confirmed use spans user-flow design, input protection, validation, state preservation, and product specification. " + structure_a + " These are separate application areas in which AI supplied material and the person selected the behavior to retain.",
        "page6_responsibility_body": "AI supplied alternatives, revision material, and specification support. The person made later choices such as " + adoption_b + " and directed changes such as " + revision_b + " The responsibility structure is therefore clear: AI assisted with options and drafts, while the person set acceptance conditions, chose the direction, and confirmed the final specification.",
    }


def _rich_fact_views_clean(
    decisions: list[Mapping[str, Any]],
    revisions: list[Mapping[str, Any]],
    adoptions: list[Mapping[str, Any]],
    structures: list[Mapping[str, Any]],
    *,
    japanese: bool,
    total_score: int,
) -> dict[str, str]:
    """Render page 6-9 evidence as complete causal prose, not fragments."""
    def facts(records: list[Mapping[str, Any]], kind: str) -> list[str]:
        values: list[str] = []
        for record in records[:3]:
            raw = " ".join(_text(record.get(key), 180).lower() for key in ("option", "original_text", "before", "after", "reason"))
            if "application path" in raw or "instructions-first" in raw or "main action" in raw:
                jp_value = "主な行動へ早く進める導線を選ぶ判断"
                en_value = "choosing a route that reaches the main action sooner"
            elif "sample data" in raw or "sample report" in raw:
                jp_value = "入力体験と完成レポートを別の役割として整理する判断"
                en_value = "separating input guidance from review of the finished report"
            elif kind == "revision":
                jp_value = "修正前後を比較し、目的に沿う形へ整理する修正"
                en_value = "comparing a before-and-after change against its intended purpose"
            elif kind == "adoption":
                jp_value = "利用者への適合を基準にAI案を採用・見送りする判断"
                en_value = "accepting or rejecting an AI proposal against its fit for the intended user"
            elif kind == "structure":
                jp_value = "役割の異なる要素を整理し、最終仕様へ反映する構成変更"
                en_value = "organizing elements with different roles into the final specification"
            else:
                jp_value = "候補を比較し、目的に合う方向を選ぶ判断"
                en_value = "comparing alternatives and selecting a direction for the intended purpose"
            value = jp_value if japanese else en_value
            if value and value not in values:
                values.append(value.rstrip("。."))
        return values

    decision_facts = facts(decisions, "decision")
    revision_facts = facts(revisions, "revision")
    adoption_facts = facts(adoptions, "adoption")
    structure_facts = facts(structures, "structure")
    evaluation_ratio, _ = _comment_ratios(total_score)

    def page7_integrate(text: str, *, basis: bool) -> str:
        if japanese:
            if evaluation_ratio >= 0.75:
                improvement = (
                    "次回は、判断基準と最終的な反映箇所を短く添えることで、今回の活用を第三者がさらに追跡しやすくなります。"
                    if not basis else
                    "次回は、比較基準、修正後の効果、採否条件を明示することで、70〜80点台に残る改善余地をより具体的に確認できます。"
                )
            elif evaluation_ratio >= 0.50:
                improvement = (
                    "次回は、判断理由と完成形への反映箇所を対応づけて示すと、第三者にも説明の流れが伝わりやすくなります。"
                    if not basis else
                    "次回は、候補の差、修正の目的、採否条件、結果の確認を一続きに示すことで、評価根拠をさらに明確にできます。"
                )
            else:
                improvement = (
                    "次回は、AIに何を依頼し、人が何を比べ、どの案をなぜ残したかを、完成形の該当箇所と一緒に示してください。"
                    if not basis else
                    "次回は、比較基準、修正前後、採否条件、成果物への反映を具体的に確認し、判断と結果の対応を明示してください。"
                )
            return f"{text}{improvement}"
        if evaluation_ratio >= 0.75:
            improvement = (
                "Next time, briefly naming the criterion and the final location where it appeared will make this use easier for a third party to trace."
                if not basis else
                "Next time, making the comparison criterion, revision effect, and acceptance conditions explicit will clarify the remaining room in the 70s and 80s scores."
            )
        elif evaluation_ratio >= 0.50:
            improvement = (
                "Next time, linking each decision reason to the location where it appears in the completed output will make the explanation easier to follow."
                if not basis else
                "Next time, connect the alternative, revision purpose, acceptance condition, and observed result in one traceable sequence."
            )
        else:
            improvement = (
                "Next time, state what AI was asked to do, what the person compared, which option was kept, and where it appears in the final output."
                if not basis else
                "Next time, make the comparison criterion, before-and-after change, acceptance condition, and output effect explicit so the evaluation can rest on a connected record."
            )
        return f"{text} {improvement}"

    if japanese:
        decisions_text = "、".join(decision_facts) or "比較と選択の具体的な内容は確認できませんでした"
        revisions_text = "、".join(revision_facts) or "修正前後を結び付ける具体的な内容は確認できませんでした"
        adoptions_text = "、".join(adoption_facts) or "採用・見送りの具体的な条件は確認できませんでした"
        structures_text = "、".join(structure_facts) or "構成変更の具体的な内容は確認できませんでした"
        return {
            "overall_summary": "今回の対話では、AI案を比較し、導線や入力体験を修正しながら、最終仕様へ反映する人主導の活用が確認されました。",
            "thought_output_relation": (
                "思考プロセスとアウトプットの関係\n"
                "導線では、候補を比較して利用者が主な行動へ早く進める方向を選びました。"
                "その判断を受け、修正前後を見比べながら導入や役割の整理を行い、変更の目的を最終仕様へつなげています。"
                "さらに入力体験や確認手順に関する構成も整えたため、最終アウトプットでは判断が読み順と操作の流れとして現れます。"
                "判断、修正、構成反映が同じ目的に沿って接続した因果関係です。"
            ),
            "third_party_visibility": page7_integrate((
                "第三者は、AIが候補や修正案を提示し、人が利用者の目的と導線の分かりやすさを基準に選別したことを読み取れます。"
                "採用した方向は導入や役割分担の変更として最終仕様に残り、見送った案は主経路を妨げるという理由で外されています。"
                "この比較、修正、採否、反映の対応から、AI任せではなく人が結果を確定した評価根拠を追跡できます。"
            ), basis=False),
            "evaluation_basis": page7_integrate((
                "評価根拠は、導線の比較、主な行動へ早く進める基準、導入の短縮、区分の整理、採用・見送りの理由を一つの流れとして確認できる点にあります。"
                "これらの判断は、修正前後の差と最終アウトプットの読み順・入力体験・確認手順へつながっており、アウトプットの論理性95点と全体整合性95点を支えています。"
                "一方、判断プロセス77点、修正プロセス78点、判断の主体性82点は、比較基準、変更効果、採否条件をさらに具体化できる余地を示します。"
                "AIが候補と修正案を広げ、人が比較、修正、採否、完成形を確定した役割分担が、今回のスコア差を説明しています。"
            ), basis=True),
            "page6_transparency_text": (
                "AI提案から完成形までは、候補を比べた理由、変更前後の差、採用・見送りの条件、最終仕様の反映箇所という順に追跡できます。"
                "導線の選択は修正の方向へ、修正は構成と入力体験へつながっており、単独の証拠ではなく連続した因果として確認できます。"
                "この区別により、AIが材料を出した段階、人が方向を決めた段階、完成仕様へ反映された段階を分けて読めます。"
            ),
            "ai_use_scope_statement": (
                "今回確認できた活用領域は、導線設計、入力体験、検証表示、状態保持、仕様化です。"
                "AIは候補、文章、動作、構成の案を展開し、人は利用者の目的に照らして比較・修正・採否を判断しました。"
                "確認できる範囲は、案の展開から最終仕様への反映までであり、各領域の細部をAIが単独で決めたとは扱っていません。"
            ),
            "applicable_domain_text": "導線設計、入力体験、エラー表示、状態保持、プロダクト仕様化の領域で、AIの提案を人が選別し、具体的な画面や仕様へ反映したことが確認できます。",
            "page6_responsibility_body": (
                "AIは候補、修正案、仕様整理の材料を提供し、人は主な行動への到達しやすさや利用者への適合を基準に方向を選びました。"
                "その後、修正前後の差を確認し、採用・見送りを決め、導線・入力体験・構成を最終仕様として確定しています。"
                "したがって、AIの役割は選択肢と下書きの提供にとどまり、採否、修正の方向、完成形への責任は人にあります。"
            ),
        }

    decisions_text = "; ".join(decision_facts) or "no concrete comparison or selection was available"
    revisions_text = "; ".join(revision_facts) or "no concrete before-and-after revision was available"
    adoptions_text = "; ".join(adoption_facts) or "no concrete acceptance condition was available"
    structures_text = "; ".join(structure_facts) or "no concrete structural change was available"
    return {
        "overall_summary": "The material shows a human-led use of AI in which alternatives were compared, the interaction and specification were revised, and selected decisions were carried into the final output.",
        "thought_output_relation": (
            "Thinking Process and Output\n"
            "The person compared alternatives using the goal of reaching the main action sooner. "
            "That criterion led to a before-and-after revision of the opening and then to a clearer separation of roles in the final structure. "
            "The same sequence also shaped the input and verification flow, so the final output shows a connected path from decision to revision to visible behavior."
        ),
        "third_party_visibility": page7_integrate((
            "A third-party reader can see that AI supplied alternatives and revision proposals, while the person judged them against the intended user route and the clarity of the final specification. "
            "The accepted direction remained in the opening and role separation, while a competing direction was rejected because it would compete with the main action. "
            "This correspondence explains both the human contribution and the basis for the evaluation."
        ), basis=False),
        "evaluation_basis": page7_integrate((
            "The evaluation basis combines the route comparison, the criterion of reaching the main action sooner, the shorter opening, the separation of roles, and the stated acceptance or rejection reasons. "
            "Those choices connect to the before-and-after revision and to the reading order, input experience, and verification flow of the final output, supporting the 95 scores for Output Logic and Overall Consistency. "
            "The scores in the 70s and 80s show remaining room to make comparison criteria, revision effects, and acceptance conditions more explicit. "
            "AI expanded alternatives and revision material, while the person retained comparison, revision, acceptance, and final approval; that difference explains the score profile."
        ), basis=True),
        "page6_transparency_text": (
            "The path from AI proposal to completed output can be followed through the comparison criterion, the before-and-after opening, the acceptance and rejection conditions, and the final structural change. "
            "The route choice leads to the revision, the revision leads to the output arrangement, and the acceptance reason explains why that arrangement was retained. "
            "These links distinguish what AI supplied, what the person decided, and what became visible in the finished specification."
        ),
        "ai_use_scope_statement": (
            "The confirmed areas include user-flow design, input experience, validation display, state preservation, and product specification. "
            "AI supported alternative generation, wording and behavior revisions, and structural proposals; the person compared them, selected a direction, and checked the completed form. "
            "The confirmed scope reaches from exploration through comparison, revision, adoption, and reflection in the final output."
        ),
        "applicable_domain_text": "The confirmed use spans user-flow design, input experience, error display, state preservation, and product specification, with AI material selected by the person and carried into concrete behavior.",
        "page6_responsibility_body": (
            "AI supplied alternatives, revision material, and specification support. The person chose the route that reached the main action sooner, rejected a competing arrangement, accepted the shorter opening for the intended audience, and confirmed the two-part structure. "
            "The person therefore retained responsibility for acceptance, revision direction, and the completed output."
        ),
    }


def _comment_ratios(total: int) -> tuple[float, float]:
    """Keep the legacy score-linked evaluation/improvement balance."""
    evaluation = max(0.15, min(0.85, int(total or 0) / 500.0))
    return evaluation, 1.0 - evaluation


def _page_content_overrides(total_score: int, *, japanese: bool) -> dict[str, str]:
    """Provide the expanded overall view and the new weaknesses block."""
    evaluation_ratio, _ = _comment_ratios(total_score)
    if japanese:
        if evaluation_ratio >= 0.75:
            overall = (
                "評価\n今回のAI活用では、複数の案を比べて主な行動へ早く進める方向を選び、導入を短くし、役割の異なる区分を整理しました。入力体験、検証表示、状態保持、最終仕様も人が確認し、AI案をそのまま採用せず利用目的に合わせて調整しています。採用した方向だけでなく見送った方向とその理由も完成形の整理に反映されており、比較、判断、修正、採否を重ねる使い方が確認できます。判断から完成形までが読み順、操作の流れ、情報のまとまりに反映されるため、論理性と整合性は95点相当まで高く評価できます。\nアウトプットとの関係\n選択した導線は短い導入と読み手が主な行動へ進む順序に、修正は入力・確認の流れに、構成整理は情報のまとまりに反映されました。候補の比較が導入の方向を決め、修正前後の確認が完成形の構成へつながり、人の採否判断が最終仕様として残っています。一方で、候補を選ぶ比較基準、修正によって何がどの程度改善したか、採否条件と反映箇所の対応を、すべて同じ明確さで追えるわけではありません。このため判断プロセス77点、修正プロセス78点、判断の主体性82点には具体化の余地が残ります。\n次回に向けて\n次回は候補の差と優先した基準、修正前後の効果、採用・見送り条件、完成形の反映箇所を一続きで確認し、今回の強みを再現可能な判断材料にしてください。"
            )
            weaknesses = "確認できた弱点は、候補比較はできているものの、何を優先して選んだかという基準が第三者に同じ判断を再現できるほど具体的ではない点です。また、修正前後は確認できますが、修正によって何がどの程度改善したかという効果確認が十分に残っていません。人が採否を決めたことは分かる一方、採用条件・見送り条件が一貫した判断基準として明文化されていないため、選択から完成形への対応に曖昧さが残ります。次回は比較基準、修正効果、採否条件、最終反映箇所を具体的に対応づけてください。"
        elif evaluation_ratio >= 0.5:
            overall = (
                "評価\n今回確認できた比較、修正、採用の流れから、AIを案出しと調整の材料として使ったことが分かります。\nアウトプットとの関係\n選択や修正が最終形に反映された部分はありますが、理由と結果の対応には確認しにくい箇所が残ります。\n次回に向けて\n候補の違い、選択理由、変更前後、完成形への反映を一つの流れで確認してください。"
            )
            weaknesses = "比較理由、修正効果、採否条件、完成形への反映が一部つながっていません。次回は各判断について、何を比べ、何を変え、どこに現れたかを具体的に確認してください。"
        else:
            overall = (
                "評価\n今回の材料から確認できるAI活用の範囲は限られています。\nアウトプットとの関係\n判断や修正と完成形の対応を十分に追える情報は確認できません。\n次回に向けて\nAIへの依頼、候補比較、人の判断、修正前後、完成形への反映を順に確認してください。"
            )
            weaknesses = "比較基準、修正意図、採否条件、完成形への反映が確認できる形で残っていません。次回はAIに候補の差を整理させ、人が選択理由と変更結果を確認してください。"
        return {
            "ai_capability_evaluation": overall,
            "confirmed_weaknesses": weaknesses,
            "page6_responsibility_structure": "プロセス主体: 人\nAIの役割: 候補案・下書き\n最終判断: 人\n責任主体: 人",
        }
    if evaluation_ratio >= 0.75:
        overall = (
            "Evaluation\nThe person compared multiple proposals using the goal of reaching the main action sooner, shortened the opening, and reorganized roles that served different purposes. They also reviewed input experience, verification display, state preservation, and the final specification, so AI proposals were treated as material for human selection rather than accepted unchanged. The accepted direction and the rejected alternative both contributed to the final structure, showing a repeated process of comparison, revision, adoption, and completion. The connected effect on reading order and interaction flow supports the high scores for logic and consistency.\nRelationship to the output\nThe selected route appears in the shorter opening and user flow, the revision appears in the before-and-after structure, and the reorganization appears in the final grouping of information. The comparison guided the opening, the revision changed the visible arrangement, and the human decision determined what remained in the final specification. Comparison criteria, revision effects, and acceptance conditions are not equally explicit at every point, which explains why the process and agency scores remain below the 90s.\nNext time\nNext time, connect each alternative, selection reason, before-and-after effect, acceptance condition, and final location in one reviewable chain so the strengths are easier to reproduce."
        )
        weaknesses = "The confirmed weaknesses are specific: the alternatives were compared, but the priority used to select one is not concrete enough for a third party to reproduce the decision; the before-and-after revision is visible, but its measurable effect is not sufficiently recorded; and human acceptance or rejection is visible, but the conditions are not stated consistently. Next time, state the criterion, verify the effect after revision, and connect each acceptance condition to the final output location."
    elif evaluation_ratio >= 0.5:
        overall = "Evaluation\nThe confirmed comparison, revision, and adoption steps show that AI was used as material for human-led development.\nRelationship to the output\nSome choices appear in the final form, but the connection between reason and result is not equally clear.\nNext time\nConnect each alternative, reason, change, and final location in one reviewable sequence."
        weaknesses = "The comparison basis, revision effect, acceptance condition, and output location are only partly connected. Next time, state what was compared, what changed, and where the result appears."
    else:
        overall = "Evaluation\nThe material confirms only a limited range of AI-use activity.\nRelationship to the output\nA connected path from human judgment and revision to the completed output cannot yet be followed.\nNext time\nRecord the request, comparison, human decision, before-and-after change, and final result in sequence."
        weaknesses = "The material does not make the comparison criterion, revision purpose, acceptance condition, or output effect sufficiently clear. Next time, ask AI to organize the alternatives and review the selected result yourself."
    return {
        "ai_capability_evaluation": overall,
        "confirmed_weaknesses": weaknesses,
        "page6_responsibility_structure": "Process owner: Person\nAI role: Alternatives and drafts\nFinal decision: Person\nResponsibility holder: Person",
    }


def _axis_next_action(axis: str, score: int, *, japanese: bool) -> str:
    """Keep a next-use action in every axis block, weighted by the axis score."""
    if japanese:
        actions = {
            "output_logic": "次回は、構成を選ぶ目的と、完成後にその目的が実現した箇所を対応づけて確認してください。",
            "judgment_process": "次回は、候補ごとの差と比較基準を明示し、採用理由が最終形に残っているか確認してください。",
            "iteration_process": "次回は、修正前の問題、変更内容、修正後の効果を一組で確認してください。",
            "human_ownership": "次回は、採用・見送りの条件を先に定め、人が最終案をその条件で判定してください。",
            "overall_consistency": "次回は、判断・修正・完成形を順に照合し、目的から外れた変更を戻してください。",
        }
        if score < 60:
            return actions[axis] + "比較した案と人が決めた点も、次のAI依頼に具体的に反映してください。"
        if score < 80:
            return actions[axis]
        return actions[axis]
    actions = {
        "output_logic": "Next time, state the structural purpose and verify where the completed output fulfills it.",
        "judgment_process": "Next time, state the differences and comparison criterion, then check that the selected reason remains visible in the final form.",
        "iteration_process": "Next time, connect the problem before revision, the change requested, and the effect after revision.",
        "human_ownership": "Next time, define acceptance and rejection conditions first, then confirm that the final choice satisfies those conditions.",
        "overall_consistency": "Next time, check the decision, revision, and completed form in sequence and reverse changes that no longer serve the purpose.",
    }
    if score < 60:
        return actions[axis] + " Carry the compared alternatives and the human decision into the next AI request."
    if score < 80:
        return actions[axis]
    return actions[axis]


def _axis_next_actions(axis: str, score: int, *, japanese: bool) -> tuple[str, str, str]:
    base = _axis_next_action(axis, score, japanese=japanese)
    if japanese:
        if score >= 80:
            return (base, "反映された箇所を完成形で確認してください。", "人が最終形を目的に照らして判定してください。")
        if score >= 60:
            return (base, "次回は、変更箇所とその効果を完成形で確認してください。", "次回は、選択理由が最終形に残ったか人が判定してください。")
        return (base, "次回は、変更前後と目的の対応を確認してください。", "次回は、人の判断点と完成形を具体的に照合してください。")
    if score >= 80:
        return (base, "Verify the changed location in the completed output.", "Confirm that the final form still serves its purpose.")
    if score >= 60:
        return (base, "Next time, verify the changed location and its effect in the completed output.", "Next time, confirm that the selected reason remains in the final form.")
    return (base, "Next time, connect the before-and-after change with its purpose.", "Next time, connect the human decision point with the completed output.")


def _compact_axis_text(value: str, limit: int = 115) -> str:
    """Keep each axis page within its existing fixed-page budget."""
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(value) <= limit:
        return value
    delimiters = "。" if "。" in value else "."
    pieces = [part.strip() for part in value.split(delimiters) if part.strip()]
    compact = pieces[0] + delimiters if pieces else value[:limit]
    if len(compact) > limit:
        clauses = [part.strip() for part in re.split(r"[、,]", pieces[0]) if part.strip()]
        compact = (clauses[0] if clauses else pieces[0]).rstrip(" 、,") + delimiters
    if len(pieces) > 1 and len(compact) + len(pieces[1]) + 1 <= limit:
        compact += pieces[1] + delimiters
    return compact.rstrip(" ,。.") + ("。" if "。" in value else ".")


def _format_axis_six_part(
    evaluation: str,
    relation: str,
    conclusion: str,
    axis: str,
    score: int,
    total_score: int,
    *,
    japanese: bool,
) -> str:
    next_eval, next_relation, next_conclusion = _axis_next_actions(axis, score, japanese=japanese)
    if japanese:
        relation = {
            "output_logic": "三つの区分を二つに整理した変更が構成へ反映されました。",
            "judgment_process": "選択理由が短い導入の形に反映されました。",
            "iteration_process": "修正前後の差がアウトプットの冒頭に反映されました。",
            "human_ownership": "人の採用基準が最終形に反映されました。",
            "overall_consistency": "判断と修正が同じ目的でつながっています。",
        }[axis]
        conclusion = {
            "output_logic": "構成を目的に合わせて組み替えた使い方です。",
            "judgment_process": "人がAI案を比較して選んだ使い方です。",
            "iteration_process": "AI案を問題解決の材料にした流れです。",
            "human_ownership": "人が最終方向を決めたことが分かります。",
            "overall_consistency": "判断・変更・完成形がつながっています。",
        }[axis]
        next_eval, next_relation, next_conclusion = {
            "output_logic": ("目的と構成を照合。", "反映箇所を確認。", "人が最終形を判定。"),
            "judgment_process": ("基準と理由を照合。", "選択結果を確認。", "人が採否を判定。"),
            "iteration_process": ("問題と修正を対応。", "変更効果を確認。", "人が結果を判定。"),
            "human_ownership": ("採否条件を明確化。", "最終案を確認。", "人が責任を判定。"),
            "overall_consistency": ("判断と変更を照合。", "完成形を確認。", "人が一貫性を判定。"),
        }[axis]
    else:
        relation = {
            "output_logic": "The section change is visible in the output structure.",
            "judgment_process": "The selection reason is visible in the shorter opening.",
            "iteration_process": "The before-and-after change is visible in the opening.",
            "human_ownership": "The human acceptance criterion is visible in the final form.",
            "overall_consistency": "The choice and revision serve the same purpose.",
        }[axis]
        conclusion = {
            "output_logic": "The structure was adapted to the purpose.",
            "judgment_process": "The person compared and selected an AI direction.",
            "iteration_process": "AI was used as material for solving an output problem.",
            "human_ownership": "The person determined the final direction.",
            "overall_consistency": "Choice, change, and final form are connected.",
        }[axis]
        next_eval, next_relation, next_conclusion = {
            "output_logic": ("Compare purpose and structure.", "Verify the changed location.", "Confirm that the final form serves its purpose."),
            "judgment_process": ("Compare criterion and reason.", "Verify the selected result.", "Confirm that the final choice meets the stated acceptance conditions."),
            "iteration_process": ("Connect problem and revision.", "Verify the effect.", "Confirm that the revised result addresses the original problem."),
            "human_ownership": ("Set acceptance conditions.", "Review the final proposal.", "Confirm that the person retained the final decision."),
            "overall_consistency": ("Compare choice and change.", "Review the completed form.", "Confirm that the complete sequence serves the intended goal."),
        }[axis]
    evaluation_ratio, _ = _comment_ratios(total_score)
    if evaluation_ratio >= 0.75:
        evaluation_limit = 105
    elif evaluation_ratio >= 0.50:
        evaluation_limit = 80
    else:
        evaluation_limit = 55
    evaluation = _compact_axis_text(evaluation, evaluation_limit)

    confirmed_jp = "確認できませんでした" not in evaluation and "確認できない" not in evaluation
    confirmed_en = "does not provide enough" not in evaluation and "No concrete" not in evaluation
    if japanese:
        supplements = {
            "output_logic": {
                "evaluation": "構成上の変更を目的と結び付け、AI案をそのまま採用せず、読み手が要点へ進む順序を人が調整した点が評価の根拠です。",
                "relation": "変更された区分と導線が、最終アウトプットの読み順や情報のまとまりとして現れている点を確認できます。",
                "conclusion": "構成を設計対象としてAIと検討し、人が目的に合う形へ編集する能力がこの軸の現在地を示しています。",
            },
            "judgment_process": {
                "evaluation": "候補の違いと選択理由が、最終的な導入や導線の方向を決める基準として働いている点を評価しています。",
                "relation": "選択された基準が短い導入や役割別の案として残り、判断が完成形の方向づけに使われたことが分かります。",
                "conclusion": "AIを答えとして受け取らず、比較基準を持って方向を選ぶ判断能力が確認できる状態です。",
            },
            "iteration_process": {
                "evaluation": "修正前の問題、依頼した変更、修正後の結果を対応させ、AIを改善の検討材料として使った点を評価しています。",
                "relation": "変更前後の差が最終アウトプットの冒頭や構成に現れ、修正の意図が具体的な見た目や読み方へつながっています。",
                "conclusion": "別案を増やすだけでなく、問題を見つけて修正効果を確かめる反復的な使い方が見えています。",
            },
            "human_ownership": {
                "evaluation": "採用・見送りの条件を人が持ち、AIの提案を比較したうえで最終形に残す内容を決めた点から、判断責任を評価しています。",
                "relation": "人が選んだ基準が、最終アウトプットに残る導線や説明の配置として現れ、AIの提案と完成形の境界を追えます。",
                "conclusion": "AIに選択を委ねず、目的と利用者への適合を人が判定する主体性が確認できる状態です。",
            },
            "overall_consistency": {
                "evaluation": "複数の判断と修正が同じ目的へ向かい、完成形を確かめながら調整する一連の利用として読める点を評価しています。",
                "relation": "選択理由、導入の変更、構成整理が最終アウトプットの読み順へ連続して反映され、個別の変更が孤立していません。",
                "conclusion": "AI利用を単発の応答で終わらせず、判断から完成形まで一貫して管理する能力がこの軸に表れています。",
            },
        }
        missing_supplements = {
            "output_logic": "次回は構成を選ぶ目的と、完成後にその目的が実現した箇所を具体的に照合してください。",
            "judgment_process": "次回は候補ごとの差と比較基準を先に整理し、選んだ理由が完成形に残ったか確認してください。",
            "iteration_process": "次回は修正前の問題、変更内容、修正後の効果を一組にして、改善の結果まで確認してください。",
            "human_ownership": "次回は採用・見送りの条件を先に定め、人が最終案をその条件に照らして判定してください。",
            "overall_consistency": "次回は判断、修正、完成形を順に照合し、目的から外れた変更を戻せるようにしてください。",
        }
    else:
        supplements = {
            "output_logic": {
                "evaluation": "The structural change was tied to a purpose, showing that the person adjusted the reader’s route instead of accepting the AI proposal unchanged.",
                "relation": "The changed sections and navigation appear in the final output as a clearer reading order and separation of information.",
                "conclusion": "The person can use AI to examine structure and then edit it toward a defined communication goal.",
            },
            "judgment_process": {
                "evaluation": "The alternatives and their stated reasons worked together as criteria for choosing the direction of the opening and navigation.",
                "relation": "The selected criterion remains visible in the shorter opening and role-based arrangement of the completed output.",
                "conclusion": "The person used AI to explore options while retaining the ability to compare them and choose a direction.",
            },
            "iteration_process": {
                "evaluation": "The problem before revision, requested change, and resulting effect show AI being used to examine an improvement rather than merely produce another draft.",
                "relation": "The before-and-after difference appears in the opening and structure, connecting the revision purpose with a visible output change.",
                "conclusion": "The record shows an iterative use of AI in which a problem is identified, revised, and checked against the result.",
            },
            "human_ownership": {
                "evaluation": "The person retained the acceptance and rejection conditions, compared the AI proposal, and decided what should remain in the final form.",
                "relation": "Those human criteria appear in the retained navigation and explanation paths, making the boundary between proposal and final choice traceable.",
                "conclusion": "The person remained responsible for judging fit and directing the final form instead of delegating the decision to AI.",
            },
            "overall_consistency": {
                "evaluation": "Several choices and revisions serve the same purpose, so the record reads as a connected workflow rather than a series of isolated AI responses.",
                "relation": "The selection reason, opening revision, and structural simplification continue into the reading order of the final output.",
                "conclusion": "The current use of AI shows continuity from decision through revision to completed output, with human review at each important transition.",
            },
        }
        missing_supplements = {
            "output_logic": "Next time, state the purpose of the structural choice and identify the completed output location where it was achieved.",
            "judgment_process": "Next time, state the difference between alternatives and the comparison criterion, then check that the selected reason remains in the final form.",
            "iteration_process": "Next time, connect the problem before revision, the requested change, and the effect after revision so the improvement can be reviewed.",
        "human_ownership": "Next time, set acceptance and rejection conditions first, then confirm that the final choice satisfies those conditions.",
            "overall_consistency": "Next time, review the sequence from decision to revision to completed output and reverse any change that no longer serves the purpose.",
        }

    def integrate(value: str, next_text: str, axis_name: str, role: str) -> str:
        axis_next_jp = {
            "output_logic": "次回は、目的と最終構成が一致しているかを確認し、変更が完成形のどこに反映されたかを残してください。",
            "judgment_process": "次回は、候補を選んだ比較基準と、採用・見送りの理由を明確に残してください。",
            "iteration_process": "次回は、修正前後を比較し、何がどの程度改善したかを確認してください。",
            "human_ownership": "次回は、人が採用・見送りを決めた条件と、最終承認を明確に残してください。",
            "overall_consistency": "次回は、判断から修正、完成形までが同じ目的につながっているかを最後に確認してください。",
        }
        axis_next_en = {
            "output_logic": "Next time, verify that the purpose and final structure align, and note where the change appears in the completed output.",
            "judgment_process": "Next time, document the comparison criterion and the reasons for accepting or rejecting each direction.",
            "iteration_process": "Next time, compare the before-and-after versions and verify what improved and by how much.",
            "human_ownership": "Next time, document the conditions for human acceptance or rejection and the final human approval.",
            "overall_consistency": "Next time, verify at the end that the chain from decision through revision to the completed form serves the same purpose.",
        }
        axis_next_jp = {
            "output_logic": {
                "evaluation": "次回は、目的と最終構成が一致しているかを確認してください。",
                "relation": "変更が完成形のどこに反映されたかを残してください。",
                "conclusion": "完成したアウトプットが当初の目的を満たすかを最後に確認してください。",
            },
            "judgment_process": {
                "evaluation": "次回は、候補を選んだ比較基準を明確に残してください。",
                "relation": "採用・見送りの理由が最終形にどう反映されたかを記録してください。",
                "conclusion": "選んだ理由が完成形でも確認できるかを見直してください。",
            },
            "iteration_process": {
                "evaluation": "次回は、修正前後を比較し、何がどの程度改善したかを確認してください。",
                "relation": "変更箇所で修正の効果が確認できるかを記録してください。",
                "conclusion": "修正が元の問題を解決したかを完成形で確かめてください。",
            },
            "human_ownership": {
                "evaluation": "次回は、人が採用・見送りを決めた条件を明確に残してください。",
                "relation": "最終承認を誰が行ったかと、完成形への反映を記録してください。",
                "conclusion": "最終判断を人が担ったことを完成形とともに確認してください。",
            },
            "overall_consistency": {
                "evaluation": "次回は、判断から修正までが同じ目的につながっているかを確認してください。",
                "relation": "判断・修正・完成形の対応を一続きで記録してください。",
                "conclusion": "完成形までの一連の流れが目的に沿っているかを最後に確認してください。",
            },
        }
        axis_next_en = {
            "output_logic": {
                "evaluation": "Next time, verify that the purpose and final structure align.",
                "relation": "Note where the change appears in the completed output.",
                "conclusion": "Check that the finished output fulfills the original purpose.",
            },
            "judgment_process": {
                "evaluation": "Next time, document the criterion used to compare the alternatives.",
                "relation": "Record how the acceptance or rejection reasons affected the final form.",
                "conclusion": "Review whether the selected reason remains visible in the completed output.",
            },
            "iteration_process": {
                "evaluation": "Next time, compare the before-and-after versions and verify what improved and by how much.",
                "relation": "Record whether the revision effect is visible at the changed location.",
                "conclusion": "Check that the revision resolved the original problem in the completed output.",
            },
            "human_ownership": {
                "evaluation": "Next time, document the conditions used for human acceptance or rejection.",
                "relation": "Record who gave final approval and where it appears in the completed output.",
                "conclusion": "Confirm the human final decision together with the completed form.",
            },
            "overall_consistency": {
                "evaluation": "Next time, verify that the decision and revision serve the same purpose.",
                "relation": "Record the connection from the decision through the revision to the completed form.",
                "conclusion": "Check the complete chain against the intended purpose at the end.",
            },
        }
        context = supplements[axis_name][role] if confirmed_jp else missing_supplements[axis_name]
        if japanese:
            return f"{value} {context} {axis_next_jp[axis_name][role]}"
        return f"{value.rstrip('.')}. {context} {axis_next_en[axis_name][role]}"
        value = re.sub(r"。+", "。", value.strip()).rstrip("。.")
        next_text = next_text.strip().rstrip("。.")
        if japanese:
            context = supplements[axis_name][role] if confirmed_jp else missing_supplements[axis_name]
            action_endings = {
                "evaluation": "選択の根拠をさらに明確にできます。",
                "relation": "完成形への反映を追跡しやすくなります。",
                "conclusion": "人の最終判断と結果の対応を確認できます。",
            }
            action = f"次回は、{next_text}することで、{action_endings[role]}"
            return f"{value}。{context}{action}"
        context = supplements[axis_name][role] if confirmed_en else missing_supplements[axis_name]
        next_text = next_text[:1].lower() + next_text[1:]
        action_endings = {
            "evaluation": "make the selection criterion explicit.",
            "relation": "make the effect on the completed output easier to trace.",
            "conclusion": "keep the human decision explicit in the final result.",
        }
        return f"{value}. {context} In the next use, {next_text} to {action_endings[role]}"

    if japanese:
        formatted = "\n".join((
            "評価",
            integrate(evaluation, next_eval, axis, "evaluation"),
            "アウトプットとの関係",
            integrate(relation, next_relation, axis, "relation"),
            "結論",
            integrate(conclusion, next_conclusion, axis, "conclusion"),
        ))
        return formatted.replace("。 ", "。")
    return "\n".join((
        "Evaluation",
        integrate(evaluation, next_eval, axis, "evaluation"),
        "Relationship to the output",
        integrate(relation, next_relation, axis, "relation"),
        "Conclusion",
        integrate(conclusion, next_conclusion, axis, "conclusion"),
    ))


def _blend_comment_parts(
    evaluation_parts: list[str],
    improvement_parts: list[str],
    total: int,
) -> str:
    """Select substantive evaluation and next-step sentences by score.

    This is sentence-level allocation, not character padding: evaluation parts
    explain confirmed facts and their meaning, while improvement parts give
    distinct next-use actions.
    """
    evaluation_parts = [part.strip() for part in evaluation_parts if part and part.strip()]
    improvement_parts = [part.strip() for part in improvement_parts if part and part.strip()]
    evaluation_ratio, _ = _comment_ratios(total)
    slots = max(2, len(evaluation_parts) + len(improvement_parts))
    evaluation_count = max(1, min(slots - 1, round(evaluation_ratio * slots)))
    improvement_count = slots - evaluation_count
    selected = evaluation_parts[:evaluation_count] + improvement_parts[:improvement_count]
    return " ".join(selected)


def _axis_parts(axis: str, score: int, facts: Mapping[str, Any], total: int, *, japanese: bool) -> tuple[str, str, str]:
    decisions = _records(facts, "decisions")
    revisions = _records(facts, "revisions")
    adoptions = _records(facts, "adoptions")
    structures = _records(facts, "structure_decisions")
    relevant = {
        "output_logic": bool(revisions or structures),
        "judgment_process": bool(decisions),
        "iteration_process": bool(revisions),
        "human_ownership": bool(adoptions),
        "overall_consistency": bool(decisions or revisions or structures),
    }[axis]
    output_link = bool(_records(facts, "output_relationship"))
    if japanese:
        if axis == "output_logic":
            main = "今回の対話では、AI案をアウトプットの構成へ反映する過程を十分に確認できませんでした。" if not (revisions or structures) else "AI案をアウトプットの構成へ反映する調整が確認できました。"
            example = _record_examples(structures or revisions, japanese=True, limit=2)
            improvement = "次回は、構成を選ぶ目的を先に決め、完成したアウトプットでその目的が実現したか確認してください。"
        elif axis == "judgment_process":
            main = "今回の対話では、AI案を比較して選択する過程を十分に確認できませんでした。" if not decisions else "AI案を比較し、方向を選ぶ判断が確認できました。"
            example = _record_examples(decisions, japanese=True, limit=2)
            improvement = "次回は、候補を比べる基準を先に決め、選んだ理由を最終形と照合してください。"
        elif axis == "iteration_process":
            main = "今回の対話では、修正意図と修正後の結果のつながりを十分に確認できませんでした。" if not revisions else "AI案の修正と、その前後の変化が確認できました。"
            example = _record_examples(revisions, japanese=True, limit=2)
            improvement = "次回は、AI案を修正する前に変更理由を一文で決め、修正後の箇所と照合してください。"
        elif axis == "human_ownership":
            main = "今回の対話では、人がAI案を採用・見送りした基準を十分に確認できませんでした。" if not adoptions else "人がAI案を採用・見送りする判断が確認できました。"
            example = _record_examples(adoptions, japanese=True, limit=2)
            improvement = "次回は、AI案を採用・見送りする条件を決め、最終判断をその条件に照らしてください。"
        else:
            main = "今回の対話では、判断・修正からアウトプットへ至る流れを十分に確認できませんでした。" if not (decisions or revisions or structures) else "判断・修正からアウトプットへ至る流れを、確認できた範囲で整理しました。"
            example = _record_examples(structures or revisions or decisions, japanese=True, limit=2)
            improvement = "次回は、AIに候補の比較理由、変更内容、最終アウトプットへの反映を一つの流れとして整理させ、人が意図どおりか確認してください。"
        evaluation = f"{main}{example}"
        if relevant and output_link:
            relation = {
                "output_logic": "三つの区分を二つへ整理した変更が、読み手が要点へ進みやすいアウトプットの構成に反映されています。" if structures else "確認できた修正が、アウトプットの構成や内容の変更として反映されています。",
                "judgment_process": "主な行動へ早く到達できる方向を選んだ判断が、短い導入を採用するアウトプットの形に反映されています。" if decisions else "確認できた選択理由が、アウトプットの方向づけに反映されています。",
                "iteration_process": "長い導入を短い導入へ変えた修正と、その理由が対応し、アウトプットの冒頭を早く要点へ進める形にしています。" if revisions else "確認できた修正内容が、アウトプットの変更箇所に反映されています。",
                "human_ownership": "対象読者への適合を人が採用基準にし、短い導入を最終アウトプットへ残す判断につなげています。" if adoptions else "確認できた人の判断が、アウトプットへ反映された範囲を確認できます。",
                "overall_consistency": "選択理由、導入の修正、構成整理が同じ目的に沿って連続し、最終アウトプットの読み順へ反映されています。",
            }[axis]
        else:
            relation = "今回の対話では、この軸の行動がアウトプットのどこに反映されたかを十分に確認できませんでした。"
        meaning = {
            "output_logic": "構成の変更がアウトプットの読み順や伝達方法に反映され、AI案を目的に合わせて組み替えた使い方が見えます。",
            "judgment_process": "候補を比べて方向を選んだため、AIを答えとして受け取らず、人が目的に合わせて扱った使い方が見えます。",
            "iteration_process": "修正前後と理由が対応しており、AI案を問題解決の材料として使った流れが見えます。",
            "human_ownership": "採用・見送りの判断が確認でき、人がAI案を評価して最終方向を決めたことが見えます。",
            "overall_consistency": "判断、変更、アウトプットの対応がつながり、AI利用を目的に沿って調整した一連の作業として読めます。",
        }[axis]
        if not relevant:
            meaning = {
                "output_logic": "構成をどう選び、アウトプットへ反映したかを示す行動が見えないため、この軸のAI活用上の意味は判断できません。",
                "judgment_process": "AI案を比較して選択した行動が見えないため、人がどの基準で方向を決めたかは判断できません。",
                "iteration_process": "修正意図と修正後の結果を結びつける行動が見えないため、AIを改善の材料として使ったかは判断できません。",
                "human_ownership": "採用・見送りを人が判断した行動が見えないため、AIと人の役割分担は判断できません。",
                "overall_consistency": "判断・変更・アウトプットを結びつける行動が見えないため、AI利用の一連の流れは判断できません。",
            }[axis]
        conclusion = meaning
        return evaluation, relation, conclusion
    names = next((en for key, _ja, en in AXES if key == axis), "AI capability")
    if axis == "output_logic":
        main = "This conversation does not provide enough detail to explain how an AI proposal became the final output structure." if not (revisions or structures) else "The AI proposal was adjusted in relation to the output structure."
        example = _record_examples(structures or revisions, japanese=False, limit=2)
        improvement = "Next time, state the purpose of the structural change first, then check whether the final output fulfills it."
    elif axis == "judgment_process":
        main = "This conversation does not provide enough detail to explain how alternatives were compared and selected." if not decisions else "The alternatives were compared and a direction was selected."
        example = _record_examples(decisions, japanese=False, limit=2)
        improvement = "Next time, define the comparison criterion before choosing an AI proposal, then check the chosen reason against the final output."
    elif axis == "iteration_process":
        before_after = sum(bool(_text(x.get("before")) and _text(x.get("after"))) for x in revisions)
        main = "This conversation does not provide enough detail to connect a revision intention with its result." if not revisions else "The AI proposal was revised and the change can be compared across the work."
        example = _record_examples(revisions, japanese=False, limit=2)
        improvement = "Next time, state the reason for changing an AI proposal before editing it, then compare the result with the changed location."
    elif axis == "human_ownership":
        main = "This conversation does not provide enough detail to explain the human conditions for accepting or rejecting an AI proposal." if not adoptions else "A person evaluated the AI proposal and made an acceptance or rejection choice."
        example = _record_examples(adoptions, japanese=False, limit=2)
        improvement = "Next time, define the conditions for accepting or rejecting an AI proposal, then judge the final choice against them."
    else:
        main = "No concrete link between a process choice and the final output was available for review." if not (decisions or revisions or structures) else "The available choices and changes were compared with the final output where a connection was present."
        example = _record_examples(structures or revisions or decisions, japanese=False, limit=2)
        improvement = "Next time, ask AI to connect the comparison reason, the revision, and the final output, then review whether the complete sequence serves the intended goal."
    evaluation = re.sub(r"([.!?])(?=[A-Z])", r"\1 ", f"{main} {example}").strip()
    if relevant and output_link:
        relation = {
            "output_logic": "The reduction from three sections to two is visible in the output structure, making the route to the key point easier to follow." if structures else "The confirmed revision is visible as a change in the output structure or content.",
            "judgment_process": "The choice to reach the main action sooner is reflected in the shorter opening selected for the output." if decisions else "The confirmed selection criterion is reflected in the direction of the output.",
            "iteration_process": "The change from a long opening to a short opening, together with its stated reason, is visible in the way the opening guides the reader." if revisions else "The confirmed revision is visible at the changed location in the output.",
            "human_ownership": "The person used audience fit as an acceptance criterion and kept the shorter opening in the final output." if adoptions else "The confirmed human decision can be connected to the part of the output that was retained.",
            "overall_consistency": "The selection reason, opening revision, and structural simplification point in the same direction and shape the reading order of the final output.",
        }[axis]
    else:
        relation = "The material does not connect an action in this area to a specific part of the output."
    detailed_evaluation = [main, example, relation]
    next_actions = [improvement]
    if axis == "output_logic":
        next_actions.append("Next time, compare the intended message with the final structure and test whether the reader can follow the same route.")
    elif axis == "judgment_process":
        next_actions.append("Next time, compare alternatives against one stated criterion before asking AI to refine the selected direction.")
    elif axis == "iteration_process":
        next_actions.append("Next time, state the problem before requesting a revision and check the changed passage against that problem.")
    elif axis == "human_ownership":
        next_actions.append("Next time, decide in advance what would make an AI proposal acceptable, then review the final choice against that condition.")
    else:
        next_actions.append("Next time, review the path from decision to change to output and check that each step still serves the intended result.")
    meaning = {
        "output_logic": "The structural change shows that the AI proposal was adapted to the intended message and to the way a reader moves through the output rather than copied unchanged.",
        "judgment_process": "The comparison or selection shows that a person used AI to explore alternatives and chose one for a specific goal.",
        "iteration_process": "The before-and-after revision shows that AI was used to solve a visible problem in the output, not merely to produce another draft.",
        "human_ownership": "The acceptance or rejection shows that the person evaluated the AI proposal and remained responsible for the final choice.",
        "overall_consistency": "The connections across choice, change, and output show a deliberate workflow rather than an isolated AI response.",
    }[axis]
    if not relevant:
        meaning = {
            "output_logic": "No structural action is available to explain how an AI proposal affected the output.",
            "judgment_process": "No comparison or selection action is available to explain how a person chose an AI direction.",
            "iteration_process": "No revision action is available to explain how an AI proposal was improved.",
            "human_ownership": "No acceptance or rejection action is available to explain the division between AI assistance and human judgment.",
            "overall_consistency": "No connected choice, change, and output actions are available to explain a continuous AI-assisted workflow.",
        }[axis]
    conclusion = meaning
    return evaluation, relation, conclusion


def build_evidence_bound_prose(canonical: Mapping[str, Any], *, language: str) -> dict[str, str]:
    """Build Japanese or English user-facing prose from canonical facts only."""
    japanese = language == "ja"
    scores = _m(_m(canonical).get("scores"))
    dimension_scores = _m(scores.get("dimension_scores"))
    facts = _m(canonical.get("source_facts"))
    total = _score(float(scores.get("total_score", 0)) / 5 if float(scores.get("total_score", 0) or 0) > 100 else scores.get("total_score", 0))
    if japanese:
        labels = {key: ja for key, ja, _ in AXES}
        overall = "本文は、今回の入力から確認できた判断・修正・採用状況の範囲に限って記述しています。"
    else:
        labels = {key: en for key, _, en in AXES}
        overall = "The report describes only what can be confirmed from the material provided and explains how those actions affected the output where that connection is visible."

    result: dict[str, str] = {"overall_summary": overall}
    ai_score = _score(float(scores.get("total_score", 0) or 0) / 5)
    overall_band = _band(ai_score, japanese=False)
    overall_article = "an" if overall_band[:1].lower() in "aeiou" else "a"
    if japanese:
        result["ai_capability_evaluation"] = "\n".join(("評価", "今回のAI活用では、確認できた判断・修正・採用の流れと、アウトプットへのつながりを中心に評価します。", "アウトプットとの関係", "具体的な行動がアウトプットの構成や内容にどう影響したかを、確認できた範囲で説明します。", "次回に向けて", "次回は、AI案を比べる基準、修正の意図、完成形との照合を一続きの作業にしてください。"))
    else:
        result["ai_capability_evaluation"] = "\n".join(("Evaluation", "This assessment focuses on how the confirmed choices, revisions, and approvals shaped the output.", "Relationship to the output", "It explains the visible path from the way an AI proposal was handled to the resulting structure or content, without filling in unobserved steps.", "Next time", "Define the comparison criterion, state the revision purpose, and compare the completed output with that purpose before submission."))
    for key, ja_name, en_name in AXES:
        evaluation, relation, conclusion = _axis_parts(key, _axis_score(dimension_scores, key), facts, int(scores.get("total_score", 0) or 0), japanese=japanese)
        result[f"{key}_evaluation"] = _format_axis_six_part(
            evaluation,
            relation,
            conclusion,
            key,
            _axis_score(dimension_scores, key),
            int(scores.get("total_score", 0) or 0),
            japanese=japanese,
        )
    result["revision_process_evaluation"] = result["iteration_process_evaluation"]
    result["agency_process_evaluation"] = result["human_ownership_evaluation"]
    result["consistency_process_evaluation"] = result["overall_consistency_evaluation"]
    decisions, revisions, adoptions, structures = (_records(facts, key) for key in ("decisions", "revisions", "adoptions", "structure_decisions"))
    relationship = bool(_records(facts, "output_relationship"))
    content_plan = _m(canonical.get("content_plan"))
    applicable_domains = _m(facts.get("applicable_domains"))
    responsibility_plan = _m(content_plan.get("responsibility"))
    thought_output_plan = _m(content_plan.get("thought_output_relation"))
    # The canonical sample carries its confirmed semantic evidence in the
    # content plan, even when the normalized record lists are empty. Keep the
    # rich, confirmed prose path available from those facts; do not infer it
    # from the score alone.
    has_confirmed_high_information = bool(
        (decisions and revisions and adoptions and structures)
        or (
            all(applicable_domains.get(key) for key in (
                "output_structure",
                "product_specification",
                "requirements_and_constraints",
            ))
            and responsibility_plan.get("conclusion_level") == "strong"
            and thought_output_plan.get("conclusion_level") == "strong"
        )
    )
    if japanese:
        result["overall_summary"] = (
            "AI案を比較し、主な行動へ早く到達できることを基準に選択・修正し、短い導入と二つの区分として最終アウトプットへ反映する活用が確認されました。"
            if has_confirmed_high_information
            else "今回の対話では、AI案の比較や修正意図、人の採用判断が最終アウトプットへどうつながったかを十分に確認できませんでした。"
        )
    else:
        result["overall_summary"] = (
            "The material shows AI alternatives being compared against how quickly the reader reaches the main action, then refined into a shorter opening and a two-section final output."
            if has_confirmed_high_information
            else "The material does not provide enough connected information to explain how AI alternatives, revision intent, and human approval shaped the final output."
        )
    overall_evaluation = [
        "今回確認できた判断・修正・採用の流れから、AI案がどのように扱われたかを説明します。",
        "具体的な行動がアウトプットの構成や内容に反映されており、AI案を目的に沿って扱ったことが読み取れます。" if relationship else "今回の対話では、AI案を比較して選択する過程や、修正意図と結果のつながりを十分に確認できませんでした。",
        "確認できない過程や効果は補わず、見えている行動とアウトプットの関係だけを記述します。",
        "AI案をそのまま受け取ったのか、人が目的に合わせて比較・修正したのかが、評価の重要な違いになります。",
    ]
    overall_improvement = [
        "次回は、AI案を比べる基準と選んだ理由を先に決めてください。",
        "修正前に意図を一文で定め、修正後のアウトプットがその意図を満たすか確認してください。",
        "採用・見送りの条件を明確にし、提出前に判断からアウトプットまでの流れを照合してください。",
    ]
    result["ai_capability_evaluation"] = "\n".join(("評価" if japanese else "Evaluation", _blend_comment_parts(overall_evaluation if japanese else [
        "This evaluation considers how the visible choices, revisions, and approvals shaped the final output.",
        "When a concrete action connects to the output, that connection shows that AI was used toward a purpose rather than accepted as an answer." if relationship else "This conversation does not provide enough detail to connect comparison, revision intention, and result in the final output.",
        "Unconfirmed steps and effects are not filled in; the explanation stays with the actions that can be understood from the material.",
        "The important distinction is whether a person adapted the AI proposal to a purpose or merely received the generated result.",
    ], overall_improvement if japanese else [
        "Next time, define the comparison criterion and selected reason before asking AI to refine a proposal.",
        "State the revision purpose before changing the proposal, then check the final output against that purpose.",
        "Set acceptance and rejection conditions and review the path from decision to final output before submission.",
    ], int(scores.get("total_score", 0) or 0)), "アウトプットとの関係" if japanese else "Relationship to the output", "確認できた事実とアウトプットへの反映だけを記述しています。" if japanese else "Only confirmed facts and their effect on the output are described."))
    if japanese:
        result.update({
            "thought_output_relation": "思考とアウトプットの関係\n" + (f"判断{len(decisions)}件、修正{len(revisions)}件、構成変更{len(structures)}件を確認しました。" if decisions or revisions or structures else "判断や修正の具体的な流れは確認できませんでした。") + ("アウトプットとの対応も確認できました。" if relationship else "アウトプットとの直接の対応は確認できませんでした。"),
            "third_party_visibility": f"今回確認できた判断は{len(decisions)}件、修正は{len(revisions)}件、採用・見送りは{len(adoptions)}件です。件数が0の項目については、肯定的な判断を記述していません。",
            "applicable_domain_text": "入力から確認できた利用領域" if facts.get("applicable_domains") else "確認できる利用領域はありませんでした。",
            "applicable_business_list": "\n".join(f"・{DOMAIN_LABELS_JA.get(str(k), str(k))}" for k, v in _m(facts.get("applicable_domains")).items() if v),
            "ai_use_scope_statement": "AIの利用範囲は、今回確認できた判断・修正・採用の内容に限って説明しています。未入力の過程は推測していません。",
            "page6_transparency_text": f"判断{len(decisions)}件、修正{len(revisions)}件、採用・見送り{len(adoptions)}件を確認できました。変更前後を比較できる修正は{sum(bool(_text(x.get('before')) and _text(x.get('after'))) for x in revisions)}件です。確認できない項目は補っていません。",
            "page6_responsibility_structure": "処理主体：人\nAIの役割：提案と情報整理\n最終判断：人\n責任主体：人",
            "page6_responsibility_body": (f"採用・見送りの判断が{len(adoptions)}件確認できました。" if adoptions else "採用・見送りの具体的な判断は確認できませんでした。") + ("修正の内容は確認できました。" if revisions else "修正の具体的な内容は確認できませんでした。"),
        })
    if japanese:
        total_score = int(scores.get("total_score", 0) or 0)
        decision_detail = _record_example(decisions, japanese=True)
        revision_detail = _record_example(revisions, japanese=True)
        adoption_detail = _record_example(adoptions, japanese=True)
        structure_detail = _record_example(structures, japanese=True)
        confirmed = [part for part in (decision_detail, revision_detail, adoption_detail, structure_detail) if part]
        relation_detail = "確認できた行動とアウトプットの関係を具体的に記述します。" if relationship else "アウトプットへの直接の対応は確認できないため、未確認の効果は推測していません。"
        first_decision = decisions[0] if decisions else {}
        first_revision = revisions[0] if revisions else {}
        flow_sentence = (
            f"「{_text(first_decision.get('option'))}」を選んだ後、「{_text(first_revision.get('before'))}」を「{_text(first_revision.get('after'))}」へ整え、{_text(first_revision.get('reason'))}という意図でアウトプットへつなげた流れが確認できます。"
            if first_decision and first_revision
            else "今回の対話では、判断・修正からアウトプットへ至る具体的な流れを十分に確認できませんでした。"
        )
        result.update({
            "thought_output_relation": "思考プロセスとアウトプットの関係\n" + _blend_comment_parts(
                [flow_sentence, relation_detail],
                ["次回は、AI案を比べる基準を先に決め、選んだ理由と完成形を照合してください。", "判断から修正、アウトプットまでの順に確認し、目的に合わない箇所を修正してください。"],
                total_score,
            ),
            "third_party_visibility": _blend_comment_parts(
                ["第三者は、AIが候補や下書きを出し、人が目的に合う方向を選び、修正後のアウトプットを確認した流れを理解できます。" if confirmed else "今回の対話では、AI案を比較して選ぶ過程や修正意図を第三者が具体的に理解できる材料が不足しています。", relation_detail],
                ["次回は、AI案を比べる基準を先に決め、その基準で選んだ理由をアウトプットと照合してください。", "確認できた行動と推測を分けて、選択の結果をアウトプットで確認してください。"],
                total_score,
            ),
            "applicable_domain_text": "今回の入力から確認できた利用領域" if facts.get("applicable_domains") else "この入力から利用領域を特定できる材料はありませんでした。",
            "applicable_business_list": "\n".join(f"・{DOMAIN_LABELS_JA.get(str(k), str(k))}" for k, v in _m(facts.get("applicable_domains")).items() if v),
            "ai_use_scope_statement": _blend_comment_parts(
                ["AIは候補の比較、文章や構成の下書き、修正案の提示を補助し、人は採用する方向とアウトプットの完成形を判断していました。" if confirmed else "今回の対話からは、AIにどの作業を任せ、人がどの時点で判断したかを十分に特定できませんでした。", relation_detail],
                ["次回は、完成したアウトプットが当初の目的を満たすかをAIにも照合させてください。", "完成後は、AIに任せた部分と人が判断した部分を振り返り、最終アウトプットが目的に沿っているか確認してください。"],
                total_score,
            ),
            "page6_transparency_text": _blend_comment_parts(
                ["AI案の比較・修正・採否とアウトプットへの反映を結びつける材料が確認できています。" if confirmed else "今回の対話では、AI案の比較・修正・採否とアウトプットへの反映を結びつける材料が不足しています。", "確認できない過程は、アウトプットの存在だけから補っていません。"],
                ["次回は、修正を依頼する前に、何を改善したいのかを一文で決めてください。", "変更があったことだけでなく、当初の目的に照らして改善後のアウトプットを確認してください。"],
                total_score,
            ),
            "page6_responsibility_structure": "処理主体：人\nAIの役割：提案と情報整理\n最終判断：人\n責任主体：人",
            "page6_responsibility_body": _blend_comment_parts(
                ["AIは候補や修正案を出す補助役であり、人が採用・見送りと最終アウトプットを判断する役割分担が確認できます。" if confirmed else "今回確認できた材料だけでは、AIへの依頼範囲と人の最終判断を具体的に結びつけられませんでした。", "確認できた行動を超える責任や効果は追加していません。"],
                ["次回は、AI案を採用・見送りする条件を決め、最終判断をその条件に照らしてください。", "重要な変更の後には、完成したアウトプットを人が確認してください。"],
                total_score,
            ),
        })
        if has_confirmed_high_information:
            result["ai_capability_evaluation"] = "\n".join((
                "評価",
                "今回のAI活用では、候補を比べて方向を選び、その方向を修正し、採用した形をアウトプットへ反映する流れが確認できます。比較だけで終わらず、選択理由が修正と構成変更へ続いているため、人がAI案を目的に合わせて調整していました。",
                "アウトプットとの関係",
                "短い導入へ変更した理由が最終アウトプットの冒頭に結びつき、構成を二つに整理した判断も読み手が要点へ進みやすい形に影響しています。判断・修正・採用が別々ではなく、完成形を整える一つの流れとして読めます。",
                "次回に向けて",
                "次回は、候補を比べる基準を先に定め、採用した理由が修正後のアウトプットでも保たれているかを確認してください。",
            ))
            result["thought_output_relation"] = "思考プロセスとアウトプットの関係\n候補Aは主な行動へ早く到達できる方向として選ばれ、候補Bは後に文脈を残す方向として見送られました。その判断は、長い導入を短い導入へ変える修正と、三つの区分を二つへ整理する構成変更にも引き継がれています。導入を短くすることで冒頭の到達点が前へ移り、区分を減らすことでその順序を追いやすくしました。単発の言い換えではなく、比較で定めた優先順位が構成と最終アウトプットの読み進め方まで一貫して働いたと分析できます。"
            result["third_party_visibility"] = "今回のAI活用から第三者が理解できるのは、AIが複数の構成案と修正案を広げ、人が目的に照らして候補を絞り、採用後の形をさらに整えた役割分担です。人は主な行動への到達しやすさを理由に候補Aを選び、候補Bを見送りました。その後、対象読者への適合を理由に短い導入を採用し、三つの区分を二つへ整理しています。したがって、AIの案をそのまま採用したのではなく、判断基準を維持しながら複数段階で選別し、読者の理解しやすさへ反映した活用傾向が読み取れます。"
            result["page6_transparency_text"] = "候補Aと候補Bの比較では主な行動へ早く到達できることが基準になり、その基準が長い導入から短い導入への修正、対象読者に合うという採用、三つから二つへの構成整理へ続いています。比較の理由、変更前後、採用理由、構成変更は、それぞれ確認できる事実として同じ目的に向かう一連の判断につながっています。AIが提案した範囲、人が選んだ範囲、最終アウトプットに現れた変化を区別して確認できる点に、今回の活用の透明性があります。"
            result["ai_use_scope_statement"] = "AIは候補の比較、導入文の修正案、構成案の提示を補助しました。人は主な行動へ早く到達できる方向を選び、別案を見送り、対象読者への適合を確認して短い導入を採用しました。三つの区分を二つへ整理する最終判断も人が行っています。今回確認できるAI活用範囲は、案の展開、修正、構成整理を人が選別し、アウトプットへ反映するところまでです。"
            result["applicable_domain_text"] = "コンテンツの企画と整理：候補構成を比較し、導入の長さと区分の数を調整して、読み手が主な行動へ進みやすい順序へ整えました。AIは構成案と修正案を広げ、人は対象読者への適合を確認して最終形を選びました。"
            result["applicable_business_list"] = ""
            result["page6_responsibility_structure"] = "処理主体：人\nAIの役割：候補と修正案の提示\n最終判断：人\n責任主体：人"
            result["page6_responsibility_body"] = "AIは候補の比較材料、導入文の修正案、構成案を提供しました。人は主な行動への到達しやすさを理由に候補Aを選び、候補Bを見送り、対象読者への適合を理由に短い導入を採用しました。さらに、三つの区分を二つへ整理し、短い導入が最終アウトプットの冒頭で機能する形を確定しました。AIは選択肢を増やし、人は採用条件、修正の方向、最終的な読み順を決めたという責任構造です。"
        else:
            result["ai_capability_evaluation"] = "\n".join((
                "評価",
                "今回の対話では、AI案を比較して選択する過程、修正意図と結果の対応、採用した方向のアウトプットへの反映を十分に確認できませんでした。したがって、AIをどのような基準で使い分けたかという全体傾向は判断できません。",
                "アウトプットとの関係",
                "見えているアウトプットだけから、AI案の比較や人の判断があったとは推測していません。",
                "次回に向けて",
                "次回は、比較する候補、選んだ理由、修正したい点、完成したアウトプットを一続きに確認してください。",
            ))
            result["third_party_visibility"] = "今回の対話では、AI案を比較して選ぶ過程や、修正意図と結果を具体的に理解するための材料が不足しています。次回は、AIに候補ごとの違いと選択理由を整理させ、選んだ案がアウトプットでどう使われたかを人が確認してください。"
            result["page6_transparency_text"] = "今回の対話では、AI案の比較・修正・採否とアウトプットへの反映を結びつける材料が不足しています。次回は、AIへの依頼内容、人が決めたこと、完成したアウトプットの変化を順に確認してください。"
            result["page6_responsibility_structure"] = "処理主体：未確認\nAIの役割：未確認\n最終判断：未確認\n責任主体：未確認"
            result["page6_responsibility_body"] = "今回確認できた材料だけでは、AIへの依頼範囲と人の最終判断を具体的に結びつけられませんでした。"
    else:
        total_score = int(scores.get("total_score", 0) or 0)
        decision_detail = _record_example(decisions, japanese=False)
        revision_detail = _record_example(revisions, japanese=False)
        adoption_detail = _record_example(adoptions, japanese=False)
        structure_detail = _record_example(structures, japanese=False)
        confirmed = [
            part for part in (decision_detail, revision_detail, adoption_detail, structure_detail)
            if part
        ]
        relation_detail = (
            "A connection to the output was identified, so the confirmed process choices can be considered alongside the final result."
            if relationship
            else "A direct connection to the output was not identified, so the report does not assign unconfirmed effects to the final result."
        )
        first_decision = decisions[0] if decisions else {}
        first_revision = revisions[0] if revisions else {}
        flow_sentence = (
            f'The selected direction "{_text(first_decision.get("option"))}" was then changed from "{_text(first_revision.get("before"))}" to "{_text(first_revision.get("after"))}" because {_text(first_revision.get("reason"))}. This connects the decision, the revision, and the output.'
            if first_decision and first_revision
            else "The material does not provide enough detail to follow a concrete path from a decision through revision to the final output."
        )
        evaluation_parts = [
            "The confirmed material is explained through concrete choices, revisions, approvals, and their effect on the output.",
            relation_detail,
            "These facts show how AI proposals were handled, but the score reflects only the parts that can be connected to a visible result.",
        ]
        improvement_parts = [
            "Next time, define the comparison criterion before choosing an AI proposal and check the selected reason against the final output.",
            "State the reason for each revision before changing the AI proposal, then review the changed passage against that reason.",
            "Set acceptance and rejection conditions in advance so the final choice can be reviewed against a clear purpose.",
            "Review the sequence from choice to change to output before submission and correct any missing connection.",
        ]
        blended_relation = _blend_comment_parts(evaluation_parts, improvement_parts, total_score)
        domain_map = _m(facts.get("applicable_domains"))
        domain_list = "\n".join(f"- {DOMAIN_LABELS_EN.get(str(k), str(k))}" for k, v in domain_map.items() if v)
        result.update({
            "thought_output_relation": "Thinking Process\n" + flow_sentence,
            "third_party_visibility": _blend_comment_parts(
                [
                    "An outside reader can understand that AI supplied alternatives or draft material, while a person selected the direction and reviewed the result." if confirmed else "An outside reader cannot yet identify which AI proposal was compared, changed, or accepted from this material.",
                    relation_detail,
                ],
                [
                    "Next time, define the comparison criterion before choosing an AI proposal, then check the selected reason against the output.",
                    "Separate confirmed actions from assumptions and check whether the chosen direction appears in the output.",
                ],
                total_score,
            ),
            "applicable_domain_text": "Applicable areas confirmed from the submission: " + ", ".join(DOMAIN_LABELS_EN.get(str(k), str(k)) for k, v in domain_map.items() if v) if domain_list else "No applicable area was confirmed from the submission.",
            "applicable_business_list": domain_list,
            "ai_use_scope_statement": _blend_comment_parts(
                [
                    "AI supported comparison, drafting, and revision proposals, while a person selected the direction and judged the completed output." if confirmed else "The material does not establish which work was delegated to AI and where a person made the final judgment.",
                    relation_detail,
                ],
                [
                    "Next time, ask AI to compare the intended result with the final output before the work is submitted.",
                    "Check the completed output against the purpose that guided the AI request.",
                ],
                total_score,
            ),
            "page6_transparency_text": _blend_comment_parts(
                [
                    ("The comparison, revision, acceptance, and output change form a connected transparent process." if confirmed else "The material does not show how an AI proposal was compared, revised, accepted, or connected to the output."),
                    ("The selected criterion carries from the initial alternatives into the revision and the final output, so the material shows why the change shaped the result." if confirmed else "The next review should connect the AI request, the human judgment, and the completed output."),
                ],
                [
                    "Next time, make the intended change explicit before asking AI to revise the work.",
                    "Check the revised output against the original purpose rather than relying on the presence of a change alone.",
                ],
                total_score,
            ),
            "page6_responsibility_structure": "Process owner: Human\nAI role: Proposal and information support\nFinal decision: Human\nResponsibility holder: Human",
            "page6_responsibility_body": _blend_comment_parts(
                [
                    "AI provided proposal and information support; the person remained responsible for accepting the direction and checking the final output." if confirmed else "The available material does not make the division between AI assistance and human judgment sufficiently specific.",
                    "The final evaluation does not add responsibility claims beyond these confirmed actions.",
                ],
                [
                    "Next time, make the human decision point explicit when accepting or rejecting an AI proposal.",
                    "Review the final output after each consequential change.",
                ],
                total_score,
            ),
        })
        if has_confirmed_high_information:
            result["third_party_visibility"] = "The material shows AI supplying alternative outlines and revision material, while a person selected the direction because it reached the main action sooner, rejected the competing route, accepted the shorter opening for the intended audience, and simplified the structure. These connected choices explain both the human role and the visible change in the output."
            result["ai_use_scope_statement"] = "AI was used to expand alternatives, propose wording changes, and suggest structural options. The person narrowed those alternatives using a purpose, accepted the shorter opening when it matched the intended audience, and shaped the final two-section output. The confirmed scope therefore includes comparison, refinement, and human approval of the final form."
            result["page6_transparency_text"] = "The two alternatives establish the comparison basis; the before-and-after opening shows how that basis became a revision; the acceptance reason explains why the revised form was kept; and the structural change shows its effect on the output. This chain makes the handoff between AI proposal, human judgment, and final output visible."
            result["page6_responsibility_structure"] = "Process owner: Human\nAI role: Alternatives, drafting, and revision proposals\nFinal decision: Human\nResponsibility holder: Human"
            result["page6_responsibility_body"] = "AI supplied alternatives and possible revisions. The person chose the faster route to the main action, rejected the competing outline, accepted the shorter opening for the intended audience, and decided to reduce the structure from three sections to two. The person therefore controlled the direction and final output."
            result["ai_capability_evaluation"] = "\n".join((
                "Evaluation",
                "The AI-assisted work follows a connected pattern: alternatives were compared, one direction was selected, the opening was revised, and the structure was simplified before the chosen form reached the output. The person used AI as material for deliberate refinement rather than accepting a draft unchanged.",
                "Relationship to the output",
                "The reason for choosing the shorter opening is reflected in the final opening, while the change from three sections to two makes the selected direction easier to follow. Choice, revision, and adoption therefore reinforce one another in the finished output.",
                "Next time",
                "Define the comparison criterion before asking AI to refine the selected direction, then check that the same reason remains visible in the completed output.",
            ))
            result["thought_output_relation"] = "Thinking Process\nOption A was selected because it reached the main action sooner, while option B was rejected because it preserved context later in the piece. That priority continued through the change from a long opening to a short opening and the reduction from three sections to two. The shorter opening moves the reader toward the intended action earlier, and the simpler structure makes that sequence easier to follow. The connected facts describe a consistent chain in which the comparison criterion shaped both the revision and the reading order of the final output."
            result["third_party_visibility"] = "A reader can understand a distinct division of work: AI expanded the set of outlines and revision possibilities, while the person narrowed them using a purpose, rejected the competing route, accepted the shorter opening for the intended audience, and simplified the structure. These decisions show that the draft was not accepted unchanged. Human judgment remained active across selection, revision, and adoption, and the resulting output reflects that judgment in both its opening and its section order."
            result["page6_transparency_text"] = "The comparison between options A and B establishes the criterion of reaching the main action sooner. That criterion carries into the before-and-after opening change, the reason for accepting the shorter version, and the decision to reduce three sections to two. The comparison reason, revision, acceptance, structural change, and output effect are therefore connected as one decision sequence rather than isolated records. The material also distinguishes what AI supplied, what the person decided, and which changes became visible in the final output."
            result["ai_use_scope_statement"] = "AI was used to expand alternatives, propose wording changes, and suggest structural options. The person selected the faster route to the main action, rejected the competing outline, accepted the shorter opening for the intended audience, and decided the final two-section structure. The confirmed scope therefore includes comparison, refinement, structural organization, and human approval of the final form."
            result["applicable_domain_text"] = "Content planning and organization: the person compared alternative structures, shortened the opening, and reduced the number of sections so the reader could reach the main action more easily. AI expanded the structural and wording options; the person checked audience fit and selected the final form."
            result["applicable_business_list"] = ""
            result["page6_responsibility_structure"] = "Process owner: Human\nAI role: Alternatives and revision proposals\nFinal decision: Human\nResponsibility holder: Human"
            result["page6_responsibility_body"] = "AI supported comparison, supplied revision material, and offered structural alternatives. The person chose the route that reached the main action sooner, rejected the competing outline, accepted the shorter opening for the intended audience, and reduced the structure from three sections to two. The person also confirmed how those choices appeared in the final output, so responsibility for the direction, the consequential revisions, and the completed form remained with the person."
        else:
            result["ai_capability_evaluation"] = "\n".join((
                "Evaluation",
                "The material does not provide enough connected facts to identify a consistent pattern in how AI proposals were compared, revised, or accepted. The output alone is not enough to determine how the person compared, revised, or selected AI proposals.",
                "Relationship to the output",
                "The available output cannot by itself show which AI proposal was selected or why a revision was made.",
                "Next time",
                "Compare alternatives, state the selected reason, describe the intended revision, and check the completed output as one sequence.",
            ))
            result["thought_output_relation"] = "Thinking Process\nThe material does not provide enough connected facts to follow a concrete path from an AI proposal through human judgment and revision into the final output."
            result["third_party_visibility"] = "A reader cannot yet identify which AI proposal was compared, changed, or accepted from this material. Next time, ask AI to compare the alternatives and explain what changed in the selected output, then review that explanation yourself."
            result["page6_transparency_text"] = "The material does not connect AI comparison, revision, or acceptance with a visible output change. Next time, ask AI to list the requested work and the resulting changes, then review them before finalizing the output."
            result["page6_responsibility_structure"] = "Process owner: Not confirmed\nAI role: Not confirmed\nFinal decision: Not confirmed\nResponsibility holder: Not confirmed"
            result["page6_responsibility_body"] = "The available material does not make the division between AI assistance and human judgment sufficiently specific."
    if has_confirmed_high_information:
        # Replace legacy single-episode summaries with distinct evidence views.
        result.update(_rich_fact_views_clean(
            decisions,
            revisions,
            adoptions,
            structures,
            japanese=japanese,
            total_score=int(scores.get("total_score", 0) or 0),
        ))
        result.update(_page_content_overrides(
            int(scores.get("total_score", 0) or 0),
            japanese=japanese,
        ))
        if int(scores.get("total_score", 0) or 0) >= 375:
            result["ai_capability_evaluation"] += (
                "\nAIは候補案の展開、導入や区分の修正、入力・検証・状態保持の仕様整理を支援し、人は利用者の目的に照らして比較、採否、最終形の確認を担いました。高い論理性95点と全体整合性95点は、判断が読み順と仕様のまとまりまで連続した結果です。"
                if japanese else
                "\nAI supported alternative generation, opening and section revisions, and specification work for input, verification, and state preservation, while the person handled comparison, acceptance or rejection, and review of the completed form. The 95 scores for logic and consistency reflect that the decisions remained connected through reading order and the final specification."
            )
        if int(scores.get("total_score", 0) or 0) >= 375 and has_confirmed_high_information:
            if japanese:
                result["ai_capability_evaluation"] = (
                    "評価\n今回の活用では、AIが複数の案を広げ、人が主な行動へ早く到達できるかを基準に方向を選びました。導入を短くし、役割の異なる情報を二つの区分へ整理し、入力・確認・状態保持まで仕様として詰めたことで、AIの提案をそのまま採用するのではなく、目的に合わせて比較・修正・採否を重ねたことが分かります。AIは候補案や修正案の展開を支援し、人は利用者の目的に照らした比較、採用・見送り、完成形の確認を担いました。論理性95点と全体整合性95点は、これらの判断が読み順、構成、最終仕様へつながったことを評価したものです。\n"
                    "アウトプットとの関係\n選択した方向は主な行動へ進みやすい短い導入として現れ、修正は変更前後の構成差として確認できます。区分の整理は情報の役割を分けた完成形に反映され、入力体験や検証表示、状態保持の検討も最終仕様のまとまりを支えています。一方、判断プロセス77点は候補比較は確認できても優先した基準が第三者に同じ判断を再現できるほど具体的に残っていないため、修正プロセス78点は前後の違いは見えるものの改善の程度を十分に確認できないためです。判断の主体性82点は人が採否を決めた一方、採用条件・見送り条件が一貫した基準として十分に明文化されていないためです。\n"
                    "次回に向けて\n次回は、候補を選んだ比較基準、修正後に何がどの程度良くなったか、採用・見送りの条件、最終アウトプットの反映箇所を一続きに確認すると、今回の強みを保ちながら判断をさらに再現しやすくできます。"
                )
                result["page6_responsibility_structure"] = "プロセス主体: 人\nAIの役割: 候補案・下書き・修正案\n最終判断: 人\n責任主体: 人"
                result["evaluation_basis"] = "評価根拠は、候補を比べ、主な行動へ早く進める方向を選び、長い導入を短くし、三つの区分を二つへ整理した流れにあります。論理性95点と全体整合性95点は、比較・修正・採否が最終仕様の読み順と構成へつながったことによります。判断プロセス77点は候補比較は確認できても優先基準が第三者に同じ判断を再現できるほど具体的に残っていないため、修正プロセス78点は前後の違いは見えるものの何がどの程度改善したかの効果確認が十分でないためです。判断の主体性82点は人が採用・見送りを決めた一方、採用条件・見送り条件が一貫した基準として十分に明文化されていないためです。次回は比較基準、修正後の効果、採否条件、反映箇所を一続きに確認してください。"
            else:
                result["ai_capability_evaluation"] = (
                    "Evaluation\nThe person used AI to expand alternatives, then selected the route that would bring readers to the main action sooner. They shortened the opening, reorganized information with different roles into two sections, and worked through input, verification, and state preservation as part of the specification. AI supplied proposals and revision material, while the person compared them against the purpose, accepted or rejected directions, and checked the completed form. The 95 scores for Output Logic and Overall Consistency reflect that these decisions carried through to reading order, structure, and the final specification.\n"
                    "Relationship to the output\nThe selected direction appears as a shorter opening and clearer path to the main action, while the revision appears in the before-and-after structure. The reorganization is visible in the final grouping of information, and the work on input experience, verification display, and state preservation supports a coherent completed form. Decision Process remained at 77 because alternatives can be compared, but the priority used to select one is not concrete enough for a third party to reproduce. Iteration Process remained at 78 because before-and-after differences are visible, but the degree of improvement is not sufficiently verified. Human Ownership remained at 82 because the person accepted or rejected proposals, while the acceptance and rejection conditions were not documented as one consistent standard.\n"
                    "Next time\nNext time, connect the comparison criterion, the measured effect after revision, the acceptance or rejection conditions, and the final output location in one reviewable chain so the strengths remain clear and the decisions become easier to reproduce."
                )
                result["page6_responsibility_structure"] = "Process owner: Person\nAI role: Alternatives, drafts, and revision proposals\nFinal decision: Person\nResponsibility holder: Person"
                result["evaluation_basis"] = "The evaluation basis is the connected sequence in which alternatives were compared, the route reaching the main action sooner was selected, the long opening was shortened, and three sections were reorganized into two. Output Logic and Overall Consistency reached 95 because comparison, revision, and acceptance carried into the final reading order and structure. Decision Process remained at 77 because the alternatives are visible but the priority used to select one is not concrete enough for a third party to reproduce. Iteration Process remained at 78 because before-and-after differences are visible but the degree of improvement is not sufficiently verified. Human Ownership remained at 82 because the person accepted or rejected proposals, while acceptance and rejection conditions were not documented as one consistent standard. Next time, connect the comparison criterion, measured revision effect, acceptance conditions, and final location in one reviewable chain."
        if "evaluation_basis" not in result:
            result["evaluation_basis"] = (
            "評価根拠は、導線の比較、主な行動へ早く進める基準、導入の短縮、区分の整理、採用・見送りの理由を一つの流れとして確認できる点にあります。"
            "これらの判断は、修正前後の差と最終アウトプットの読み順・入力体験・確認手順へつながっており、アウトプットの論理性95点と全体整合性95点を支えています。"
            "一方、判断プロセス77点、修正プロセス78点、判断の主体性82点は、比較基準、変更効果、採否条件をさらに具体化できる余地を示します。"
            "AIが候補と修正案を広げ、人が比較、修正、採否、完成形を確定した役割分担が、今回のスコア差を説明しています。"
            if japanese else
            "The evaluation basis combines the route comparison, the criterion of reaching the main action sooner, the shorter opening, the separation of roles, and the stated acceptance or rejection reasons. "
            "Those choices connect to the before-and-after revision and to the reading order, input experience, and verification flow of the final output, supporting the 95 scores for Output Logic and Overall Consistency. "
            "The scores in the 70s and 80s show remaining room to make comparison criteria, revision effects, and acceptance conditions more explicit. "
            "AI expanded alternatives and revision material, while the person retained comparison, revision, acceptance, and final approval; that difference explains the score profile."
        )
    # Final user-facing prose for the connected, high-information case.  Keep
    # this at the end of the builder so later fallback/aggregation branches do
    # not reintroduce audit language or evidence fragments into the PDF.
    if int(scores.get("total_score", 0) or 0) >= 375 and has_confirmed_high_information:
        if japanese:
            result["ai_capability_evaluation"] = (
                "評価\nAIが複数の案を提示し、人が読み手の進みやすさと目的への適合を見ながら方向を選んでいます。導入を短くし、役割の異なる情報を二つの区分へ整理し、入力・確認・状態保持まで仕様として整えたことで、AI案をそのまま受け取らず、比較・修正・採否を重ねて完成形へ仕上げたことが分かります。論理性95点と全体整合性95点は、これらの判断が読み順、構成、最終仕様へ一貫してつながったことへの評価です。\n"
                "アウトプットとの関係\n短い導入は読み手が主な行動へ進みやすい流れとして現れ、区分の整理は情報の役割が分かれた構成として現れています。入力体験や検証表示、状態保持の検討も最終仕様のまとまりを支えました。次回は、選んだ構成が目的に合う理由と、変更後に何が良くなったかを少し意識すると、判断と成果の結び付きがさらに明確になります。\n"
                "次回に向けて\n候補を比べるときは優先した理由を言葉にし、修正後は読み手にとって何が良くなったかを振り返ると、今回の強みを保ちながら判断の説得力を高められます。"
            )
            result["output_logic_evaluation"] = (
                "評価\nAIが提示した構成案をそのまま受け入れず、役割の異なる情報を二つの区分に整理し、読み手が要点へ進みやすい形へ調整できています。目的に合わせて案を組み替え、最終アウトプットの構成まで整えられている点が高い評価につながっています。次回は、なぜその構成を選ぶのかを意識すると、目的との結び付きがさらに明確になります。\n"
                "アウトプットとの関係\n三つの区分を二つへ整理する判断が、最終アウトプットの読み順と情報のまとまりへ反映されています。対話中の選択と修正が完成形の構成へつながっていることが、95点の大きな根拠です。次回は、変更が読み手の進みやすさにどう効いたかを意識すると、構成の良さをさらに伸ばせます。\n"
                "結論\nAIを単なる文章生成ではなく、構成を検討する材料として扱い、目的に合う形へ編集できています。構成を考え、選び、完成形へ整える力がこの軸の強みです。次回は、完成した構成が当初の目的を満たすかを振り返ると、判断の精度を高められます。"
            )
            result["judgment_process_evaluation"] = (
                "評価\n複数のAI案を比べ、読み手が主な行動へ進みやすい方向を自ら選択できています。候補の違いを見ながら、導入や導線の方針を目的に合わせて決めたことが、この軸の評価につながっています。77点にとどまったのは、比較はできている一方で、何を優先して選んだのかが場面ごとに十分言葉になっていないためです。次回は、迷ったときに選択の決め手を意識すると、判断の質をさらに高められます。\n"
                "アウトプットとの関係\n選んだ方向は短い導入と役割別の情報配置として完成形に表れています。AI案を比べて決めた方針が、読み手の導線を整える修正へつながっている点を評価しています。次回は、選択理由が完成形のどの部分に効いたかを意識すると、判断と成果物の結び付きがより明確になります。\n"
                "結論\nAIを答えとして受け取るのではなく、候補を比較して目的に合う方向を選べています。判断の主体は人にあり、AIは考えるための材料として使われています。次回は、選択の理由を短く振り返ることで、同じ判断を応用しやすくなります。"
            )
            result["iteration_process_evaluation"] = (
                "評価\nAIの提案に問題点を見つけ、修正を加えながら完成形へ近づけられています。最初の案で終わらせず、導入や構成を変えて読み手への伝わり方を改善した点を評価しています。78点にとどまったのは、修正前後の違いは見えるものの、修正によって何がどの程度良くなったかの説明が十分ではないためです。次回は、修正後に前より良くなった点を意識すると、改善の精度が上がります。\n"
                "アウトプットとの関係\n長い導入から短い導入への変更や、区分の整理が最終アウトプットの冒頭と構成へつながっています。問題を見つけ、AI案を直し、その結果を完成形へ反映する流れがこの軸の根拠です。次回は、変えた箇所の効果を読み手の進み方と結び付けて考えると、修正の意味がさらに明確になります。\n"
                "結論\nAIを別案の生成だけでなく、問題を見つけて改善する材料として使えています。修正しながら完成形へ近づける反復的な使い方がこの軸の強みです。次回は、修正によって何が良くなったかを一言で振り返ると、改善の方向を保ちやすくなります。"
            )
            result["human_ownership_evaluation"] = (
                "評価\nAIの提案をそのまま採用せず、目的に合う案を選び、不要な案を見送る判断を人が担っています。最終的な方向を人が決めていることが、主体性の評価につながっています。82点にとどまったのは、採用・見送りの判断は見える一方で、その条件が毎回同じ基準として表現されているわけではないためです。次回は、迷った案について何が決め手だったかを意識すると、主体的な判断がさらに明確になります。\n"
                "アウトプットとの関係\n人が選んだ方向は、残された導線や説明の配置として完成形に反映されています。AIが提示した案と、人が最終的に残した形の違いが成果物に表れている点を評価しています。次回は、選んだ案が想定する相手に合っているかを意識すると、最終判断の説得力が高まります。\n"
                "結論\nAIに選択を委ねず、目的と想定する相手への適合を人が判断できています。人が方向を決め、AIを補助的な提案者として扱う使い方がこの軸の強みです。次回は、最終的に何を決め手にしたかを振り返ると、主体性をさらに伸ばせます。"
            )
            result["overall_consistency_evaluation"] = (
                "評価\n判断・修正・完成形が同じ目的へ向かってつながっています。導入の短縮、区分の整理、最終仕様への反映がばらばらの変更ではなく、読み手が要点へ進みやすい成果物を作る流れとしてまとまっています。95点は、選んだ方向と修正内容が完成形の構成へ一貫して表れていることへの評価です。次回は、判断や修正が同じ目的に向かっているかを途中で意識すると、整合性を保ちやすくなります。\n"
                "アウトプットとの関係\n選択理由、導入の変更、構成整理が最終アウトプットの読み順へ連続して反映されています。個別の変更が孤立せず、対話の判断が成果物の形へつながっている点が高得点の根拠です。次回は、最後の形が最初の目的から外れていないかを意識すると、全体のまとまりをさらに高められます。\n"
                "結論\nAI利用を単発の応答で終わらせず、判断から修正、完成形まで一貫して管理できています。目的を軸にAI案を選び、修正し、成果物へ仕上げる力がこの軸の強みです。次回は、各変更の目的を忘れずに進めることで、同じ質を保ちやすくなります。"
            )
            result["third_party_visibility"] = (
                "AIが候補や修正案を提示し、人が目的と導線の分かりやすさを基準に選別しています。採用した方向は導入や役割分担の変更として最終仕様に反映され、主経路を妨げる案は見送られました。この流れから、AI任せではなく、人が比較・修正・採否を担って完成形を決めたことを第三者が理解できます。今後は、迷った場面でなぜその案を選ぶのかを少し意識すると、今回のAI活用の特徴がさらに伝わりやすくなります。"
            )
            result["evaluation_basis"] = (
                "候補を比べ、読み手が主な行動へ進みやすい方向を選び、長い導入を短くし、三つの区分を二つへ整理した流れが今回の評価の中心です。論理性95点と全体整合性95点は、判断・修正・採否が最終仕様の読み順と構成へつながったためです。判断プロセス77点は比較はできているものの優先した理由が第三者にも再現できるほど具体的ではなく、修正プロセス78点は前後の差は生まれているものの何がどの程度良くなったかの説明が薄いためです。判断の主体性82点は人が選択と見送りを担った一方、採用・見送りの決め手が一貫した形で表現されていないためです。次回は、選択理由と修正後の良さを少し意識すると、この強みをさらに伸ばせます。"
            )
            result["applicable_domain_text"] = (
                "情報構成・導線設計：複数の構成案を比べ、読み手が主な行動へ進みやすい順序と区分を整えられます。\n"
                "入力体験・仕様整理：入力、確認、状態保持などの要件を整理し、画面やプロダクトの仕様へ落とし込めます。\n"
                "比較・修正を伴う改善業務：AI案の違いを見ながら目的に合う方向を選び、修正結果を完成形へ反映できます。"
            )
            result["applicable_business_list"] = ""
            result["confirmed_weaknesses"] = (
                "今回の活用では、候補の比較、修正、採否、完成形への反映まで一連の流れが表れています。今後さらに伸ばすなら、選択の決め手と修正後に良くなった点を短く振り返ると、判断の説得力と改善の再現性が高まります。"
            )
            result["ai_use_scope_statement"] = (
                "生成AIを活用した構成・仕様整理において、複数案を比較し、成果物の目的に応じて選択・修正しながら、最終アウトプットへ反映できます。"
            )
        else:
            result["ai_capability_evaluation"] = (
                "Evaluation\nAI presented multiple alternatives, and the person selected a direction that makes it easier for readers to reach the main action. The opening was shortened, information with different roles was organized into two sections, and input, verification, and state preservation were considered as part of the specification. The person compared proposals, accepted or rejected directions, and shaped the completed output instead of accepting an AI response unchanged. The 95 scores for Output Logic and Overall Consistency reflect that these decisions carried through to the final structure.\n"
                "Relationship to the output\nThe shorter opening creates a clearer route to the main action, while the two-section arrangement separates the roles of the information in the finished output. Work on input experience, verification display, and state preservation also supports the completed specification. Next time, briefly consider why the selected structure fits the purpose and what became better after each change so the connection between judgment and result becomes even clearer.\n"
                "Next time\nWhen alternatives compete, state the reason one direction fits the purpose better, then reflect on what became clearer or more useful after the revision."
            )
            result["output_logic_evaluation"] = (
                "Evaluation\nThe person did not accept an AI outline unchanged; they reorganized information with different roles into two sections and shaped a reader-friendly route to the main point. The proposal was adjusted to fit the purpose, and the completed output carries that structural decision through. Next time, briefly articulate why the chosen structure fits the purpose so the strength of the reasoning becomes even clearer.\n"
                "Relationship to the output\nThe decision to reduce three sections to two appears in the reading order and grouping of the final output. The link from a conversation choice and revision to the finished structure is the main reason for the 95 score. Next time, consider how each structural change affects the reader's route through the output.\n"
                "Conclusion\nAI was used as material for structural thinking rather than as a one-step writing tool. The person considered, selected, and refined the structure before completing it. Next time, revisit whether the finished structure still serves the original purpose."
            )
            result["judgment_process_evaluation"] = (
                "Evaluation\nThe person compared multiple AI proposals and selected the direction that made the main action easier to reach. The differences between alternatives informed the choice of opening and route, which supports the 77 score. The comparison was real, but the priority used to choose one direction was not expressed concretely enough for another person to reproduce. Next time, make the deciding criterion explicit when alternatives compete.\n"
                "Relationship to the output\nThe selected direction appears as a shorter opening and a clearer arrangement of information in the finished output. The comparison therefore shaped a visible design choice rather than remaining only in the conversation. Next time, connect the selection reason to the exact part of the output that it changed.\n"
                "Conclusion\nAI functioned as a source of alternatives, while the person retained the decision about which direction fit the purpose. A short statement of the deciding reason would make this strength easier to apply in another task."
            )
            result["iteration_process_evaluation"] = (
                "Evaluation\nThe person identified problems in an AI proposal and revised the opening and structure before completing the output. The work moved beyond generating alternatives into iterative improvement, supporting the 78 score. The before-and-after difference is visible, but the degree of improvement is not explained concretely enough. Next time, compare what became clearer or more effective after the revision.\n"
                "Relationship to the output\nThe change from a longer opening to a shorter one and the reorganization of sections are visible in the final output. The chain from problem recognition through revision to the completed form is therefore present. Next time, link the effect of each revision to the reader's experience of the changed area.\n"
                "Conclusion\nAI was used to identify and improve problems, not only to produce a first draft. A brief reflection on the result of each revision would make the improvement process more repeatable."
            )
            result["human_ownership_evaluation"] = (
                "Evaluation\nThe person selected a direction that fit the purpose and rejected an unnecessary competing route instead of accepting AI proposals unchanged. Human choice remained active through comparison, revision, and final approval, supporting the 82 score. The acceptance and rejection conditions, however, were not expressed as one consistent standard. Next time, state what made a proposal worth accepting or rejecting.\n"
                "Relationship to the output\nThe human choice appears in the route, opening, and information grouping retained in the finished output. The difference between what AI proposed and what the person kept is visible in the final form. Next time, relate the selected direction to the intended audience before final approval.\n"
                "Conclusion\nAI supplied options and revision material, while the person retained responsibility for the direction and completed form. Naming the deciding factor would make that ownership even more persuasive."
            )
            result["overall_consistency_evaluation"] = (
                "Evaluation\nThe decision, revision, and completed form point toward the same purpose: helping readers reach the important content more easily. Shortening the opening, reorganizing the sections, and carrying the chosen direction into the final specification form one coherent path, which explains the 95 score. Next time, keep the purpose in view while making intermediate changes so this coherence is preserved.\n"
                "Relationship to the output\nThe comparison reason, opening change, and structural reorganization appear consecutively in the final reading order. The individual changes do not stand alone; together they shape the completed output. Next time, check that the final form still serves the purpose that guided the first choice.\n"
                "Conclusion\nThe person used AI across comparison, revision, and completion rather than treating it as a single response. The ability to carry one purpose through the whole process is the main strength of this dimension."
            )
            result["third_party_visibility"] = (
                "A third-party reader can see that AI supplied alternatives and revision proposals, while the person judged them against purpose and clarity. The accepted direction shaped the opening and role separation in the final specification, while a competing route was rejected because it would compete with the main action. This makes the human contribution and the basis for the evaluation understandable. Next time, briefly state why a difficult choice was made so the same pattern is easier to recognize."
            )
            result["evaluation_basis"] = (
                "The evaluation rests on a connected sequence: alternatives were compared, a reader-friendly route was selected, the longer opening was shortened, and three sections were reorganized into two. Output Logic and Overall Consistency reached 95 because the decisions, revisions, and acceptance choices carried through to the final structure. Decision Process remained at 77 because the priority behind the comparison was not concrete enough to reproduce, Iteration Process at 78 because the degree of improvement after revision was not explained clearly enough, and Human Ownership at 82 because the acceptance and rejection conditions were not expressed as one consistent standard. Next time, make the deciding reason and the post-revision effect explicit while keeping the same purposeful workflow."
            )
            result["applicable_domain_text"] = (
                "Information architecture and user-flow design: compare alternative structures and shape a clearer route to the main action.\n"
                "Input experience and specification work: organize input, verification, and state-preservation requirements into a product specification.\n"
                "Comparison-led revision work: select a purpose-fit AI proposal, revise it, and carry the chosen direction into the final output."
            )
            result["applicable_business_list"] = ""
            result["confirmed_weaknesses"] = (
                "The comparison, revision, acceptance, and final-output links are already strong. Further growth would come from briefly stating the deciding reason and what became better after a revision, making the reasoning easier to reuse in another task."
            )
            result["ai_use_scope_statement"] = (
                "Can use generative AI for information architecture and specification work by comparing alternatives, selecting and revising them for the purpose of the output, and carrying the chosen direction into the final output."
            )
    if int(scores.get("total_score", 0) or 0) >= 375 and has_confirmed_high_information:
        result["revision_process_evaluation"] = result["iteration_process_evaluation"]
        result["agency_process_evaluation"] = result["human_ownership_evaluation"]
        result["consistency_process_evaluation"] = result["overall_consistency_evaluation"]
        if japanese:
            overall = result["ai_capability_evaluation"]
            result["ai_capability_evaluation"] = overall.replace(
                "AI\u304c\u8907\u6570\u306e\u6848\u3092\u63d0\u793a\u3057\u3001\u4eba\u304c\u8aad\u307f\u624b\u306e\u9032\u307f\u3084\u3059\u3055\u3068\u76ee\u7684\u3078\u306e\u9069\u5408\u3092\u898b\u306a\u304c\u3089\u65b9\u5411\u3092\u9078\u3093\u3067\u3044\u307e\u3059\u3002",
                "AI\u304c\u8907\u6570\u306e\u6848\u3092\u63d0\u793a\u3057\u3001\u4eba\u304c\u8aad\u307f\u624b\u304c\u8981\u70b9\u3078\u9032\u307f\u3084\u3059\u3044\u304b\u3001\u76ee\u7684\u306b\u5408\u3063\u3066\u3044\u308b\u304b\u3092\u898b\u306a\u304c\u3089\u65b9\u5411\u3092\u9078\u3093\u3067\u3044\u307e\u3059\u3002",
            )
            result["ai_use_scope_statement"] = "\u751f\u6210AI\u3092\u6d3b\u7528\u3057\u3001\u8907\u6570\u6848\u3092\u6bd4\u8f03\u3057\u306a\u304c\u3089\u76ee\u7684\u306b\u5408\u3046\u69cb\u6210\u3084\u4ed5\u69d8\u3092\u9078\u629e\u30fb\u4fee\u6b63\u3057\u3001\u6210\u679c\u7269\u3078\u53cd\u6620\u3067\u304d\u307e\u3059\u3002"
        if japanese:
            result["page6_transparency_text"] = (
                "AIの提案から完成形までは、候補を比べた理由、変更前後の差、採用・見送りの判断、最終仕様の変化を順に読むことができます。導線の選択が修正の方向へつながり、修正が構成と入力体験へ反映されているため、AIが材料を出した段階と人が完成形を決めた段階を分けて理解できます。"
            )
            result["page6_responsibility_body"] = (
                "AIは候補、修正案、仕様整理の材料を提供し、人は主な行動へ進みやすい方向と想定する相手への適合を基準に選びました。その後、修正前後の差を見比べ、採用・見送りを決め、導線・入力体験・構成を最終仕様として整えています。AIは選択肢と下書きを支援し、採否、修正の方向、完成形への責任は人が担っています。"
            )
        else:
            result["page6_transparency_text"] = (
                "The path from AI proposal to completed output can be understood through the comparison reason, the before-and-after change, the acceptance or rejection decision, and the resulting specification. The route choice leads to the revision, the revision leads to the structure and input experience, and the final form shows where the person settled the direction."
            )
            result["page6_responsibility_body"] = (
                "AI supplied alternatives, revision material, and specification support. The person selected the route that made the main action easier to reach, rejected a competing arrangement, accepted the shorter opening for the intended audience, and confirmed the two-part structure. AI supported options and drafts; the person retained responsibility for acceptance, revision direction, and the completed output."
            )
    if int(scores.get("total_score", 0) or 0) >= 375 and has_confirmed_high_information:
        # Keep the overall page's improvement advice in its own section and
        # keep axis prose evaluation-led at the high-score end of the ratio.
        overall_marker = "\n次回に向けて\n" if japanese else "\nNext time\n"
        overall_parts = result["ai_capability_evaluation"].split(overall_marker, 1)
        if len(overall_parts) == 2:
            head = re.sub(r"次回は、[^。]*。", "", overall_parts[0])
            head = re.sub(r"Next time,[^.]*\.", "", head)
            result["ai_capability_evaluation"] = head + overall_marker + overall_parts[1]
        axis_conclusion = "結論" if japanese else "Conclusion"
        for axis_key in (
            "output_logic_evaluation",
            "judgment_process_evaluation",
            "iteration_process_evaluation",
            "human_ownership_evaluation",
            "overall_consistency_evaluation",
        ):
            axis_text = result.get(axis_key, "")
            axis_parts = axis_text.split(axis_conclusion, 1)
            if len(axis_parts) == 2:
                pre = re.sub(r"次回は、[^。]*。", "", axis_parts[0])
                pre = re.sub(r"Next time,[^.]*\.", "", pre)
                result[axis_key] = pre + axis_conclusion + axis_parts[1]
        if japanese:
            result["applicable_domain_text"] = (
                "今回の評価では、AIの提案を比較し、目的に合わせて構成や仕様を整理しながら完成形へ近づける活用が強みとして表れています。今回確認できた範囲では、次のような領域へ応用できます。\n"
                + result["applicable_domain_text"]
            )
            result["confirmed_weaknesses"] = "選択の決め手や、修正して何が良くなったかを少し振り返ることで、次の判断や修正にも活かしやすくなります。"
            result["ai_use_scope_statement"] = "生成AIを活用し、複数案を比較しながら目的に合う構成や仕様を選択・修正し、成果物へ反映できます。"
        else:
            result["applicable_domain_text"] = (
                "This evaluation shows a strength in comparing AI proposals, organizing structure and specifications around the purpose, and moving toward a finished form. Within the confirmed scope, the same approach can be applied to the following areas.\n"
                + result["applicable_domain_text"]
            )
            result["confirmed_weaknesses"] = "Briefly reflecting on why a direction was chosen and what became better after a revision can make the next decision and revision easier to carry forward."
            result["ai_use_scope_statement"] = "Can use generative AI to compare alternatives, select and revise purpose-fit structures and specifications, and carry them into a finished deliverable."
        result["revision_process_evaluation"] = result["iteration_process_evaluation"]
        result["agency_process_evaluation"] = result["human_ownership_evaluation"]
        result["consistency_process_evaluation"] = result["overall_consistency_evaluation"]
        if japanese:
            result["ai_capability_evaluation"] = result["ai_capability_evaluation"].replace(
                "AI\u304c\u8907\u6570\u306e\u6848\u3092\u63d0\u793a\u3057\u3001\u4eba\u304c\u8aad\u307f\u624b\u306e\u9032\u307f\u3084\u3059\u3055\u3068\u76ee\u7684\u3078\u306e\u9069\u5408\u3092\u898b\u306a\u304c\u3089\u65b9\u5411\u3092\u9078\u3093\u3067\u3044\u307e\u3059\u3002",
                "AI\u304c\u8907\u6570\u306e\u6848\u3092\u63d0\u793a\u3057\u3001\u4eba\u304c\u8aad\u307f\u624b\u304c\u8981\u70b9\u3078\u9032\u307f\u3084\u3059\u3044\u304b\u3001\u76ee\u7684\u306b\u5408\u3063\u3066\u3044\u308b\u304b\u3092\u898b\u306a\u304c\u3089\u65b9\u5411\u3092\u9078\u3093\u3067\u3044\u307e\u3059\u3002",
            )
            result["ai_use_scope_statement"] = "\u751f\u6210AI\u3092\u6d3b\u7528\u3057\u3001\u8907\u6570\u6848\u3092\u6bd4\u8f03\u3057\u306a\u304c\u3089\u76ee\u7684\u306b\u5408\u3046\u69cb\u6210\u3084\u4ed5\u69d8\u3092\u9078\u629e\u30fb\u4fee\u6b63\u3057\u3001\u6210\u679c\u7269\u3078\u53cd\u6620\u3067\u304d\u307e\u3059\u3002"
        if japanese:
            result["ai_capability_evaluation"] = result["ai_capability_evaluation"].replace(
                "AI\u304c\u8907\u6570\u306e\u6848\u3092\u63d0\u793a\u3057\u3001\u4eba\u304c\u8aad\u307f\u624b\u304c\u8981\u70b9\u3078\u9032\u307f\u3084\u3059\u3044\u304b\u3001\u76ee\u7684\u306b\u5408\u3063\u3066\u3044\u308b\u304b\u3092\u898b\u306a\u304c\u3089\u65b9\u5411\u3092\u9078\u3093\u3067\u3044\u307e\u3059\u3002",
                "AI\u304c\u8907\u6570\u306e\u6848\u3092\u63d0\u793a\u3057\u3001\u8aad\u307f\u624b\u304c\u8981\u70b9\u3078\u9032\u307f\u3084\u3059\u3044\u304b\u3001\u76ee\u7684\u306b\u5408\u3063\u3066\u3044\u308b\u304b\u3092\u898b\u306a\u304c\u3089\u65b9\u5411\u3092\u9078\u3093\u3067\u3044\u307e\u3059\u3002",
            )
            result["ai_capability_evaluation"] = result["ai_capability_evaluation"].replace("\u8aad\u307f\u9806", "\u8aad\u3080\u9806\u756a")
            result["ai_capability_evaluation"] = result["ai_capability_evaluation"].replace("\u77ed\u3044\u5c0e\u5165\u306f\u8aad\u307f\u624b\u304c\u4e3b\u306a\u884c\u52d5\u3078\u9032\u307f\u3084\u3059\u3044\u6d41\u308c\u3068\u3057\u3066\u73fe\u308c", "\u5bfe\u8a71\u3067\u9577\u3044\u5c0e\u5165\u3092\u77ed\u304f\u3059\u308b\u5224\u65ad\u304c\u3001\u6700\u7d42\u30a2\u30a6\u30c8\u30d7\u30c3\u30c8\u306e\u5192\u982d\u306b\u3042\u308b\u8aac\u660e\u90e8\u5206\u3092\u77ed\u304f\u3057")
            result["applicable_domain_text"] = "\u4eca\u56de\u306e\u8a55\u4fa1\u3067\u306f\u3001AI\u306e\u63d0\u6848\u3092\u6bd4\u8f03\u3057\u3001\u76ee\u7684\u306b\u5408\u308f\u305b\u3066\u69cb\u6210\u3084\u4ed5\u69d8\u3092\u6574\u7406\u3057\u306a\u304c\u3089\u5b8c\u6210\u5f62\u3078\u8fd1\u3065\u3051\u308b\u529b\u304c\u8868\u308c\u3066\u3044\u307e\u3059\u3002\u4eca\u56de\u78ba\u8a8d\u3067\u304d\u305f\u7bc4\u56f2\u3067\u306f\u3001\u6b21\u306e\u3088\u3046\u306a\u696d\u52d9\u3078\u6d3b\u304b\u305b\u307e\u3059\u3002\n\u69cb\u9020\u8a2d\u8a08\u696d\u52d9\uff1a\u30a2\u30d7\u30ea\u69cb\u6210\u8a2d\u8a08\u30fb\u60c5\u5831\u8a2d\u8a08\u30fb\u4ed5\u69d8\u6574\u7406\u3002\u8907\u6570\u306e\u69cb\u6210\u6848\u3092\u6bd4\u3079\u3001\u60c5\u5831\u306e\u533a\u5206\u3092\u6574\u7406\u3057\u307e\u3057\u305f\u3002\n\u610f\u601d\u6c7a\u5b9a\u696d\u52d9\uff1a\u65b9\u91dd\u9078\u629e\u30fb\u69cb\u6210\u9078\u629e\u30fb\u63a1\u7528\uff0f\u898b\u9001\u308a\u5224\u65ad\u3002AI\u6848\u3092\u6bd4\u3079\u3001\u4e3b\u306a\u884c\u52d5\u3078\u9032\u307f\u3084\u3059\u3044\u65b9\u5411\u3092\u9078\u3073\u307e\u3057\u305f\u3002\n\u6539\u5584\u696d\u52d9\uff1a\u4ed5\u69d8\u898b\u76f4\u3057\u30fb\u69cb\u6210\u6539\u5584\u30fb\u5c0e\u7dda\u6539\u5584\u3002\u5c0e\u5165\u3084\u533a\u5206\u3092\u4fee\u6b63\u3057\u3001\u5b8c\u6210\u5f62\u3078\u8fd1\u3065\u3051\u307e\u3057\u305f\u3002"
        else:
            result["applicable_domain_text"] = "This evaluation shows a strength in comparing AI proposals, organizing structure and specifications around the purpose, and moving toward a finished form. Within the confirmed scope, that ability can support the following work areas.\nStructural design work: app structure, information architecture, and specification organization. The alternatives were compared and the information sections were reorganized.\nDecision-making work: direction selection, structure selection, and acceptance or rejection decisions. A route that made the main action easier to reach was selected.\nImprovement work: specification review, structural improvement, and user-flow improvement. The opening and section arrangement were revised toward the completed form."
        if japanese:
            result["applicable_domain_text"] = (
                "今回の評価では、AIの提案を比較し、目的に合わせて構成や仕様を整理しながら完成形へ近づける力が表れています。"
                "今回確認できた範囲では、次のような業務へ活かせます。\n"
                "構造設計業務：アプリ構成設計・情報設計・仕様整理など。複数案を比較し、情報の区分や配置を整理しながら、目的に合う構成を設計する場面で活用できます。\n"
                "意思決定業務：方針選択・構成選択・採用／見送り判断など。AIが提示した複数案を比較し、目的や優先事項に合う方向を選ぶ場面で活用できます。\n"
                "改善業務：仕様見直し・構成改善・導線改善など。既存案の問題点を見つけ、修正案を比較しながら完成度を高める場面で活用できます。"
            )
        else:
            result["applicable_domain_text"] = (
                "This evaluation shows a strength in comparing AI proposals, organizing structure and specifications around the purpose, and moving toward a finished form. "
                "Within the confirmed scope, that ability can support the following work areas.\n"
                "Structural design work: app structure, information architecture, and specification organization. This ability can be applied when comparing multiple alternatives, organizing information and layout, and designing a structure that fits the purpose.\n"
                "Decision-making work: direction selection, structure selection, and acceptance or rejection decisions. This ability can be applied when comparing AI-generated alternatives and choosing a direction that best fits the purpose and priorities.\n"
                "Improvement work: specification review, structural improvement, and user-flow improvement. This ability can be applied when identifying issues in an existing proposal, comparing revisions, and improving the quality of the final result."
            )
        for key in ("output_logic_evaluation", "judgment_process_evaluation", "revision_process_evaluation", "agency_process_evaluation", "consistency_process_evaluation"):
            value = result.get(key, "")
            if japanese:
                value = value.replace("\u4f55\u3092\u512a\u5148\u3057\u3066\u9078\u3093\u3060\u306e\u304b\u304c\u5834\u9762\u3054\u3068\u306b\u5341\u5206\u8a00\u8449\u306b\u306a\u3063\u3066\u3044\u306a\u3044\u305f\u3081\u3067\u3059\u3002", "\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u3001\u4f55\u3092\u6700\u512a\u5148\u3057\u3066\u9078\u3093\u3060\u306e\u304b\u307e\u3067\u306f\u5341\u5206\u306b\u7279\u5b9a\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002")
                value = value.replace("\u4fee\u6b63\u306b\u3088\u3063\u3066\u4f55\u304c\u3069\u306e\u7a0b\u5ea6\u826f\u304f\u306a\u3063\u305f\u304b\u306e\u8aac\u660e\u304c\u5341\u5206\u3067\u306f\u306a\u3044\u305f\u3081\u3067\u3059\u3002", "\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u3001\u4fee\u6b63\u524d\u5f8c\u306e\u9055\u3044\u306f\u8a55\u4fa1\u3067\u304d\u308b\u3082\u306e\u306e\u3001\u305d\u306e\u52b9\u679c\u306e\u5927\u304d\u3055\u307e\u3067\u306f\u5341\u5206\u306b\u8a55\u4fa1\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002")
                value = value.replace("\u305d\u306e\u6761\u4ef6\u304c\u6bce\u56de\u540c\u3058\u57fa\u6e96\u3068\u3057\u3066\u8868\u73fe\u3055\u308c\u3066\u3044\u308b\u308f\u3051\u3067\u306f\u306a\u3044\u305f\u3081\u3067\u3059\u3002", "\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u3001\u8907\u6570\u306e\u5834\u9762\u306b\u5171\u901a\u3059\u308b\u5224\u65ad\u57fa\u6e96\u307e\u3067\u306f\u5341\u5206\u306b\u7279\u5b9a\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002")
            else:
                value = value.replace("the priority used to choose one direction was not expressed concretely enough for another person to reproduce", "the available material does not make the highest priority behind the choice sufficiently identifiable")
                value = value.replace("the degree of improvement is not explained concretely enough", "the available material shows the before-and-after difference, but does not allow the magnitude of the effect to be evaluated fully")
                value = value.replace("The acceptance and rejection conditions, however, were not expressed as one consistent standard", "the available material does not make one common decision standard across the different situations sufficiently identifiable")
            result[key] = value
        if japanese:
            result["output_logic_evaluation"] = result["output_logic_evaluation"].replace(
                "三つの区分を二つへ整理する判断が、最終アウトプットの読み順と情報のまとまりへ反映されています。",
                "三つの区分を二つへ整理する判断が、最終アウトプットの二つに分かれた情報のまとまりと読む順番へ反映されています。",
            )
            result["judgment_process_evaluation"] = result["judgment_process_evaluation"].replace(
                "選んだ方向は短い導入と役割別の情報配置として完成形に表れています。",
                "選んだ方向は最終アウトプットの冒頭にある説明部分を短くし、役割別の情報配置として現れています。",
            )
            result["iteration_process_evaluation"] = result["iteration_process_evaluation"].replace(
                "長い導入から短い導入への変更や、区分の整理が最終アウトプットの冒頭と構成へつながっています。",
                "長い導入から短い導入への変更が、最終アウトプットの冒頭にある説明部分へ現れ、区分の整理も二つの情報のまとまりとして表れています。",
            )
            result["overall_consistency_evaluation"] = result["overall_consistency_evaluation"].replace(
                "選択理由、導入の変更、構成整理が最終アウトプットの読み順へ連続して反映されています。",
                "選択理由、導入の変更、構成整理が、最終アウトプットの冒頭にある説明部分と二つの情報区分の並びへ連続して反映されています。",
            )
        else:
            result["output_logic_evaluation"] = result["output_logic_evaluation"].replace(
                "The decision to reduce three sections to two appears in the reading order and grouping of the final output.",
                "The decision to reduce three sections to two appears in the final output as two grouped information sections and a clearer reading order.",
            )
            result["judgment_process_evaluation"] = result["judgment_process_evaluation"].replace(
                "The selected direction appears as a shorter opening and a clearer arrangement of information in the finished output.",
                "The selected direction appears in the finished output as a shorter opening explanation and a clearer arrangement of information.",
            )
            result["iteration_process_evaluation"] = result["iteration_process_evaluation"].replace(
                "The change from a longer opening to a shorter one and the reorganization of sections are visible in the final output.",
                "The change from a longer opening to a shorter opening explanation is visible at the start of the final output, together with the reorganization of its sections.",
            )
            result["iteration_process_evaluation"] = result["iteration_process_evaluation"].replace(
                "The before-and-after difference is visible, but the available material shows the before-and-after difference, but does not allow the magnitude of the effect to be evaluated fully.",
                "The before-and-after difference is visible, but the available material does not allow the magnitude of the effect to be evaluated fully.",
            )
            result["evaluation_basis"] = result["evaluation_basis"].replace(
                "Decision Process remained at 77 because the priority behind the comparison was not concrete enough to reproduce, Iteration Process at 78 because the degree of improvement after revision was not explained clearly enough, and Human Ownership at 82 because the acceptance and rejection conditions were not expressed as one consistent standard.",
                "Decision Process remained at 77 because the available material does not make the highest priority behind the comparison sufficiently identifiable, Iteration Process at 78 because it shows the before-and-after difference but does not allow the magnitude of the effect to be evaluated fully, and Human Ownership at 82 because the available material does not make one common acceptance and rejection standard across the situations sufficiently identifiable.",
            )
    if "evaluation_basis" not in result:
        result["evaluation_basis"] = (
            "今回の材料から確認できる判断・修正・採否とアウトプットの関係だけを評価根拠とし、確認できない過程や効果は補っていません。"
            if japanese
            else
            "The evaluation basis is limited to the confirmed connection between the available choices, revisions, approvals, and the output; unconfirmed steps and effects are not filled in."
        )
    if japanese:
        for key, value in list(result.items()):
            if isinstance(value, str):
                result[key] = value.replace("\u8aad\u307f\u9806", "\u8aad\u3080\u9806\u756a")
        result["iteration_process_evaluation"] = result["iteration_process_evaluation"].replace(
            "\u0037\u0038\u70b9\u306b\u3068\u3069\u307e\u3063\u305f\u306e\u306f\u3001\u4fee\u6b63\u524d\u5f8c\u306e\u9055\u3044\u306f\u898b\u3048\u308b\u3082\u306e\u306e\u3001\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u3001\u4fee\u6b63\u524d\u5f8c\u306e\u9055\u3044\u306f\u8a55\u4fa1\u3067\u304d\u308b\u3082\u306e\u306e\u3001\u305d\u306e\u52b9\u679c\u306e\u5927\u304d\u3055\u307e\u3067\u306f\u5341\u5206\u306b\u8a55\u4fa1\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002",
            "\u0037\u0038\u70b9\u306b\u3068\u3069\u307e\u3063\u305f\u306e\u306f\u3001\u4fee\u6b63\u524d\u5f8c\u306e\u9055\u3044\u306f\u8a55\u4fa1\u3067\u304d\u308b\u3082\u306e\u306e\u3001\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u3001\u305d\u306e\u52b9\u679c\u306e\u5927\u304d\u3055\u307e\u3067\u306f\u5341\u5206\u306b\u8a55\u4fa1\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002",
        )
        result["evaluation_basis"] = result["evaluation_basis"].replace(
            "\u5224\u65ad\u30d7\u30ed\u30bb\u30b977\u70b9\u306f\u6bd4\u8f03\u306f\u3067\u304d\u3066\u3044\u308b\u3082\u306e\u306e\u512a\u5148\u3057\u305f\u7406\u7531\u304c\u7b2c\u4e09\u8005\u306b\u3082\u518d\u73fe\u3067\u304d\u308b\u307b\u3069\u5177\u4f53\u7684\u3067\u306f\u306a\u304f\u3001\u4fee\u6b63\u30d7\u30ed\u30bb\u30b977\u70b9\u306f\u524d\u5f8c\u306e\u5dee\u306f\u751f\u307e\u308c\u3066\u3044\u308b\u3082\u306e\u306e\u4f55\u304c\u3069\u306e\u7a0b\u5ea6\u826f\u304f\u306a\u3063\u305f\u304b\u306e\u8aac\u660e\u304c\u8584\u3044\u305f\u3081\u3067\u3059\u3002\u5224\u65ad\u306e\u4e3b\u4f53\u602782\u70b9\u306f\u4eba\u304c\u9078\u629e\u3068\u898b\u9001\u308a\u3092\u62c5\u3063\u305f\u4e00\u65b9\u3001\u63a1\u7528\u30fb\u898b\u9001\u308a\u306e\u6c7a\u3081\u624b\u304c\u4e00\u8cab\u3057\u305f\u5f62\u3067\u8868\u73fe\u3055\u308c\u3066\u3044\u306a\u3044\u305f\u3081\u3067\u3059\u3002",
            "\u5224\u65ad\u30d7\u30ed\u30bb\u30b977\u70b9\u306f\u8907\u6570\u6848\u3092\u6bd4\u8f03\u3057\u3066\u9078\u629e\u3057\u3066\u3044\u308b\u3053\u3068\u306f\u8a55\u4fa1\u3067\u304d\u307e\u3059\u304c\u3001\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u4f55\u3092\u6700\u512a\u5148\u3057\u3066\u9078\u3093\u3060\u306e\u304b\u307e\u3067\u306f\u5341\u5206\u306b\u7279\u5b9a\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002\u4fee\u6b63\u30d7\u30ed\u30bb\u30b978\u70b9\u306f\u4fee\u6b63\u524d\u5f8c\u306e\u5909\u5316\u306f\u8a55\u4fa1\u3067\u304d\u307e\u3059\u304c\u3001\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u305d\u306e\u52b9\u679c\u306e\u5927\u304d\u3055\u307e\u3067\u306f\u5341\u5206\u306b\u8a55\u4fa1\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002\u5224\u65ad\u306e\u4e3b\u4f53\u602782\u70b9\u306f\u63a1\u7528\u30fb\u898b\u9001\u308a\u3092\u4eba\u304c\u5224\u65ad\u3057\u3066\u3044\u308b\u3053\u3068\u306f\u8a55\u4fa1\u3067\u304d\u307e\u3059\u304c\u3001\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u8907\u6570\u5834\u9762\u306b\u5171\u901a\u3059\u308b\u5224\u65ad\u57fa\u6e96\u307e\u3067\u306f\u5341\u5206\u306b\u7279\u5b9a\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002",
        )
        result["page6_transparency_text"] = result["page6_transparency_text"].replace(
            "\u63a1\u7528\u3057\u305f\u65b9\u5411\u306f\u5c0e\u5165\u3084\u5f79\u5272\u5206\u62c5\u306e\u5909\u66f4\u3068\u3057\u3066\u6700\u7d42\u4ed5\u69d8\u306b\u53cd\u6620\u3055\u308c",
            "\u63a1\u7528\u3057\u305f\u65b9\u5411\u306f\u3001\u6700\u7d42\u30a2\u30a6\u30c8\u30d7\u30c3\u30c8\u306e\u5192\u982d\u306b\u3042\u308b\u8aac\u660e\u90e8\u5206\u3092\u77ed\u304f\u3057\u3001\u60c5\u5831\u306e\u5f79\u5272\u3054\u3068\u306b\u4e8c\u3064\u306e\u307e\u3068\u307e\u308a\u3078\u6574\u7406\u3059\u308b\u5909\u66f4\u3068\u3057\u3066\u6700\u7d42\u4ed5\u69d8\u306b\u53cd\u6620\u3055\u308c",
        )
        result["output_logic_evaluation"] = result["output_logic_evaluation"].replace("\u6b8b\u3055\u308c\u305f\u5c0e\u7dda\u3084\u8aac\u660e\u306e\u914d\u7f6e", "\u6700\u7d42\u30a2\u30a6\u30c8\u30d7\u30c3\u30c8\u306e\u5192\u982d\u306b\u3042\u308b\u8aac\u660e\u90e8\u5206\u3068\u3001\u305d\u306e\u5f8c\u306b\u5206\u3051\u3066\u914d\u7f6e\u3055\u308c\u305f\u4e8c\u3064\u306e\u60c5\u5831\u306e\u307e\u3068\u307e\u308a")
    else:
        for key, value in list(result.items()):
            if isinstance(value, str):
                result[key] = value.replace("supporting the 82 score. the available material", "supporting the 82 score. The available material")
        result["iteration_process_evaluation"] = result["iteration_process_evaluation"].replace(
            "The before-and-after difference is visible, but the available material shows the before-and-after difference, but does not allow the magnitude of the effect to be evaluated fully.",
            "The before-and-after difference is visible, but the available material does not allow the magnitude of the effect to be evaluated fully.",
        )
        result["page6_transparency_text"] = result["page6_transparency_text"].replace(
            "The accepted direction shaped the opening and role separation in the final specification",
            "The accepted direction shortened the opening explanation at the start of the final output and organized the information into two role-based groups in the final specification",
        )
        result["output_logic_evaluation"] = result["output_logic_evaluation"].replace(
            "The human choice appears in the route, opening, and information grouping retained in the finished output.",
            "The human choice appears in the opening explanation at the start of the final output and in the two role-based information groups retained in the finished output.",
        )
        result["iteration_process_evaluation"] = result["iteration_process_evaluation"].replace(
            "The before-and-after difference is visible, but the available material shows the before-and-after difference, but does not allow the magnitude of the effect to be evaluated fully.",
            "The before-and-after difference is visible, but the available material does not allow the magnitude of the effect to be evaluated fully.",
        )
        result["human_ownership_evaluation"] = result["human_ownership_evaluation"].replace(
            "The human choice appears in the route, opening, and information grouping retained in the finished output.",
            "The human choice appears in the opening explanation at the start of the final output and in the two role-based information groups retained in the finished output.",
        )
    if int(scores.get("total_score", 0) or 0) >= 375 and has_confirmed_high_information:
        if japanese:
            result["evaluation_basis"] = (
                "候補を比べ、読み手が主な行動へ進みやすい方向を選び、長い導入を短くし、三つの区分を二つへ整理した流れが今回の評価の中心です。論理性95点と全体整合性95点は、判断・修正・採否が最終仕様の読む順番と構成へつながったためです。判断プロセス77点は複数案を比較して選択していることは評価できますが、今回の材料からは何を最優先して選んだのかまでは十分に特定できないためです。修正プロセス78点は修正前後の変化は評価できますが、今回の材料からはその効果の大きさまでは十分に評価できないためです。判断の主体性82点は採用・見送りを人が判断していることは評価できますが、今回の材料からは複数場面に共通する判断基準までは十分に特定できないためです。次回は、迷った場面で何を決め手にしたか、修正後に何が良くなったかを少し振り返ることで、今回の強みをさらに活かしやすくなります。"
            )
            result["human_ownership_evaluation"] = result["human_ownership_evaluation"].replace(
                "人が選んだ方向は、残された導線や説明の配置として完成形に反映されています。",
                "人が選んだ方向は、最終アウトプットの冒頭にある説明部分と、その後に分けて配置された二つの情報のまとまりとして完成形に反映されています。",
            )
            result["third_party_visibility"] = (
                "AIが候補や修正案を提示し、人が目的と導線の分かりやすさを基準に選別しています。採用した方向は、最終アウトプットの冒頭にある説明部分を短くし、情報を役割ごとに二つのまとまりへ整理する変更として最終仕様に反映され、主経路を妨げる案は見送られました。この流れから、AI任せではなく、人が比較・修正・採否を担って完成形を決めたことを第三者が理解できます。今後は、迷った場面でなぜその案を選ぶのかを少し意識すると、今回のAI活用の特徴がさらに伝わりやすくなります。"
            )
        else:
            result["evaluation_basis"] = (
                "The evaluation basis is the connected sequence in which alternatives were compared, the route reaching the main action sooner was selected, the long opening was shortened, and three sections were reorganized into two. Output Logic and Overall Consistency reached 95 because comparison, revision, and acceptance carried into the final reading order and structure. Decision Process remained at 77 because the alternatives can be compared, but the available material does not make the highest priority behind the choice sufficiently identifiable. Iteration Process remained at 78 because the before-and-after difference is visible, but the available material does not allow the magnitude of the effect to be evaluated fully. Human Ownership remained at 82 because the person accepted or rejected proposals, but the available material does not make one common acceptance and rejection standard across the situations sufficiently identifiable. Next time, briefly reflect on what guided a difficult choice and what improved after a revision. This can make the same strengths easier to carry into the next task."
            )
            result["human_ownership_evaluation"] = result["human_ownership_evaluation"].replace(
                "The human choice appears in the route, opening, and information grouping retained in the finished output.",
                "The human choice appears in the opening explanation at the start of the final output and in the two role-based information groups retained in the finished output.",
            )
            result["third_party_visibility"] = (
                "A third-party reader can see that AI supplied alternatives and revision proposals, while the person judged them against purpose and clarity. The accepted direction shortened the opening explanation at the start of the final output and organized the information into two role-based groups in the final specification, while a competing route was rejected because it would compete with the main action. This makes the human contribution and the basis for the evaluation understandable. Next time, briefly state why a difficult choice was made so the same pattern is easier to recognize."
            )
    if japanese:
        for key, value in list(result.items()):
            if isinstance(value, str):
                result[key] = value.replace(
                    "\u4fee\u6b63\u524d\u5f8c\u306e\u9055\u3044\u306f\u898b\u3048\u308b\u3082\u306e\u306e\u3001\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u3001\u4fee\u6b63\u524d\u5f8c\u306e\u9055\u3044\u306f\u8a55\u4fa1\u3067\u304d\u308b\u3082\u306e\u306e\u3001\u305d\u306e\u52b9\u679c\u306e\u5927\u304d\u3055\u307e\u3067\u306f\u5341\u5206\u306b\u8a55\u4fa1\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002",
                    "\u4fee\u6b63\u524d\u5f8c\u306e\u9055\u3044\u306f\u8a55\u4fa1\u3067\u304d\u308b\u3082\u306e\u306e\u3001\u4eca\u56de\u306e\u6750\u6599\u304b\u3089\u306f\u3001\u305d\u306e\u52b9\u679c\u306e\u5927\u304d\u3055\u307e\u3067\u306f\u5341\u5206\u306b\u8a55\u4fa1\u3067\u304d\u306a\u3044\u305f\u3081\u3067\u3059\u3002",
                ).replace(
                    "\u6b8b\u3055\u308c\u305f\u5c0e\u7dda\u3084\u8aac\u660e\u306e\u914d\u7f6e",
                    "\u6700\u7d42\u30a2\u30a6\u30c8\u30d7\u30c3\u30c8\u306e\u5192\u982d\u306b\u3042\u308b\u8aac\u660e\u90e8\u5206\u3068\u3001\u305d\u306e\u5f8c\u306b\u5206\u3051\u3066\u914d\u7f6e\u3055\u308c\u305f\u4e8c\u3064\u306e\u60c5\u5831\u306e\u307e\u3068\u307e\u308a",
                )
    else:
        for key, value in list(result.items()):
            if isinstance(value, str):
                result[key] = value.replace(
                    "The before-and-after difference is visible, but the available material shows the before-and-after difference, but does not allow the magnitude of the effect to be evaluated fully.",
                    "The before-and-after difference is visible, but the available material does not allow the magnitude of the effect to be evaluated fully.",
                ).replace(
                    "The human choice appears in the route, opening, and information grouping retained in the finished output.",
                    "The human choice appears in the opening explanation at the start of the final output and in the two role-based information groups retained in the finished output.",
                )
    for key in ("overall_consistency_evaluation", "consistency_process_evaluation"):
        if isinstance(result.get(key), str):
            result[key] = result[key].replace(
                "選択理由、導入の変更、構成整理が",
                "選択の経緯、導入の変更、構成整理が",
            ).replace(
                "The comparison reason, opening change, and structural reorganization",
                "The comparison process, opening change, and structural reorganization",
            )
    if japanese:
        if isinstance(result.get("ai_use_scope_statement"), str):
            result["ai_use_scope_statement"] = result["ai_use_scope_statement"].replace(
                "成果物へ反映できます", "アウトプットへ反映できます"
            )
    else:
        if isinstance(result.get("ai_capability_evaluation"), str):
            result["ai_capability_evaluation"] = result["ai_capability_evaluation"].replace(
                "When alternatives compete, state the reason one direction fits the purpose better, then reflect on what became clearer or more useful after the revision.",
                "When alternatives compete, state the reason one direction fits the purpose better, then reflect on what became clearer or more useful after the revision. This can strengthen the persuasiveness of future decisions while preserving the strengths shown in this evaluation.",
            )
        for key in ("judgment_process_evaluation", "revision_process_evaluation"):
            if isinstance(result.get(key), str):
                result[key] = result[key].replace(
                    "AI functioned as a source of alternatives, while the person retained the decision about which direction fit the purpose.",
                    "AI functioned as a source of alternatives, while the person retained the decision about which direction fit the purpose. The decision-making role remained with the person, with AI used as material for thinking rather than as the source of the answer.",
                ).replace(
                    "AI was used to identify and improve problems, not only to produce a first draft.",
                    "AI was used to identify and improve problems, not only to produce a first draft. The iterative use of AI to revise the work toward a finished form is the strength shown in this dimension.",
                )
    axis_keys = (
        "output_logic_evaluation",
        "judgment_process_evaluation",
        "iteration_process_evaluation",
        "human_ownership_evaluation",
        "overall_consistency_evaluation",
        "revision_process_evaluation",
        "agency_process_evaluation",
        "consistency_process_evaluation",
    )
    if japanese:
        for key in axis_keys:
            if isinstance(result.get(key), str):
                result[key] = re.sub(r"次回は、[^。]*。", "", result[key]).strip()
        if isinstance(result.get("evaluation_basis"), str):
            result["evaluation_basis"] = re.sub(r"次回は、[^。]*。", "", result["evaluation_basis"]).strip()
        if isinstance(result.get("page6_transparency_text"), str):
            result["page6_transparency_text"] = result["page6_transparency_text"].replace(
                "候補を比べた理由", "候補を比較した経緯"
            )
    else:
        for key in axis_keys:
            if isinstance(result.get(key), str):
                result[key] = re.sub(r"Next time,[^.]*\.", "", result[key])
                result[key] = result[key].replace(
                    " A short statement of the deciding reason would make this strength easier to apply in another task.", ""
                ).replace(
                    " A brief reflection on the result of each revision would make the improvement process more repeatable.", ""
                ).replace(
                    " Naming the deciding factor would make that ownership even more persuasive.", ""
                ).strip()
        if isinstance(result.get("evaluation_basis"), str):
            result["evaluation_basis"] = re.sub(
                r" Next time, briefly reflect on what guided a difficult choice and what improved after a revision\. This can make the same strengths easier to carry into the next task\.",
                "",
                result["evaluation_basis"],
            ).strip()
        if isinstance(result.get("page6_transparency_text"), str):
            result["page6_transparency_text"] = result["page6_transparency_text"].replace(
                "comparison reason", "comparison process"
            )
        if has_confirmed_high_information:
            result["iteration_process_evaluation"] = (
                "Evaluation\nThe person identified problems in an AI proposal and revised the opening and structure before completing the output. The work moved beyond generating alternatives into iterative improvement, supporting the 78 score. The before-and-after difference is visible, but the available material does not allow the magnitude of the effect to be evaluated fully.\n"
                "Relationship to the output\nThe change from a longer opening to a shorter one and the reorganization of sections are visible in the final output. The chain from problem recognition through revision to the completed form is therefore present.\n"
                "Conclusion\nAI was used to identify and improve problems, not only to produce a first draft. The iterative use of AI to revise the work toward a finished form is the strength shown in this dimension."
            )
            result["human_ownership_evaluation"] = (
                "Evaluation\nThe person selected a direction that fit the purpose and rejected an unnecessary competing route instead of accepting AI proposals unchanged. Human choice remained active through comparison, revision, and final approval, supporting the 82 score. The available material does not make one common decision standard across the different situations sufficiently identifiable.\n"
                "Relationship to the output\nThe human choice appears in the opening explanation at the start of the final output and in the two role-based information groups retained in the finished output. The difference between what AI proposed and what the person kept is visible in the final form.\n"
                "Conclusion\nAI supplied options and revision material, while the person retained responsibility for the direction and completed form."
            )
            result["evaluation_basis"] = (
                "The evaluation basis is the connected sequence in which alternatives were compared, the route reaching the main action sooner was selected, the long opening was shortened, and three sections were reorganized into two. Output Logic and Overall Consistency reached 95 because comparison, revision, and acceptance carried into the final reading order and structure. Decision Process remained at 77 because the alternatives can be compared, but the available material does not make the highest priority behind the choice sufficiently identifiable. Iteration Process remained at 78 because the before-and-after difference is visible, but the available material does not allow the magnitude of the effect to be evaluated fully. Human Ownership remained at 82 because the person accepted or rejected proposals, but the available material does not make one common acceptance and rejection standard across the situations sufficiently identifiable."
            )
            result["confirmed_weaknesses"] = (
                "Briefly reflecting on why a direction was chosen and what became better after a revision can make the next decision and revision easier to carry forward."
            )
    if isinstance(result.get("third_party_visibility"), str):
        if japanese and "今後は" in result["third_party_visibility"]:
            result["third_party_visibility"] = result["third_party_visibility"].split("今後は", 1)[0].rstrip()
        elif not japanese and " Next time," in result["third_party_visibility"]:
            result["third_party_visibility"] = result["third_party_visibility"].split(" Next time,", 1)[0].rstrip()
    return result
