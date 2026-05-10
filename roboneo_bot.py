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
import secrets
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
BOT_TOKEN  = "8635281196:AAHnPRQfF7VKKaeMFg1yttU4E7nFotf5q-s"
ADMIN_ID   = 7131184806
SUPPORT    = "@min_gows"          # 👈 Thay username hỗ trợ

PAYOS_CLIENT_ID = "13f08821-7d23-45a0-9ab5-c02c59fb337c"
PAYOS_API_KEY   = "7682b6e5-d570-48da-8347-1e2175f8a8dd"
PAYOS_CHECKSUM  = "345a7f892bd9c7641a043d04442c81da2f37c789ddf4dc9cac43c8b462870037"
PAYOS_API_URL   = "https://api-merchant.payos.vn"
SERVER_URL      = "https://my-server-production-37d7.up.railway.app"

LOW_STOCK_THRESHOLD = 3   # Cảnh báo khi kho dưới X tài khoản
MIN_TOPUP = 2000          # Số tiền nạp tối thiểu (đồng)
MAX_PENDING_ORDERS = 1    # Số đơn mua hàng chờ thanh toán tối đa mỗi user
MAX_PENDING_TOPUPS = 1    # Số đơn nạp ví chờ thanh toán tối đa mỗi user

# ════════════════════════════════════════════════════
#                 FILE DỮ LIỆU
# ════════════════════════════════════════════════════
PRODUCTS_FILE = "products.json"
DB_FILE       = "data.json"

