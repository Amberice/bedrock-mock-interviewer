import json
import boto3
import os
import time

# --- Configuration ---
REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("TABLE_NAME")
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-micro-v1:0")
MAX_HISTORY = 12 

# --- Clients ---
dynamodb = boto3.resource("dynamodb", region_name=REGION)
bedrock = boto3.client("bedrock-runtime", region_name=REGION)
table = dynamodb.Table(TABLE_NAME)

def handler(event, context):
    path = event.get("rawPath", "")
    
    # 1. Health Check
    if path.endswith("/health"):
        return {
            "statusCode": 200, 
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"ok": True})
        }

    # 2. Chat Endpoint
    if path.endswith("/chat"):
        try:
            body_str = event.get("body", "{}")
            if not body_str: body_str = "{}"
            body = json.loads(body_str)
            
            session_id = body.get("session_id")
            user_text = body.get("message", "")

            if not session_id or not user_text:
                return {
                    "statusCode": 400, 
                    "body": json.dumps({"error": "session_id and message are required"})
                }

            # Load History
            db_response = table.get_item(Key={"session_id": session_id})
            history = db_response.get("Item", {}).get("history", [])

            # Rolling Window
            if len(history) > MAX_HISTORY:
                history = history[-MAX_HISTORY:]

            # Prepare Payload
            new_user_msg = {"role": "user", "content": [{"text": user_text}]}
            messages_to_send = history + [new_user_msg]

            payload = {
                "schemaVersion": "messages-v1",
                "system": [{"text": "You are a professional interviewer. Keep your questions concise."}],
                "messages": messages_to_send,
                "inferenceConfig": {"maxTokens": 300, "temperature": 0.5}
            }

            # Call Bedrock
            br_response = bedrock.invoke_model(
                modelId=MODEL_ID,
                body=json.dumps(payload)
            )
            
            model_data = json.loads(br_response["body"].read())
            ai_text = model_data["output"]["message"]["content"][0]["text"]

            # Save History
            new_ai_msg = {"role": "assistant", "content": [{"text": ai_text}]}
            updated_history = messages_to_send + [new_ai_msg]
            
            if len(updated_history) > MAX_HISTORY:
                updated_history = updated_history[-MAX_HISTORY:]

            table.put_item(Item={
                "session_id": session_id,
                "history": updated_history,
                "last_updated": int(time.time())
            })

            return {
                "statusCode": 200, 
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"reply": ai_text, "session_id": session_id})
            }

        except Exception as e:
            print(f"Error: {str(e)}")
            return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

    return {"statusCode": 404, "body": json.dumps({"error": "Path not found"})}
