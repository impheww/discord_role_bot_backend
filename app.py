import os
from flask import Flask, request, jsonify
import requests
from threading import Lock
import re
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import ViewportSize
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
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ]
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
                viewport=ViewportSize(width=390, height=844),
                is_mobile=True,
                has_touch=True,
                locale="th-TH"
            )

            # 🔥 stealth
            context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'languages', { get: () => ['th-TH','th'] });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
            """)

            page = context.new_page()

            print("🔥 OPEN")
            page.goto(link, wait_until="domcontentloaded", timeout=30000)

            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            page.wait_for_timeout(3000)

            # =========================
            # 🔥 HUMAN BEHAVIOR
            # =========================
            page.mouse.move(200, 400)
            page.wait_for_timeout(500)
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(1000)

            # =========================
            # 🔥 CLICK ปุ่มรับ
            # =========================
            try:
                page.wait_for_timeout(4000)

                candidates = page.locator("button, div, span, a")

                count = candidates.count()
                print("🔍 clickable:", count)

                clicked = False

                for i in range(count):
                    el = candidates.nth(i)

                    text = ""
                    if el.is_visible():
                        raw = el.text_content()
                        if raw:
                            text = raw.lower()

                    if any(k in text for k in ["รับ", "ซอง", "open", "gift"]):
                        try:
                            el.click(timeout=2000)
                            print(f"✅ คลิกตัวที่ {i} | text={text}")
                            clicked = True
                            break
                        except Exception as e:
                            print("❌ click fail:", e)

                if not clicked:
                    print("❌ ไม่เจอปุ่มรับซองจริงๆ")
                    return {"success": False, "error": "no_button"}
                print("✅ clicked รับซอง")

            except Exception as e:
                print("❌ click ไม่ได้:", e)
                return {"success": False, "error": "no_button"}

            # =========================
            # 🔥 WAIT INPUT
            # =========================
            try:
                page.wait_for_selector("input", timeout=15000)

                inputs = page.locator("input")
                if inputs.count() == 0:
                    return {"success": False, "error": "no_input"}

                phone_input = inputs.first
                phone_input.click()
                page.wait_for_timeout(300)

                # 👇 พิมพ์แบบมนุษย์
                for digit in WALLET_PHONE:
                    phone_input.type(digit, delay=120)

                print("📱 ใส่เบอร์แล้ว")

            except PlaywrightTimeoutError:
                print("❌ input ไม่มา")
                return {"success": False, "error": "no_input"}

            # =========================
            # 🔘 CONFIRM
            # =========================
            try:
                confirm = page.get_by_role("button").filter(
                    has_text=re.compile("ยืนยัน|รับเงิน|continue|ตกลง", re.I)
                ).first

                confirm.click(timeout=5000)
                print("✅ confirm แล้ว")

            except Exception as e:
                print("⚠️ confirm fail:", e)
                return {"success": False, "error": "no_confirm"}

            # =========================
            # 🔥 WAIT RESULT
            # =========================
            try:
                page.wait_for_timeout(5000)

                content = page.inner_text("body")

                if "สำเร็จ" in content:
                    return {"success": True, "amount": 0}

                if "หมดอายุ" in content:
                    return {"success": False, "error": "expired"}

                if "ใช้ไปแล้ว" in content:
                    return {"success": False, "error": "already_used"}

                return {"success": False, "error": "unknown"}

            except Exception as e:
                print("❌ result error:", e)
                return {"success": False, "error": "timeout"}

    except Exception as e:
        print("💀 error:", e)
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
