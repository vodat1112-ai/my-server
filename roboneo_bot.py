"""
╔══════════════════════════════════════════════════════╗
║         ROBONEO BOT — Phiên bản đầy đủ              ║
║  pip install python-telegram-bot==21.9 aiohttp flask ║
║  Chạy: python roboneo_bot.py                         ║
╚══════════════════════════════════════════════════════╝
"""

import logging
import hashlib
import hmac
import asyncio
import threading
import time
import json
import os
import io
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import aiohttp

# ════════════════════════════════════════════════════
#                    CẤU HÌNH
# ════════════════════════════════════════════════════
BOT_TOKEN  = "8620998717:AAE7P-MimVeUMB1lG29T10MXe7gGqQtzOw8"
ADMIN_ID   = 7131184806
SUPPORT    = "@your_support"          # 👈 Thay username hỗ trợ

PAYOS_CLIENT_ID = "13f08821-7d23-45a0-9ab5-c02c59fb337c"
PAYOS_API_KEY   = "7682b6e5-d570-48da-8347-1e2175f8a8dd"
PAYOS_CHECKSUM  = "345a7f892bd9c7641a043d04442c81da2f37c789ddf4dc9cac43c8b462870037"
PAYOS_API_URL   = "https://api-merchant.payos.vn"
SERVER_URL      = "https://my-server-production-37d7.up.railway.app"

LOW_STOCK_THRESHOLD = 3   # Cảnh báo khi kho dưới X tài khoản
MIN_TOPUP = 2000          # Số tiền nạp tối thiểu (đồng)

# ════════════════════════════════════════════════════
#                 FILE DỮ LIỆU
# ════════════════════════════════════════════════════
PRODUCTS_FILE = "products.json"
DB_FILE       = "data.json"

DEFAULT_PRODUCTS = {
    "sp1": {
        "name": "Roboneo tài khoản 120-140🥕",
        "price": 1000, "pd": "1k", "stock": 0, "accounts": [],
        "msg": "🛒 <b>Xác nhận đơn hàng</b>\n\n📦 Sản phẩm: <b>{name}</b>\n💰 Giá: <b>{price}</b>/tài khoản\n📊 Còn lại: <b>{stock} tài khoản</b>\n\n✏️ Nhập số lượng cần mua (tối đa {stock}):"
    },
    "sp2": {
        "name": "Roboneo tài khoản 170-190🥕",
        "price": 2000, "pd": "2k", "stock": 0, "accounts": [],
        "msg": "🛒 <b>Xác nhận đơn hàng</b>\n\n📦 Sản phẩm: <b>{name}</b>\n💰 Giá: <b>{price}</b>/tài khoản\n📊 Còn lại: <b>{stock} tài khoản</b>\n\n✏️ Nhập số lượng cần mua (tối đa {stock}):"
    },
    "sp3": {
        "name": "Roboneo tài khoản 220-240🥕",
        "price": 2500, "pd": "2k5", "stock": 0, "accounts": [],
        "msg": "🛒 <b>Xác nhận đơn hàng</b>\n\n📦 Sản phẩm: <b>{name}</b>\n💰 Giá: <b>{price}</b>/tài khoản\n📊 Còn lại: <b>{stock} tài khoản</b>\n\n✏️ Nhập số lượng cần mua (tối đa {stock}):"
    },
    "sp4": {
        "name": "Roboneo tài khoản 270-290🥕",
        "price": 3000, "pd": "3k", "stock": 0, "accounts": [],
        "msg": "🛒 <b>Xác nhận đơn hàng</b>\n\n📦 Sản phẩm: <b>{name}</b>\n💰 Giá: <b>{price}</b>/tài khoản\n📊 Còn lại: <b>{stock} tài khoản</b>\n\n✏️ Nhập số lượng cần mua (tối đa {stock}):"
    },
}

# ════════════════════════════════════════════════════
#               QUẢN LÝ DỮ LIỆU JSON
# ════════════════════════════════════════════════════
def load_products():
    if not os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_PRODUCTS, f, ensure_ascii=False, indent=2)
    with open(PRODUCTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_products(products):
    with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, ensure_ascii=False, indent=2)

def load_db():
    if not os.path.exists(DB_FILE):
        default = {"users": {}, "orders": [], "vouchers": {}}
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f, ensure_ascii=False, indent=2)
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_user(db, user_id):
    uid = str(user_id)
    if uid not in db["users"]:
        db["users"][uid] = {"balance": 0, "orders": [], "name": ""}
    return db["users"][uid]

# ════════════════════════════════════════════════════
#                   LOGGING
# ════════════════════════════════════════════════════
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════
#           PENDING ORDERS & TOPUPS (RAM)
# ════════════════════════════════════════════════════
PENDING_ORDERS = {}   # order_code -> order dict
PENDING_TOPUPS = {}   # order_code -> topup dict  ← MỚI
PAYMENT_TIMEOUT = 300  # 5 phút = 300 giây

# ════════════════════════════════════════════════════
#         HỦY ĐƠN SAU TIMEOUT + ĐỒNG HỒ ĐẾM NGƯỢC
# ════════════════════════════════════════════════════
async def cancel_order_after_timeout(pending_key: str, msg_id: int, chat_id: int):
    """Đếm ngược 5 phút cho đơn MUA HÀNG."""
    key = pending_key
    for remaining in [240, 180, 120, 60]:
        await asyncio.sleep(60)
        if key not in PENDING_ORDERS:
            return
        mins = remaining // 60
        try:
            order = PENDING_ORDERS[key]
            await telegram_app.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=msg_id,
                caption=(
                    f"🏦 Chuyển khoản tới <b>MB Bank - 2910036879</b>\n\n"
                    f"📌 Mã đơn hàng (ghi chú): <code>{order['order_code']}</code>\n"
                    f"💰 Số tiền: <b>{order['total']:,}đ</b>\n"
                    f"⏳ Thời gian còn lại: <b>{mins} phút</b>\n\n"
                    f"✅ Sau khi chuyển thành công, bot sẽ tự động xác nhận và gửi tài khoản."
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Thanh toán ngay", url=order.get("checkout_url","#"))],
                    [InlineKeyboardButton("❌ Hủy đơn", callback_data=f"cancel_{key}")]
                ])
            )
        except Exception:
            pass

    await asyncio.sleep(60)
    if key not in PENDING_ORDERS:
        return
    PENDING_ORDERS.pop(key, None)
    try:
        await telegram_app.bot.edit_message_caption(
            chat_id=chat_id, message_id=msg_id,
            caption="⌛ <b>Đơn hàng đã hết hạn!</b>\n\nVui lòng tạo đơn mới.",
            parse_mode="HTML"
        )
    except Exception:
        pass
    try:
        await telegram_app.bot.send_message(
            chat_id,
            "⌛ Đơn hàng của bạn đã hết hạn thanh toán (5 phút).\nNhấn 🛒 <b>Mua hàng</b> để tạo đơn mới.",
            parse_mode="HTML"
        )
    except Exception:
        pass


