
import os
import time
import logging
import replicate
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from googletrans import Translator

# محیط توسعه و تنظیمات
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))

translator = Translator()
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)
user_last_request_time = {}

# لاگ‌ها
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# بررسی عضویت کانال‌ها
async def check_user_membership(user_id, context):
    try:
        for channel in [CHANNEL_1, CHANNEL_2]:
            member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ['member', 'creator', 'administrator']:
                return False
        return True
    except Exception as e:
        logger.error(f"Error checking membership: {e}")
        return False

# شروع
async def start(update: Update, context: CallbackContext):
    if update.message.chat.type != 'private':
        return

    user_id = update.effective_user.id
    joined = await check_user_membership(user_id, context)

    if not joined:
        keyboard = [
            [InlineKeyboardButton("📢 کانال ۱", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("📢 کانال ۲", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_joined")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا در کانال‌ها عضو شوید:", reply_markup=reply_markup)
        return

    welcome = "🌟 به ربات خوش اومدی!\n\nبا من می‌تونی متن رو تبدیل به عکس کنی یا عکس‌تو تبدیل به انیمه کنی!\nاز دکمه‌ها استفاده کن 😊"
    keyboard = [
        [InlineKeyboardButton("🖼️ تبدیل متن به عکس", callback_data="text_to_image")],
        [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data="photo_to_anime")],
        [InlineKeyboardButton("📌 راهنما", callback_data="help")]
    ]
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard))

# دکمه ها
async def button_handler(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "check_joined":
        if await check_user_membership(user_id, context):
            await start(update, context)
        else:
            await query.message.reply_text("❌ هنوز عضو نشدید. لطفاً ابتدا در کانال‌ها عضو شوید.")
    elif query.data == "text_to_image":
        await query.message.reply_text("📝 لطفاً یک متن بفرستید.")
        context.user_data["mode"] = "prompt"
    elif query.data == "photo_to_anime":
        await query.message.reply_text("📬 لطفاً عکس مورد نظر رو ارسال کن.")
        context.user_data["mode"] = "anime"
    elif query.data == "help":
        await query.message.reply_text("📌 راهنمای استفاده:\n\n- عکس آپلود کن، تبدیل میشه به انیمه : /anime\n- متن بده، عکس تحویلت می‌دیم : /prompt\n- فاصله بین درخواست‌ها طبق محدودیت تعیین‌شده توسط ادمینه.")

# دستورات
async def prompt_command(update: Update, context: CallbackContext):
    if update.message.chat.type != 'private':
        return
    await update.message.reply_text("📝 لطفاً یک متن بفرستید.")
    context.user_data["mode"] = "prompt"

async def anime_command(update: Update, context: CallbackContext):
    if update.message.chat.type != 'private':
        return
    await update.message.reply_text("📬 لطفاً عکس مورد نظر رو ارسال کن.")
    context.user_data["mode"] = "anime"

async def stats(update: Update, context: CallbackContext):
    if update.message.chat.type != 'private':
        return
    if update.effective_user.id == ADMIN_ID:
        users = len(user_last_request_time)
        await update.message.reply_text(f"📊 تعداد کاربران: {users}")
    else:
        await update.message.reply_text("دستور فقط برای ادمین در دسترسه.")

# پیام‌ها
async def message_handler(update: Update, context: CallbackContext):
    if update.message.chat.type != 'private':
        return

    user_id = update.effective_user.id
    now = time.time()
    last_time = user_last_request_time.get(user_id, 0)
    if now - last_time < TIME_LIMIT_MIN * 60:
        remaining = int(TIME_LIMIT_MIN * 60 - (now - last_time))
        await update.message.reply_text(f"⏳ لطفاً {remaining} ثانیه صبر کن.")
        return
    user_last_request_time[user_id] = now

    mode = context.user_data.get("mode")

    if mode == "prompt":
        input_text = update.message.text
        translated = translator.translate(input_text, src="fa", dest="en").text
        await update.message.reply_text("🎨 در حال ساخت تصویر...")
        try:
            output = replicate.run(
                "stability-ai/stable-diffusion:db21e45a3d3703b3ce68c479ec9be29b23a464df1c8c0d3b55b8b427d60e17e3",
                input={"prompt": translated, "num_outputs": 1, "guidance_scale": 7.5, "num_inference_steps": 50}
            )
            await update.message.reply_photo(output[0])
        except Exception as e:
            await update.message.reply_text("❌ مشکلی پیش اومد. لطفاً بعداً دوباره تلاش کنید.")

    elif mode == "anime" and update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
        photo_url = photo_file.file_path
        await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")
        try:
            output = replicate.run(
                "laksjd/animegan-v2:d5918e02b7353e92b293e38f5584dc86b62b978089f8f6e9f5ef16b7074c35d7",
                input={"image": photo_url}
            )
            await update.message.reply_photo(output[0])
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=photo_url, caption=f"📥 عکس از {user_id}")
        except Exception as e:
            await update.message.reply_text("❌ تبدیل تصویر با خطا مواجه شد.")
    else:
        await update.message.reply_text("لطفاً دستور مورد نظر را انتخاب کنید.")

# شروع برنامه
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("prompt", prompt_command))
app.add_handler(CommandHandler("anime", anime_command))
app.add_handler(CommandHandler("stats", stats))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.ALL, message_handler))
app.run_polling()
