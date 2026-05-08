"""
Bot Telegram bán tài khoản Roboneo
Cài đặt: pip install python-telegram-bot==20.7
Chạy: python roboneo_bot.py
"""

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

# ==================== CẤU HÌNH ====================
BOT_TOKEN = "8620998717:AAE7P-MimVeUMB1lG29T10MXe7gGqQtzOw8"  # 👈 Thay bằng token bot của bạn
ADMIN_ID   = 7131184806             # 👈 Thay bằng Telegram ID của admin

# ==================== DỮ LIỆU SẢN PHẨM ====================
# Chỉnh giá và số lượng tại đây
PRODUCTS = {
    "sp1": {
        "name": "Roboneo tài khoản 120-140🥕",
        "price": 1000,
        "price_display": "1k",
        "stock": 0,
        "accounts": []   # 👈 Admin thêm tài khoản vào đây theo format "user|pass"
    },
    "sp2": {
        "name": "Roboneo tài khoản 170-190🥕",
        "price": 2000,  # 👈 Chỉnh giá sản phẩm 2
        "price_display": "2k",
        "stock": 0,       # 👈 Chỉnh số lượng sản phẩm 2
        "accounts": []
    },
    "sp3": {S
        "name": "Roboneo tài khoản 220-240🥕",
        "price": 2500,
        "price_display": "2k5",
        "stock": 0,
        "accounts": []
    },
}

# ==================== LOGGING ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== KEYBOARD CHÍNH ====================
def main_menu_keyboard():
    keyboard = [
        [KeyboardButton("🛒 Mua hàng")],
        [KeyboardButton("👤 Hồ sơ"), KeyboardButton("📋 Lịch sử mua")],
        [KeyboardButton("👛 Ví")],
        [KeyboardButton("💬 Hỗ trợ")],
        [KeyboardButton("🌐 Ngôn ngữ")],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# ==================== HANDLER: /start ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"🎉 Chào mừng <b>{user.first_name}</b> đến với cửa hàng!\n\n"
        "📌 <b>Hướng dẫn nhanh:</b>\n"
        "1. Nhấn nút <b>🛒 Mua hàng</b>.\n"
        "2. Chọn sản phẩm bạn muốn mua.\n"
        "3. Chọn thanh toán bằng QR và quét mã để thanh toán.\n"
        "4. Sau khi thanh toán xong, bot sẽ tự động xử lý đơn hàng.\n\n"
        "🎯 Vui lòng chọn menu:"
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=main_menu_keyboard())