# ════════════════════════════════════════════════════
#   HỦY ĐƠN NẠP VI SAU TIMEOUT + ĐẾM NGƯỢC  ← MỚI
# ════════════════════════════════════════════════════
async def cancel_topup_after_timeout(pending_key: str, msg_id: int, chat_id: int):
    """Đếm ngược 5 phút cho đơn NẠP VÍ."""
    key = pending_key
    for remaining in [240, 180, 120, 60]:
        await asyncio.sleep(60)
        if key not in PENDING_TOPUPS:
            return
        mins = remaining // 60
        try:
            topup = PENDING_TOPUPS[key]
            await telegram_app.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=msg_id,
                caption=(
                    f"💰 <b>Nạp tiền vào ví</b>\n\n"
                    f"🏦 Chuyển khoản tới <b>MB Bank - 2910036879</b>\n"
                    f"📌 Nội dung chuyển khoản: <code>{topup['order_code']}</code>\n"
                    f"💵 Số tiền: <b>{topup['amount']:,}đ</b>\n"
                    f"⏳ Thời gian còn lại: <b>{mins} phút</b>\n\n"
                    f"✅ Bot sẽ tự động cộng tiền vào ví sau khi nhận được."
                ),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Thanh toán ngay", url=topup.get("checkout_url", "#"))],
                    [InlineKeyboardButton("❌ Hủy nạp tiền", callback_data=f"cancel_topup_{key}")]
                ])
            )
        except Exception:
            pass

    await asyncio.sleep(60)
    if key not in PENDING_TOPUPS:
        return
    PENDING_TOPUPS.pop(key, None)
    try:
        await telegram_app.bot.edit_message_caption(
            chat_id=chat_id, message_id=msg_id,
            caption="⌛ <b>Yêu cầu nạp tiền đã hết hạn!</b>\n\nVui lòng thử lại.",
            parse_mode="HTML"
        )
    except Exception:
        pass
    try:
        await telegram_app.bot.send_message(
            chat_id,
            "⌛ Yêu cầu nạp tiền của bạn đã hết hạn (5 phút).\nNhấn 👛 <b>Ví</b> → <b>💰 Nạp tiền</b> để thử lại.",
            parse_mode="HTML"
        )
    except Exception:
        pass

# ════════════════════════════════════════════════════
#                    FLASK
# ════════════════════════════════════════════════════
flask_app    = Flask(__name__)
telegram_app = None
bot_loop     = None

def verify_payos_signature(data: dict, signature: str) -> bool:
    sorted_data = "&".join(
        f"{k}={'' if data[k] is None else data[k]}"
        for k in sorted(data.keys()) if k != "signature"
    )
    expected = hmac.new(PAYOS_CHECKSUM.encode(), sorted_data.encode(), hashlib.sha256).hexdigest()
    logger.info(f"PayOS sig check | expected={expected} | got={signature}")
    if not signature:
        return True
    return hmac.compare_digest(expected, signature)

@flask_app.route("/payos-webhook", methods=["POST"])
def payos_webhook():
    try:
        body = request.get_json()
        logger.info(f"PayOS webhook nhận: {body}")
        if not body:
            return jsonify({"error": "no body"}), 400

        data      = body.get("data", {})
        signature = body.get("signature", "")

        if not verify_payos_signature(data, signature):
            logger.warning(f"Chữ ký PayOS không hợp lệ! data={data}")
            return jsonify({"error": "invalid signature"}), 400

        order_code = str(data.get("orderCode", ""))
        status     = data.get("status", "")
        code       = str(body.get("code", ""))

        logger.info(f"PayOS status={status} | code={code} | orderCode={order_code}")

        is_paid = (code == "00") or (status == "PAID")

        if is_paid:
            # ── Kiểm tra đơn MUA HÀNG ──────────────────
            order = PENDING_ORDERS.pop(order_code, None)
            if order:
                logger.info(f"✅ Đơn mua hàng {order_code} — đang giao hàng...")
                if bot_loop and not bot_loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        send_accounts_to_user(order), bot_loop
                    )
                else:
                    logger.error("❌ bot_loop chưa sẵn sàng!")
                return jsonify({"success": True}), 200

            # ── Kiểm tra đơn NẠP VÍ ────────────────────
            topup = PENDING_TOPUPS.pop(order_code, None)
            if topup:
                logger.info(f"✅ Đơn nạp ví {order_code} — đang cộng tiền...")
                if bot_loop and not bot_loop.is_closed():
                    asyncio.run_coroutine_threadsafe(
                        process_topup(topup), bot_loop
                    )
                else:
                    logger.error("❌ bot_loop chưa sẵn sàng!")
                return jsonify({"success": True}), 200

            logger.warning(f"⚠️ Không tìm thấy đơn {order_code} trong PENDING_ORDERS hoặc PENDING_TOPUPS!")

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Lỗi webhook: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

@flask_app.route("/payment-success", methods=["GET"])
def payment_success():
    return """<!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>Thanh toán thành công</title>
    <style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0d1117;color:#fff;}
    .box{text-align:center;padding:40px;background:#161b22;border-radius:12px;border:1px solid #2ecc8a33;}
    h1{color:#2ecc8a;font-size:2em;margin-bottom:10px;}p{color:#7a85a3;}</style></head>
    <body><div class="box"><h1>✅ Thanh toán thành công!</h1>
    <p>Bot đang xử lý và gửi tài khoản cho bạn.<br>Vui lòng quay lại Telegram.</p>
    <p style="margin-top:20px;font-size:12px;color:#3a4460">Bạn có thể đóng trang này.</p>
    </div></body></html>""", 200

@flask_app.route("/topup-success", methods=["GET"])
def topup_success():
    return """<!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>Nạp tiền thành công</title>
    <style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0d1117;color:#fff;}
    .box{text-align:center;padding:40px;background:#161b22;border-radius:12px;border:1px solid #2ecc8a33;}
    h1{color:#2ecc8a;font-size:2em;margin-bottom:10px;}p{color:#7a85a3;}</style></head>
    <body><div class="box"><h1>💰 Nạp tiền thành công!</h1>
    <p>Tiền đã được cộng vào ví của bạn.<br>Vui lòng quay lại Telegram để kiểm tra.</p>
    <p style="margin-top:20px;font-size:12px;color:#3a4460">Bạn có thể đóng trang này.</p>
    </div></body></html>""", 200

@flask_app.route("/payment-cancel", methods=["GET"])
def payment_cancel():
    return """<!DOCTYPE html><html><head><meta charset="UTF-8">
    <title>Đã hủy thanh toán</title>
    <style>body{font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#0d1117;color:#fff;}
    .box{text-align:center;padding:40px;background:#161b22;border-radius:12px;border:1px solid #e0556633;}
    h1{color:#e05566;font-size:2em;margin-bottom:10px;}p{color:#7a85a3;}</style></head>
    <body><div class="box"><h1>❌ Đã hủy thanh toán</h1>
    <p>Đơn hàng đã bị hủy.<br>Quay lại Telegram để thử lại.</p>
    <p style="margin-top:20px;font-size:12px;color:#3a4460">Bạn có thể đóng trang này.</p>
    </div></body></html>""", 200

