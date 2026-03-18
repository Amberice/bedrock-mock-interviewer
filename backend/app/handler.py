import json
import boto3
import os
import base64
import time

# --- AWS Configuration ---
REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("TABLE_NAME")
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-micro-v1:0")

# --- Initialize Clients ---
dynamodb = boto3.resource("dynamodb", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
polly = boto3.client("polly", region_name=REGION)
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None


def get_system_prompt(target_role: str) -> str:
    return f"""
You are Stellar AI, a senior FAANG interviewer with a ruthless but fair hiring bar.
You are direct, skeptical, precise, and insight-driven. You do NOT inflate scores.
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

RUTHLESS SCORING STANDARD (0-10):
- 0: greeting, filler, refusal, "idk", "not sure", or no meaningful interview content
- 1-2: extremely weak answer with minimal substance, weak ownership, and little evaluable detail
- 3-4: vague, generic, partial, or high-level answer with some signal but missing enough detail, structure, or evidence
- 5-6: partially structured, some signal, but still shallow, underdeveloped, or missing trade-offs
- 7: solid hire-level answer; clear structure, ownership, metrics, and reasoning
- 8: strong answer with credible complexity, trade-offs, and measurable outcomes
- 9-10: exceptional bar-raiser answer; crisp, insightful, quantified, nuanced, and defensible under follow-up

STRICT SCORING RULES:
- Do NOT reward confidence, polish, or long wording unless substance is present.
- Do NOT give 7+ unless the answer includes specific actions and measurable result or clear technical/business trade-offs.
- Intro/background summaries are NOT strong answers and should usually score 2-4.
- If the answer is vague, generic, or lacks evidence, keep the score below 5.
- Do not assign 0 to an answer that contains meaningful ownership, action, or a measurable outcome, even if it is incomplete.
- For partial but real answers, usually score in the 3-5 range and ask a sharper follow-up question.
- Use 0 only when there is effectively no evaluable interview content.

ADDITIONAL EVALUATION DIMENSIONS:
When scoring, also assess:
- communication
- problem structuring
- trade-off judgment
- risk awareness
- execution feasibility
- metrics thinking
- ownership

RISK AWARENESS means the candidate identifies constraints, edge cases, stakeholder risks, operational risks, compliance or trust risks, and mitigation paths.

EXECUTION FEASIBILITY means the candidate proposes something realistic, sequenced, and implementable rather than vague or idealized.

RECOMMENDATION RULES:
- 0-2: No Hire
- 3-4: Lean No Hire
- 5-6: Mixed / Borderline
- 7: Lean Hire
- 8: Hire
- 9-10: Strong Hire

RATIONALE RULES:
- Explain why the score was given using evidence from the answer.
- Do not use generic praise.
- Mention what is missing if the answer is weak.

QUESTION SELECTION LOGIC:
- Engineering: system design, architecture, debugging, APIs, scale, reliability, trade-offs
- Product/Program/Operations/Business: metrics, execution trade-offs, stakeholder conflict, prioritization, operational risk, process design, scale

FEEDBACK STYLE:
- Be concise, sharp, and useful.
- 2-4 sentences max.
- Say what is weak.
- Say what is missing.
- Say exactly what to improve next time.
- Name the framework expected:
  - STAR/CAR for behavioral
  - trade-offs / architecture / metrics for technical-execution answers

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


def sanitize_history(history):
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
    return cleaned


def generate_audio(text: str):
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


def extract_json(text: str):
    text = (text or "").strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
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


def is_sample_answer_request(normalized: str) -> bool:
    triggers = [
        "sample answer",
        "example answer",
        "perfect answer",
        "better answer",
        "rewrite my answer",
        "can you rewrite",
        "give me an answer",
        "model answer",
        "show me how to answer",
    ]
    return any(t in normalized for t in triggers)


def is_intro_style_input(normalized: str, user_msg: str) -> bool:
    intro_markers = [
        "i'm looking for",
        "i am looking for",
        "my background",
        "previously worked",
        "i transitioned",
    ]

    has_intro_marker = any(marker in normalized for marker in intro_markers)
    lacks_story_structure = (
        "situation" not in normalized
        and "task" not in normalized
        and "action" not in normalized
        and "result" not in normalized
        and "%" not in user_msg
        and not any(ch.isdigit() for ch in user_msg)
    )
    return has_intro_marker and lacks_story_structure


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

    very_short = len(user_msg.strip()) < 25
    has_number = "%" in user_msg or any(ch.isdigit() for ch in user_msg)
    has_action_signal = any(
        phrase in normalized
        for phrase in [
            "i led", "i built", "i created", "i launched", "i owned",
            "i implemented", "i drove", "i designed", "i reduced",
            "i improved", "i partnered", "i resolved", "i developed"
        ]
    )

    return (
        very_short
        or normalized in low_signal_phrases
        or (
            "context" not in normalized
            and "result" not in normalized
            and "metric" not in normalized
            and not has_number
            and not has_action_signal
        )
    )


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


def default_category_scores():
    return {
        "communication": 0,
        "problem_structuring": 0,
        "tradeoff_judgment": 0,
        "risk_awareness": 0,
        "execution_feasibility": 0,
        "metrics_thinking": 0,
        "ownership": 0,
    }


def has_meaningful_signal(user_msg: str, normalized: str) -> bool:
    has_metric = "%" in user_msg or any(ch.isdigit() for ch in user_msg)
    has_action_signal = any(
        phrase in normalized
        for phrase in [
            "i led", "i built", "i created", "i launched", "i owned",
            "i implemented", "i drove", "i designed", "i reduced",
            "i improved", "i partnered", "i resolved", "i developed"
        ]
    )
    return has_metric or has_action_signal


def normalize_scorecard(scorecard, feedback, score):
    scorecard = scorecard or {}

    normalized = {
        "recommendation": scorecard.get("recommendation") or recommendation_from_score(score),
        "confidence": scorecard.get("confidence", "Low"),
        "categoryScores": scorecard.get("categoryScores") or default_category_scores(),
        "strengths": scorecard.get("strengths", []),
        "gaps": scorecard.get("gaps", []),
        "rationale": scorecard.get("rationale") or feedback,
    }

    full_categories = default_category_scores()
    incoming = normalized["categoryScores"] if isinstance(
        normalized["categoryScores"], dict) else {}
    full_categories.update(incoming)
    normalized["categoryScores"] = full_categories

    if not isinstance(normalized["strengths"], list):
        normalized["strengths"] = []
    if not isinstance(normalized["gaps"], list):
        normalized["gaps"] = []

    return normalized


def handler(event, context):
    t0 = time.time()

    try:
        body = json.loads(event.get("body", "{}"))
        user_msg = (body.get("message", "") or "").strip()
        session_id = body.get("session_id", "default")
        target_role = body.get("role", "Software Engineer (Backend)")
    except Exception:
        return {
            "statusCode": 400,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS",
            },
            "body": json.dumps({"message": "Invalid JSON"}),
        }

    normalized = user_msg.lower()

    too_short = len(user_msg.strip()) < 20 or normalized in {
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
                "The response did not contain enough detail, structure, "
                "ownership, or measurable outcome to assess interview performance."
            ),
        }

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS",
            },
            "body": json.dumps(
                {
                    "session_id": session_id,
                    "target_role": target_role,
                    "reply": "I cannot evaluate that. Give me a real answer with context, what you did, and a measurable result.",
                    "score": 0,
                    "feedback": short_feedback,
                    "scorecard": short_scorecard,
                    "transcript": [],
                    "audio": None,
                }
            ),
        }

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
            inferenceConfig={"maxTokens": 1000, "temperature": 0.35},
        )

        raw_content = response["output"]["message"]["content"][0]["text"]
        ai_data = extract_json(raw_content)

        reply_text = (ai_data.get("reply") or "").strip()
        score = int(ai_data.get("score", 0) or 0)
        feedback = (ai_data.get("feedback") or "").strip()
        scorecard = normalize_scorecard(
            ai_data.get("scorecard"), feedback, score)

        if is_sample_answer_request(normalized):
            score = 0
            if not feedback:
                feedback = "Sample answer requested."
            scorecard["recommendation"] = "No Hire"
            scorecard["confidence"] = "High"
            scorecard["rationale"] = feedback

        if is_intro_style_input(normalized, user_msg):
            score = 3 if score == 0 else min(score, 4)
            feedback = (
                "This is background context, not a full interview answer. "
                "Turn it into STAR/CAR: describe one situation, what you did, and the measurable result."
            )
            scorecard["recommendation"] = "Lean No Hire"
            scorecard["confidence"] = "Medium"
            scorecard["rationale"] = feedback
            if "Needs a concrete STAR/CAR example." not in scorecard["gaps"]:
                scorecard["gaps"].append("Needs a concrete STAR/CAR example.")

        elif is_vague_input(normalized, user_msg):
            score = 2 if score == 0 else min(score, 4)
            feedback = (
                "This answer has some signal, but it is too vague to score highly. "
                "Use STAR/CAR and include context, actions, and at least one measurable result."
            )
            scorecard["recommendation"] = "Lean No Hire"
            scorecard["confidence"] = "Medium"
            scorecard["rationale"] = feedback
            if "Missing sufficient specificity and measurable outcomes." not in scorecard["gaps"]:
                scorecard["gaps"].append(
                    "Missing sufficient specificity and measurable outcomes."
                )

        if score >= 7:
            has_metric = "%" in user_msg or any(
                ch.isdigit() for ch in user_msg)
            has_action_signal = any(
                phrase in normalized
                for phrase in [
                    "i led", "i built", "i created", "i launched", "i owned",
                    "i implemented", "i drove", "i designed", "i reduced",
                    "i improved", "i partnered", "i resolved"
                ]
            )

            if not (has_metric and has_action_signal):
                score = min(score, 5)
                feedback = (
                    "This answer is overstated relative to the evidence. "
                    "A strong score needs concrete ownership plus measurable impact."
                )
                scorecard["recommendation"] = "Mixed / Borderline"
                scorecard["confidence"] = "Medium"
                scorecard["rationale"] = feedback
                if "Strong score not supported by clear ownership and measurable impact." not in scorecard["gaps"]:
                    scorecard["gaps"].append(
                        "Strong score not supported by clear ownership and measurable impact."
                    )

        if has_meaningful_signal(user_msg, normalized) and score == 0:
            score = 4
            feedback = (
                "This answer has some signal, but it is still too high-level. "
                "Add more context, key actions, and trade-offs to reach a stronger score."
            )
            scorecard["recommendation"] = "Lean No Hire"
            scorecard["confidence"] = "Medium"
            scorecard["rationale"] = feedback
            if "Has some signal, but needs more specific actions, structure, and trade-offs." not in scorecard["gaps"]:
                scorecard["gaps"].append(
                    "Has some signal, but needs more specific actions, structure, and trade-offs."
                )

        scorecard["recommendation"] = recommendation_from_score(score)
        if not scorecard.get("rationale"):
            scorecard["rationale"] = feedback

        transcript = history + [
            {"role": "user", "content": [{"text": user_msg}]},
            {"role": "assistant", "content": [{"text": reply_text}]},
        ]

        audio_b64 = generate_audio(reply_text) if reply_text else None

    except Exception as e:
        print(f"Bedrock Error: {e}")
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "POST,OPTIONS",
            },
            "body": json.dumps({"message": "AI Processing Failure"}),
        }

    try:
        if table is not None:
            updated_history = transcript[-20:]
            table.put_item(
                Item={
                    "session_id": session_id,
                    "history": updated_history,
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
            }
        )
    )

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,OPTIONS",
        },
        "body": json.dumps(
            {
                "session_id": session_id,
                "target_role": target_role,
                "reply": reply_text,
                "score": score,
                "feedback": feedback,
                "scorecard": scorecard,
                "transcript": transcript,
                "audio": audio_b64,
            }
        ),
    }