# ==================== HANDLER: MUA HÀNG ====================
async def show_products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = []
    for pid, product in PRODUCTS.items():
        label = f"{product['name']} | {product['price_display']} | 📦 {product['stock']}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"buy_{pid}")])
    keyboard.append([InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")])

    await update.message.reply_text(
        "🛍️ <b>Danh sách sản phẩm:</b>\n"
        "<i>(Tên sản phẩm | Giá | Số lượng kho)</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== HANDLER: CHỌN SẢN PHẨM ====================
async def product_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "back_main":
        await query.message.delete()
        return

    if data.startswith("buy_"):
        pid = data.replace("buy_", "")
        product = PRODUCTS.get(pid)
        if not product:
            await query.edit_message_text("❌ Sản phẩm không tồn tại.")
            return

        if product["stock"] <= 0:
            await query.edit_message_text("😔 Sản phẩm này đã hết hàng. Vui lòng chọn sản phẩm khác.")
            return

        context.user_data["selected_product"] = pid

        keyboard = [
            [InlineKeyboardButton("✅ Xác nhận mua", callback_data=f"confirm_{pid}")],
            [InlineKeyboardButton("🔙 Quay lại", callback_data="show_products_again")],
        ]
        await query.edit_message_text(
            f"🛒 <b>Xác nhận đơn hàng</b>\n\n"
            f"📦 Sản phẩm: <b>{product['name']}</b>\n"
            f"💰 Giá: <b>{product['price_display']}</b>\n"
            f"📊 Còn lại: <b>{product['stock']} tài khoản</b>\n\n"
            f"Bạn có chắc muốn mua không?",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    elif data.startswith("confirm_"):
        pid = data.replace("confirm_", "")
        product = PRODUCTS.get(pid)

        if product["stock"] <= 0:
            await query.edit_message_text("😔 Sản phẩm vừa hết hàng!")
            return

        if product["accounts"]:
            account = product["accounts"].pop(0)
            product["stock"] -= 1

            await query.edit_message_text(
                f"✅ <b>Thanh toán thành công!</b>\n\n"
                f"📦 Sản phẩm: <b>{product['name']}</b>\n"
                f"🔑 Tài khoản của bạn:\n"
                f"<code>{account}</code>\n\n"
                f"Cảm ơn bạn đã mua hàng! 🎉",
                parse_mode="HTML"
            )
            # Thông báo admin
            await context.bot.send_message(
                ADMIN_ID,
                f"🛒 Đơn hàng mới!\n"
                f"👤 User: {query.from_user.full_name} (@{query.from_user.username})\n"
                f"📦 Sản phẩm: {product['name']}\n"
                f"💰 Giá: {product['price_display']}"
            )
        else:
            # Chưa có tài khoản → thông báo thủ công
            await query.edit_message_text(
                f"⏳ <b>Đơn hàng đã được ghi nhận!</b>\n\n"
                f"📦 Sản phẩm: <b>{product['name']}</b>\n"
                f"💰 Giá: <b>{product['price_display']}</b>\n\n"
                f"🔔 Admin sẽ gửi tài khoản cho bạn trong thời gian sớm nhất.\n"
                f"Vui lòng liên hệ 💬 Hỗ trợ nếu cần.",
                parse_mode="HTML"
            )
            await context.bot.send_message(
                ADMIN_ID,
                f"⚠️ Đơn hàng chờ xử lý!\n"
                f"👤 User: {query.from_user.full_name} (@{query.from_user.username}) - ID: {query.from_user.id}\n"
                f"📦 Sản phẩm: {product['name']}\n"
                f"💰 Giá: {product['price_display']}\n"
                f"❗ Chưa có tài khoản trong kho, cần xử lý thủ công!"
            )

    elif data == "show_products_again":
        keyboard = []
        for pid, product in PRODUCTS.items():
            label = f"{product['name']} | {product['price_display']} | 📦 {product['stock']}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"buy_{pid}")])
        keyboard.append([InlineKeyboardButton("🔙 Quay lại", callback_data="back_main")])
        await query.edit_message_text(
            "🛍️ <b>Danh sách sản phẩm:</b>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ==================== HANDLER: CÁC NÚT MENU KHÁC ====================
async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🛒 Mua hàng":
        await show_products(update, context)

    elif text == "👤 Hồ sơ":
        user = update.effective_user
        await update.message.reply_text(
            f"👤 <b>Hồ sơ của bạn</b>\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"👋 Tên: {user.full_name}\n"
            f"📛 Username: @{user.username or 'Chưa đặt'}",
            parse_mode="HTML"
        )

    elif text == "📋 Lịch sử mua":
        await update.message.reply_text(
            "📋 <b>Lịch sử mua hàng</b>\n\n"
            "Chức năng đang phát triển. Vui lòng quay lại sau!",
            parse_mode="HTML"
        )

    elif text == "👛 Ví":
        await update.message.reply_text(
            "👛 <b>Ví của bạn</b>\n\n"
            "💰 Số dư: <b>0đ</b>\n\n"
            "Chức năng nạp tiền đang phát triển!",
            parse_mode="HTML"
        )

    elif text == "💬 Hỗ trợ":
        await update.message.reply_text(
            "💬 <b>Hỗ trợ khách hàng</b>\n\n"
            "Vui lòng liên hệ admin: @your_admin_username\n"  # 👈 Thay username admin
            "Thời gian hỗ trợ: 8:00 - 22:00 hàng ngày.",
            parse_mode="HTML"
        )

    elif text == "🌐 Ngôn ngữ":
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🇻🇳 Tiếng Việt", callback_data="lang_vi")],
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        ])
        await update.message.reply_text("🌐 Chọn ngôn ngữ:", reply_markup=keyboard)

# ==================== HANDLER: ADMIN THÊM TÀI KHOẢN ====================
# Dùng lệnh: /addaccount sp1 username|password
async def add_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Cú pháp: /addaccount <sp1|sp2|sp3> <tài_khoản>\n"
            "Ví dụ: /addaccount sp1 user123|pass456"
        )
        return

    pid = context.args[0]
    account = context.args[1]

    if pid not in PRODUCTS:
        await update.message.reply_text("❌ Mã sản phẩm không hợp lệ. Dùng: sp1, sp2, sp3")
        return

    PRODUCTS[pid]["accounts"].append(account)
    PRODUCTS[pid]["stock"] += 1
    await update.message.reply_text(
        f"✅ Đã thêm tài khoản vào <b>{PRODUCTS[pid]['name']}</b>\n"
        f"📦 Kho hiện tại: {PRODUCTS[pid]['stock']} tài khoản",
        parse_mode="HTML"
    )

# ==================== HANDLER: ADMIN XEM KHO ====================
async def view_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bạn không có quyền dùng lệnh này.")
        return

    text = "📊 <b>Tình trạng kho hàng:</b>\n\n"
    for pid, product in PRODUCTS.items():
        text += f"• {product['name']}\n  💰 Giá: {product['price_display']} | 📦 Kho: {product['stock']}\n\n"
    await update.message.reply_text(text, parse_mode="HTML")

# ==================== MAIN ====================
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Lệnh
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addaccount", add_account))
    app.add_handler(CommandHandler("stock", view_stock))

    # Callback inline keyboard
    app.add_handler(CallbackQueryHandler(product_callback))

    # Menu nút bấm
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, menu_handler))

    logger.info("✅ Bot đang chạy...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
