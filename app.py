import os
from flask import Flask, request, jsonify
import requests
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

        if data.get("status", {}).get("code") != "SUCCESS":
            print("⚠️ VERIFY ไม่ SUCCESS แต่จะลอง redeem ต่อ")
            return {"status": "ok", "amount": 0}

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
        voucher_id = extract_code(link)

        if not voucher_id:
            return {"success": False, "error": "invalid"}

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
            "Origin": "https://gift.truemoney.com",
            "Referer": link
        }

        # =========================
        # 🔍 VERIFY
        # =========================
        verify_url = f"https://gift.truemoney.com/campaign/vouchers/{voucher_id}/verify"

        r = requests.post(
            verify_url,
            json={"mobile": WALLET_PHONE},
            headers=headers,
            timeout=10
        )

        print("🔍 VERIFY:", r.status_code, r.text)

        # =========================
        # 🔥 REDEEM
        # =========================
        redeem_url = f"https://gift.truemoney.com/campaign/vouchers/{voucher_id}/redeem"

        r = requests.post(
            redeem_url,
            json={"mobile": WALLET_PHONE},
            headers=headers,
            timeout=15
        )

        print("🔥 REDEEM:", r.status_code, r.text)

        data = r.json()

        status = data.get("status", {}).get("code", "")
        voucher = data.get("data", {}).get("voucher", {})

        if status == "SUCCESS" and voucher.get("status") == "REDEEMED":
            return {
                "success": True,
                "amount": float(voucher.get("amount_baht", 0))
            }

        elif voucher.get("status") == "EXPIRED":
            return {"success": False, "error": "expired"}

        elif voucher.get("status") == "REDEEMED":
            return {"success": False, "error": "already_used"}

        else:
            return {"success": False, "error": "failed"}

    except Exception as e:
        print("💀 API ERROR:", e)
        return {"success": False, "error": "exception"}
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

    print("🔍 VALID:", is_valid_truemoney_link(link))
    print("🔍 LINK:", link)

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

    # ===== REDEEM =====
    redeem_result = redeem_angpao(link)

    with lock:
        processing_links.discard(link)

    if redeem_result["success"]:
        amount = redeem_result.get("amount", 0)

        with lock:
            used_links.add(link)

        return jsonify({
            "success": True,
            "amount": amount,
            "auto": True
        })

    # fallback
    return jsonify(redeem_result)
# ================= HOME =================
@app.route("/")
def home():
    return "Backend is running!"
# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