DEFAULT_PRODUCTS = {
    "sp1": {
        "name": "FOTOR AI 110+ Credits",
        "price": 4000, "pd": "4k", "stock": 0, "accounts": [],
        "sold": 0,          # ← MỚI: đếm số đã bán
        "note": "",         # ← MỚI: ghi chú sản phẩm
        "msg": "🛒 <b>Xác nhận đơn hàng</b>\n\n📦 Sản phẩm: <b>{name}</b>\n💰 Giá: <b>{price}</b>/tài khoản\n📊 Còn lại: <b>{stock} tài khoản</b>\n\n✏️ Nhập số lượng cần mua (tối đa {stock}):"
    },
    "sp2": {
        "name": "Fotor AI 150+ Credits",
        "price": 6500, "pd": "6k5", "stock": 0, "accounts": [],
        "sold": 0,
        "note": "",
        "msg": "🛒 <b>Xác nhận đơn hàng</b>\n\n📦 Sản phẩm: <b>{name}</b>\n💰 Giá: <b>{price}</b>/tài khoản\n📊 Còn lại: <b>{stock} tài khoản</b>\n\n✏️ Nhập số lượng cần mua (tối đa {stock}):"
    },
    "sp3": {
        "name": "Fotor AI 200+ Credits",
        "price": 8000, "pd": "8k", "stock": 0, "accounts": [],
        "sold": 0,
        "note": "",
        "msg": "🛒 <b>Xác nhận đơn hàng</b>\n\n📦 Sản phẩm: <b>{name}</b>\n💰 Giá: <b>{price}</b>/tài khoản\n📊 Còn lại: <b>{stock} tài khoản</b>\n\n✏️ Nhập số lượng cần mua (tối đa {stock}):"
    },
    "sp4": {
        "name": "Chatgpt Plus 1 Tháng (KBH)",
        "price": 29000, "pd": "29K", "stock": 0, "accounts": [],
        "sold": 0,
        "note": "",
        "msg": "🛒 <b>Xác nhận đơn hàng</b>\n\n📦 Sản phẩm: <b>{name}</b>\n💰 Giá: <b>{price}</b>/tài khoản\n📊 Còn lại: <b>{stock} tài khoản</b>\n\n✏️ Nhập số lượng cần mua (tối đa {stock}):"
    },
    "sp5": {
        "name": "Capcut Pro Team 35Day (BHF)",
        "price": 19000, "pd": "19K", "stock": 0, "accounts": [],
        "sold": 0,
        "note": "",
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
        data = json.load(f)
    # Migration: thêm field sold/note nếu sản phẩm cũ chưa có
    changed = False
    for pid, p in data.items():
        if "sold" not in p:
            p["sold"] = 0
            changed = True
        if "note" not in p:
            p["note"] = ""
            changed = True
    if changed:
        with open(PRODUCTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    return data

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

def next_product_id(products: dict) -> str:
    """Tự động tạo ID sản phẩm tiếp theo dạng sp1, sp2, ..."""
    existing_nums = []
    for pid in products:
        if pid.startswith("sp") and pid[2:].isdigit():
            existing_nums.append(int(pid[2:]))
    next_num = max(existing_nums, default=0) + 1
    return f"sp{next_num}"

def default_msg_template() -> str:
    return (
        "🛒 <b>Xác nhận đơn hàng</b>\n\n"
        "📦 Sản phẩm: <b>{name}</b>\n"
        "💰 Giá: <b>{price}</b>/tài khoản\n"
        "📊 Còn lại: <b>{stock} tài khoản</b>\n\n"
        "✏️ Nhập số lượng cần mua (tối đa {stock}):"
    )

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
PENDING_TOPUPS = {}   # order_code -> topup dict
PAYMENT_TIMEOUT = 300  # 5 phút = 300 giây

# Lock bảo vệ đọc/ghi kho — tránh race condition khi 2 khách mua cùng lúc
STOCK_LOCK = threading.Lock()

# ════════════════════════════════════════════════════
#          KIỂM TRA GIỚI HẠN PENDING MỖI USER
# ════════════════════════════════════════════════════
def get_user_pending_orders(user_id: int) -> list:
    return [
        (key, o) for key, o in PENDING_ORDERS.items()
        if o["user_id"] == user_id
    ]

def get_user_pending_topups(user_id: int) -> list:
    return [
        (key, t) for key, t in PENDING_TOPUPS.items()
        if t["user_id"] == user_id
    ]

def format_pending_orders_text(pending: list) -> str:
    lines_out = []
    for key, o in pending:
        lines_out.append(
            f"  • Mã <code>{o['order_code']}</code> — "
            f"<b>{o['total']:,}đ</b>"
        )
    return "\n".join(lines_out)

def format_pending_topups_text(pending: list) -> str:
    lines_out = []
    for key, t in pending:
        lines_out.append(
            f"  • Mã <code>{t['order_code']}</code> — "
            f"<b>{t['amount']:,}đ</b>"
        )
    return "\n".join(lines_out)


# ════════════════════════════════════════════════════
#         HỦY ĐƠN SAU TIMEOUT + ĐỒNG HỒ ĐẾM NGƯỢC
# ════════════════════════════════════════════════════
async def cancel_order_after_timeout(pending_key: str, msg_id: int, chat_id: int):
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
                    f"🏦 Vui lòng thanh toán ngay\n\n"
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


async def cancel_topup_after_timeout(pending_key: str, msg_id: int, chat_id: int):
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
        return False
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
#         XỬ LÝ NẠP VÍ SAU KHI THANH TOÁN
# ════════════════════════════════════════════════════
async def process_topup(topup: dict):
    try:
        chat_id = topup["chat_id"]
        user_id = topup["user_id"]
        amount  = topup["amount"]
        code    = topup["order_code"]

        with STOCK_LOCK:
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

        sent       = None
        product    = None
        order_code = order.get("order_code", f"RBN{int(time.time())}")
        acc_text   = ""
        discount_text = ""
        record     = None

        with STOCK_LOCK:
            products = load_products()
            product  = products.get(pid)
            if not product:
                return

            db = load_db()
            u  = get_user(db, order["user_id"])

            if len(product["accounts"]) >= qty:
                sent = product["accounts"][:qty]
                product["accounts"] = product["accounts"][qty:]
                product["stock"]    = len(product["accounts"])
                # ← MỚI: cộng số đã bán
                product["sold"]     = product.get("sold", 0) + qty
                save_products(products)

                acc_text      = "\n".join(f"<code>{a}</code>" for a in sent)
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

        if sent:
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
            if method == "wallet":
                with STOCK_LOCK:
                    db_refund = load_db()
                    u_refund  = get_user(db_refund, order["user_id"])
                    u_refund["balance"] += total
                    save_db(db_refund)
                logger.info(f"Hoàn tiền ví {order['user_id']} | +{total:,}đ | kho hết [{pid}]")
                await telegram_app.bot.send_message(
                    chat_id,
                    f"⚠️ <b>Thanh toán thành công nhưng kho vừa hết!</b>\n\n"
                    f"💰 <b>{total:,}đ</b> đã được hoàn lại vào ví của bạn.\n"
                    f"📦 {product['name']} x{qty}\n\n"
                    f"Vui lòng thử lại sau khi hàng được bổ sung. Liên hệ: {SUPPORT}",
                    parse_mode="HTML"
                )
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
                f"💰 {total:,}đ\n"
                f"💳 Phương thức: {method}\n"
                f"❗ Kho không đủ!{' (Đã hoàn tiền ví)' if method == 'wallet' else ''}",
                parse_mode="HTML"
            )

    except Exception as e:
        logger.error(f"Lỗi gửi tài khoản: {e}")

# ════════════════════════════════════════════════════
#                   KEYBOARD
# ════════════════════════════════════════════════════
def main_menu_keyboard():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📖 Hướng dẫn")],
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
        "📌 <b>Hướng dẫn:</b>\n"
        "1. Nhấn 🛒 <b>Mua hàng</b> → chọn sản phẩm\n"
        "2. Nhập số lượng cần mua\n"
        "3. Nhập mã giảm giá (nếu có)\n"
        "4. Chọn hình thức thanh toán:\n"
        "   • 💳 Thanh toán (tự động)\n"
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
#      XỬ LÝ NẠP TIỀN VÀO VÍ QUA PAYOS
# ════════════════════════════════════════════════════
async def handle_topup_payos(update: Update, context: ContextTypes.DEFAULT_TYPE, amount: int):
    user = update.effective_user

    order_code_int = int(time.time()) * 1000 + secrets.randbelow(1000)
    order_code_int = order_code_int % 999999999 + 1
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
            description=f"{user.id}",
            buyer_name=user.full_name,
            return_url=f"{SERVER_URL}/topup-success"
        )

        if result.get("code") == "00":
            payment_url = result["data"]["checkoutUrl"]
            PENDING_TOPUPS[pending_key]["checkout_url"] = payment_url

            caption = (
                f"💰 <b>Nạp tiền vào ví</b>\n\n"
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
        logger.error(f"Lỗi tạo QR nạp ví: {e}")
        await processing_msg.edit_text("❌ Lỗi kết nối PayOS. Vui lòng thử lại!")

# ════════════════════════════════════════════════════
#                   CALLBACK
# ════════════════════════════════════════════════════
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data     = query.data
    products = load_products()

    # ── Nạp tiền ví — chọn mức nhanh ──────────────
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

    # ── Nạp tiền — chọn mức cố định ───────────────
    if data.startswith("topup_amount_"):
        amount = int(data.replace("topup_amount_", ""))
        db     = load_db()
        u      = get_user(db, query.from_user.id)
        await query.edit_message_text(
            f"💰 <b>Xác nhận nạp tiền</b>\n\n"
            f"💵 Số tiền: <b>{amount:,}đ</b>\n"
            f"👛 Số dư hiện tại: <b>{u['balance']:,}đ</b>\n"
            f"📈 Số dư sau nạp: <b>{u['balance'] + amount:,}đ</b>\n\n"
            f"Xác nhận thanh toán",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Xác nhận", callback_data=f"topup_confirm_{amount}")],
                [InlineKeyboardButton("🔙 Chọn lại", callback_data="topup_wallet")],
            ])
        )
        return

    # ── Nạp tiền — nhập tùy chỉnh ─────────────────
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

    # ── Nạp tiền — xác nhận ───────────────────────
    if data.startswith("topup_confirm_"):
        amount = int(data.replace("topup_confirm_", ""))
        user_pending_topups = get_user_pending_topups(query.from_user.id)
        if len(user_pending_topups) >= MAX_PENDING_TOPUPS:
            pending_info = format_pending_topups_text(user_pending_topups)
            await query.edit_message_text(
                f"⚠️ <b>Bạn đang có {len(user_pending_topups)} yêu cầu nạp tiền chờ xử lý!</b>\n\n"
                f"{pending_info}\n\n"
                f"Vui lòng hoàn tất hoặc hủy yêu cầu cũ trước khi tạo mới.\n"
                f"Yêu cầu sẽ tự hủy sau <b>5 phút</b> nếu chưa thanh toán.",
                parse_mode="HTML"
            )
            return
        context.user_data["topup_amount"] = amount
        await query.edit_message_text("⏳ Đang tạo link thanh toán...")

        user           = query.from_user
        order_code_int = int(time.time()) * 1000 + secrets.randbelow(1000)
        order_code_int = order_code_int % 999999999 + 1
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
                description=f"{user.id}",
                buyer_name=user.full_name,
                return_url=f"{SERVER_URL}/topup-success"
            )

            if result.get("code") == "00":
                payment_url = result["data"]["checkoutUrl"]
                PENDING_TOPUPS[pending_key]["checkout_url"] = payment_url

                caption = (
                    f"💰 <b>Nạp tiền vào ví</b>\n\n"
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

    # ── Hủy nạp tiền ──────────────────────────────
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

    # ── Quay lại màn ví ───────────────────────────
    if data == "back_wallet":
        db = load_db()
        u  = get_user(db, query.from_user.id)
        await query.edit_message_text(
            f"👛 <b>Ví của bạn</b>\n\n"
            f"💰 Số dư: <b>{u['balance']:,}đ</b>\n\n"
            f"Để nạp tiền, liên hệ admin: {SUPPORT}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Nạp tiền ngay", callback_data="topup_wallet")]
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

        # ← MỚI: thêm ghi chú vào tin nhắn chọn sản phẩm nếu có
        note = p.get("note", "").strip()
        if note:
            msg += f"\n\n📝 <b>Ghi chú:</b>\n{note}"

        kb  = [[InlineKeyboardButton("🔙 Quay lại", callback_data="back_products")]]
        await query.edit_message_text(msg, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

    # ── Chọn hình thức thanh toán ───────────────────
    elif data.startswith("pay_"):
        parts  = data.split("_")
        method = parts[1]
        pid    = parts[2]
        qty_raw = int(parts[3])

        trusted_pid = context.user_data.get("pid")
        trusted_qty = context.user_data.get("qty")
        if trusted_pid != pid or trusted_qty != qty_raw:
            await query.edit_message_text("❌ Phiên mua hàng không hợp lệ. Vui lòng chọn lại sản phẩm.")
            context.user_data.clear()
            return

        qty = trusted_qty
        p   = products.get(pid)
        if not p:
            await query.edit_message_text("❌ Lỗi đơn hàng.")
            return

        if qty < 1 or qty > p["stock"]:
            await query.edit_message_text(
                f"❌ Số lượng không hợp lệ (kho còn {p['stock']}).\nVui lòng tạo đơn mới."
            )
            context.user_data.clear()
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
                        [InlineKeyboardButton("💳 Thanh toán ngay", callback_data=f"pay_payos_{pid}_{qty}")],
                        [InlineKeyboardButton("💰 Nạp tiền vào ví",  callback_data="topup_wallet")],
                        [InlineKeyboardButton("🔙 Quay lại",          callback_data="back_products")],
                    ])
                )
                return

            with STOCK_LOCK:
                db = load_db()
                u  = get_user(db, query.from_user.id)
                if u["balance"] < total:
                    await query.edit_message_text(
                        f"❌ <b>Số dư không đủ!</b>\n\n"
                        f"💰 Số dư ví: <b>{u['balance']:,}đ</b>\n"
                        f"💵 Cần thanh toán: <b>{total:,}đ</b>",
                        parse_mode="HTML"
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
            order_code_int = int(time.time()) * 1000 + secrets.randbelow(1000)
            order_code_int = order_code_int % 999999999 + 1
            user_pending_orders = get_user_pending_orders(query.from_user.id)
            if len(user_pending_orders) >= MAX_PENDING_ORDERS:
                pending_info = format_pending_orders_text(user_pending_orders)
                await query.edit_message_text(
                    f"⚠️ <b>Bạn đang có {len(user_pending_orders)} đơn chờ thanh toán!</b>\n\n"
                    f"{pending_info}\n\n"
                    f"Vui lòng hoàn tất hoặc hủy đơn cũ trước khi tạo đơn mới.\n"
                    f"Đơn sẽ tự hủy sau <b>5 phút</b> nếu chưa thanh toán.",
                    parse_mode="HTML"
                )
                return
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
                        f"💰 Vui lòng chuyển khoản thanh toán\n"
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

    if text == "👛 Ví":
        db = load_db()
        u  = get_user(db, user.id)
        await update.message.reply_text(
            f"👛 <b>Ví của bạn</b>\n\n"
            f"💰 Số dư: <b>{u['balance']:,}đ</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💰 Nạp tiền ngay", callback_data="topup_wallet")]
            ])
        ); return

    if text == "💬 Hỗ trợ":
        await update.message.reply_text(
            f"💬 <b>Hỗ trợ khách hàng</b>\n\n"
            f"Liên hệ: {SUPPORT}\n"
            f"Thời gian: 8:00 – 22:00 hàng ngày.",
            parse_mode="HTML"
        ); return

    if text == "📖 Hướng dẫn":
        await update.message.reply_text(
            f"📖 <b>Hướng dẫn sử dụng</b>\n\n"
            "- Hướng dẫn chi tiết: https://docs.google.com/document/d/1tJ3buVmKXF2MobGoBdeE3n_HwfxyrwQg/edit?usp=drive_link&ouid=114797070754633372255&rtpof=true&sd=true\n\n"
            "- Có thể tạo nhiều video cùng lúc.\n"
            "📌 <b>Các bước mua hàng:</b>\n"
            "1. Nhấn 🛒 <b>Mua hàng</b> → chọn sản phẩm\n"
            "2. Nhập số lượng cần mua\n"
            "3. Nhập mã giảm giá (nếu có)\n"
            "4. Chọn hình thức thanh toán:\n"
            "   • 💳 Thanh toán (tự động)\n"
            "   • 👛 Số dư ví\n"
            "5. Bot tự động gửi tài khoản sau khi thanh toán! 🎉",
            parse_mode="HTML"
        ); return

    # ── Nhập số tiền nạp tùy chỉnh ─────────────────
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
            f"Xác nhận thanh toán",
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

