from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ======= เพิ่ม route =======
@app.route("/")
def home():
    return "Backend is running!"
# =========================
# ฟังก์ชันเช็คซองอั่งเปา
# =========================
def check_angpao(link):
    try:
        voucher_id = link.split("?v=")[-1]

        url = f"https://gift.truemoney.com/campaign/vouchers/{voucher_id}/redeem"

        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json"
        }

        # ⚠ ใช้เบอร์ test (ต้องมี wallet จริง)
        data = {
            "mobile": "0806084308",  # 🔥 ใส่เบอร์ TrueWallet ของคุณ
            "voucher_hash": voucher_id
        }

        res = requests.post(url, json=data, headers=headers)
        result = res.json()

        print(result)

        if result["status"]["code"] == "SUCCESS":
            amount = float(result["data"]["my_ticket"]["amount_baht"])
            return {"success": True, "amount": amount}

        else:
            return {"success": False, "reason": result["status"]["message"]}

    except Exception as e:
        return {"success": False, "reason": str(e)}

# =========================
# API รับลิ้งจาก Discord
# =========================
@app.route("/check", methods=["POST"])
def check():
    data = request.json

    user_id = data["user_id"]
    link = data["link"]

    result = check_angpao(link)

    return jsonify({
        "user_id": user_id,
        "result": result
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)