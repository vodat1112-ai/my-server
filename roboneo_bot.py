"""
Bot Telegram bán tài khoản Roboneo - Tích hợp PayOS
pip install python-telegram-bot==20.7 aiohttp flask
"""

import logging
import json
import hashlib
import hmac
import asyncio
import threading
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)
import aiohttp

# ==================== CẤU HÌNH ====================
BOT_TOKEN   = "8620998717:AAE7P-MimVeUMB1lG29T10MXe7gGqQtzOw8"
ADMIN_ID    = 7131184806

PAYOS_CLIENT_ID  = "13f08821-7d23-45a0-9ab5-c02c59fb337c"
PAYOS_API_KEY    = "7682b6e5-d570-48da-8347-1e2175f8a8dd"
PAYOS_CHECKSUM   = "345a7f892bd9c7641a043d04442c81da2f37c789ddf4dc9cac43c8b462870037"
PAYOS_API_URL    = "https://api-merchant.payos.vn"

# URL Railway của bạn (cập nhật sau khi deploy)
SERVER_URL = "https://my-server-production-37d7.up.railway.app"

# ==================== DỮ LIỆU SẢN PHẨM ====================
# Admin cập nhật kho bằng lệnh /addacc hoặc trang HTML
PRODUCTS = {
    "sp1": {
        "name": "Roboneo tài khoản 120-140🥕",
        "price": 90000,
        "pd": "90k",
        "stock": 0,
        "accounts": []
    },
    "sp2": {
        "name": "Roboneo tài khoản 170-190🥕",
        "price": 150000,
        "pd": "150k",
        "stock": 0,
        "accounts": []
    },
    "sp3": {
        "name": "Roboneo tài khoản 220-240🥕",
        "price": 300000,
        "pd": "300k",
        "stock": 0,
        "accounts": []
    },
}

# Lưu đơn hàng đang chờ thanh toán: {order_code: {user_id, pid, qty, chat_id}}
PENDING_ORDERS = {}

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== FLASK WEBHOOK SERVER ====================
flask_app = Flask(__name__)
telegram_app = None  # sẽ được gán sau

def verify_payos_signature(data: dict, signature: str) -> bool:
    """Xác thực chữ ký PayOS"""
    sorted_data = "&".join(f"{k}={v}" for k, v in sorted(data.items()) if k != "signature")
    expected = hmac.new(
        PAYOS_CHECKSUM.encode(),
        sorted_data.encode(),
        hashlib.sha256
    ).hexdigest()
    return expected == signature

@flask_app.route("/payos-webhook", methods=["POST"])
def payos_webhook():
    try:
        body = request.get_json()
        logger.info(f"PayOS webhook: {body}")

        if not body:
            return jsonify({"error": "no body"}), 400

        data = body.get("data", {})
        signature = body.get("signature", "")

        # Xác thực chữ ký
        if not verify_payos_signature(data, signature):
            logger.warning("Chữ ký PayOS không hợp lệ!")
            return jsonify({"error": "invalid signature"}), 400

        order_code = str(data.get("orderCode", ""))
        status = data.get("status", "")

        if status == "PAID" and order_code in PENDING_ORDERS:
            order = PENDING_ORDERS.pop(order_code)
            # Gửi tài khoản cho khách qua asyncio
            asyncio.run_coroutine_threadsafe(
                send_accounts_to_user(order),
                telegram_app.bot._application.loop if hasattr(telegram_app, '_application') else asyncio.get_event_loop()
            )

        return jsonify({"success": True}), 200

    except Exception as e:
        logger.error(f"Lỗi webhook: {e}")
        return jsonify({"error": str(e)}), 500

@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

# ==================== PAYOS API ====================
async def create_payment_link(order_code: int, amount: int, description: str, buyer_name: str) -> dict:
    """Tạo link thanh toán PayOS"""
    payload = {
        "orderCode": order_code,
        "amount": amount,
        "description": description,
        "buyerName": buyer_name,
        "returnUrl": f"{SERVER_URL}/payment-success",
        "cancelUrl": f"{SERVER_URL}/payment-cancel",
        "webhookUrl": f"{SERVER_URL}/payos-webhook",
    }

    # Tạo chữ ký
    sign_str = f"amount={amount}&cancelUrl={payload['cancelUrl']}&description={description}&orderCode={order_code}&returnUrl={payload['returnUrl']}"
    signature = hmac.new(
        PAYOS_CHECKSUM.encode(),
        sign_str.encode(),
        hashlib.sha256
    ).hexdigest()
    payload["signature"] = signature

    headers = {
        "x-client-id": PAYOS_CLIENT_ID,
        "x-api-key": PAYOS_API_KEY,
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{PAYOS_API_URL}/v2/payment-requests",
            json=payload,
            headers=headers
        ) as resp:
            return await resp.json()