async def notify_buyers_on_restock(pid: str, product: dict, added_count: int):
    try:
        db = load_db()
        notified = set()
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 Mua ngay", callback_data=f"buy_{pid}")]
        ])
        for order in db.get("orders", []):
            if order.get("pid") != pid:
                continue
            uid = order.get("user_id")
            if uid and str(uid) not in notified:
                notified.add(str(uid))
                try:
                    await telegram_app.bot.send_message(
                        chat_id=int(uid),
                        text=(
                            f"🔔 <b>Hàng mới vừa về!</b>\n\n"
                            f"📦 <b>{product['name']}</b>\n"
                            f"➕ Thêm: <b>{added_count}</b>\n"
                            f"📦 Tồn kho hiện tại: <b>{product['stock']}</b>"
                        ),
                        parse_mode="HTML",
                        reply_markup=kb
                    )
                except Exception:
                    pass
        logger.info(f"Đã thông báo restock [{pid}] đến {len(notified)} user.")
    except Exception as e:
        logger.error(f"Lỗi notify_buyers_on_restock: {e}")

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return
    if not context.args:
        await update.message.reply_text(
            "Cú pháp: /thongbao &lt;nội dung&gt;\nVí dụ: /thongbao 🎉 Shop có khuyến mãi hôm nay!",
            parse_mode="HTML"
        ); return

    msg = " ".join(context.args)
    db  = load_db()
    all_users = list(db.get("users", {}).keys())

    if not all_users:
        await update.message.reply_text("⚠️ Chưa có user nào trong hệ thống."); return

    await update.message.reply_text(f"📤 Đang gửi đến {len(all_users)} user...")

    success, failed = 0, 0
    for uid in all_users:
        try:
            await telegram_app.bot.send_message(
                chat_id=int(uid),
                text=f"📢 <b>Thông báo từ cửa hàng</b>\n\n{msg}",
                parse_mode="HTML"
            )
            success += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"✅ Broadcast hoàn tất!\n"
        f"📨 Thành công: <b>{success}</b>\n"
        f"❌ Thất bại: <b>{failed}</b>",
        parse_mode="HTML"
    )

