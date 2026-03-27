from flask import Flask, request
import requests

app = Flask(__name__)

SECRET_KEY = "0865148237P1"  # รหัสกัน HACK

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1486698291251904552/WljpcJO_TKgt9bjP7BPB8behkAJD2Bv8E99A5sXCd-H0MZvm1CftIJaxuh5ZzJsHnRq_"

@app.route("/")
def home():
    return "Backend is running!"

@app.route("/callback", methods=["POST"])
def callback():
    secret = request.headers.get("X-SECRET")

    if secret != SECRET_KEY:
        return {"error": "unauthorized"}, 403

    data = request.json

    status = data.get("status")
    user_id = data.get("user_id")
    amount = data.get("amount")

    if status == "SUCCESS":
        requests.post(DISCORD_WEBHOOK_URL, json={
            "content": f"PAID:{user_id}:{amount}"
        })

    return {"ok": True}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)