@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ════════════════════════════════════════════════════
#                  PAYOS API
# ════════════════════════════════════════════════════
async def create_payment_link(order_code: int, amount: int, description: str,
                               buyer_name: str, return_url: str = None) -> dict:
    description = description[:25]
    ret_url = return_url or f"{SERVER_URL}/payment-success"
    cancel_url = f"{SERVER_URL}/payment-cancel"
    payload = {
        "orderCode":   order_code,
        "amount":      amount,
        "description": description,
        "buyerName":   buyer_name,
        "returnUrl":   ret_url,
        "cancelUrl":   cancel_url,
    }
    sign_str = (
        f"amount={amount}"
        f"&cancelUrl={cancel_url}"
        f"&description={description}"
        f"&orderCode={order_code}"
        f"&returnUrl={ret_url}"
    )
    payload["signature"] = hmac.new(
        PAYOS_CHECKSUM.encode(), sign_str.encode(), hashlib.sha256
    ).hexdigest()

    headers = {
        "x-client-id":  PAYOS_CLIENT_ID,
        "x-api-key":    PAYOS_API_KEY,
        "Content-Type": "application/json"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{PAYOS_API_URL}/v2/payment-requests",
            json=payload, headers=headers
        ) as resp:
            return await resp.json()

# ════════════════════════════════════════════════════
#              CẢNH BÁO KHO THẤP
# ════════════════════════════════════════════════════
async def check_low_stock(pid: str, product: dict):
    if product["stock"] < LOW_STOCK_THRESHOLD:
        emoji = "❌" if product["stock"] == 0 else "⚠️"
        await telegram_app.bot.send_message(
            ADMIN_ID,
            f"{emoji} <b>Cảnh báo kho thấp!</b>\n\n"
            f"📦 {product['name']}\n"
            f"📊 Còn lại: <b>{product['stock']} tài khoản</b>\n\n"
            f"Bổ sung bằng lệnh:\n"
            f"<code>/addacc {pid} user|pass user2|pass2 ...</code>\n"
            f"Hoặc gửi file .txt với caption: <code>{pid}</code>",
            parse_mode="HTML"
        )

# ════════════════════════════════════════════════════
#         XỬ LÝ NẠP VÍ SAU KHI THANH TOÁN  ← MỚI
# ════════════════════════════════════════════════════
async def process_topup(topup: dict):
    """Cộng tiền vào ví người dùng sau khi PayOS xác nhận."""
    try:
        chat_id = topup["chat_id"]
        user_id = topup["user_id"]
        amount  = topup["amount"]
        code    = topup["order_code"]

        db = load_db()
        u  = get_user(db, user_id)
        u["balance"] += amount
        save_db(db)

        logger.info(f"✅ Nạp ví {user_id} | +{amount:,}đ | mã {code}")

        await telegram_app.bot.send_message(
            chat_id,
            f"✅ <b>Nạp tiền thành công!</b>\n\n"
            f"🔖 Mã giao dịch: <code>{code}</code>\n"
            f"💰 Số tiền nạp: <b>+{amount:,}đ</b>\n"
            f"👛 Số dư ví hiện tại: <b>{u['balance']:,}đ</b>\n\n"
            f"Cảm ơn bạn đã nạp tiền! 🎉",
            parse_mode="HTML"
        )
        await telegram_app.bot.send_message(
            ADMIN_ID,
            f"💰 <b>Nạp ví thành công!</b>\n"
            f"👤 User ID: {user_id}\n"
            f"💵 Số tiền: {amount:,}đ\n"
            f"👛 Số dư mới: {u['balance']:,}đ\n"
            f"🔖 {code}",
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Lỗi xử lý nạp ví: {e}")

# ════════════════════════════════════════════════════
#              GỬI TÀI KHOẢN SAU KHI THANH TOÁN
# ════════════════════════════════════════════════════
async def send_accounts_to_user(order: dict):
    try:
        chat_id  = order["chat_id"]
        pid      = order["pid"]
        qty      = order["qty"]
        total    = order["total"]
        discount = order.get("discount", 0)
        method   = order.get("method", "payos")
        voucher  = order.get("voucher", "")

        products = load_products()
        product  = products.get(pid)
        if not product:
            return

        db = load_db()
        u  = get_user(db, order["user_id"])

        order_code = order.get("order_code", f"RBN{int(time.time())}")

        if len(product["accounts"]) >= qty:
            sent = product["accounts"][:qty]
            product["accounts"] = product["accounts"][qty:]
            product["stock"]    = len(product["accounts"])
            save_products(products)

            acc_text = "\n".join(f"<code>{a}</code>" for a in sent)
            discount_text = f"\n🏷️ Đã giảm: <b>{discount:,}đ</b>" if discount > 0 else ""

            record = {
                "code": order_code, "user_id": order["user_id"],
                "pid": pid, "product_name": product["name"],
                "qty": qty, "total": total, "discount": discount,
                "method": method, "status": "done",
                "time": datetime.now().strftime("%H:%M %d/%m/%Y")
            }
            db["orders"].append(record)
            u["orders"].append(order_code)

            if voucher and voucher.upper() in db["vouchers"]:
                v = db["vouchers"][voucher.upper()]
                if v["uses"] > 0:
                    v["uses"] -= 1
            save_db(db)

            await telegram_app.bot.send_message(
                chat_id,
                f"✅ <b>Thanh toán thành công!</b>\n\n"
                f"🔖 Mã đơn: <code>{order_code}</code>\n"
                f"📦 <b>{product['name']}</b> x{qty}\n"
                f"💰 Tổng: <b>{total:,}đ</b>{discount_text}\n\n"
                f"🔑 <b>Tài khoản của bạn:</b>\n{acc_text}\n\n"
                f"Cảm ơn bạn đã mua hàng! 🎉",
                parse_mode="HTML"
            )
            await telegram_app.bot.send_message(
                ADMIN_ID,
                f"✅ <b>Đơn hoàn tất!</b>\n"
                f"👤 {order['user_id']}\n"
                f"📦 {product['name']} x{qty}\n"
                f"💰 {total:,}đ\n🔖 {order_code}",
                parse_mode="HTML"
            )
            await check_low_stock(pid, product)

        else:
            await telegram_app.bot.send_message(
                chat_id,
                f"✅ <b>Thanh toán thành công!</b>\n\n"
                f"📦 {product['name']} x{qty}\n"
                f"🔔 Admin sẽ gửi tài khoản sớm nhất. Liên hệ: {SUPPORT}",
                parse_mode="HTML"
            )
            await telegram_app.bot.send_message(
                ADMIN_ID,
                f"⚠️ <b>Đơn cần xử lý thủ công!</b>\n"
                f"👤 User ID: {order['user_id']}\n"
                f"📦 {product['name']} x{qty}\n"
                f"💰 {total:,}đ\n❗ Kho không đủ!",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Lỗi gửi tài khoản: {e}")

# ════════════════════════════════════════════════════
#                   KEYBOARD
# ════════════════════════════════════════════════════
def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("🛒 Mua hàng")],
        [KeyboardButton("👤 Hồ sơ"), KeyboardButton("📋 Lịch sử mua")],
        [KeyboardButton("👛 Ví")],
        [KeyboardButton("💬 Hỗ trợ")],
    ], resize_keyboard=True)

