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
table = dynamodb.Table(TABLE_NAME)


# --- THE DYNAMIC PERSONA ENGINE ---
def get_system_prompt(target_role: str) -> str:
    return f"""
You are Stellar AI, a senior FAANG interviewer operating with a high hiring bar. You are professional, direct, and precise.
Interview target role: {target_role}

ALLOWED ROLE CATEGORIES (GUARDRAIL):
- engineering, product, program, operations, analytics, business, corporate
If the target role does not reasonably fit one of these categories, you MUST refuse and ask the user to pick a valid tech/corporate role. Set score=0.

INTERACTION MODES (pick exactly one each turn):
A) QUESTION MODE: If the user has not answered a question yet, ask exactly ONE role-appropriate interview question.
B) EVALUATION MODE: If the user is answering, evaluate their answer and then ask the next question (one question only).
C) MODEL_ANSWER MODE: If the user explicitly asks for a sample/perfect answer, provide a concise FAANG-level model answer using the correct framework, then ask one follow-up question.

QUESTION SELECTION LOGIC:
- Engineering roles: prefer system design, architecture, debugging, API integration, scalability, reliability, trade-offs.
- Product/Program/Operations/Business: prefer metric-driven scenarios, execution trade-offs, stakeholder alignment, risk management, operational deep dives.

SCORING (0–10):
- 0: greetings, clarifying questions, refusal, or insufficient content to evaluate.
- 1–3: unstructured, incorrect, no metrics, no trade-offs.
- 4–6: partial structure, vague, weak metrics, missed risks/trade-offs.
- 7: hire — clear framework + concrete metrics/tech details + correct reasoning.
- 8–10: bar-raiser — crisp structure, strong edge cases, explicit trade-offs, strong measurable impact.

FEEDBACK RULES:
- 2–3 sentences max.
- Must mention what was missing and what to add next time.
- Must name the framework expected (STAR/CAR for behavioral; trade-offs/complexity for technical).

OUTPUT SCHEMA (STRICT):
Return VALID JSON ONLY. No markdown. No extra text.
Keys must always exist:
{{
  "reply": "string",
  "score": 0,
  "feedback": "string"
}}
"""


def sanitize_history(history):
    """Keep only Bedrock-compatible turns: role in {user, assistant} and content=[{text:...}]"""
    cleaned = []
    for m in history or []:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content", [])
        if (
            isinstance(content, list)
            and content
            and isinstance(content[0], dict)
            and "text" in content[0]
        ):
            cleaned.append({"role": role, "content": [
                           {"text": str(content[0]["text"])}]})
    return cleaned


def generate_audio(text: str):
    """Generate MP3 audio (base64) using Polly. Returns None on failure."""
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
    """
    Best-effort JSON extraction:
    - If model returns extra text around JSON, try slice from first '{' to last '}'.
    """
    text = (text or "").strip()
    try:
        return json.loads(text)
    except Exception:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start: end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            pass

    return {"reply": text, "score": 0, "feedback": "Parsing error: model did not return valid JSON."}


def handler(event, context):
    t0 = time.time()

    # 1) Parse input
    try:
        body = json.loads(event.get("body", "{}"))
        user_msg = (body.get("message", "") or "").strip()
        session_id = body.get("session_id", "default")
        target_role = body.get("role", "Software Engineer (Backend)")
    except Exception:
        return {"statusCode": 400, "body": "Invalid JSON"}

    # 2) Guardrail for too-short input
    normalized = user_msg.lower()
    too_short = len(user_msg) < 20 or normalized in {
        "idk", "not sure", "no idea", "n/a", "na"}
    if too_short:
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
                    "reply": "I need a bit more detail to evaluate. Please expand: what was the context, what did you do, and what measurable result did you get?",
                    "score": 0,
                    "feedback": "Too little detail to score. Add structure (STAR/CAR) and at least one metric or trade-off.",
                    "audio": None,
                }
            ),
        }

    # 3) Fetch history
    try:
        db_item = table.get_item(Key={"session_id": session_id})
        history = db_item.get("Item", {}).get("history", [])
    except Exception:
        history = []

    # 4) Build Bedrock inputs (CORRECT for converse):
    #    - system prompt goes into top-level `system=[...]`
    #    - messages ONLY contain user/assistant
    dynamic_prompt = get_system_prompt(target_role)
    history = sanitize_history(history)
    messages = history + [{"role": "user", "content": [{"text": user_msg}]}]

    # 5) Call Bedrock
    try:
        response = bedrock.converse(
            modelId=MODEL_ID,
            system=[{"text": dynamic_prompt}],
            messages=messages,
            inferenceConfig={"maxTokens": 1000, "temperature": 0.5},
        )

        raw_content = response["output"]["message"]["content"][0]["text"]
        ai_data = extract_json(raw_content)

        reply_text = (ai_data.get("reply") or "").strip()
        score = int(ai_data.get("score", 0) or 0)
        feedback = (ai_data.get("feedback") or "").strip()

        audio_b64 = generate_audio(reply_text) if reply_text else None

    except Exception as e:
        print(f"Bedrock Error: {e}")
        return {"statusCode": 500, "body": "AI Processing Failure"}

    # 6) Save updated history (store assistant as plain text turn)
    try:
        new_user_turn = {"role": "user", "content": [{"text": user_msg}]}
        new_assistant_turn = {"role": "assistant",
                              "content": [{"text": reply_text}]}
        updated_history = (history + [new_user_turn, new_assistant_turn])[-20:]
        table.put_item(
            Item={
                "session_id": session_id,
                "history": updated_history,
                "last_updated": str(time.time()),
            }
        )
    except Exception as e:
        print(f"DynamoDB write error: {e}")

    # 7) Optional structured latency log (CloudWatch Logs)
    print(
        json.dumps(
            {
                "type": "metric",
                "name": "TotalLatencyMs",
                "value": int((time.time() - t0) * 1000),
                "session_id": session_id,
                "target_role": target_role,
                "score": score,
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
                "reply": reply_text,
                "score": score,
                "feedback": feedback,
                "audio": audio_b64,
            }
        ),
    }
