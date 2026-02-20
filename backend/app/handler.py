import json

def handler(event, context):
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"ok": True, "message": "Hello from your CDK App!"})
    }