# ════════════════════════════════════════════════════
#                    /start
# ════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db = load_db()
    u  = get_user(db, user.id)
    u["name"] = user.full_name
    save_db(db)

    await update.message.reply_text(
        f"🎉 Chào mừng <b>{user.first_name}</b> đến với cửa hàng!\n\n"
        "Hướng dẫn sử dụng Roboneo: https://docs.google.com/document/d/1tJ3buVmKXF2MobGoBdeE3n_HwfxyrwQg/edit?usp=drive_link&ouid=114797070754633372255&rtpof=true&sd=true\n"
        "📌 <b>Hướng dẫn:</b>\n"
        "1. Nhấn 🛒 <b>Mua hàng</b> → chọn sản phẩm\n"
        "2. Nhập số lượng cần mua\n"
        "3. Nhập mã giảm giá (nếu có)\n"
        "4. Chọn hình thức thanh toán:\n"
        "   • 💳 PayOS (tự động)\n"
        "   • 👛 Số dư ví\n"
        "5. Bot tự động gửi tài khoản sau khi thanh toán!\n\n"
        "🎯 Chọn menu bên dưới:",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard()
    )

# ════════════════════════════════════════════════════
#                 HIỆN SẢN PHẨM
# ════════════════════════════════════════════════════
async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = load_products()
    keyboard = []
    for pid, p in products.items():
        status = "✅" if p["stock"] > 0 else "❌"
        label  = f"{status} {p['name']} | {p['pd']} | 📦{p['stock']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"buy_{pid}")])

    target = update.message or update.callback_query.message
    await target.reply_text(
        "🛍️ <b>Danh sách sản phẩm:</b>\n<i>Chọn sản phẩm bạn muốn mua</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ════════════════════════════════════════════════════
#      XỬ LÝ NẠP TIỀN VÀO VÍ QUA PAYOS  ← MỚI
# ════════════════════════════════════════════════════
async def handle_topup_payos(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
    """Tạo link PayOS cho việc nạp ví."""
    user = update.effective_user

    order_code_int = int(time.time() * 1000) % 9999999
    order_code_str = f"NAP{user.id % 10000:04d}{order_code_int % 10000:04d}"
    pending_key    = str(order_code_int)

    PENDING_TOPUPS[pending_key] = {
        "order_code": order_code_str,
        "user_id":    user.id,
        "chat_id":    update.message.chat_id,
        "amount":     amount,
    }
    logger.info(f"Tạo đơn nạp ví | key={pending_key} | orderCode={order_code_int} | amount={amount}")

    processing_msg = await update.message.reply_text("⏳ Đang tạo link thanh toán...")

    try:
        result = await create_payment_link(
            order_code=order_code_int,
            amount=amount,
            description=f"Nap vi {user.id}",
            buyer_name=user.full_name,
            return_url=f"{SERVER_URL}/topup-success"
        )

        if result.get("code") == "00":
            payment_url = result["data"]["checkoutUrl"]
            PENDING_TOPUPS[pending_key]["checkout_url"] = payment_url

            caption = (
                f"💰 <b>Nạp tiền vào ví</b>\n\n"
                f"🏦 Chuyển khoản tới <b>MB Bank - 2910036879</b>\n"
                f"📌 Nội dung chuyển khoản: <code>{order_code_str}</code>\n"
                f"💵 Số tiền: <b>{amount:,}đ</b>\n"
                f"⏳ Thời gian còn lại: <b>5 phút</b>\n\n"
                f"✅ Bot sẽ tự động cộng tiền vào ví sau khi nhận được."
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 Thanh toán ngay", url=payment_url)],
                [InlineKeyboardButton("❌ Hủy nạp tiền", callback_data=f"cancel_topup_{pending_key}")]
            ])

            chat_id_now = update.message.chat_id

            try:
                await processing_msg.delete()
            except Exception:
                pass

            # QR VietQR
            vietqr_url = (
                f"https://img.vietqr.io/image/MB-2910036879-compact2.png"
                f"?amount={amount}"
                f"&addInfo={order_code_str}"
                f"&accountName=VO%20THANH%20DAT"
            )

            sent = None
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(vietqr_url) as resp:
                        if resp.status == 200:
                            img_bytes = await resp.read()
                            sent = await context.bot.send_photo(
                                chat_id=chat_id_now,
                                photo=io.BytesIO(img_bytes),
                                caption=caption,
                                parse_mode="HTML",
                                reply_markup=kb
                            )
            except Exception as qr_err:
                logger.warning(f"Lỗi tạo VietQR cho nạp ví: {qr_err}")

            if not sent:
                sent = await context.bot.send_message(
                    chat_id=chat_id_now,
                    text=caption,
                    parse_mode="HTML",
                    reply_markup=kb
                )

            PENDING_TOPUPS[pending_key]["msg_id"] = sent.message_id

            asyncio.create_task(cancel_topup_after_timeout(
                pending_key, sent.message_id, chat_id_now
            ))

        else:
            PENDING_TOPUPS.pop(pending_key, None)
            await processing_msg.edit_text(
                f"❌ Lỗi tạo thanh toán: {result.get('desc', 'Không xác định')}"
            )

    except Exception as e:
        PENDING_TOPUPS.pop(pending_key, None)
        logger.error(f"Lỗi tạo PayOS nạp ví: {e}")
        await processing_msg.edit_text("❌ Lỗi kết nối PayOS. Vui lòng thử lại!")

# ════════════════════════════════════════════════════
#                   CALLBACK
# ════════════════════════════════════════════════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data     = query.data
    products = load_products()

    # ── Nạp tiền ví — chọn mức nhanh ──────────────  ← MỚI
    if data == "topup_wallet":
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("5,000đ",  callback_data="topup_amount_5000"),
                InlineKeyboardButton("10,000đ", callback_data="topup_amount_10000"),
                InlineKeyboardButton("20,000đ", callback_data="topup_amount_20000"),
            ],
            [
                InlineKeyboardButton("50,000đ",  callback_data="topup_amount_50000"),
                InlineKeyboardButton("100,000đ", callback_data="topup_amount_100000"),
                InlineKeyboardButton("200,000đ", callback_data="topup_amount_200000"),
            ],
            [InlineKeyboardButton("✏️ Nhập số tiền khác", callback_data="topup_custom")],
            [InlineKeyboardButton("🔙 Quay lại", callback_data="back_wallet")],
        ])
        await query.edit_message_text(
            "💰 <b>Nạp tiền vào ví</b>\n\n"
            "Chọn mức nạp hoặc nhập số tiền tùy chỉnh:\n"
            f"<i>(Tối thiểu {MIN_TOPUP:,}đ)</i>",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    # ── Nạp tiền — chọn mức cố định ───────────────  ← MỚI
    if data.startswith("topup_amount_"):
        amount = int(data.replace("topup_amount_", ""))
        db     = load_db()
        u      = get_user(db, query.from_user.id)
        await query.edit_message_text(
            f"💰 <b>Xác nhận nạp tiền</b>\n\n"
            f"💵 Số tiền: <b>{amount:,}đ</b>\n"
            f"👛 Số dư hiện tại: <b>{u['balance']:,}đ</b>\n"
            f"📈 Số dư sau nạp: <b>{u['balance'] + amount:,}đ</b>\n\n"
            f"Xác nhận thanh toán qua PayOS?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Xác nhận", callback_data=f"topup_confirm_{amount}")],
                [InlineKeyboardButton("🔙 Chọn lại", callback_data="topup_wallet")],
            ])
        )
        return

    # ── Nạp tiền — nhập tùy chỉnh ─────────────────  ← MỚI
    if data == "topup_custom":
        context.user_data["wait_topup_amount"] = True
        await query.edit_message_text(
            f"✏️ <b>Nhập số tiền muốn nạp</b>\n\n"
            f"Tối thiểu: <b>{MIN_TOPUP:,}đ</b>\n\n"
            f"Nhập số tiền (chỉ nhập số, ví dụ: 30000):",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Quay lại", callback_data="topup_wallet")]
            ])
        )
        return

    # ── Nạp tiền — xác nhận ───────────────────────  ← MỚI
    if data.startswith("topup_confirm_"):
        amount = int(data.replace("topup_confirm_", ""))
        # Tạo một "fake" update.message-like để tái dùng handle_topup_payos
        context.user_data["topup_amount"] = amount
        await query.edit_message_text("⏳ Đang tạo link thanh toán...")

        # Tạo đơn PayOS trực tiếp ở đây (vì không có update.message)
        user           = query.from_user
        order_code_int = int(time.time() * 1000) % 9999999
        order_code_str = f"NAP{user.id % 10000:04d}{order_code_int % 10000:04d}"
        pending_key    = str(order_code_int)

        PENDING_TOPUPS[pending_key] = {
            "order_code": order_code_str,
            "user_id":    user.id,
            "chat_id":    query.message.chat_id,
            "amount":     amount,
        }

        try:
            result = await create_payment_link(
                order_code=order_code_int,
                amount=amount,
                description=f"Nap vi {user.id}",
                buyer_name=user.full_name,
                return_url=f"{SERVER_URL}/topup-success"
            )

            if result.get("code") == "00":
                payment_url = result["data"]["checkoutUrl"]
                PENDING_TOPUPS[pending_key]["checkout_url"] = payment_url

                caption = (
                    f"💰 <b>Nạp tiền vào ví</b>\n\n"
                    f"🏦 Chuyển khoản tới <b>MB Bank - 2910036879</b>\n"
                    f"📌 Nội dung chuyển khoản: <code>{order_code_str}</code>\n"
                    f"💵 Số tiền: <b>{amount:,}đ</b>\n"
                    f"⏳ Thời gian còn lại: <b>5 phút</b>\n\n"
                    f"✅ Bot sẽ tự động cộng tiền vào ví sau khi nhận được."
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Thanh toán ngay", url=payment_url)],
                    [InlineKeyboardButton("❌ Hủy nạp tiền", callback_data=f"cancel_topup_{pending_key}")]
                ])

                chat_id_now = query.message.chat_id
                try:
                    await query.delete_message()
                except Exception:
                    pass

                vietqr_url = (
                    f"https://img.vietqr.io/image/MB-2910036879-compact2.png"
                    f"?amount={amount}"
                    f"&addInfo={order_code_str}"
                    f"&accountName=VO%20THANH%20DAT"
                )

                sent = None
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(vietqr_url) as resp:
                            if resp.status == 200:
                                img_bytes = await resp.read()
                                sent = await telegram_app.bot.send_photo(
                                    chat_id=chat_id_now,
                                    photo=io.BytesIO(img_bytes),
                                    caption=caption,
                                    parse_mode="HTML",
                                    reply_markup=kb
                                )
                except Exception as qr_err:
                    logger.warning(f"Lỗi VietQR nạp ví: {qr_err}")

                if not sent:
                    sent = await telegram_app.bot.send_message(
                        chat_id=chat_id_now,
                        text=caption,
                        parse_mode="HTML",
                        reply_markup=kb
                    )

                PENDING_TOPUPS[pending_key]["msg_id"] = sent.message_id
                asyncio.create_task(cancel_topup_after_timeout(
                    pending_key, sent.message_id, chat_id_now
                ))

            else:
                PENDING_TOPUPS.pop(pending_key, None)
                await query.edit_message_text(
                    f"❌ Lỗi tạo thanh toán: {result.get('desc', 'Không xác định')}"
                )

        except Exception as e:
            PENDING_TOPUPS.pop(pending_key, None)
            logger.error(f"Lỗi PayOS nạp ví: {e}")
            await query.edit_message_text("❌ Lỗi kết nối PayOS. Vui lòng thử lại!")
        return

    # ── Hủy nạp tiền ──────────────────────────────  ← MỚI
    if data.startswith("cancel_topup_"):
        key = data[len("cancel_topup_"):]
        if key in PENDING_TOPUPS:
            PENDING_TOPUPS.pop(key)
            try:
                await query.edit_message_caption(
                    caption="❌ <b>Đã hủy nạp tiền.</b>\n\nNhấn 👛 Ví → 💰 Nạp tiền để thử lại.",
                    parse_mode="HTML"
                )
            except Exception:
                await query.edit_message_text(
                    "❌ <b>Đã hủy nạp tiền.</b>", parse_mode="HTML"
                )
        else:
            await query.answer("Giao dịch không tồn tại hoặc đã xử lý.", show_alert=True)
        return

    # ── Quay lại màn ví ───────────────────────────  ← MỚI
    if data == "back_wallet":
        db = load_db()
        u  = get_user(db, query.from_user.id)
        await query.edit_message_text(
            f"👛 <b>Ví của bạn</b>\n\n"
            f"💰 Số dư: <b>{u['balance']:,}đ</b>\n\n"
            f"Để nạp tiền, liên hệ admin: {SUPPORT}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Nạp tiền qua PayOS", callback_data="topup_wallet")]
            ])
        )
        return

    # ── Chọn sản phẩm ──────────────────────────────
    if data.startswith("buy_"):
        pid = data[4:]
        p   = products.get(pid)
        if not p:
            await query.edit_message_text("❌ Sản phẩm không tồn tại.")
            return
        if p["stock"] <= 0:
            await query.edit_message_text("😔 Sản phẩm này đã hết hàng!")
            return

        context.user_data["pid"]      = pid
        context.user_data["wait_qty"] = True

        msg = (p.get("msg") or "").replace("{name}", p["name"]).replace("{price}", p["pd"]).replace("{stock}", str(p["stock"]))
        kb  = [[InlineKeyboardButton("🔙 Quay lại", callback_data="back_products")]]
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    # ── Chọn hình thức thanh toán ───────────────────
    elif data.startswith("pay_"):
        parts  = data.split("_")
        method = parts[1]
        pid    = parts[2]
        qty    = int(parts[3])
        p      = products.get(pid)
        if not p:
            await query.edit_message_text("❌ Lỗi đơn hàng.")
            return

        total    = p["price"] * qty
        discount = 0
        voucher  = context.user_data.pop("voucher", "")

        if voucher:
            db = load_db()
            v  = db["vouchers"].get(voucher.upper())
            if v and v["uses"] > 0:
                discount = int(total * v["percent"] / 100)
                total   -= discount

        if method == "wallet":
            db = load_db()
            u  = get_user(db, query.from_user.id)
            if u["balance"] < total:
                await query.edit_message_text(
                    f"❌ <b>Số dư không đủ!</b>\n\n"
                    f"💰 Số dư ví: <b>{u['balance']:,}đ</b>\n"
                    f"💵 Cần thanh toán: <b>{total:,}đ</b>\n"
                    f"📉 Thiếu: <b>{total - u['balance']:,}đ</b>",
                    parse_mode="HTML",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 Thanh toán PayOS", callback_data=f"pay_payos_{pid}_{qty}")],
                        [InlineKeyboardButton("💰 Nạp tiền vào ví",  callback_data="topup_wallet")],
                        [InlineKeyboardButton("🔙 Quay lại",          callback_data="back_products")],
                    ])
                )
                return

            u["balance"] -= total
            save_db(db)

            order_code = f"RBN{query.from_user.id % 10000:04d}{len(db['orders'])+1:04d}"
            order = {
                "order_code": order_code,
                "user_id": query.from_user.id,
                "chat_id": query.message.chat_id,
                "pid": pid, "qty": qty,
                "total": total, "discount": discount,
                "method": "wallet", "voucher": voucher
            }
            await query.edit_message_text("⏳ Đang xử lý...")
            await send_accounts_to_user(order)

        elif method == "payos":
            order_code_int = int(time.time() * 1000) % 9999999
            order_code_str = f"RBN{query.from_user.id % 10000:04d}{order_code_int % 10000:04d}"
            pending_key    = str(order_code_int)

            PENDING_ORDERS[pending_key] = {
                "order_code": order_code_str,
                "user_id": query.from_user.id,
                "chat_id": query.message.chat_id,
                "pid": pid, "qty": qty,
                "total": total, "discount": discount,
                "method": "payos", "voucher": voucher
            }
            logger.info(f"Tạo đơn PayOS | key={pending_key} | orderCode={order_code_int} | amount={total}")

            await query.edit_message_text("⏳ Đang tạo link thanh toán...")
            try:
                result = await create_payment_link(
                    order_code=order_code_int,
                    amount=total,
                    description=f"{qty} RBN",
                    buyer_name=query.from_user.full_name
                )
                if result.get("code") == "00":
                    payment_url   = result["data"]["checkoutUrl"]
                    discount_text = f"\n🏷️ Giảm giá: <b>{discount:,}đ</b>" if discount > 0 else ""

                    PENDING_ORDERS[pending_key]["checkout_url"] = payment_url

                    caption = (
                        f"🏦 Chuyển khoản tới <b>MB Bank - 2910036879</b>\n\n"
                        f"📌 Mã đơn hàng (ghi chú): <code>{order_code_str}</code>\n"
                        f"💰 Vui lòng chuyển khoản <b>{total:,}đ MB bank</b>.{discount_text}\n"
                        f"⏳ Thời gian còn lại: <b>5 phút</b>\n\n"
                        f"✅ Sau khi chuyển thành công, bot sẽ tự động xác nhận và gửi tài khoản."
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("💳 Thanh toán ngay", url=payment_url)],
                        [InlineKeyboardButton("❌ Hủy đơn", callback_data=f"cancel_{pending_key}")]
                    ])

                    chat_id_now = query.message.chat_id
                    try:
                        await query.delete_message()
                    except Exception:
                        pass

                    vietqr_url = (
                        f"https://img.vietqr.io/image/MB-2910036879-compact2.png"
                        f"?amount={total}"
                        f"&addInfo={order_code_str}"
                        f"&accountName=VO%20THANH%20DAT"
                    )

                    sent = None
                    try:
                        async with aiohttp.ClientSession() as session:
                            async with session.get(vietqr_url) as resp:
                                if resp.status == 200:
                                    img_bytes = await resp.read()
                                    sent = await telegram_app.bot.send_photo(
                                        chat_id=chat_id_now,
                                        photo=io.BytesIO(img_bytes),
                                        caption=caption,
                                        parse_mode="HTML",
                                        reply_markup=kb
                                    )
                    except Exception as qr_err:
                        logger.warning(f"Lỗi tạo VietQR: {qr_err}")

                    if not sent:
                        sent = await telegram_app.bot.send_message(
                            chat_id=chat_id_now,
                            text=caption,
                            parse_mode="HTML",
                            reply_markup=kb
                        )

                    PENDING_ORDERS[pending_key]["msg_id"] = sent.message_id
                    asyncio.create_task(cancel_order_after_timeout(
                        pending_key, sent.message_id, chat_id_now
                    ))

                else:
                    PENDING_ORDERS.pop(pending_key, None)
                    await query.edit_message_text(
                        f"❌ Lỗi tạo thanh toán: {result.get('desc', 'Không xác định')}"
                    )
            except Exception as e:
                PENDING_ORDERS.pop(pending_key, None)
                logger.error(f"Lỗi PayOS: {e}")
                await query.edit_message_text("❌ Lỗi kết nối PayOS. Vui lòng thử lại!")

    # ── Hủy đơn mua hàng ────────────────────────────
    elif data.startswith("cancel_"):
        key = data[7:]
        if key in PENDING_ORDERS:
            PENDING_ORDERS.pop(key)
            try:
                await query.edit_message_caption(
                    caption="❌ <b>Đơn hàng đã bị hủy.</b>\n\nNhấn 🛒 Mua hàng để tạo đơn mới.",
                    parse_mode="HTML"
                )
            except Exception:
                await query.edit_message_text("❌ <b>Đơn hàng đã bị hủy.</b>", parse_mode="HTML")
        else:
            await query.answer("Đơn hàng không tồn tại hoặc đã được xử lý.", show_alert=True)

    # ── Quay lại danh sách sản phẩm ─────────────────
    elif data == "back_products":
        keyboard = []
        for pid, p in products.items():
            status = "✅" if p["stock"] > 0 else "❌"
            label  = f"{status} {p['name']} | {p['pd']} | 📦{p['stock']}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"buy_{pid}")])
        await query.edit_message_text(
            "🛍️ <b>Danh sách sản phẩm:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ════════════════════════════════════════════════════
#              XỬ LÝ TEXT (số lượng, voucher, menu)
# ════════════════════════════════════════════════════
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    user = update.effective_user

    # ── Menu buttons ────────────────────────────────
    if text == "🛒 Mua hàng":
        await show_products(update, context); return

    if text == "👤 Hồ sơ":
        db = load_db()
        u  = get_user(db, user.id)
        await update.message.reply_text(
            f"👤 <b>Hồ sơ của bạn</b>\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"👋 Tên: {user.full_name}\n"
            f"📛 Username: @{user.username or 'Chưa đặt'}\n"
            f"👛 Số dư ví: <b>{u['balance']:,}đ</b>\n"
            f"📋 Tổng đơn: <b>{len(u.get('orders', []))}</b>",
            parse_mode="HTML"
        ); return

    if text == "📋 Lịch sử mua":
        db = load_db()
        u  = get_user(db, user.id)
        codes = u.get("orders", [])
        if not codes:
            await update.message.reply_text("📋 Bạn chưa có đơn hàng nào.")
            return
        recent = [o for o in db["orders"] if o["code"] in codes][-5:]
        out = "📋 <b>Lịch sử mua hàng (5 đơn gần nhất):</b>\n\n"
        for o in reversed(recent):
            out += (
                f"🔖 <code>{o['code']}</code>\n"
                f"📦 {o['product_name']} x{o['qty']}\n"
                f"💵 {o['total']:,}đ — {o['time']}\n"
                f"{'─'*28}\n"
            )
        await update.message.reply_text(out, parse_mode="HTML"); return

    # ── Ví — có nút Nạp tiền ────────────────────────  ← CẬP NHẬT
    if text == "👛 Ví":
        db = load_db()
        u  = get_user(db, user.id)
        await update.message.reply_text(
            f"👛 <b>Ví của bạn</b>\n\n"
            f"💰 Số dư: <b>{u['balance']:,}đ</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Nạp tiền qua PayOS", callback_data="topup_wallet")]
            ])
        ); return

    if text == "💬 Hỗ trợ":
        await update.message.reply_text(
            f"💬 <b>Hỗ trợ khách hàng</b>\n\n"
            f"Liên hệ: {SUPPORT}\n"
            f"Thời gian: 8:00 – 22:00 hàng ngày.",
            parse_mode="HTML"
        ); return

    # ── Nhập số tiền nạp tùy chỉnh ─────────────────  ← MỚI
    if context.user_data.get("wait_topup_amount"):
        context.user_data["wait_topup_amount"] = False
        raw = text.replace(",", "").replace(".", "").strip()
        if not raw.isdigit():
            await update.message.reply_text(
                f"❌ Vui lòng nhập số hợp lệ (ví dụ: 50000)\nTối thiểu {MIN_TOPUP:,}đ"
            )
            return
        amount = int(raw)
        if amount < MIN_TOPUP:
            await update.message.reply_text(
                f"❌ Số tiền nạp tối thiểu là <b>{MIN_TOPUP:,}đ</b>",
                parse_mode="HTML"
            )
            return

        db = load_db()
        u  = get_user(db, user.id)
        await update.message.reply_text(
            f"💰 <b>Xác nhận nạp tiền</b>\n\n"
            f"💵 Số tiền: <b>{amount:,}đ</b>\n"
            f"👛 Số dư hiện tại: <b>{u['balance']:,}đ</b>\n"
            f"📈 Số dư sau nạp: <b>{u['balance'] + amount:,}đ</b>\n\n"
            f"Xác nhận thanh toán qua PayOS?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Xác nhận nạp tiền", callback_data=f"topup_confirm_{amount}")],
                [InlineKeyboardButton("🔙 Hủy", callback_data="topup_wallet")],
            ])
        )
        return

    # ── Nhập số lượng sản phẩm ──────────────────────
    if context.user_data.get("wait_qty"):
        pid = context.user_data.get("pid")
        products = load_products()
        p   = products.get(pid)
        if not p:
            context.user_data["wait_qty"] = False
            return

        if not text.isdigit():
            await update.message.reply_text(f"❌ Vui lòng nhập số hợp lệ (1 – {p['stock']})")
            return

        qty = int(text)
        if qty < 1 or qty > p["stock"]:
            await update.message.reply_text(f"❌ Số lượng phải từ 1 đến {p['stock']}")
            return

        context.user_data["wait_qty"] = False
        context.user_data["qty"]      = qty

        total = p["price"] * qty
        await ask_payment_method(update, pid, qty, total, 0, "")
        return

    await update.message.reply_text(
        "💡 Vui lòng sử dụng menu bên dưới.",
        reply_markup=main_menu_keyboard()
    )