# ==================== GỬI TÀI KHOẢN ====================
async def send_accounts_to_user(order: dict):
    """Gửi tài khoản cho khách sau khi thanh toán thành công"""
    try:
        user_id = order["user_id"]
        chat_id = order["chat_id"]
        pid = order["pid"]
        qty = order["qty"]
        product = PRODUCTS.get(pid)

        if not product:
            return

        if product["stock"] < qty or len(product["accounts"]) < qty:
            # Không đủ hàng → báo admin xử lý thủ công
            await telegram_app.bot.send_message(
                chat_id,
                f"✅ <b>Thanh toán thành công!</b>\n\n"
                f"📦 Sản phẩm: <b>{product['name']}</b>\n"
                f"🔔 Admin sẽ gửi tài khoản cho bạn trong thời gian sớm nhất.\n"
                f"Vui lòng liên hệ hỗ trợ nếu cần!",
                parse_mode="HTML"
            )
            await telegram_app.bot.send_message(
                ADMIN_ID,
                f"⚠️ Đơn hàng cần xử lý thủ công!\n"
                f"👤 User ID: {user_id}\n"
                f"📦 Sản phẩm: {product['name']}\n"
                f"🔢 Số lượng: {qty}\n"
                f"❗ Kho không đủ hàng!"
            )
            return

        # Lấy tài khoản từ kho
        accounts = product["accounts"][:qty]
        product["accounts"] = product["accounts"][qty:]
        product["stock"] = len(product["accounts"])

        acc_text = "\n".join(f"<code>{a}</code>" for a in accounts)

        await telegram_app.bot.send_message(
            chat_id,
            f"✅ <b>Thanh toán thành công!</b>\n\n"
            f"📦 Sản phẩm: <b>{product['name']}</b>\n"
            f"🔢 Số lượng: <b>{qty} tài khoản</b>\n\n"
            f"🔑 Tài khoản của bạn:\n{acc_text}\n\n"
            f"Cảm ơn bạn đã mua hàng! 🎉",
            parse_mode="HTML"
        )

        await telegram_app.bot.send_message(
            ADMIN_ID,
            f"✅ Đơn hàng hoàn tất!\n"
            f"👤 User ID: {user_id}\n"
            f"📦 {product['name']} x{qty}\n"
            f"💰 {product['pd']} x{qty} = {product['price'] * qty:,}đ"
        )

    except Exception as e:
        logger.error(f"Lỗi gửi tài khoản: {e}")

# ==================== KEYBOARD ====================
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("🛒 Mua hàng")],
        [KeyboardButton("👤 Hồ sơ"), KeyboardButton("💬 Hỗ trợ")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==================== HANDLER: /start ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"🎉 Chào mừng <b>{user.first_name}</b> đến với cửa hàng!\n\n"
        "📌 <b>Hướng dẫn:</b>\n"
        "1. Nhấn <b>🛒 Mua hàng</b>\n"
        "2. Chọn sản phẩm và nhập số lượng\n"
        "3. Quét mã QR thanh toán\n"
        "4. Bot tự động gửi tài khoản!\n\n"
        "🎯 Chọn menu bên dưới:"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard())