# ════════════════════════════════════════════════════
#  ← MỚI: /addsp — Thêm sản phẩm mới
#  Cú pháp: /addsp <Tên Sản Phẩm> | <Giá> | <Giá hiển thị>
#  Ví dụ:   /addsp Capcut Pro 35D | 10000 | 10K
# ════════════════════════════════════════════════════
async def cmd_addsp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return

    raw = " ".join(context.args).strip()
    if not raw or "|" not in raw:
        await update.message.reply_text(
            "📌 <b>Cú pháp:</b>\n"
            "<code>/addsp Tên Sản Phẩm | Giá | Giá hiển thị</code>\n\n"
            "Ví dụ:\n"
            "<code>/addsp Capcut Pro Team 35D | 10000 | 10K</code>\n\n"
            "• <b>Giá</b>: số nguyên (đơn vị đồng)\n"
            "• <b>Giá hiển thị</b>: văn bản tùy ý (vd: 10K, 29.000đ)\n"
            "• ID sản phẩm sẽ được tự động tạo (sp6, sp7, ...)",
            parse_mode="HTML"
        ); return

    parts = [p.strip() for p in raw.split("|")]
    if len(parts) < 3:
        await update.message.reply_text(
            "❌ Thiếu thông tin! Cần đủ 3 phần cách nhau bởi <code>|</code>\n"
            "Ví dụ: <code>/addsp Capcut Pro | 10000 | 10K</code>",
            parse_mode="HTML"
        ); return

    name   = parts[0].strip()
    pd_str = parts[2].strip()

    if not parts[1].strip().isdigit():
        await update.message.reply_text(
            f"❌ Giá phải là số nguyên, nhận được: <code>{parts[1]}</code>",
            parse_mode="HTML"
        ); return

    price = int(parts[1].strip())

    if not name:
        await update.message.reply_text("❌ Tên sản phẩm không được để trống!"); return
    if price <= 0:
        await update.message.reply_text("❌ Giá phải lớn hơn 0!"); return

    products = load_products()
    new_pid  = next_product_id(products)

    products[new_pid] = {
        "name":     name,
        "price":    price,
        "pd":       pd_str,
        "stock":    0,
        "accounts": [],
        "sold":     0,
        "note":     "",
        "msg":      default_msg_template()
    }
    save_products(products)

    await update.message.reply_text(
        f"✅ <b>Đã thêm sản phẩm mới!</b>\n\n"
        f"🆔 ID: <code>{new_pid}</code>\n"
        f"📦 Tên: <b>{name}</b>\n"
        f"💰 Giá: <b>{price:,}đ</b> ({pd_str})\n"
        f"📊 Kho: <b>0 tài khoản</b>\n\n"
        f"Thêm tài khoản vào kho:\n"
        f"<code>/addacc {new_pid} user|pass</code>",
        parse_mode="HTML"
    )

