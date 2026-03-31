from flask import Flask, request, jsonify
import requests
import time
import random

app = Flask(__name__)

# ================= CONFIG =================
WALLET_PHONE = "0806084308"  # 🔴 เบอร์ฉัน
DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1486698291251904552/WljpcJO_TKgt9bjP7BPB8behkAJD2Bv8E99A5sXCd-H0MZvm1CftIJaxuh5ZzJsHnRq_"

# ================= UTILS =================
def extract_code(link):
    if "v=" not in link:
        return None
    return link.split("v=")[-1]

# ================= CHECK =================
def check_angpao(link):
    try:
        code = extract_code(link)
        if not code:
            return {"status": "invalid"}

        url = f"https://gift.truemoney.com/campaign/vouchers/{code}/verify"

        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)

        if res.status_code != 200:
            return {"status": "invalid"}

        data = res.json()

        if data["status"]["code"] != "SUCCESS":
            return {"status": "invalid"}

        voucher = data["data"]["voucher"]

        if voucher["status"] == "REDEEMED":
            return {"status": "used"}

        return {
            "status": "ok",
            "amount": float(voucher["amount_baht"])
        }

    except Exception as e:
        print("CHECK ERROR:", e)
        return {"status": "invalid"}
# ================= REDEEM =================
def redeem_angpao(link):
    try:
        code = extract_code(link)

        url = f"https://gift.truemoney.com/campaign/vouchers/{code}/redeem"

        payload = {
            "mobile": WALLET_PHONE
        }

        for _ in range(3):
            res = requests.post(url, json=payload, headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/json"
            })

            data = res.json()

            if data["status"]["code"] == "SUCCESS":
                return {
                    "success": True,
                    "amount": float(data["data"]["voucher"]["amount_baht"])
                }

            time.sleep(random.uniform(1, 2))

        return {"success": False}

    except Exception as e:
        print("REDEEM ERROR:", e)
        return {"success": False}
# ================= API =================
@app.route("/redeem", methods=["POST"])
def redeem():
    data = request.json
    link = data.get("link")
    user_id = data.get("user_id")

    check_result = check_angpao(link)

    # ❌ ลิ้งผิด
    if check_result["status"] == "invalid":
        return jsonify({"status": "invalid"})

    # ❌ ใช้แล้ว
    if check_result["status"] == "used":
        return jsonify({"status": "used"})

    # ✅ พยายาม auto
    redeem_result = redeem_angpao(link)

    if redeem_result["success"]:
        amount = redeem_result["amount"]

        requests.post(DISCORD_WEBHOOK, json={
            "content": f"PAID:{user_id}:{amount}"
        })

        return jsonify({
            "status": "success",
            "amount": amount,
            "auto": True
        })

    # 🟡 fallback
    return jsonify({
        "status": "success",
        "amount": check_result["amount"],
        "auto": False
    })

# ================= HOME =================
@app.route("/")
def home():
    return "Backend is running!"

# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