# ════════════════════════════════════════════════════
#           HIỆN CHỌN HÌNH THỨC THANH TOÁN
# ════════════════════════════════════════════════════
async def ask_payment_method(update, pid, qty, total, discount, voucher):
    products = load_products()
    p = products.get(pid)
    discount_text = f"\n🏷️ Giảm giá: <b>-{discount:,}đ</b>" if discount > 0 else ""
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 Thanh toán (tự động)", callback_data=f"pay_payos_{pid}_{qty}")],
        [InlineKeyboardButton("👛 Dùng số dư ví",              callback_data=f"pay_wallet_{pid}_{qty}")],
        [InlineKeyboardButton("🔙 Quay lại",                   callback_data="back_products")],
    ])
    await update.message.reply_text(
        f"📋 <b>Xác nhận đơn hàng</b>\n\n"
        f"📦 {p['name']} x{qty}{discount_text}\n"
        f"💵 Tổng cộng: <b>{total:,}đ</b>\n\n"
        f"Chọn hình thức thanh toán:",
        parse_mode="HTML",
        reply_markup=kb
    )

# ════════════════════════════════════════════════════
#               LỆNH ADMIN
# ════════════════════════════════════════════════════

async def cmd_addacc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return
    if len(context.args) < 2:
        await update.message.reply_text(
            "📌 Cú pháp:\n"
            "/addacc <pid> <user|pass>                    — 1 acc\n"
            "/addacc <pid> <user|pass> <user|pass> ...   — nhiều acc\n\n"
            "Hoặc gửi file .txt (mỗi dòng 1 acc), caption = pid"
        ); return

    pid  = context.args[0]
    accs = context.args[1:]
    products = load_products()

    if pid not in products:
        await update.message.reply_text(
            f"❌ Không tìm thấy '{pid}'\nID hiện có: {', '.join(products.keys())}"
        ); return

    existing = set(products[pid]["accounts"])
    added, skipped = [], []
    for acc in accs:
        acc = acc.strip()
        if not acc: continue
        if acc in existing:
            skipped.append(acc)
        else:
            products[pid]["accounts"].append(acc)
            existing.add(acc)
            added.append(acc)

    products[pid]["stock"] = len(products[pid]["accounts"])
    save_products(products)

    text = (
        f"✅ <b>Đã thêm {len(added)} tài khoản</b> vào\n"
        f"📦 <b>{products[pid]['name']}</b>\n"
        f"📊 Kho hiện tại: <b>{products[pid]['stock']} tài khoản</b>"
    )
    if skipped:
        text += f"\n⚠️ Bỏ qua {len(skipped)} acc trùng"
    await update.message.reply_text(text, parse_mode="HTML")
    await check_low_stock(pid, products[pid])

