import json
import boto3
import os
import base64
import time
import re
from typing import Any, Dict, List, Optional, Tuple

# --- AWS Configuration ---
REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("TABLE_NAME")
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-micro-v1:0")

# --- Initialize Clients ---
dynamodb = boto3.resource("dynamodb", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
polly = boto3.client("polly", region_name=REGION)
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None


# =========================
# Prompting
# =========================
def get_system_prompt(target_role: str) -> str:
    return f"""
You are Stellar AI, a senior FAANG interviewer with a high but fair hiring bar.
You are direct, skeptical, precise, and evidence-based.
You do not inflate scores.
You also do not under-score answers that show real substance.

Interview target role: {target_role}

ALLOWED ROLE CATEGORIES:
- engineering
- product
- program
- operations
- analytics
- business
- corporate

If the target role does not reasonably fit one of those categories, refuse briefly, ask the user to choose a valid role, and set score=0.

INTERACTION MODES:
Choose exactly one mode each turn:

A) QUESTION_MODE
- Use when the user has not answered a real interview question yet.
- Ask exactly ONE role-appropriate interview question.

B) EVALUATION_MODE
- Use when the user is attempting to answer.
- Evaluate the answer honestly.
- Then ask exactly ONE next question.

C) MODEL_ANSWER_MODE
- Use when the user explicitly asks for a sample answer, ideal answer, better answer, rewrite, or example answer.
- Provide a concise but strong sample answer using the right framework.
- Then ask exactly ONE follow-up question.

SCORING PRINCIPLE:
Score based on demonstrated evidence in the response, not just tone, polish, or story length.

IMPORTANT ANTI-ANCHOR RULE:
Do NOT default to 4/10.
4 is only appropriate when the answer has some real signal but is still clearly weak or underdeveloped.
If the answer contains clear ownership, sequenced actions, concrete decision-making, trade-offs, risk handling, and measurable outcomes, it should usually score at least 5-6.
If it contains all of those at strong depth, it should score 7+.

IMPORTANT INPUT HYGIENE RULE:
If the user's message appears to contain:
- an answer plus a rewritten version of the same answer,
- praise or commentary about the answer,
- coaching language such as "this is a powerful narrative" or "strong candidate story",
then evaluate only the underlying candidate answer content and ignore editorial praise, duplicated rewrites, and explanatory commentary.

Do not increase the score because the pasted text contains polished framing written by a coach or assistant.
Score the answer as if spoken directly by the candidate in an interview.

SCORING STANDARD (0-10):
- 0: no meaningful interview content; greeting, filler, refusal, "idk", or no attempt
- 1-2: extremely weak; minimal ownership, little action, no meaningful outcome
- 3-4: weak/incomplete; some signal, but insufficient structure, ownership, or evidence
- 5: adequate; clear situation, some ownership, some actions, some result, but shallow or missing depth
- 6: solid; clear ownership, concrete actions, credible result, but still lacking stronger trade-offs, constraints, or deeper reasoning
- 7: strong; clear ownership, well-structured actions, sound judgment, trade-offs or constraints, measurable outcome
- 8: very strong; high complexity, strong prioritization, nuanced trade-offs, measurable impact, strong prevention or scaling thinking
- 9-10: exceptional; crisp, highly defensible, deeply reasoned, quantified, nuanced, and bar-raising under follow-up

EVIDENCE-TO-SCORE MAPPING:
Before choosing a score, silently check for these seven signals:
1. Clear problem framing and stakes
2. Explicit ownership and decision rights
3. Concrete actions in sequence
4. Trade-offs or prioritization logic
5. Risk awareness / constraints / edge cases
6. Measurable outcomes or credible impact
7. Follow-through such as prevention, monitoring, scaling, or process improvement

Scoring guidance based on evidence count:
- 0-1 signals: score 0-2
- 2-3 signals: score 3-4
- 4 signals: score 5
- 5 signals: score 6
- 6 signals: score 7-8
- 7 signals with strong depth and clarity: score 8-10

DOWNWARD ADJUSTMENT RULE:
Only keep the score below 5 if the answer is truly vague, generic, or missing multiple core elements.

UPWARD ADJUSTMENT RULE:
If the answer includes:
- explicit ownership,
- concrete actions,
- at least one trade-off or constraint,
- risk awareness,
- and a measurable or clearly credible outcome,
then do NOT score below 6 unless the answer is internally inconsistent.

DO NOT PENALIZE FOR CONTEXT:
Do not penalize a strong answer simply because it comes from compliance, operations, risk, customer experience, program management, analytics, incident response, or process improvement rather than classic software engineering.

ADDITIONAL EVALUATION DIMENSIONS:
Assess:
- communication
- problem_structuring
- tradeoff_judgment
- risk_awareness
- execution_feasibility
- metrics_thinking
- ownership

RECOMMENDATION RULES:
- 0-2: No Hire
- 3-4: Lean No Hire
- 5-6: Mixed / Borderline
- 7: Lean Hire
- 8: Hire
- 9-10: Strong Hire

FEEDBACK STYLE:
- Be concise, sharp, and useful.
- 3-5 sentences max.
- State what worked.
- State what is missing.
- State exactly what would move the answer up one score band.
- Name the framework expected:
  - STAR/CAR for behavioral
  - trade-offs / architecture / metrics for technical-execution answers

RATIONALE RULES:
- Explain why the score was given using evidence from the answer.
- Distinguish between:
  - weak experience
  - strong experience told weakly
- If the answer is summary-heavy but still contains real ownership/actions/results, do not over-penalize it into the 3-4 band.

QUESTION SELECTION LOGIC:
- Engineering: system design, architecture, debugging, APIs, scale, reliability, trade-offs
- Product/Program/Operations/Business: metrics, execution trade-offs, stakeholder conflict, prioritization, operational risk, process design, scale

MODEL ANSWER RULES:
- If the user asks for an example answer, provide one that is concise, strong, and realistic.
- Do not write a novel.
- Use a structure that sounds like a top candidate, not a textbook.

OUTPUT SCHEMA:
Return VALID JSON ONLY. No markdown. No extra text.
Always return:
{{
  "reply": "string",
  "score": 0,
  "feedback": "string",
  "scorecard": {{
    "recommendation": "string",
    "confidence": "string",
    "categoryScores": {{
      "communication": 0,
      "problem_structuring": 0,
      "tradeoff_judgment": 0,
      "risk_awareness": 0,
      "execution_feasibility": 0,
      "metrics_thinking": 0,
      "ownership": 0
    }},
    "strengths": ["string"],
    "gaps": ["string"],
    "rationale": "string"
  }}
}}
"""


# =========================
# Utilities
# =========================
def cors_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "POST,OPTIONS",
    }


