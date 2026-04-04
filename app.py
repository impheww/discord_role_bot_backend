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
                    "--disable-infobars",
                    "--window-size=390,844",
                ]
            )

            context = browser.new_context(
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
                viewport=ViewportSize(width=390, height=844),
                is_mobile=True,
                has_touch=True,
                locale="th-TH"
            )

            # 🔥 หลอกว่าไม่ใช่ bot
            context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });

            window.chrome = {
                runtime: {}
            };

            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3],
            });

            Object.defineProperty(navigator, 'languages', {
                get: () => ['th-TH', 'th'],
            });
            """)

            page = context.new_page()

            # debug network
            page.on("response", lambda r: print("📡", getattr(r, "status", "?"), r.url))  # type: ignore

            print("🔥 OPEN LINK")
            page.goto(link, wait_until="domcontentloaded", timeout=20000)

            # กัน React โหลดไม่ทัน
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)

            # =========================
            # 🔥 CLICK "รับซอง"
            # =========================
            try:
                page.get_by_role("button", name=re.compile("รับซอง", re.I)).click(timeout=10000)
                print("✅ คลิกปุ่มรับซองแล้ว")
            except PlaywrightTimeoutError:
                return {"success": False, "error": "no_button"}

            # =========================
            # 🔥 WAIT INPUT (สำคัญสุด)
            # =========================
            try:
                # 🔥 รอ input แบบยืดหยุ่น (ดีกว่า wait_for_function)
                page.wait_for_selector("input", timeout=10000)

                # 👇 เพิ่ม human behavior กัน detect
                page.mouse.move(100, 200)
                page.wait_for_timeout(500)
                page.mouse.wheel(0, 300)
                page.wait_for_timeout(800)

                inputs = page.locator("input")
                count = inputs.count()
                print("🔍 INPUT COUNT:", count)

                if count == 0:
                    return {"success": False, "error": "no_input"}

                phone_input = inputs.first

                phone_input.click()
                page.wait_for_timeout(300)

                phone_input.fill(WALLET_PHONE)

                print("📱 กรอกเบอร์แล้ว:", WALLET_PHONE)

            except PlaywrightTimeoutError:
                print("❌ input ไม่มา (timeout)")
                return {"success": False, "error": "no_input"}

            # =========================
            # 🔘 CLICK CONFIRM
            # =========================
            confirm_clicked = False

            try:
                btn = page.get_by_role("button").filter(
                    has_text=re.compile("ยืนยัน|รับเงิน|ตกลง|continue|ถัดไป", re.I)
                ).first

                btn.click(timeout=5000)
                confirm_clicked = True
                print("✅ กดยืนยันแล้ว")

            except Exception as e:
                print("⚠️ confirm click error:", e)

            if not confirm_clicked:
                try:
                    page.locator("button").first.click()
                    print("⚠️ fallback กดปุ่มแรก")
                except Exception as e:
                    print("❌ fallback click error:", e)
                    return {"success": False, "error": "no_confirm"}

            # =========================
            # 🔥 WAIT API RESPONSE
            # =========================
            try:
                print("⏳ รอ API...")

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

                except Exception as e:
                    print("⏰ timeout error:", e)
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