async def cmd_addacc_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return

    doc = update.message.document
    pid = (update.message.caption or "").strip()

    if not doc.file_name.endswith(".txt"):
        await update.message.reply_text("❌ Chỉ hỗ trợ file .txt"); return
    if not pid:
        await update.message.reply_text(
            "❌ Chưa nhập ID sản phẩm!\nGửi file kèm caption là ID, ví dụ: sp1"
        ); return

    products = load_products()
    if pid not in products:
        await update.message.reply_text(
            f"❌ Không tìm thấy '{pid}'\nID hiện có: {', '.join(products.keys())}"
        ); return

    file      = await doc.get_file()
    raw       = await file.download_as_bytearray()
    content   = raw.decode("utf-8", errors="ignore")
    lines     = [l.strip() for l in content.splitlines() if l.strip()]

    if not lines:
        await update.message.reply_text("❌ File trống!"); return

    existing = set(products[pid]["accounts"])
    added, skipped = [], []
    for line in lines:
        if line in existing:
            skipped.append(line)
        else:
            products[pid]["accounts"].append(line)
            existing.add(line)
            added.append(line)

    products[pid]["stock"] = len(products[pid]["accounts"])
    save_products(products)

    await update.message.reply_text(
        f"✅ <b>Import file thành công!</b>\n\n"
        f"📦 <b>{products[pid]['name']}</b>\n"
        f"➕ Đã thêm: <b>{len(added)} tài khoản</b>\n"
        f"⚠️ Bỏ qua (trùng): <b>{len(skipped)}</b>\n"
        f"📊 Kho hiện tại: <b>{products[pid]['stock']} tài khoản</b>",
        parse_mode="HTML"
    )
    await check_low_stock(pid, products[pid])

