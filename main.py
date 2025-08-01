import os
import logging
import time
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import replicate

# متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))

# ذخیره زمان آخرین درخواست کاربران
user_last_request = {}

# پیکربندی Replicate
os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

logging.basicConfig(level=logging.INFO)

# تابع بررسی عضویت
async def is_user_member(update: Update, context: CallbackContext) -> bool:
    user_id = update.effective_user.id
    try:
        chat1 = await context.bot.get_chat_member(CHANNEL_1, user_id)
        chat2 = await context.bot.get_chat_member(CHANNEL_2, user_id)
        return chat1.status in ['member', 'administrator', 'creator'] and chat2.status in ['member', 'administrator', 'creator']
    except:
        return False

# پیام خوش‌آمد
async def start(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        return
    if not await is_user_member(update, context):
        keyboard = [
            [InlineKeyboardButton("کانال 1", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("کانال 2", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("گروه اسپانسر", url=GROUP_LINK)],
            [InlineKeyboardButton("عضو شدم ✅", callback_data="check_membership")]
        ]
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا در کانال‌ها عضو شوید 👇", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    await show_menu(update, context)

# نمایش منو
async def show_menu(update: Update, context: CallbackContext):
    text = "خوش آمدید! یکی از گزینه‌های زیر را انتخاب کنید:\n\n/anime - تبدیل عکس به انیمه 🎌\n/prompt - تولید تصویر از متن 🎨\n/help - راهنمای استفاده 📘"
    await context.bot.send_message(chat_id=update.effective_user.id, text=text)

# راهنما
async def help_command(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        return
    await update.message.reply_text("📌 راهنمای استفاده:\n\n- /anime : عکس آپلود کن، تبدیل میشه به انیمه.\n- /prompt : متن بده، عکس تحویلت می‌دیم.\n- فاصله بین درخواست‌ها طبق محدودیت تعیین‌شده توسط ادمینه.")

# دکمه بررسی عضویت
async def check_membership_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    if await is_user_member(update, context):
        await query.edit_message_text("✅ عضویت تایید شد.")
        await show_menu(update, context)
    else:
        await query.edit_message_text("⛔️ هنوز عضو نشدید. لطفاً ابتدا در کانال‌ها عضو شوید.")

# زمان‌بندی
def is_allowed(user_id):
    now = time.time()
    last = user_last_request.get(user_id, 0)
    if now - last < TIME_LIMIT_MIN * 60:
        return False, int(TIME_LIMIT_MIN * 60 - (now - last))
    user_last_request[user_id] = now
    return True, 0

# /prompt
async def prompt_command(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    allowed, wait_time = is_allowed(user_id)
    if not allowed:
        await update.message.reply_text(f"⏳ لطفاً {wait_time} ثانیه صبر کن.")
        return
    await update.message.reply_text("📝 لطفاً متن خود را بفرستید.")

# پاسخ به پیام متنی
async def handle_text(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        return
    prompt = update.message.text
    user_id = update.effective_user.id
    allowed, wait_time = is_allowed(user_id)
    if not allowed:
        await update.message.reply_text(f"⏳ لطفاً {wait_time} ثانیه صبر کن.")
        return
    await update.message.reply_text("🖼 در حال ساخت تصویر...")
    output = replicate.run("stability-ai/sdxl:latest", input={"prompt": prompt})
    await update.message.reply_photo(photo=output[0])

# /anime
async def anime_command(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        return
    await update.message.reply_text("📸 لطفاً یک عکس ارسال کنید.")

# دریافت عکس
async def handle_photo(update: Update, context: CallbackContext):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    allowed, wait_time = is_allowed(user_id)
    if not allowed:
        await update.message.reply_text(f"⏳ لطفاً {wait_time} ثانیه صبر کن.")
        return
    file = await update.message.photo[-1].get_file()
    file_url = file.file_path
    await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")
    output = replicate.run("tstramer/animeganv2:latest", input={"image": file_url})
    await update.message.reply_photo(photo=output)

    # ارسال برای ادمین
    await context.bot.send_message(chat_id=ADMIN_ID, text=f"🧑‍💻 عکس جدید از کاربر: {update.effective_user.id}")
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=file_url, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("بلاک", callback_data=f"block_{user_id}")]]))

# /stats فقط برای ادمین
async def stats(update: Update, context: CallbackContext):
    if update.effective_user.id != ADMIN_ID:
        return
    count = len(user_last_request)
    await update.message.reply_text(f"📊 تعداد کاربران: {count}")

# بلاک (اختیاری)
async def block_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer("در نسخه رایگان بلاک فعال نیست ❌")

# راه‌اندازی
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("prompt", prompt_command))
    app.add_handler(CommandHandler("anime", anime_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(check_membership_callback, pattern="check_membership"))
    app.add_handler(CallbackQueryHandler(block_callback, pattern="block_"))

    print("ربات در حال اجراست...")
    app.run_polling()
