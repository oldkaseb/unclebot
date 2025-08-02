import os
import logging
import replicate
import datetime
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler
)

# ----------
# تنظیمات اولیه
# ----------
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_ID = os.getenv("GROUP_ID")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN", 15))
replicate_client = replicate.Client(api_token=REPLICATE_TOKEN)
logging.basicConfig(level=logging.INFO)

# ----------
# کنترل فاصله زمانی بین درخواست‌ها
# ----------
last_requests = {}
def is_time_allowed(user_id):
    now = datetime.datetime.now()
    if user_id in last_requests:
        delta = now - last_requests[user_id]
        if delta.total_seconds() < TIME_LIMIT * 60:
            return False
    last_requests[user_id] = now
    return True

# ----------
# بررسی عضویت در کانال‌ها
# ----------
async def check_membership(user_id, context):
    try:
        for channel in [CHANNEL_1, CHANNEL_2]:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        return True
    except:
        return False

# ----------
# هندلر /start
# ----------
async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        keyboard = [[InlineKeyboardButton("عضویت در کانال اول", url=CHANNEL_1_LINK)],
                    [InlineKeyboardButton("عضویت در کانال دوم", url=CHANNEL_2_LINK)],
                    [InlineKeyboardButton("عضو شدم ✅", callback_data="check_join")]]
        await update.message.reply_text("🔒 برای استفاده از ربات، ابتدا در کانال‌ها عضو شوید:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    keyboard = [[InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data="anime")],
                [InlineKeyboardButton("🖼️ تبدیل متن به عکس", callback_data="prompt")]]
    await update.message.reply_text("به ربات عمو عکسی خوش آمدی! یکی از گزینه‌های زیر را انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))

# ----------
# بررسی عضویت دوباره
# ----------
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "check_join":
        if await check_membership(user_id, context):
            await start_handler(update, context)
        else:
            await query.edit_message_text("هنوز عضو نشدی! لطفاً بعد از عضویت دکمه 'عضو شدم' رو بزن.")
    elif query.data == "anime":
        context.user_data["mode"] = "anime"
        await query.edit_message_text("📸 لطفاً عکس موردنظر را ارسال کنید:")
    elif query.data == "prompt":
        context.user_data["mode"] = "prompt"
        await query.edit_message_text("💬 لطفاً پرامپت (توضیح تصویری) خود را وارد کنید:")

# ----------
# پیام متنی برای تبدیل پرامپت
# ----------
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    user_id = update.effective_user.id
    if not await check_membership(user_id, context): return
    mode = context.user_data.get("mode")
    if mode == "prompt":
        if not is_time_allowed(user_id):
            await update.message.reply_text(f"⏳ لطفاً {TIME_LIMIT} دقیقه صبر کن و دوباره تلاش کن.")
            return
        prompt = update.message.text
        await update.message.reply_text("⏳ در حال تولید تصویر...")
        try:
            output = replicate_client.run(
                "stability-ai/stable-diffusion",
                input={"prompt": prompt}
            )
            await update.message.reply_photo(photo=output[0])
        except:
            await update.message.reply_text("❌ مشکلی در تولید تصویر به‌وجود آمد. لطفاً تلاش کن.")

# ----------
# دریافت عکس و تبدیل به انیمه
# ----------
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private": return
    user_id = update.effective_user.id
    if not await check_membership(user_id, context): return
    mode = context.user_data.get("mode")
    if mode == "anime":
        if not is_time_allowed(user_id):
            await update.message.reply_text(f"⏳ لطفاً {TIME_LIMIT} دقیقه صبر کن و دوباره تلاش کن.")
            return
        await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")
        photo = update.message.photo[-1]
        file = await photo.get_file()
        path = await file.download_to_drive()
        try:
            output = replicate_client.run(
                "cjwbw/animegan2",
                input={"image": open(path, "rb")}
            )
            await update.message.reply_photo(photo=output)
        except:
            await update.message.reply_text("❌ تبدیل عکس با خطا مواجه شد. لطفاً عکس دیگری امتحان کن.")
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=open(path, "rb"), caption=f"کاربر: {user_id}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بلاک", callback_data=f"block_{user_id}")]]))

# ----------
# بلاک کردن کاربران توسط ادمین
# ----------
blocked_users = set()
async def admin_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("block_"):
        uid = int(query.data.split("_")[1])
        blocked_users.add(uid)
        await query.edit_message_caption(caption="✅ کاربر بلاک شد.")

# ----------
# کامندهای کمکی
# ----------
async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 برای شروع، از دکمه‌ها استفاده کن یا دستور /start رو بزن.")

# ----------
# اجرای ربات
# ----------
async def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("prompt", message_handler))
    app.add_handler(CommandHandler("anime", photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(admin_block))
    await app.run_polling(close_loop=False)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "already running" in str(e):
            loop = asyncio.get_event_loop()
            loop.create_task(main())
            loop.run_forever()