# ════════════════════════════════════════════════════
#  ← MỚI: /xoasp — Xóa sản phẩm
#  Cú pháp: /xoasp <pid>
# ════════════════════════════════════════════════════
async def cmd_xoasp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return

    if not context.args:
        products = load_products()
        lines = ["🗑️ <b>Xóa sản phẩm</b>\n\nCú pháp: <code>/xoasp &lt;pid&gt;</code>\n"]
        for pid, p in products.items():
            lines.append(f"• <code>/xoasp {pid}</code> — {p['name']} (kho: {p['stock']})")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    pid = context.args[0].lower().strip()
    products = load_products()

    if pid not in products:
        await update.message.reply_text(
            f"❌ Không tìm thấy sản phẩm <code>{pid}</code>\n"
            f"ID hiện có: {', '.join(f'<code>{k}</code>' for k in products.keys())}",
            parse_mode="HTML"
        ); return

    p = products[pid]
    # Xác nhận nếu còn hàng trong kho
    if p["stock"] > 0:
        context.user_data[f"confirm_delete_{pid}"] = True
        await update.message.reply_text(
            f"⚠️ <b>Xác nhận xóa sản phẩm?</b>\n\n"
            f"📦 <b>{p['name']}</b>\n"
            f"📊 Còn lại <b>{p['stock']} tài khoản</b> trong kho!\n\n"
            f"Nhập lại lệnh để xác nhận:\n"
            f"<code>/xoasp {pid} confirm</code>",
            parse_mode="HTML"
        ); return

    # Nếu arg thứ 2 là "confirm" hoặc kho trống → xóa luôn
    if len(context.args) >= 2 and context.args[1].lower() == "confirm" or p["stock"] == 0:
        name = p["name"]
        del products[pid]
        save_products(products)
        await update.message.reply_text(
            f"🗑️ <b>Đã xóa sản phẩm!</b>\n\n"
            f"🆔 ID: <code>{pid}</code>\n"
            f"📦 Tên: {name}",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"⚠️ Sản phẩm còn hàng. Thêm <code>confirm</code> để xóa:\n"
            f"<code>/xoasp {pid} confirm</code>",
            parse_mode="HTML"
        )

