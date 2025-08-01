import os
import time
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from dotenv import load_dotenv

load_dotenv()

# -- متغیرها فقط از Railway خوانده می‌شوند
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_ID = os.getenv("GROUP_ID")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN")) * 60

user_last_call = {}
blocked_users = set()
user_ids = set()

def translate_to_english(text):
    try:
        response = requests.post("https://libretranslate.de/translate", data={
            'q': text, 'source': 'fa', 'target': 'en'
        })
        return response.json().get("translatedText", text)
    except:
        return text

def generate_image(prompt):
    url = "https://api.replicate.com/v1/predictions"
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    json_data = {
        "version": "db21e45a-dbf4-4cfe-8c54-7f6c5dfbfa9c",
        "input": {"prompt": translate_to_english(prompt)}
    }
    r = requests.post(url, headers=headers, json=json_data)
    output = r.json().get('prediction', {}).get('output')
    return output[-1] if output else None

def convert_to_anime(image_url):
    url = "https://api.replicate.com/v1/predictions"
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    json_data = {
        "version": "d631142b-2cd2-4f86-82f6-5c48d3d8c597",
        "input": {"image": image_url}
    }
    r = requests.post(url, headers=headers, json=json_data)
    output = r.json().get('prediction', {}).get('output')
    return output[-1] if output else None

async def check_membership(user_id, context):
    for chat in [CHANNEL_1, CHANNEL_2, GROUP_ID]:
        try:
            member = await context.bot.get_chat_member(chat, user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                return False
        except:
            return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ids.add(user_id)
    if user_id in blocked_users:
        return

    if not await check_membership(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📸 عضویت در کانال ۱", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("🎨 عضویت در کانال ۲", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)],
        ]
        await update.message.reply_text(
            "برای استفاده از ربات لطفاً ابتدا عضو کانال‌ها و گروه زیر شوید 👇",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    await update.message.reply_text(
        "سلام دوست عزیز 👋\n\n"
        "✨ خوش اومدی به ربات عمو عکسی!\n"
        "📸 می‌تونی عکس بسازی یا عکس‌هاتو به انیمه تبدیل کنی.\n"
        "⏳ برای حفظ کیفیت، بین هر درخواست ۲۰ دقیقه فاصله لازمه.\n\n"
        "حالا یه پیام متنی یا عکس بفرست تا شروع کنیم!"
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in blocked_users:
        return

    if not await check_membership(user_id, context):
        await start(update, context)
        return

    now = time.time()
    if now - user_last_call.get(user_id, 0) < TIME_LIMIT:
        remaining = int((TIME_LIMIT - (now - user_last_call[user_id])) / 60)
        await update.message.reply_text(f"⏳ لطفاً {remaining} دقیقه دیگر دوباره امتحان کن.")
        return

    user_last_call[user_id] = now
    prompt = update.message.text
    await update.message.reply_text("🎨 در حال ساخت تصویر...")
    image_url = generate_image(prompt)
    if image_url:
        await update.message.reply_photo(photo=image_url)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_url, caption=f"📤 از کاربر {user_id}\n📝 {prompt}")
    else:
        await update.message.reply_text("❌ خطا در تولید تصویر.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in blocked_users:
        return

    if not await check_membership(user_id, context):
        await start(update, context)
        return

    now = time.time()
    if now - user_last_call.get(user_id, 0) < TIME_LIMIT:
        remaining = int((TIME_LIMIT - (now - user_last_call[user_id])) / 60)
        await update.message.reply_text(f"⏳ لطفاً {remaining} دقیقه دیگر دوباره امتحان کن.")
        return

    user_last_call[user_id] = now
    file = await update.message.photo[-1].get_file()
    image_url = file.file_path
    await update.message.reply_text("🎭 در حال تبدیل به انیمه...")
    anime_url = convert_to_anime(image_url)
    if anime_url:
        await update.message.reply_photo(photo=anime_url)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=anime_url, caption=f"🎭 انیمه از {user_id}")
    else:
        await update.message.reply_text("❌ تبدیل به انیمه ناموفق بود.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        await update.message.reply_text(f"📊 تعداد کاربران: {len(user_ids)}")

async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        try:
            uid = int(context.args[0])
            blocked_users.add(uid)
            await update.message.reply_text(f"❌ کاربر {uid} بلاک شد.")
        except:
            await update.message.reply_text("فرمت اشتباه. مثال: /block 123456789")

async def unblock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        try:
            uid = int(context.args[0])
            blocked_users.discard(uid)
            await update.message.reply_text(f"✅ کاربر {uid} آزاد شد.")
        except:
            await update.message.reply_text("فرمت اشتباه. مثال: /unblock 123456789")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CommandHandler("unblock", unblock))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