async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    products = load_products()
    text = "📊 <b>Tình trạng kho:</b>\n\n"
    for pid, p in products.items():
        icon = "✅" if p["stock"] > LOW_STOCK_THRESHOLD else ("⚠️" if p["stock"] > 0 else "❌")
        text += f"{icon} [{pid}] {p['name']}\n   💰 {p['pd']} | 📦 {p['stock']} acc\n\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_napvi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return
    if len(context.args) < 2:
        await update.message.reply_text("Cú pháp: /napvi <user_id> <số tiền>"); return

    uid    = str(context.args[0])
    amount = int(context.args[1])
    db     = load_db()
    u      = get_user(db, uid)
    u["balance"] += amount
    save_db(db)

    await update.message.reply_text(
        f"✅ Đã nạp <b>{amount:,}đ</b> vào ví user {uid}\n"
        f"Số dư mới: <b>{u['balance']:,}đ</b>",
        parse_mode="HTML"
    )
    try:
        await telegram_app.bot.send_message(
            int(uid),
            f"💰 <b>Ví đã được nạp tiền!</b>\n\n"
            f"➕ <b>+{amount:,}đ</b>\n"
            f"💳 Số dư hiện tại: <b>{u['balance']:,}đ</b>",
            parse_mode="HTML"
        )
    except Exception:
        pass