# ════════════════════════════════════════════════════
#  ← MỚI: /ghichu — Thêm/xem/xóa ghi chú sản phẩm
#  Cú pháp: /ghichu <pid> <nội dung ghi chú>
#           /ghichu <pid>          → xem ghi chú hiện tại
#           /ghichu <pid> xoa      → xóa ghi chú
# ════════════════════════════════════════════════════
async def cmd_ghichu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return

    products = load_products()

    if not context.args:
        lines = ["📝 <b>Ghi chú sản phẩm</b>\n\n"]
        lines.append("<b>Cú pháp:</b>")
        lines.append("• Xem ghi chú: <code>/ghichu &lt;pid&gt;</code>")
        lines.append("• Đặt ghi chú: <code>/ghichu &lt;pid&gt; &lt;nội dung&gt;</code>")
        lines.append("• Xóa ghi chú: <code>/ghichu &lt;pid&gt; xoa</code>\n")
        lines.append("<b>Sản phẩm hiện có:</b>")
        for pid, p in products.items():
            note_preview = f"✏️ {p.get('note','')[:30]}..." if p.get("note") else "_(trống)_"
            lines.append(f"• <code>{pid}</code> — {p['name']}\n  {note_preview}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    pid = context.args[0].lower().strip()
    if pid not in products:
        await update.message.reply_text(
            f"❌ Không tìm thấy sản phẩm <code>{pid}</code>\n"
            f"ID hiện có: {', '.join(f'<code>{k}</code>' for k in products.keys())}",
            parse_mode="HTML"
        ); return

    p = products[pid]

    # Chỉ xem ghi chú
    if len(context.args) == 1:
        note = p.get("note", "").strip()
        if note:
            await update.message.reply_text(
                f"📝 <b>Ghi chú [{pid}] {p['name']}:</b>\n\n{note}",
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f"📝 <b>[{pid}] {p['name']}</b> chưa có ghi chú.\n\n"
                f"Đặt ghi chú: <code>/ghichu {pid} Nội dung ghi chú</code>",
                parse_mode="HTML"
            )
        return

    # Xóa ghi chú
    remaining = " ".join(context.args[1:]).strip()
    if remaining.lower() in ("xoa", "xóa", "delete", "clear"):
        p["note"] = ""
        save_products(products)
        await update.message.reply_text(
            f"🗑️ <b>Đã xóa ghi chú</b> của [{pid}] {p['name']}",
            parse_mode="HTML"
        ); return

    # Đặt ghi chú mới
    p["note"] = remaining
    save_products(products)
    await update.message.reply_text(
        f"✅ <b>Đã cập nhật ghi chú!</b>\n\n"
        f"📦 [{pid}] <b>{p['name']}</b>\n\n"
        f"📝 <b>Ghi chú:</b>\n{remaining}",
        parse_mode="HTML"
    )

# ════════════════════════════════════════════════════
#  ← MỚI: /suasp — Sửa tên/giá/giá hiển thị sản phẩm
#  Cú pháp: /suasp <pid> ten <tên mới>
#           /suasp <pid> gia <giá mới>
#           /suasp <pid> hienthi <giá hiển thị mới>
# ════════════════════════════════════════════════════
async def cmd_suasp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return

    if len(context.args) < 3:
        await update.message.reply_text(
            "📌 <b>Cú pháp sửa sản phẩm:</b>\n\n"
            "• Sửa tên: <code>/suasp &lt;pid&gt; ten &lt;tên mới&gt;</code>\n"
            "• Sửa giá: <code>/suasp &lt;pid&gt; gia &lt;giá mới&gt;</code>\n"
            "• Sửa hiển thị: <code>/suasp &lt;pid&gt; hienthi &lt;giá hiển thị&gt;</code>\n\n"
            "Ví dụ:\n"
            "<code>/suasp sp1 ten Fotor AI Pro 200 Credits</code>\n"
            "<code>/suasp sp1 gia 8000</code>\n"
            "<code>/suasp sp1 hienthi 8K</code>",
            parse_mode="HTML"
        ); return

    pid   = context.args[0].lower().strip()
    field = context.args[1].lower().strip()
    value = " ".join(context.args[2:]).strip()

    products = load_products()
    if pid not in products:
        await update.message.reply_text(
            f"❌ Không tìm thấy <code>{pid}</code>",
            parse_mode="HTML"
        ); return

    p = products[pid]

    if field in ("ten", "tên", "name"):
        old = p["name"]
        p["name"] = value
        save_products(products)
        await update.message.reply_text(
            f"✅ Đã đổi tên sản phẩm <code>{pid}</code>\n"
            f"• Cũ: {old}\n• Mới: <b>{value}</b>",
            parse_mode="HTML"
        )
    elif field in ("gia", "giá", "price"):
        if not value.isdigit():
            await update.message.reply_text("❌ Giá phải là số nguyên!"); return
        old = p["price"]
        p["price"] = int(value)
        save_products(products)
        await update.message.reply_text(
            f"✅ Đã đổi giá sản phẩm <code>{pid}</code>\n"
            f"• Cũ: {old:,}đ\n• Mới: <b>{int(value):,}đ</b>",
            parse_mode="HTML"
        )
    elif field in ("hienthi", "hiển thị", "pd", "display"):
        old = p["pd"]
        p["pd"] = value
        save_products(products)
        await update.message.reply_text(
            f"✅ Đã đổi giá hiển thị sản phẩm <code>{pid}</code>\n"
            f"• Cũ: {old}\n• Mới: <b>{value}</b>",
            parse_mode="HTML"
        )
    else:
        await update.message.reply_text(
            f"❌ Trường không hợp lệ: <code>{field}</code>\n"
            f"Dùng: <code>ten</code> | <code>gia</code> | <code>hienthi</code>",
            parse_mode="HTML"
        )

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
    if added:
        await notify_buyers_on_restock(pid, products[pid], len(added))

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
    if added:
        await notify_buyers_on_restock(pid, products[pid], len(added))

async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    products = load_products()
    text = "📊 <b>Tình trạng kho:</b>\n\n"
    for pid, p in products.items():
        icon = "✅" if p["stock"] > LOW_STOCK_THRESHOLD else ("⚠️" if p["stock"] > 0 else "❌")
        # ← MỚI: hiện thêm cột đã bán
        sold = p.get("sold", 0)
        text += (
            f"{icon} [{pid}] {p['name']}\n"
            f"   💰 {p['pd']} | 📦 {p['stock']} acc | 🛒 Đã bán: {sold}\n\n"
        )
    await update.message.reply_text(text, parse_mode="HTML")

async def cmd_viewacc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return

    products = load_products()

    if not context.args:
        lines = ["🔑 <b>Xem tài khoản trong kho</b>\n\nCú pháp: <code>/viewacc &lt;pid&gt;</code>\n"]
        for pid, p in products.items():
            icon = "✅" if p["stock"] > LOW_STOCK_THRESHOLD else ("⚠️" if p["stock"] > 0 else "❌")
            lines.append(f"{icon} <code>/viewacc {pid}</code> — {p['name']} ({p['stock']} acc)")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    pid = context.args[0].lower()
    if pid not in products:
        await update.message.reply_text(
            f"❌ Không tìm thấy <b>{pid}</b>\nID hiện có: {', '.join(products.keys())}",
            parse_mode="HTML"
        )
        return

    p = products[pid]
    accounts = p["accounts"]

    if not accounts:
        await update.message.reply_text(
            f"❌ <b>[{pid}] {p['name']}</b>\n\nKho trống, chưa có tài khoản nào.",
            parse_mode="HTML"
        )
        return

    CHUNK = 50
    total = len(accounts)
    chunks = [accounts[i:i+CHUNK] for i in range(0, total, CHUNK)]

    sent_msgs = []
    for idx, chunk in enumerate(chunks):
        header = (
            f"🔑 <b>[{pid}] {p['name']}</b>\n"
            f"📦 Còn <b>{total}</b> tài khoản"
            + (f" — Trang {idx+1}/{len(chunks)}" if len(chunks) > 1 else "")
            + "\n⚠️ <i>Tin nhắn tự xóa sau 60 giây</i>\n\n"
        )
        acc_lines = "\n".join(
            f"{i+1+idx*CHUNK}. <code>{acc}</code>"
            for i, acc in enumerate(chunk)
        )
        msg = await update.message.reply_text(
            header + acc_lines,
            parse_mode="HTML"
        )
        sent_msgs.append(msg)

    try:
        await update.message.delete()
    except Exception:
        pass

    async def delete_after_delay():
        await asyncio.sleep(60)
        for m in sent_msgs:
            try:
                await m.delete()
            except Exception:
                pass

    asyncio.create_task(delete_after_delay())


async def cmd_napvi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!"); return
    if len(context.args) < 2:
        await update.message.reply_text("Cú pháp: /napvi <user_id> <số tiền>"); return

    uid    = str(context.args[0])
    amount = int(context.args[1])

    with STOCK_LOCK:
        db = load_db()
        u  = get_user(db, uid)
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
        "<b>─── Quản lý sản phẩm ───</b>\n"
        "/addsp &lt;Tên&gt; | &lt;Giá&gt; | &lt;Hiển thị&gt;          — Thêm sản phẩm mới\n"
        "/suasp &lt;pid&gt; ten/gia/hienthi &lt;giá trị&gt;    — Sửa sản phẩm\n"
        "/xoasp &lt;pid&gt;                             — Xóa sản phẩm\n"
        "/ghichu &lt;pid&gt; &lt;nội dung&gt;                — Đặt ghi chú sản phẩm\n"
        "/ghichu &lt;pid&gt;                             — Xem ghi chú\n"
        "/ghichu &lt;pid&gt; xoa                        — Xóa ghi chú\n\n"
        "<b>─── Quản lý kho ───</b>\n"
        "/addacc &lt;pid&gt; &lt;user|pass&gt; [...]          — Thêm acc\n"
        "<i>Gửi file .txt + caption = pid</i>           — Import hàng loạt\n"
        "/stock                                     — Xem kho + đã bán\n"
        "/viewacc &lt;pid&gt;                            — Xem chi tiết acc (tự xóa 60s)\n\n"
        "<b>─── Đơn hàng & Tài chính ───</b>\n"
        "/orders                                    — 10 đơn gần nhất\n"
        "/napvi &lt;user_id&gt; &lt;tiền&gt;                  — Nạp ví thủ công\n"
        "/addvoucher &lt;CODE&gt; &lt;%&gt; &lt;lần&gt;            — Tạo voucher\n"
        "/vouchers                                  — Xem voucher\n\n"
        "<b>─── Broadcast ───</b>\n"
        "/broadcast &lt;nội dung&gt;                   — Gửi thông báo tất cả user\n"
        "/thongbao &lt;nội dung&gt;                     — (tương tự /broadcast)",
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
async def cmd_myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"🪪 <b>Thông tin tài khoản của bạn:</b>\n\n"
        f"👤 Tên: <b>{user.full_name}</b>\n"
        f"🆔 User ID: <code>{user.id}</code>\n\n"
        f"<i>Gửi ID này cho admin khi cần hỗ trợ.</i>",
        parse_mode="HTML"
    )

