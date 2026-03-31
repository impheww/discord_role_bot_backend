from flask import Flask, request, jsonify
import requests
import time
import random
from threading import Lock
# ============= LINK PATTERN ==============
def is_valid_truemoney_link(link: str) -> bool:
    link = link.strip().replace("<", "").replace(">", "")
    return "gift.truemoney.com/campaign" in link and "v=" in link
# ==========================================
app = Flask(__name__)

used_links = set()
processing_links = set()
lock = Lock()
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

        res = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://gift.truemoney.com/",
            "Origin": "https://gift.truemoney.com"
        }, timeout=10)

        print("STATUS CODE:", res.status_code)
        print("RAW TEXT:", res.text)

        data = res.json()
        print("TRUEMONEY RESPONSE:", data)

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
    data = request.get_json(silent=True) or {}
    print("🔥 ได้ data จาก bot:", data)

    link = data.get("link")
    user_id = data.get("user_id")

    print("👉 link:", link)
    print("👉 user_id:", user_id)

    if not link:
        return jsonify({"status": "error", "message": "no link"}), 400

    # 🔒 validate link แน่น
    if not link or not is_valid_truemoney_link(link):
        return jsonify({
            "success": False,
            "error": "invalid"
        }), 400

    with lock:

        # ❌ ลิ้งซ้ำ
        if link in used_links:
            return jsonify({"success": False, "error": "used"})

        # ❌ กำลังใช้อยู่ (กัน race)
        if link in processing_links:
            return jsonify({"success": False, "error": "processing"})

        processing_links.add(link)

    # ===== CHECK =====
    check_result = check_angpao(link)

    if check_result["status"] == "invalid":
        processing_links.discard(link)
        return jsonify({"success": False, "error": "invalid"})

    if check_result["status"] == "used":
        processing_links.discard(link)
        return jsonify({"success": False, "error": "used"})

    # ===== REDEEM =====
    redeem_result = redeem_angpao(link)

    with lock:
        processing_links.discard(link)

    if redeem_result["success"]:
        amount = redeem_result["amount"]

        with lock:
            used_links.add(link)

        return jsonify({
            "success": True,
            "amount": amount,
            "auto": True
        })

    # fallback
    return jsonify({
        "success": True,
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
