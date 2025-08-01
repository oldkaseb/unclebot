import os
import requests
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from dotenv import load_dotenv
from datetime import datetime, timedelta

# --- بارگذاری متغیرها ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
GROUP_ID = os.getenv("GROUP_ID")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN")) * 60  # تبدیل به ثانیه

# --- متغیرهای در حافظه ---
user_last_call = {}
blocked_users = set()
user_ids = set()

# --- تابع ترجمه پرامپت فارسی به انگلیسی ---
def translate_to_english(text):
    try:
        response = requests.post("https://libretranslate.de/translate", json={
            "q": text, "source": "fa", "target": "en", "format": "text"
        })
        return response.json()["translatedText"]
    except:
        return text

# --- بررسی عضویت کاربر ---
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for chat_id in [CHANNEL_1, CHANNEL_2, GROUP_ID]:
        try:
            status = await context.bot.get_chat_member(chat_id, user_id)
            if status.status not in ["member", "administrator", "creator"]:
                return False
        except:
            return False
    return True

# --- دکمه بررسی مجدد عضویت ---
async def check_membership_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update.effective_user = query.from_user
    if await check_membership(update, context):
        await query.message.reply_text("✅ شما با موفقیت عضو شدید! حالا می‌تونید از ربات استفاده کنید.")
    else:
        await query.message.reply_text("⛔ هنوز عضو کانال‌ها و گروه نشدید!")

# --- منوی جوین اجباری ---
async def send_join_message(update: Update):
    keyboard = [
        [InlineKeyboardButton("کانال ۱", url=CHANNEL_1_LINK),
         InlineKeyboardButton("کانال ۲", url=CHANNEL_2_LINK)],
        [InlineKeyboardButton("گروه اسپانسر", url=GROUP_LINK)],
        [InlineKeyboardButton("عضو شدم ✅", callback_data="check_join")]
    ]
    await update.message.reply_text(
        "برای استفاده از ربات لطفاً ابتدا در کانال‌ها و گروه زیر عضو شوید:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# --- تولید عکس با Replicate ---
def generate_image(prompt):
    prompt_en = translate_to_english(prompt)
    url = "https://api.replicate.com/v1/predictions"
    headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}"}
    json_data = {
        "version": "db21e45a-dbf4-4cfe-8c54-7f6c5dfbfa9c",
        "input": {"prompt": prompt_en}
    }
    r = requests.post(url, headers=headers, json=json_data)
    return r.json().get("prediction", {}).get("output")[-1]

# --- تبدیل عکس به انیمه ---
def convert_to_anime(image_url):
    url = "https://api.replicate.com/v1/predictions"
    headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}"}
    json_data = {
        "version": "d631142b-2cd2-4f86-82f6-5c48d3d8c597",
        "input": {"image": image_url}
    }
    r = requests.post(url, headers=headers, json=json_data)
    return r.json().get("prediction", {}).get("output")[-1]

# --- کنترل فاصله زمانی ---
def is_time_limited(user_id):
    now = datetime.now()
    if user_id in user_last_call:
        diff = (now - user_last_call[user_id]).total_seconds()
        if diff < TIME_LIMIT_MIN:
            return int(TIME_LIMIT_MIN - diff)
    user_last_call[user_id] = now
    return 0

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update, context):
        await send_join_message(update)
        return
    await update.message.reply_text(
        "🎉 به ربات عمو عکسی خوش اومدی!\nاز دکمه‌ها یا دستورات زیر استفاده کن:\n\n"
        "/prompt - تولید تصویر از متن\n"
        "/anime - تبدیل عکس به انیمه\n"
        "/help - راهنمای استفاده"
    )

# --- /help ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 راهنمای ربات:\n"
        "/prompt - تولید تصویر از متن فارسی\n"
        "/anime - ارسال عکس برای تبدیل به انیمه\n"
        "/stats - نمایش آمار (فقط ادمین)\n"
        "/start - نمایش منوی اصلی"
    )

# --- /prompt ---
async def prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await check_membership(update, context):
        await send_join_message(update)
        return
    wait = is_time_limited(user_id)
    if wait:
        await update.message.reply_text(f"⏳ لطفاً {wait} ثانیه صبر کن و دوباره تلاش کن.")
        return
    await update.message.reply_text("📝 لطفاً متن مورد نظر رو برای تولید تصویر بفرست.")

# --- دریافت متن برای پرامپت ---
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text.startswith("/"):
        return
    user_id = update.effective_user.id
    wait = is_time_limited(user_id)
    if wait:
        await update.message.reply_text(f"⏳ لطفاً {wait} ثانیه صبر کن.")
        return
    await update.message.reply_text("🖼 در حال ساخت تصویر...")
    url = generate_image(update.message.text)
    if url:
        await update.message.reply_photo(photo=url)
    else:
        await update.message.reply_text("❌ مشکلی در تولید تصویر پیش آمد.")

# --- /anime ---
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_membership(update, context):
        await send_join_message(update)
        return
    await update.message.reply_text("📷 لطفاً عکس مورد نظر رو ارسال کن.")

# --- دریافت عکس برای تبدیل ---
async def image_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in blocked_users:
        return
    file = await update.message.photo[-1].get_file()
    file_url = file.file_path
    await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")
    result = convert_to_anime(file_url)
    if result:
        await update.message.reply_photo(photo=result)
    else:
        await update.message.reply_text("❌ خطا در تبدیل عکس.")

    # ارسال به ادمین
    caption = f"📸 عکس از کاربر {user_id}"
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=file_url, caption=caption)

# --- /stats ---
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(f"📊 تعداد کاربران: {len(user_ids)}")

# --- اجرای ربات ---
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("prompt", prompt))
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(MessageHandler(filters.PHOTO, image_handler))
    app.add_handler(CallbackQueryHandler(check_membership_button, pattern="check_join"))
    app.run_polling()

if __name__ == "__main__":
    main()
