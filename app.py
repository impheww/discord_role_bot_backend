import os
from flask import Flask, request, jsonify
import requests
from threading import Lock
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Error as PlaywrightError
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
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            page = browser.new_page(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
            )

            # 🔥 debug network (fix warning ด้วย type ignore)
            page.on("response", lambda r: print("📡", getattr(r, "status", "?"), r.url))  # type: ignore

            print("🔥 OPEN LINK")
            page.goto(link, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector("body", timeout=10000)

            # 🔍 หา "รับซอง"
            try:
                page.locator("text=รับซอง").first.click(timeout=10000)
                print("✅ คลิกปุ่มรับซองแล้ว")
                # 🔥 กรอกเบอร์โทร
                try:
                    phone_input = page.wait_for_selector("input[type='tel']", timeout=5000)
                    phone_input.fill(WALLET_PHONE)
                    print("📱 กรอกเบอร์แล้ว:", WALLET_PHONE)
                except PlaywrightError:
                    print("❌ ไม่พบช่องกรอกเบอร์")
                    return {"success": False, "error": "no_input"}
            except PlaywrightTimeoutError:
                print("❌ หา 'รับซอง' ไม่เจอ")
                return {"success": False, "error": "no_button"}

            # ✅ รอ input
            try:
                page.wait_for_selector("input", timeout=10000)
            except PlaywrightTimeoutError:
                return {"success": False, "error": "no_input"}

            print("🔥 FILL PHONE")
            page.fill("input", WALLET_PHONE)

            # 🔘 กดยืนยัน
            buttons = page.query_selector_all("button")

            confirm_clicked = False

            for btn in buttons:
                try:
                    text = btn.inner_text().strip()
                    print("🔍 BUTTON:", text)

                    if any(word in text for word in [
                        "รับเงิน", "ยืนยัน", "ตกลง", "ถัดไป", "continue", "รับซอง"
                    ]):
                        btn.click()
                        print("✅ กดยืนยันแล้ว:", text)
                        confirm_clicked = True
                        break
                except PlaywrightError:
                    continue

            if not confirm_clicked:
                try:
                    buttons[0].click()
                    print("✅ fallback: กดปุ่มแรก")
                except PlaywrightError:
                    return {"success": False, "error": "no_confirm"}

            # 🔥 กัน race condition
            page.wait_for_timeout(1000)

            # =====================================
            # 🔥 ดัก network response
            # =====================================
            try:
                print("⏳ รอ network response...")

                with page.expect_response(
                    lambda r: (
                        ("redeem" in r.url or "voucher" in r.url)
                        and getattr(r, "status", 0) == 200
                    ),
                    timeout=60000
                ) as resp_info:
                    pass

                response = resp_info.value
                data = response.json()
                print("✅ API:", data)

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
                    return {"success": False, "error": "unknown"}

            except PlaywrightTimeoutError:
                print("⚠️ API timeout → fallback DOM")

                # 🔥 fallback DOM
                try:
                    page.wait_for_function("""
                        () => {
                            const t = document.body.innerText;
                            return t.includes('สำเร็จ') || 
                                   t.includes('หมดอายุ') || 
                                   t.includes('ใช้ไปแล้ว');
                        }
                    """, timeout=15000)

                    content = page.inner_text("body")

                    if "สำเร็จ" in content:
                        return {"success": True, "amount": 0}

                    elif "หมดอายุ" in content:
                        return {"success": False, "error": "expired"}

                    elif "ใช้ไปแล้ว" in content:
                        return {"success": False, "error": "already_used"}

                    else:
                        return {"success": False, "error": "unknown"}

                except PlaywrightError:
                    return {"success": False, "error": "timeout"}

    except PlaywrightTimeoutError:
        return {"success": False, "error": "timeout"}

    except Exception as e:
        print("ERROR:", e)
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
