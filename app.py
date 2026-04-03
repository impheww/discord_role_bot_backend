import os
from flask import Flask, request, jsonify
import requests
from threading import Lock
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
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

            print("🔥 OPEN LINK")
            page.goto(link, wait_until="domcontentloaded", timeout=20000)

            page.wait_for_selector("body", timeout=10000)

            # 🔍 หา "รับซอง"
            clicked = False

            try:
                page.locator("text=รับซอง").first.click(timeout=10000)
                print("✅ คลิกปุ่มรับซองแล้ว")
                clicked = True
            except PlaywrightTimeoutError:
                print("❌ หา 'รับซอง' ไม่เจอ")

            if not clicked:
                page.screenshot(path="debug_no_button.png")
                print("📄 PAGE:", page.inner_text("body")[:500])
                return {"success": False, "error": "no_button"}

            # ✅ รอ input
            try:
                page.wait_for_selector("input", timeout=10000)
            except PlaywrightTimeoutError:
                print("❌ ไม่เจอ input")
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

                except Exception as e:
                    print("skip confirm btn error:", e)

            # 🔥 fallback
            if not confirm_clicked:
                try:
                    buttons[0].click()
                    confirm_clicked = True
                    print("✅ fallback: กดปุ่มแรก")
                except IndexError:
                    print("❌ ไม่มีปุ่มให้ fallback")
                except Exception as e:
                    print("❌ fallback error:", e)

            if not confirm_clicked:
                return {"success": False, "error": "no_confirm"}
            # =====================================
            # 🔥 fallback รอ modal/text หลัง confirm
            # =====================================
            try:
                page.wait_for_selector("div[role=dialog] >> text=สำเร็จ", timeout=10000)
                print("✅ พบ modal สำเร็จ")
            except PlaywrightTimeoutError:
                print("⚠️ ไม่พบ modal, จะตรวจผลจาก page.inner_text แทน")

            # =====================================
            # 🔥 รอผลลัพธ์จาก API จริง
            # =====================================
            try:
                print("⏳ กดปุ่มแล้ว รอ network response...")

                # จับ response API ของ TrueMoney หลังกดปุ่มยืนยัน
                with page.expect_response(
                        lambda resp: "vouchers" in resp.url and resp.status == 200,  # partial match เฉพาะ path ที่ชัวร์
                        timeout=45000
                ) as resp_info:
                    # กดยืนยัน (button ที่เจอก่อนหน้านี้)
                    if not confirm_clicked:
                        page.locator("text=รับซองเลย").first.click()
                redeem_resp = resp_info.value
                data = redeem_resp.json()
                print("✅ REDEEM RESPONSE:", data)

                # วิเคราะห์ผล
                status = data.get("status", {}).get("code", "")
                voucher = data.get("data", {}).get("voucher", {})

                if status == "SUCCESS" and voucher.get("status") == "REDEEMED":
                    return {"success": True, "amount": float(voucher.get("amount_baht", 0))}

                elif voucher.get("status") == "EXPIRED":
                    return {"success": False, "error": "expired"}

                elif voucher.get("status") == "REDEEMED":
                    return {"success": False, "error": "already_used"}

                else:
                    return {"success": False, "error": "unknown"}

            except PlaywrightTimeoutError:
                print("⚠️ รอ network response timeout")
                return {"success": False, "error": "timeout"}
            except Exception as e:
                print("❌ REDEEM ERROR:", e)
                return {"success": False, "error": "exception"}

    except PlaywrightTimeoutError:
        print("TIMEOUT ERROR")
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
