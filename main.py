import os
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

load_dotenv()

# بارگذاری متغیرها از محیط
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
GROUP_ID = os.getenv("GROUP_ID")
GROUP_LINK = os.getenv("GROUP_LINK")
TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN")) * 60
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")

user_last_call = {}
blocked_users = set()
user_ids = set()

# --- ترجمه فارسی به انگلیسی ---
def translate_to_english(text):
    try:
        response = requests.post("https://libretranslate.de/translate", data={
            'q': text,
            'source': 'fa',
            'target': 'en'
        })
        return response.json().get("translatedText", text)
    except:
        return text

# --- تولید عکس با Replicate ---
def generate_image(prompt):
    prompt_en = translate_to_english(prompt)
    url = "https://api.replicate.com/v1/predictions"
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    json_data = {
        "version": "db21e45a-dbf4-4cfe-8c54-7f6c5dfbfa9c",
        "input": {"prompt": prompt_en}
    }
    r = requests.post(url, headers=headers, json=json_data)
    output = r.json().get("prediction", {}).get("output")
    return output[-1] if output else None

# --- تبدیل عکس به انیمه با Replicate ---
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

# --- بررسی مصرف Replicate ---
def check_replicate_usage():
    url = "https://api.replicate.com/v1/account/usage"
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    usage = requests.get(url, headers=headers).json()
    remaining = usage["credits"]['remaining']
    return remaining

# --- بررسی عضویت ---
async def check_membership(user_id, context):
    for chat_id in [CHANNEL_1, CHANNEL_2, GROUP_ID]:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ["administrator", "creator", "member"]:
                return False
        except:
            return False
    return True

# --- استارت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ids.add(user_id)
    if user_id in blocked_users:
        return

    if not await check_membership(user_id, context):
        keyboard = [
            [InlineKeyboardButton("کانال ۱", url=f"https://t.me/{CHANNEL_1}"), InlineKeyboardButton("کانال ۲", url=f"https://t.me/{CHANNEL_2}")],
            [InlineKeyboardButton("گروه اسپانسر", url=GROUP_LINK)]
        ]
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا در کانال‌ها و گروه زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    await update.message.reply_text(
        "سلام دوست عزیز 🌸\n\nبه ربات تبدیل عکس و متن به تصویر خوش اومدی!\n\n⏳ برای حفظ کیفیت ربات، بین هر درخواست شما باید حداقل ۲۰ دقیقه فاصله باشه.\n\nلطفاً یکی از گزینه‌های زیر رو انتخاب کن:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("تبدیل عکس به انیمه 🎌", callback_data="anime")]
        ])
    )

# --- مدیریت دکمه‌ها ---
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "anime":
        await query.edit_message_text("لطفاً عکست رو بفرست تا برات به سبک انیمه تبدیلش کنم!")

# --- مدیریت پیام ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in blocked_users:
        return

    if not await check_membership(user_id, context):
        return

    now = time.time()
    if user_id in user_last_call and now - user_last_call[user_id] < TIME_LIMIT:
        await update.message.reply_text("⛔ لطفاً کمی صبر کنید. بین هر درخواست باید حداقل ۲۰ دقیقه فاصله باشه.")
        return

    user_last_call[user_id] = now

    if update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        anime_url = convert_to_anime(file.file_path)
        if anime_url:
            await update.message.reply_photo(anime_url)
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🎨 کاربر {user_id} یک عکس انیمه دریافت کرد: {anime_url}")
        else:
            await update.message.reply_text("مشکلی در پردازش تصویر پیش اومد!")
    else:
        prompt = update.message.text
        image_url = generate_image(prompt)
        if image_url:
            await update.message.reply_photo(image_url)
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"🖼️ کاربر {user_id} یک تصویر تولید کرد: {image_url}\nپرامپت: {prompt}")
        else:
            await update.message.reply_text("مشکلی در تولید تصویر پیش اومد!")

# --- ادمین /stats ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    remaining = check_replicate_usage()
    await update.message.reply_text(f"📊 تعداد کاربران: {len(user_ids)}\n🪙 اعتبار باقی‌مانده Replicate: {remaining:.2f} credits")

# --- بلاک دستی ---
async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        uid = int(context.args[0])
        blocked_users.add(uid)
        await update.message.reply_text(f"کاربر {uid} مسدود شد.")
    except:
        await update.message.reply_text("فرمت دستور صحیح نیست. مثال: /block 123456789")

# --- اجرای برنامه ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))
    print("Bot is running...")
    app.run_polling()