def response_json(status_code: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": cors_headers(),
        "body": json.dumps(payload),
    }


def sanitize_history(history: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    cleaned = []
    for m in history or []:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue

        content = m.get("content", [])
        if (
            isinstance(content, list)
            and len(content) > 0
            and isinstance(content[0], dict)
            and "text" in content[0]
        ):
            cleaned.append(
                {
                    "role": role,
                    "content": [{"text": str(content[0]["text"])}],
                }
            )
    return cleaned[-20:]


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def clamp_score(score: int) -> int:
    return max(0, min(10, score))


def generate_audio(text: str) -> Optional[str]:
    try:
        clean_text = text.replace("*", "").replace("#", "").replace("`", "")
        response = polly.synthesize_speech(
            Text=clean_text,
            OutputFormat="mp3",
            VoiceId="Ruth",
            Engine="neural",
        )
        return base64.b64encode(response["AudioStream"].read()).decode("utf-8")
    except Exception as e:
        print(f"Polly Error: {e}")
        return None


def extract_json(text: str) -> Dict[str, Any]:
    text = (text or "").strip()

    if not text:
        return {
            "reply": "",
            "score": 0,
            "feedback": "Empty model response.",
            "scorecard": {},
        }

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return {
        "reply": text,
        "score": 0,
        "feedback": "Parsing error: model did not return valid JSON.",
        "scorecard": {},
    }


def preprocess_candidate_answer(user_msg: str) -> str:
    text = user_msg.strip()
    lower_text = text.lower()

    cut_markers = [
        "this story is a powerful narrative",
        "your refined and detailed narrative",
        "here's a polished version",
        "here is a polished version",
    ]

    cut_positions = [lower_text.find(
        marker) for marker in cut_markers if lower_text.find(marker) != -1]
    if cut_positions:
        text = text[: min(cut_positions)].strip()

    return text


# =========================
# Input classification
# =========================
def is_sample_answer_request(normalized: str) -> bool:
    triggers = [
        "sample answer",
        "example answer",
        "perfect answer",
        "better answer",
        "rewrite my answer",
        "rewrite this answer",
        "can you rewrite",
        "give me an answer",
        "model answer",
        "show me how to answer",
        "ideal answer",
    ]
    return any(t in normalized for t in triggers)


def has_metric_signal(user_msg: str) -> bool:
    return "%" in user_msg or bool(re.search(r"\b\d+(\.\d+)?\b", user_msg))


def has_action_signal(normalized: str) -> bool:
    return any(
        phrase in normalized
        for phrase in [
            "i led",
            "i built",
            "i created",
            "i launched",
            "i owned",
            "i implemented",
            "i drove",
            "i designed",
            "i reduced",
            "i improved",
            "i partnered",
            "i resolved",
            "i developed",
            "i scoped",
            "i prioritized",
            "i traced",
            "i traced back",
            "i rolled back",
            "i contained",
            "i mitigated",
        ]
    )


def has_structured_story_signal(normalized: str) -> bool:
    keywords = [
        "situation",
        "task",
        "action",
        "result",
        "context",
        "problem",
        "challenge",
        "stake",
        "impact",
        "outcome",
        "trade-off",
        "tradeoff",
        "constraint",
        "risk",
        "rollback",
        "monitor",
        "prevention",
    ]
    return any(k in normalized for k in keywords)


def has_meaningful_signal(user_msg: str, normalized: str) -> bool:
    return has_metric_signal(user_msg) or has_action_signal(normalized) or has_structured_story_signal(normalized)


def is_intro_style_input(normalized: str, user_msg: str) -> bool:
    intro_markers = [
        "my background",
        "i'm looking for",
        "i am looking for",
        "previously worked",
        "i transitioned",
        "i currently work at",
        "i work at",
        "i have experience in",
    ]
    return (
        any(marker in normalized for marker in intro_markers)
        and not has_action_signal(normalized)
        and not has_metric_signal(user_msg)
        and not has_structured_story_signal(normalized)
    )


def is_vague_input(normalized: str, user_msg: str) -> bool:
    low_signal_phrases = {
        "i think i have enough scope for this job",
        "i think i am qualified",
        "i think i'm qualified",
        "i have enough scope",
        "i can do this job",
        "i am a good fit",
        "i'm a good fit",
    }

    very_short = len(user_msg.strip()) < 35

    return (
        very_short
        or normalized.strip() in low_signal_phrases
        or (
            not has_metric_signal(user_msg)
            and not has_action_signal(normalized)
            and not has_structured_story_signal(normalized)
        )
    )


# =========================
# Scoring support
# =========================
def recommendation_from_score(score: int) -> str:
    if score >= 9:
        return "Strong Hire"
    if score >= 8:
        return "Hire"
    if score >= 7:
        return "Lean Hire"
    if score >= 5:
        return "Mixed / Borderline"
    if score >= 3:
        return "Lean No Hire"
    return "No Hire"


def default_category_scores() -> Dict[str, int]:
    return {
        "communication": 0,
        "problem_structuring": 0,
        "tradeoff_judgment": 0,
        "risk_awareness": 0,
        "execution_feasibility": 0,
        "metrics_thinking": 0,
        "ownership": 0,
    }


def normalize_scorecard(scorecard: Optional[Dict[str, Any]], feedback: str, score: int) -> Dict[str, Any]:
    scorecard = scorecard or {}

    normalized = {
        "recommendation": scorecard.get("recommendation") or recommendation_from_score(score),
        "confidence": scorecard.get("confidence", "Medium"),
        "categoryScores": scorecard.get("categoryScores") or default_category_scores(),
        "strengths": scorecard.get("strengths", []),
        "gaps": scorecard.get("gaps", []),
        "rationale": scorecard.get("rationale") or feedback,
    }

    full_categories = default_category_scores()
    incoming = normalized["categoryScores"] if isinstance(
        normalized["categoryScores"], dict) else {}
    for k, v in incoming.items():
        full_categories[k] = clamp_score(safe_int(v, 0))
    normalized["categoryScores"] = full_categories

    if not isinstance(normalized["strengths"], list):
        normalized["strengths"] = []
    if not isinstance(normalized["gaps"], list):
        normalized["gaps"] = []

    normalized["recommendation"] = recommendation_from_score(score)

    if not normalized["rationale"]:
        normalized["rationale"] = feedback

    return normalized


def estimate_fallback_score(user_msg: str, normalized: str) -> int:
    signals = 0

    if any(word in normalized for word in [
        "problem", "issue", "risk", "escalation", "failure", "incident", "challenge", "stakes", "zero-tolerance"
    ]):
        signals += 1

    if any(phrase in normalized for phrase in [
        "i owned", "i led", "i drove", "i decided", "i implemented", "i designed",
        "i partnered", "i resolved", "i launched", "i created", "i built", "i scoped",
        "i rolled back", "i contained", "i traced", "i mitigated"
    ]):
        signals += 1

    if any(word in normalized for word in [
        "first", "then", "after", "next", "finally", "rollback", "containment", "traceback", "sequenced"
    ]):
        signals += 1

    if any(word in normalized for word in [
        "trade-off", "tradeoff", "constraint", "because", "instead of", "prioritized", "safest mitigation"
    ]):
        signals += 1

    if any(word in normalized for word in [
        "risk", "compliance", "edge case", "blast radius", "monitor", "validation", "guardrail",
        "regulatory", "safety", "enforcement"
    ]):
        signals += 1

    if has_metric_signal(user_msg):
        signals += 1

    if any(word in normalized for word in [
        "prevent", "monitoring", "governance", "post-change", "invariant", "scaled", "recurrence",
        "versioning", "validation checks"
    ]):
        signals += 1

    if signals <= 1:
        return 2
    if signals <= 3:
        return 4
    if signals == 4:
        return 5
    if signals == 5:
        return 6
    if signals == 6:
        return 7
    return 8


def detect_answer_contamination(user_msg: str, normalized: str) -> Dict[str, Any]:
    contamination_flags = []

    meta_phrases = [
        "this story is a powerful narrative",
        "strong candidate for an interview",
        "your refined and detailed narrative",
        "here's a polished version",
        "here is a polished version",
        "structured to emphasize key aspects",
        "highlights your leadership",
        "compelling story",
        "showcases your ability",
        "values both strategic leadership",
        "problem & stakes:",
        "decision rights / roles:",
        "containment & rollback:",
        "root cause & prevention:",
    ]

    for phrase in meta_phrases:
        if phrase in normalized:
            contamination_flags.append(f"meta_phrase:{phrase}")

    quoted_problem_count = normalized.count(
        "we enabled two new dangerous goods")
    if quoted_problem_count > 1:
        contamination_flags.append("duplicated_story_content")

    section_markers = [
        "problem & stakes",
        "decision rights / roles",
        "containment & rollback",
        "root cause & prevention",
        "result:",
    ]
    repeated_sections = sum(
        1 for marker in section_markers if normalized.count(marker) > 0)
    if repeated_sections >= 3:
        contamination_flags.append("editorialized_structuring")

    return {
        "is_contaminated": len(contamination_flags) > 0,
        "flags": contamination_flags,
    }


def apply_guardrails(
    user_msg: str,
    normalized: str,
    score: int,
    feedback: str,
    scorecard: Dict[str, Any],
) -> Tuple[int, str, Dict[str, Any]]:
    score = clamp_score(score)
    contamination = detect_answer_contamination(user_msg, normalized)
    is_contaminated = contamination["is_contaminated"]

    if is_sample_answer_request(normalized):
        score = 0
        if not feedback:
            feedback = "Sample answer requested."
        scorecard["recommendation"] = "No Hire"
        scorecard["confidence"] = "High"
        scorecard["rationale"] = feedback
        return score, feedback, scorecard

    if is_intro_style_input(normalized, user_msg) and score <= 2:
        score = 3
        feedback = (
            "This is background context, not yet a full interview answer. "
            "Turn it into STAR/CAR: describe one situation, what you owned, what you did, and the measurable result."
        )
        scorecard["confidence"] = "Medium"
        if "Needs a concrete STAR/CAR example." not in scorecard["gaps"]:
            scorecard["gaps"].append("Needs a concrete STAR/CAR example.")

    elif is_vague_input(normalized, user_msg) and score <= 2:
        score = 3 if has_meaningful_signal(user_msg, normalized) else 2
        feedback = (
            "This response is still too vague to score highly. "
            "Use STAR/CAR and make the context, decisions, actions, and result explicit."
        )
        scorecard["confidence"] = "Medium"
        if "Missing sufficient specificity and measurable outcomes." not in scorecard["gaps"]:
            scorecard["gaps"].append(
                "Missing sufficient specificity and measurable outcomes.")

    if score == 0 and has_meaningful_signal(user_msg, normalized):
        score = estimate_fallback_score(user_msg, normalized)

        if score <= 4:
            feedback = (
                "This answer has some signal, but it still lacks enough specificity or structure "
                "for a stronger score. Use STAR/CAR and make the actions, decisions, and result clearer."
            )
        elif score == 5:
            feedback = (
                "This is a credible answer with real substance. To move higher, make the trade-offs, "
                "constraints, and measurable impact more explicit."
            )
        else:
            feedback = (
                "This answer shows strong substance and ownership. To score even higher, "
                "sharpen the reasoning, trade-offs, and quantified impact."
            )

        scorecard["confidence"] = "Medium"
        scorecard["rationale"] = feedback

    if score >= 7:
        has_metric = has_metric_signal(user_msg)
        has_action = has_action_signal(normalized)
        has_tradeoff = any(
            k in normalized for k in ["trade-off", "tradeoff", "constraint", "because", "instead of", "prioritized"]
        )
        if not (has_action and (has_metric or has_tradeoff)):
            score = 6
            feedback = (
                "This is a solid answer, but the score should not be higher without clearer evidence "
                "of measurable impact or stronger trade-off reasoning."
            )
            scorecard["confidence"] = "Medium"
            if "Top-tier score not fully supported by explicit impact or trade-off evidence." not in scorecard["gaps"]:
                scorecard["gaps"].append(
                    "Top-tier score not fully supported by explicit impact or trade-off evidence."
                )

    if is_contaminated:
        if score >= 8:
            score = 7
        elif score >= 7:
            score = 6

        feedback = (
            "This response appears partially editorialized or padded with rewrite/praise language, "
            "so I am discounting it slightly. The underlying story is solid, but I want the raw candidate answer: "
            "state the situation, what you owned, what trade-off you made, and the measurable result."
        )

        scorecard["confidence"] = "Medium"
        scorecard["rationale"] = feedback
        if "Response includes rewrite/meta-commentary that may inflate the score." not in scorecard["gaps"]:
            scorecard["gaps"].append(
                "Response includes rewrite/meta-commentary that may inflate the score.")

    score = clamp_score(score)
    scorecard["recommendation"] = recommendation_from_score(score)

    if not scorecard.get("rationale"):
        scorecard["rationale"] = feedback

    return score, feedback, scorecard


# =========================
# Main handler
# =========================
def handler(event, context):
    t0 = time.time()

    try:
        body = json.loads(event.get("body", "{}"))
        user_msg_raw = (body.get("message", "") or "").strip()
        user_msg = preprocess_candidate_answer(user_msg_raw)
        session_id = body.get("session_id", "default")
        target_role = body.get("role", "Software Engineer (Backend)")
    except Exception:
        return response_json(400, {"message": "Invalid JSON"})

    normalized = user_msg.lower().strip()

    too_short = len(user_msg) < 20 or normalized in {
        "idk", "not sure", "no idea", "n/a", "na", "i don't know", "dont know"
    }

    if too_short:
        short_feedback = (
            "Too little substance to score. Use STAR/CAR and include ownership "
            "plus at least one metric or concrete outcome."
        )
        short_scorecard = {
            "recommendation": "No Hire",
            "confidence": "High",
            "categoryScores": default_category_scores(),
            "strengths": [],
            "gaps": ["Too little substance to evaluate."],
            "rationale": (
                "The response did not contain enough detail, structure, ownership, "
                "or measurable outcome to assess interview performance."
            ),
        }

        return response_json(
            200,
            {
                "session_id": session_id,
                "target_role": target_role,
                "reply": "I cannot evaluate that. Give me a real answer with context, what you did, and a measurable result.",
                "score": 0,
                "feedback": short_feedback,
                "scorecard": short_scorecard,
                "transcript": [],
                "audio": None,
                "debug_version": "v3-contamination-fixed",
            },
        )

    try:
        if table is not None:
            db_item = table.get_item(Key={"session_id": session_id})
            history = db_item.get("Item", {}).get("history", [])
        else:
            history = []
    except Exception as e:
        print(f"DynamoDB read error: {e}")
        history = []

    dynamic_prompt = get_system_prompt(target_role)
    history = sanitize_history(history)
    messages = history + [{"role": "user", "content": [{"text": user_msg}]}]

    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            system=[{"text": dynamic_prompt}],
            messages=messages,
            inferenceConfig={"maxTokens": 1200, "temperature": 0.2},
        )

        raw_content = response["output"]["message"]["content"][0]["text"]
        ai_data = extract_json(raw_content)

        reply_text = (ai_data.get("reply") or "").strip()
        score = clamp_score(safe_int(ai_data.get("score", 0), 0))
        feedback = (ai_data.get("feedback") or "").strip()

        if not feedback:
            feedback = "Insufficient feedback returned by the model."

        scorecard = normalize_scorecard(
            ai_data.get("scorecard"), feedback, score)

        score, feedback, scorecard = apply_guardrails(
            user_msg=user_msg,
            normalized=normalized,
            score=score,
            feedback=feedback,
            scorecard=scorecard,
        )

        transcript = history + [
            {"role": "user", "content": [{"text": user_msg}]},
            {"role": "assistant", "content": [{"text": reply_text}]},
        ]
        transcript = transcript[-20:]

        audio_b64 = generate_audio(reply_text) if reply_text else None

    except Exception as e:
        print(f"Bedrock Error: {e}")
        return response_json(500, {"message": "AI Processing Failure"})

    try:
        if table is not None:
            table.put_item(
                Item={
                    "session_id": session_id,
                    "history": transcript,
                    "last_updated": str(time.time()),
                }
            )
    except Exception as e:
        print(f"DynamoDB write error: {e}")

    print(
        json.dumps(
            {
                "type": "metric",
                "name": "TotalLatencyMs",
                "value": int((time.time() - t0) * 1000),
                "session_id": session_id,
                "target_role": target_role,
                "score": score,
                "recommendation": scorecard.get("recommendation"),
                "debug_version": "v3-contamination-fixed",
            }
        )
    )

    return response_json(
        200,
        {
            "session_id": session_id,
            "target_role": target_role,
            "reply": reply_text,
            "score": score,
            "feedback": feedback,
            "scorecard": scorecard,
            "transcript": transcript,
            "audio": audio_b64,
            "debug_version": "v3-contamination-fixed",
        },
    )