# ==================== HANDLER: MUA HÀNG ====================
async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for pid, p in PRODUCTS.items():
        status = "✅" if p["stock"] > 0 else "❌"
        label = f"{status} {p['name']} | {p['pd']} | 📦{p['stock']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"buy_{pid}")])

    await update.message.reply_text(
        "🛍️ <b>Danh sách sản phẩm:</b>\n"
        "<i>(Trạng thái | Tên | Giá | Kho)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== HANDLER: CALLBACK ====================
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("buy_"):
        pid = data[4:]
        product = PRODUCTS.get(pid)
        if not product:
            await query.edit_message_text("❌ Sản phẩm không tồn tại.")
            return

        if product["stock"] <= 0:
            await query.edit_message_text("😔 Sản phẩm này đã hết hàng!")
            return

        context.user_data["selected_pid"] = pid
        msg = product.get("msg", "").replace("{name}", product["name"]).replace("{price}", product["pd"]).replace("{stock}", str(product["stock"]))
        if not msg:
            msg = (
                f"🛒 <b>Xác nhận đơn hàng</b>\n\n"
                f"📦 Sản phẩm: <b>{product['name']}</b>\n"
                f"💰 Giá: <b>{product['pd']}/tài khoản</b>\n"
                f"📊 Còn lại: <b>{product['stock']} tài khoản</b>\n\n"
                f"✏️ Nhập số lượng cần mua (tối đa {product['stock']}):"
            )

        await query.edit_message_text(msg, parse_mode="HTML")

# ==================== HANDLER: NHẬP SỐ LƯỢNG ====================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if text == "🛒 Mua hàng":
        await show_products(update, context)
        return

    if text == "👤 Hồ sơ":
        await update.message.reply_text(
            f"👤 <b>Hồ sơ của bạn</b>\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"👋 Tên: {user.full_name}\n"
            f"📛 Username: @{user.username or 'Chưa đặt'}",
            parse_mode="HTML"
        )
        return

    if text == "💬 Hỗ trợ":
        await update.message.reply_text(
            "💬 <b>Hỗ trợ khách hàng</b>\n\n"
            "Liên hệ admin để được hỗ trợ.\n"
            "Thời gian: 8:00 - 22:00 hàng ngày.",
            parse_mode="HTML"
        )
        return

    # Xử lý nhập số lượng
    pid = context.user_data.get("selected_pid")
    if pid and text.isdigit():
        qty = int(text)
        product = PRODUCTS.get(pid)

        if not product:
            await update.message.reply_text("❌ Có lỗi xảy ra, vui lòng thử lại.")
            return

        if qty <= 0:
            await update.message.reply_text("❌ Số lượng phải lớn hơn 0!")
            return

        if qty > product["stock"]:
            await update.message.reply_text(
                f"❌ Kho chỉ còn <b>{product['stock']}</b> tài khoản!\n"
                f"Vui lòng nhập lại:",
                parse_mode="HTML"
            )
            return

        total = product["price"] * qty

        # Tạo order code unique
        import time
        order_code = int(time.time()) % 9999999

        # Lưu đơn hàng chờ thanh toán
        PENDING_ORDERS[str(order_code)] = {
            "user_id": user.id,
            "chat_id": update.effective_chat.id,
            "pid": pid,
            "qty": qty,
        }
        context.user_data.pop("selected_pid", None)

        # Tạo link PayOS
        await update.message.reply_text("⏳ Đang tạo link thanh toán...")

        try:
            result = await create_payment_link(
                order_code=order_code,
                amount=total,
                description=f"Mua {qty} {product['name'][:20]}",
                buyer_name=user.full_name
            )

            if result.get("code") == "00":
                payment_url = result["data"]["checkoutUrl"]
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Thanh toán ngay", url=payment_url)]
                ])
                await update.message.reply_text(
                    f"✅ <b>Đơn hàng đã tạo!</b>\n\n"
                    f"📦 Sản phẩm: <b>{product['name']}</b>\n"
                    f"🔢 Số lượng: <b>{qty} tài khoản</b>\n"
                    f"💰 Tổng tiền: <b>{total:,}đ</b>\n\n"
                    f"👇 Nhấn nút bên dưới để thanh toán QR:",
                    parse_mode="HTML",
                    reply_markup=keyboard
                )
            else:
                PENDING_ORDERS.pop(str(order_code), None)
                await update.message.reply_text(
                    f"❌ Lỗi tạo thanh toán: {result.get('desc', 'Không xác định')}\n"
                    f"Vui lòng thử lại!",
                )
        except Exception as e:
            PENDING_ORDERS.pop(str(order_code), None)
            logger.error(f"Lỗi tạo PayOS: {e}")
            await update.message.reply_text("❌ Lỗi kết nối PayOS. Vui lòng thử lại!")

# ==================== HANDLER: ADMIN ====================
async def add_acc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Không có quyền!")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Cú pháp: /addacc <sp1|sp2|sp3> <tài_khoản>\n"
            "Ví dụ: /addacc sp1 user123|pass456\n\n"
            "Thêm nhiều tài khoản:\n"
            "/addacc sp1 user1|pass1\n"
            "/addacc sp1 user2|pass2"
        )
        return

    pid = context.args[0]
    account = context.args[1]

    if pid not in PRODUCTS:
        await update.message.reply_text("❌ Mã sản phẩm không hợp lệ. Dùng: sp1, sp2, sp3")
        return

    PRODUCTS[pid]["accounts"].append(account)
    PRODUCTS[pid]["stock"] = len(PRODUCTS[pid]["accounts"])
    await update.message.reply_text(
        f"✅ Đã thêm vào <b>{PRODUCTS[pid]['name']}</b>\n"
        f"📦 Kho hiện tại: <b>{PRODUCTS[pid]['stock']} tài khoản</b>",
        parse_mode="HTML"
    )

async def stock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = "📊 <b>Tình trạng kho:</b>\n\n"
    for p in PRODUCTS.values():
        status = "✅" if p["stock"] > 3 else ("⚠️" if p["stock"] > 0 else "❌")
        text += f"{status} {p['name']}\n   💰 {p['pd']} | 📦 {p['stock']} tài khoản\n\n"
    await update.message.reply_text(text, parse_mode="HTML")

# ==================== FLASK SERVER THREAD ====================
def run_flask():
    flask_app.run(host="0.0.0.0", port=8080, debug=False, use_reloader=False)

# ==================== MAIN ====================
def main():
    global telegram_app

    # Khởi động Flask webhook server trong thread riêng
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("✅ Flask webhook server đang chạy trên port 8080")

    # Khởi động Telegram bot
    telegram_app = Application.builder().token(BOT_TOKEN).build()

    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("addacc", add_acc))
    telegram_app.add_handler(CommandHandler("stock", stock_cmd))
    telegram_app.add_handler(CallbackQueryHandler(callback_handler))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("✅ Bot đang chạy...")
    telegram_app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()