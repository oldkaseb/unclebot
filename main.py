import os
import replicate
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler,
                          filters, ContextTypes, CallbackQueryHandler)

# راه‌اندازی لاگر
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
GROUP_ID = os.getenv("GROUP_ID")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))

# راه‌اندازی Replicate
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

user_last_request_time = {}

async def check_user_membership(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    for channel in [CHANNEL_1, CHANNEL_2]:
        try:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logger.error(f"خطا در بررسی عضویت کاربر {user_id}: {e}")
            return False
    return True

def get_main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🧠 تبدیل متن به عکس", callback_data="text2img"),
            InlineKeyboardButton("👀 تبدیل عکس به انیمه", callback_data="img2anime"),
        ]
    ])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_user_membership(context, user_id):
        keyboard = [[
            InlineKeyboardButton("عضویت در کانال ۱", url=f"https://t.me/{CHANNEL_1}"),
            InlineKeyboardButton("عضویت در کانال ۲", url=f"https://t.me/{CHANNEL_2}"),
            InlineKeyboardButton("گروه اسپانسر", url=f"https://t.me/{GROUP_ID}"),
        ], [
            InlineKeyboardButton("عضو شدم ✅", callback_data="check_membership")
        ]]
        await update.message.reply_text("برای استفاده از ربات لطفاً در دو کانال عضو شوید:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    await update.message.reply_text("به ربات عمو عکسی خوش اومدی! یکی از گزینه‌های زیر را انتخاب کن:", reply_markup=get_main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_membership":
        if await check_user_membership(context, user_id):
            await query.edit_message_text("✅ عضویت شما تأیید شد! از گزینه‌های زیر استفاده کن:", reply_markup=get_main_menu())
        else:
            await query.edit_message_text("⛔️ هنوز عضو نشده‌ای. لطفاً هر دو کانال را دنبال کن و دوباره امتحان کن.")

    elif query.data == "text2img":
        context.user_data["mode"] = "text2img"
        await query.edit_message_text("لطفاً پرامپت (توضیح تصویری) خود را وارد کنید:")

    elif query.data == "img2anime":
        context.user_data["mode"] = "img2anime"
        await query.edit_message_text("لطفاً عکس موردنظر را ارسال کنید:")

async def prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get("mode") != "text2img":
        return

    last_time = user_last_request_time.get(user_id)
    now = asyncio.get_event_loop().time()
    if last_time and now - last_time < TIME_LIMIT_MIN * 60:
        await update.message.reply_text(f"⏱ لطفاً {TIME_LIMIT_MIN} دقیقه صبر کن و دوباره تلاش کن.")
        return

    prompt = update.message.text
    await update.message.reply_text("⏳ در حال تولید تصویر...")

    try:
        output = replicate.run(
            "stability-ai/stable-diffusion-3:latest",
            input={"prompt": prompt}
        )
        if output:
            await update.message.reply_photo(photo=output[0])
            user_last_request_time[user_id] = now
        else:
            await update.message.reply_text("❌ مشکلی در تولید تصویر به‌وجود آمد. لطفاً بعداً تلاش کن.")
    except Exception as e:
        logger.error(f"خطا در تبدیل متن به عکس: {e}")
        await update.message.reply_text("❌ تولید تصویر با خطا مواجه شد. لطفاً پرامپت ساده‌تری امتحان کن.")

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get("mode") != "img2anime":
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_url = file.file_path

    await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")

    try:
        output = replicate.run(
            "412392713/animeganv3:latest",
            input={"image": image_url}
        )
        if output:
            await update.message.reply_photo(photo=output)
        else:
            await update.message.reply_text("❌ تبدیل عکس با خطا مواجه شد. لطفاً عکس دیگری امتحان کن.")
    except Exception as e:
        logger.error(f"خطا در تبدیل عکس به انیمه: {e}")
        await update.message.reply_text("❌ تبدیل عکس با خطا مواجه شد. لطفاً عکس دیگری امتحان کن.")

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, prompt_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))

    await app.run_polling()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except RuntimeError as e:
        if "event loop is already running" in str(e):
            logger.warning("Event loop already running. Skipping asyncio.run().")
        else:
            raise
