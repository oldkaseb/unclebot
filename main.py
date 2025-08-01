import os
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

# متغیرهای محیطی
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
GROUP_ID = os.getenv("GROUP_ID")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN")) * 60

# وضعیت کاربران
user_last_call = {}
blocked_users = set()
user_ids = set()

# مترجم فارسی به انگلیسی
def translate_to_english(text):
    try:
        response = requests.post("https://libretranslate.de/translate", data={
            "q": text,
            "source": "fa",
            "target": "en",
            "format": "text"
        })
        return response.json()["translatedText"]
    except:
        return text

# تولید عکس از متن
def generate_image(prompt):
    prompt_en = translate_to_english(prompt)
    url = "https://api.replicate.com/v1/predictions"
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    json_data = {
        "version": "db21e5a1-dbf4-4cfe-8c54-7f6c5dfbfa9c",
        "input": {"prompt": prompt_en}
    }
    r = requests.post(url, headers=headers, json=json_data)
    output = r.json().get("prediction", {}).get("output")
    return output[-1] if output else None

# تبدیل عکس به انیمه
def convert_to_anime(image_url):
    url = "https://api.replicate.com/v1/predictions"
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    json_data = {
        "version": "d631142b-2cd2-4f86-82f6-5c48d3d8c597",
        "input": {"image": image_url}
    }
    r = requests.post(url, headers=headers, json=json_data)
    output = r.json().get("prediction", {}).get("output")
    return output[-1] if output else None

# بررسی عضویت
async def check_membership(user_id, context):
    try:
        for chat_id in [CHANNEL_1, CHANNEL_2, GROUP_ID]:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        return True
    except:
        return False

# دکمه‌های عضویت
def get_join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("کانال ۱", url=CHANNEL_1_LINK),
         InlineKeyboardButton("کانال ۲", url=CHANNEL_2_LINK)],
        [InlineKeyboardButton("گروه اسپانسر", url=GROUP_LINK)]
    ])

# پیام استارت
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا در کانال‌ها و گروه زیر عضو شوید:", reply_markup=get_join_keyboard())
        return
    user_ids.add(user_id)
    await update.message.reply_text(
        "🎉 خوش اومدی به ربات عمو عکسی!\n\n"
        "📷 برای تولید تصویر، فقط یک جمله توصیفی بفرست\n"
        "🎭 همچنین می‌تونی یه عکس بفرستی تا به انیمه تبدیلش کنم!\n\n"
        "⏱ هر کاربر هر {} دقیقه یکبار می‌تونه درخواست بده.".format(TIME_LIMIT // 60)
    )

# دریافت متن
async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا در کانال‌ها و گروه زیر عضو شوید:", reply_markup=get_join_keyboard())
        return
    if user_id in blocked_users:
        return
    now = time.time()
    if user_id in user_last_call and now - user_last_call[user_id] < TIME_LIMIT:
        remain = int((TIME_LIMIT - (now - user_last_call[user_id])) // 60)
        await update.message.reply_text(f"⛔ لطفاً {remain} دقیقه صبر کن و دوباره تلاش کن.")
        return
    await update.message.reply_text("⏳ در حال ساخت تصویر...")
    user_last_call[user_id] = now
    image_url = generate_image(update.message.text)
    if image_url:
        await update.message.reply_photo(photo=image_url)
    else:
        await update.message.reply_text("❌ مشکلی پیش اومد. لطفاً دوباره امتحان کن.")

# دریافت عکس
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا در کانال‌ها و گروه زیر عضو شوید:", reply_markup=get_join_keyboard())
        return
    if user_id in blocked_users:
        return
    now = time.time()
    if user_id in user_last_call and now - user_last_call[user_id] < TIME_LIMIT:
        remain = int((TIME_LIMIT - (now - user_last_call[user_id])) // 60)
        await update.message.reply_text(f"⛔ لطفاً {remain} دقیقه صبر کن.")
        return
    photo = update.message.photo[-1]
    file = await photo.get_file()
    image_url = file.file_path
    await update.message.reply_text("⏳ در حال تبدیل عکس به انیمه...")
    user_last_call[user_id] = now
    anime_url = convert_to_anime(image_url)
    if anime_url:
        await update.message.reply_photo(photo=anime_url)
    else:
        await update.message.reply_text("❌ تبدیل انجام نشد.")

# آمار ویژه ادمین
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(f"📊 تعداد کاربران: {len(user_ids)}")

# بلاک‌کردن کاربر
async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        user_id = int(context.args[0])
        blocked_users.add(user_id)
        await update.message.reply_text(f"⛔ کاربر {user_id} بلاک شد.")
    except:
        await update.message.reply_text("فرمت صحیح: /block 123456789")

# اجرای ربات
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("block", block_user))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))

    app.run_polling()