async def cmd_addvoucher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return
    if len(context.args) < 3:
        await update.message.reply_text(
            "Cú pháp: /addvoucher <CODE> <%giảm> <số lần>\nVí dụ: /addvoucher SALE20 20 10"
        ); return

    code    = context.args[0].upper()
    percent = int(context.args[1])
    uses    = int(context.args[2])
    db      = load_db()
    db["vouchers"][code] = {"percent": percent, "uses": uses}
    save_db(db)
    await update.message.reply_text(
        f"✅ Tạo voucher <b>{code}</b>\n🏷️ Giảm {percent}% — {uses} lượt dùng",
        parse_mode="HTML"
    )

async def cmd_vouchers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    db = load_db()
    if not db["vouchers"]:
        await update.message.reply_text("Chưa có voucher nào."); return
    text = "🎟️ <b>Danh sách voucher:</b>\n\n"
    for code, v in db["vouchers"].items():
        status = "✅" if v["uses"] > 0 else "❌ Hết lượt"
        text  += f"{status} <code>{code}</code> — {v['percent']}% — còn {v['uses']} lượt\n"
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    db = load_db()
    recent = db["orders"][-10:]
    if not recent:
        await update.message.reply_text("Chưa có đơn hàng nào."); return
    text = "📋 <b>10 đơn gần nhất:</b>\n\n"
    for o in reversed(recent):
        text += (
            f"🔖 <code>{o['code']}</code>\n"
            f"📦 {o['product_name']} x{o['qty']} — {o['total']:,}đ\n"
            f"👤 {o['user_id']} — {o['time']}\n\n"
        )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    await update.message.reply_text(
        "🛠️ <b>Lệnh Admin:</b>\n\n"
        "/addacc &lt;pid&gt; &lt;user|pass&gt; [user|pass ...]  — Thêm 1 hoặc nhiều acc\n"
        "<i>Gửi file .txt + caption = pid</i>              — Import hàng loạt\n"
        "/stock                                         — Xem kho\n"
        "/orders                                        — 10 đơn gần nhất\n"
        "/napvi &lt;user_id&gt; &lt;tiền&gt;                    — Nạp ví thủ công\n"
        "/addvoucher &lt;CODE&gt; &lt;%&gt; &lt;lần&gt;              — Tạo voucher\n"
        "/vouchers                                      — Xem voucher",
        parse_mode="HTML"
    )

# ════════════════════════════════════════════════════
#                  FLASK THREAD
# ════════════════════════════════════════════════════
def run_flask():
    flask_app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

# ════════════════════════════════════════════════════
#                     MAIN
# ════════════════════════════════════════════════════
def main():
    global telegram_app, bot_loop

    telegram_app = Application.builder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start",       start))
    telegram_app.add_handler(CommandHandler("addacc",      cmd_addacc))
    telegram_app.add_handler(CommandHandler("stock",       cmd_stock))
    telegram_app.add_handler(CommandHandler("napvi",       cmd_napvi))
    telegram_app.add_handler(CommandHandler("addvoucher",  cmd_addvoucher))
    telegram_app.add_handler(CommandHandler("vouchers",    cmd_vouchers))
    telegram_app.add_handler(CommandHandler("orders",      cmd_orders))
    telegram_app.add_handler(CommandHandler("help",        cmd_help))

    telegram_app.add_handler(MessageHandler(filters.Document.TXT, cmd_addacc_file))
    telegram_app.add_handler(CallbackQueryHandler(callback_handler))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    bot_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(bot_loop)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask đang chạy trên port 8080")

    logger.info("✅ Roboneo Bot đang chạy...")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()