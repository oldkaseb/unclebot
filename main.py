import os
import time
import logging
import requests
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

load_dotenv()

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
        return response.json()['translatedText']
    except:
        return text

# --- تولید عکس از متن با Replicate ---
def generate_image(prompt):
    prompt_en = translate_to_english(prompt)
    url = "https://api.replicate.com/v1/predictions"
    headers = {"Authorization": f"Token {REPLICATE_TOKEN}"}
    json_data = {
        "version": "db21e45a-dbf4-4cfe-8c54-7f6c5dfbfa9c",
        "input": {"prompt": prompt_en}
    }
    r = requests.post(url, headers=headers, json=json_data)
    output = r.json().get('prediction', {}).get('output')
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
    output = r.json().get('prediction', {}).get('output')
    return output[-1] if output else None

# --- بررسی عضویت ---
async def check_membership(user_id, context):
    async def is_member(chat_id):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            return member.status in ['member', 'administrator', 'creator']
        except:
            return False

    return all([
        await is_member(CHANNEL_1),
        await is_member(CHANNEL_2),
        await is_member(GROUP_ID)
    ])

# --- استارت ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_ids.add(user_id)

    if user_id in blocked_users:
        return

    if not await check_membership(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📸 عضویت در کانال ۱", url=f"https://t.me/{CHANNEL_1}"),],
            [InlineKeyboardButton("🎨 عضویت در کانال ۲", url=f"https://t.me/{CHANNEL_2}"),],
            [InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)]
        ]
        await update.message.reply_text("لطفاً ابتدا در کانال‌ها و گروه زیر عضو شوید 👇", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    keyboard = [
        [InlineKeyboardButton("🖼 ساخت تصویر از متن", callback_data='text_to_image')],
        [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data='photo_to_anime')]
    ]
    await update.message.reply_text(
        "سلام! 👋\nبه ربات ساخت تصویر خوش آمدید.\nبرای حفظ کیفیت، بین هر درخواست ۲۰ دقیقه فاصله لازم است.\nیکی از گزینه‌های زیر را انتخاب کنید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- هندل دکمه‌ها ---
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    now = time.time()

    if user_id in blocked_users:
        return

    if user_id in user_last_call and now - user_last_call[user_id] < TIME_LIMIT:
        remaining = int((TIME_LIMIT - (now - user_last_call[user_id])) / 60)
        await query.edit_message_text(f"⏳ لطفاً {remaining} دقیقه دیگر تلاش کنید.")
        return

    user_last_call[user_id] = now

    if query.data == 'text_to_image':
        context.user_data['mode'] = 'text'
        await query.edit_message_text("📝 لطفاً پرامپت متنی خود را ارسال کنید:")
    elif query.data == 'photo_to_anime':
        context.user_data['mode'] = 'photo'
        await query.edit_message_text("📤 لطفاً عکسی را ارسال کنید:")

# --- هندل متن ---
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get('mode') == 'text':
        prompt = update.message.text
        await update.message.reply_text("🎨 در حال تولید تصویر... لطفاً منتظر بمانید")
        image_url = generate_image(prompt)
        if image_url:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_url, caption=f"📤 تصویر توسط کاربر {user_id}")
        else:
            await update.message.reply_text("❌ مشکلی در تولید تصویر پیش آمد.")

# --- هندل عکس ---
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if context.user_data.get('mode') == 'photo':
        photo = await update.message.photo[-1].get_file()
        path = f"{user_id}_{int(time.time())}.jpg"
        await photo.download_to_drive(path)

        await update.message.reply_text("✨ در حال تبدیل به انیمه... لطفاً صبر کنید")
        link = convert_to_anime(photo.file_path)

        if link:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=link)
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=link, caption=f"🎭 عکس انیمه‌شده از {user_id}")
        else:
            await update.message.reply_text("❌ تبدیل به انیمه با خطا مواجه شد.")

# --- بلاک کردن کاربران ---
async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID:
        try:
            target_id = int(context.args[0])
            blocked_users.add(target_id)
            await update.message.reply_text(f"❌ کاربر {target_id} مسدود شد.")
        except:
            await update.message.reply_text("استفاده درست: /block 123456")

# --- بررسی مصرف ---
def check_replicate_usage():
    url = "https://api.replicate.com/v1/account/usage"
    headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}"}
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        remaining = data.get("credits", {}).get("remaining", 999)  # اگر وجود نداشت، پیش‌فرض 999
        return remaining
    except Exception as e:
        print("خطا در گرفتن اعتبار Replicate:", e)
        return 999


# --- اجرای ربات ---
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("block", block_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    if check_replicate_usage():
        print("⚠️ مصرف Replicate به کمتر از ۲۰ اعتبار رسیده است!")

    app.run_polling()