def main():
    global telegram_app, bot_loop

    telegram_app = Application.builder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start",       start))
    telegram_app.add_handler(CommandHandler("myid",        cmd_myid))
    telegram_app.add_handler(CommandHandler("addacc",      cmd_addacc))
    telegram_app.add_handler(CommandHandler("stock",       cmd_stock))
    telegram_app.add_handler(CommandHandler("viewacc",     cmd_viewacc))
    telegram_app.add_handler(CommandHandler("napvi",       cmd_napvi))
    telegram_app.add_handler(CommandHandler("addvoucher",  cmd_addvoucher))
    telegram_app.add_handler(CommandHandler("vouchers",    cmd_vouchers))
    telegram_app.add_handler(CommandHandler("orders",      cmd_orders))
    telegram_app.add_handler(CommandHandler("help",        cmd_help))
    telegram_app.add_handler(CommandHandler("broadcast",   cmd_broadcast))
    telegram_app.add_handler(CommandHandler("thongbao",    cmd_broadcast))

    # ← MỚI: đăng ký lệnh admin mới
    telegram_app.add_handler(CommandHandler("addsp",       cmd_addsp))
    telegram_app.add_handler(CommandHandler("xoasp",       cmd_xoasp))
    telegram_app.add_handler(CommandHandler("ghichu",      cmd_ghichu))
    telegram_app.add_handler(CommandHandler("suasp",       cmd_suasp))

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