import os
from flask import Flask, request, jsonify
from threading import Lock
import re
from playwright.sync_api import sync_playwright
from playwright.sync_api import ViewportSize
import time
import logging
# ============= LINK PATTERN ==============
def is_valid_truemoney_link(link: str) -> bool:
    link = link.strip().replace("<", "").replace(">", "")
    return "gift.truemoney.com/campaign" in link and "v=" in link
# ==========================================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

user_last_request = {}
used_links = set()
processing_links = set()
lock = Lock()
# ================= CONFIG =================
WALLET_PHONE = "0806084308"  # 🔴 เบอร์ฉัน
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK")
# ================= UTILS =================
def extract_code(link):
    if "v=" not in link:
        return None
    return link.split("v=")[-1]
# ================= SPAM =================
def is_spam(user_id):
    now = time.time()

    if user_id in user_last_request:
        if now - user_last_request[user_id] < 5:
            return True

    user_last_request[user_id] = now
    return False
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
            page.wait_for_timeout(3000)

            # =========================
            # 🔥 CLICK "รับซอง"
            # =========================
            try:
                open_btn = None
                buttons = page.get_by_role("button")

                for i in range(buttons.count()):
                    btn = buttons.nth(i)
                    text = (btn.text_content() or "").strip()

                    if any(k in text for k in ["รับซอง", "open", "gift"]):
                        if btn.is_visible():
                            open_btn = btn
                            print(f"🎯 FOUND OPEN BUTTON: {text}")
                            break

                if not open_btn:
                    print("❌ ไม่เจอปุ่มรับซอง")
                    return {"success": False, "error": "no_button"}

                open_btn.click(delay=100)
                print("✅ clicked รับซอง")

                # 🔥 ต้องมี input โผล่ = เข้า flow แล้ว
                page.wait_for_selector("input", timeout=15000)

            except Exception as e:
                print("❌ click รับซองไม่ได้:", e)
                return {"success": False, "error": "no_button"}

            # =========================
            # 📱 ใส่เบอร์
            # =========================
            try:
                inputs = page.locator("input")

                if inputs.count() == 0:
                    return {"success": False, "error": "no_input"}

                phone_input = inputs.first
                phone_input.click()
                page.wait_for_timeout(300)

                for digit in WALLET_PHONE:
                    phone_input.type(digit, delay=120)

                print("📱 ใส่เบอร์แล้ว")

            except Exception as e:
                print("❌ input error:", e)
                return {"success": False, "error": "no_input"}

            # =========================
            # 🔘 CONFIRM (FINAL FIX)
            # =========================
            try:
                page.wait_for_timeout(1500)

                confirm_btn = None

                # 🔥 1. ลองกด Enter ก่อน (สำคัญมาก)
                try:
                    phone_input.press("Enter")
                    print("⌨️ press Enter")
                    page.wait_for_timeout(2000)
                except Exception as e:
                    print("⚠️ Enter fail:", e)

                # 🔥 2. หา button + role=button
                candidates = page.locator("button, div[role=button]")

                for i in range(candidates.count()):
                    el = candidates.nth(i)

                    if not el.is_visible():
                        continue

                    text = (el.text_content() or "").strip()

                    if any(k in text for k in ["ยืนยัน", "รับเงิน", "ตกลง"]):
                        confirm_btn = el
                        print(f"🎯 FOUND CONFIRM: {text}")
                        break

                # 🔥 3. fallback: หา element ใหญ่ (เผื่อไม่มี text)
                if not confirm_btn:
                    print("⚠️ fallback scan...")

                    candidates = page.locator("div, button")

                    for i in range(candidates.count()):
                        el = candidates.nth(i)

                        if not el.is_visible():
                            continue

                        box = el.bounding_box()
                        if not box:
                            continue

                        if box["width"] > 150 and box["height"] > 40:
                            confirm_btn = el
                            print(f"⚠️ fallback confirm index={i}")
                            break

                # ❌ ยังไม่เจอจริง
                if not confirm_btn:
                    print("❌ ไม่เจอปุ่ม confirm จริง")
                    return {"success": False, "error": "no_confirm"}

                # 🔥 CLICK + monitor request
                try:
                    with page.expect_response(lambda r: "redeem" in r.url or "campaign" in r.url, timeout=10000):
                        confirm_btn.click(delay=100)
                        print("✅ clicked confirm + request detected")
                except Exception as e:
                    print("⚠️ no request detected:", e)
                    confirm_btn.click(delay=100)
                    print("⚠️ clicked confirm fallback")

            except Exception as e:
                print("❌ confirm error:", e)
                return {"success": False, "error": "no_confirm"}

            # =========================
            # 🔥 WAIT RESULT (REAL)
            # =========================
            try:
                page.wait_for_timeout(3000)

                # 🔥 รอ UI เปลี่ยนจริง
                try:
                    page.wait_for_function("""
                    () => {
                        const body = document.body.innerText;
                        return !body.includes('กรอกเบอร์โทรศัพท์');
                    }
                    """, timeout=8000)
                except Exception as e:
                    logging.warning(f"⚠️ UI ไม่เปลี่ยน: {e}")

                content = page.inner_text("body").lower()

                print("📄 TEXT LENGTH:", len(content))
                print("📄 TEXT SAMPLE:", content[:400])

                # 📸 debug screenshot
                try:
                    page.screenshot(path="debug_after_confirm.png")
                except Exception as e:
                    print("❌ ERROR:", e)
                    pass

                # ✅ SUCCESS
                if any(k in content for k in [
                    "รับเงินสำเร็จ",
                    "คุณได้รับเงิน",
                    "ได้รับเงิน",
                    "successfully",
                ]):

                    # หาเงินจาก text
                    match = re.search(r'฿\s?([\d,.]+)', content)
                    amount = 0

                    if match:
                        amount = float(match.group(1).replace(",", ""))

                    print(f"💰 EXTRACTED AMOUNT: {amount}")

                    return {
                        "success": True,
                        "amount": amount
                    }

                # ❌ USED
                if any(k in content for k in [
                    "already",
                    "used",
                    "รับไปแล้ว",
                    "ครบแล้ว"
                ]):
                    return {"success": False, "error": "used"}

                # ❌ EXPIRED
                if any(k in content for k in [
                    "หมดอายุ",
                    "expired"
                ]):
                    return {"success": False, "error": "expired"}

                # ❌ STILL SAME PAGE
                if "กรอกเบอร์โทรศัพท์" in content:
                    print("⚠️ ยังอยู่หน้าเดิม → confirm ไม่ทำงาน")
                    return {"success": False, "error": "confirm_not_work"}

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
    if link:
        link = link.strip()
        if not isinstance(link, str):
            return jsonify({"success": False, "error": "invalid_type"}), 400
    user_id = data.get("user_id")
    # 🔥 edge: ไม่มี user_id
    if not user_id:
        return jsonify({"success": False, "error": "no_user"}), 400

    print("👉 link:", link)
    print("👉 user_id:", user_id)

    # 🔥 กัน spam
    if is_spam(user_id):
        return jsonify({"success": False, "error": "spam"}), 429

    print("🔍 VALID:", is_valid_truemoney_link(link))
    print("🔍 LINK:", link)

    # 🔥 check link
    if not link or not is_valid_truemoney_link(link):
        return jsonify({
            "success": False,
            "error": "invalid"
        }), 400

    with lock:

        # ❌ ลิ้งซ้ำในระบบ (ยังไม่ต้องไปยิง API)
        if link in used_links:
            return jsonify({"success": False, "error": "duplicate"})

        # ❌ กำลังใช้อยู่ (กันคนกดพร้อมกัน)
        if link in processing_links:
            return jsonify({"success": False, "error": "processing"})

        processing_links.add(link)

    # ===== REDEEM =====
    try:
        redeem_result = redeem_angpao(link)
    except Exception as e:
        logging.error(f"Redeem error: {e}")
        redeem_result = {"success": False, "error": "server_error"}
    finally:
        with lock:
            processing_links.discard(link)

    if redeem_result["success"]:
        amount = redeem_result.get("amount", 0)

        with lock:
            used_links.add(link)

            # 🔥 limit ขนาด
            if len(used_links) > 1000:
                used_links.clear()

        print(f"💰 FINAL AMOUNT SENT: {amount}")

        return jsonify({
            "success": True,
            "amount": amount,
            "auto": True
        })

    return jsonify(redeem_result)
# ================= HOME =================
@app.route("/")
def home():
    return "Backend is running!"
# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
