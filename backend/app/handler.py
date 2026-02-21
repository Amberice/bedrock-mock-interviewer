import json
import boto3
import os

# Initialize Bedrock with the correct region
bedrock = boto3.client(
    service_name="bedrock-runtime",
    region_name=os.environ.get("AWS_REGION", "us-east-1")
)

MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-micro-v1:0")

def handler(event, context):
    path = event.get("rawPath", "")

    # --- 1. Health Check ---
    if path.endswith("/health"):
        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"ok": True, "message": "System operational"})
        }

    # --- 2. AI Demo (Nova Micro) ---
    if path.endswith("/demo"):
        try:
            # The specific payload schema required by Nova
            request_body = {
                "schemaVersion": "messages-v1",
                "system": [{"text": "You are a professional interviewer. Ask exactly ONE simple question about Python."}],
                "messages": [
                    {"role": "user", "content": [{"text": "Start the interview."}]}
                ],
                "inferenceConfig": {
                    "maxTokens": 300,
                    "temperature": 0.5
                }
            }

            response = bedrock.invoke_model(
                modelId=MODEL_ID,
                body=json.dumps(request_body)
            )

            # Parse Nova response
            model_response = json.loads(response["body"].read())
            ai_text = model_response["output"]["message"]["content"][0]["text"]

            return {
                "statusCode": 200,
                "headers": {"content-type": "application/json"},
                "body": json.dumps({"question": ai_text})
            }

        except Exception as e:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": str(e)})
            }

    return {"statusCode": 404, "body": json.dumps({"error": "Path not found"})}
