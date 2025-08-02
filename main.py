import os
import logging
import replicate
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, CallbackQueryHandler, filters)

# تنظیمات لاگ‌ها
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# دریافت مقادیر از متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_ID = os.getenv("GROUP_ID")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))

# تنظیم کلاینت Replicate
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

# دیکشنری برای ذخیره وضعیت کاربران
user_state = {}
user_last_request_time = {}

# بررسی عضویت
async def check_membership(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        member1 = await context.bot.get_chat_member(chat_id=CHANNEL_1, user_id=user_id)
        member2 = await context.bot.get_chat_member(chat_id=CHANNEL_2, user_id=user_id)
        return member1.status in ["member", "administrator", "creator"] and \
               member2.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"خطا در بررسی عضویت: {e}")
        return False

# دکمه‌ها
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🖼 تبدیل متن به عکس", callback_data="text2image")],
        [InlineKeyboardButton("👀 تبدیل عکس به انیمه", callback_data="image2anime")]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        buttons = [[InlineKeyboardButton("عضویت در کانال 1", url=CHANNEL_1_LINK)],
                   [InlineKeyboardButton("عضویت در کانال 2", url=CHANNEL_2_LINK)],
                   [InlineKeyboardButton("📢 گروه اسپانسر", url=GROUP_LINK)],
                   [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join")]]
        reply_markup = InlineKeyboardMarkup(buttons)
        await update.message.reply_text("🔒 برای استفاده از ربات ابتدا باید در کانال‌های زیر عضو شوید:", reply_markup=reply_markup)
        return
    await update.message.reply_text("به ربات عمو عکسی خوش آمدی! یکی از گزینه‌های زیر را انتخاب کن:", reply_markup=get_main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_join":
        if await check_membership(user_id, context):
            await query.edit_message_text("✅ عضویت تأیید شد! از دکمه‌های زیر استفاده کن:", reply_markup=get_main_menu())
        else:
            await query.edit_message_text("⛔️ هنوز عضو کانال‌ها نیستی! لطفاً ابتدا عضو شو و دوباره امتحان کن.", reply_markup=query.message.reply_markup)

    elif query.data == "text2image":
        user_state[user_id] = "awaiting_prompt"
        await query.edit_message_text("لطفاً پرامپت (توضیح تصویری) خود را وارد کنید:")

    elif query.data == "image2anime":
        user_state[user_id] = "awaiting_photo"
        await query.edit_message_text("لطفاً عکس موردنظر را ارسال کنید:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        return
    text = update.message.text
    if user_id in user_state and user_state[user_id] == "awaiting_prompt":
        await generate_image_from_text(update, context, text)
        user_state.pop(user_id)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        return
    if user_id in user_state and user_state[user_id] == "awaiting_photo":
        file = await update.message.photo[-1].get_file()
        image_url = file.file_path
        await convert_image_to_anime(update, context, image_url)
        user_state.pop(user_id)

async def generate_image_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt: str):
    msg = await update.message.reply_text("⏳ در حال تولید تصویر...")
    try:
        output = replicate_client.run(
            "stability-ai/stable-diffusion:db21e45a3d3703b3ce68c479ec9be29b23a464df1c8c0d3b55b8b427d60e17e3",
            input={"prompt": prompt}
        )
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=output[0])
    except Exception as e:
        logger.error(f"خطا در تولید تصویر از متن: {e}")
        await update.message.reply_text("❌ مشکلی در تولید تصویر به‌وجود آمد. لطفاً بعداً تلاش کن.")
    finally:
        await msg.delete()

async def convert_image_to_anime(update: Update, context: ContextTypes.DEFAULT_TYPE, image_url: str):
    msg = await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")
    try:
        output = replicate_client.run(
            "cjwbw/animeganv2",
            input={"image": image_url}
        )
        await context.bot.send_photo(chat_id=update.effective_chat.id, photo=output)
    except Exception as e:
        logger.error(f"خطا در تبدیل عکس به انیمه: {e}")
        await update.message.reply_text("❌ تبدیل عکس با خطا مواجه شد. لطفاً عکس دیگری امتحان کن.")
    finally:
        await msg.delete()

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("ربات با موفقیت راه‌اندازی شد.")
    await app.run_polling(close_loop=False)

if __name__ == '__main__':
    asyncio.run(main())
