import os
import time
import logging
import replicate
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from googletrans import Translator

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN")) * 60

translator = Translator()
user_last_call = {}

HELP_TEXT = """📌 راهنمای استفاده:

🖼 تبدیل متن به تصویر:
با زدن دکمه «ساخت عکس از متن» یا دستور /prompt یک متن وارد کنید تا عکس ساخته شود.

🎭 تبدیل عکس به انیمه:
روی دکمه «تبدیل عکس به انیمه» بزنید و عکس ارسال کنید تا به انیمه تبدیل شود.

⏳ توجه: برای حفظ کیفیت ربات، بین هر درخواست ۲۰ دقیقه فاصله است.

از همراهی شما سپاسگزاریم 💖
"""

def translate_fa_to_en(text):
    return translator.translate(text, src='fa', dest='en').text

def check_time_limit(user_id):
    now = time.time()
    last_call = user_last_call.get(user_id, 0)
    if now - last_call < TIME_LIMIT:
        return int((TIME_LIMIT - (now - last_call)) / 60)
    user_last_call[user_id] = now
    return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if update.message.chat.type != 'private':
        return

    keyboard = [
        [InlineKeyboardButton("📸 عضویت در کانال ۱", url=CHANNEL_1_LINK)],
        [InlineKeyboardButton("🎨 عضویت در کانال ۲", url=CHANNEL_2_LINK)],
        [InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)],
        [InlineKeyboardButton("عضو شدم ✅", callback_data="check_membership")]
    ]
    await update.message.reply_text(
        "🌟 به ربات خوش اومدی!

لطفاً برای استفاده از ربات، ابتدا در کانال‌های زیر عضو شو:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def check_membership(user_id, context):
    async def is_member(chat_id):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            return member.status in ['member', 'administrator', 'creator']
        except:
            return False
    return await is_member(CHANNEL_1) and await is_member(CHANNEL_2)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_membership":
        if await check_membership(user_id, context):
            keyboard = [
                [InlineKeyboardButton("🖼 ساخت عکس از متن", callback_data='text_to_image')],
                [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data='photo_to_anime')],
                [InlineKeyboardButton("📚 راهنما", callback_data='help')]
            ]
            await query.edit_message_text("✅ عضویت تایید شد! یکی از گزینه‌های زیر رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("❌ هنوز عضویت شما تایید نشده. لطفاً ابتدا در هر دو کانال عضو شوید و مجدداً امتحان کنید.")

    elif query.data == 'text_to_image':
        limit = check_time_limit(user_id)
        if limit:
            await query.edit_message_text(f"⏳ لطفاً {limit} دقیقه دیگه دوباره تلاش کنید.")
            return
        context.user_data['mode'] = 'text'
        await query.edit_message_text("📝 لطفاً یک متن بفرست تا تصویر ساخته بشه.")

    elif query.data == 'photo_to_anime':
        limit = check_time_limit(user_id)
        if limit:
            await query.edit_message_text(f"⏳ لطفاً {limit} دقیقه دیگه دوباره تلاش کنید.")
            return
        context.user_data['mode'] = 'photo'
        await query.edit_message_text("📤 لطفاً عکس مورد نظر رو ارسال کن.")

    elif query.data == "help":
        await query.edit_message_text(HELP_TEXT)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") != 'text': return
    user_id = update.effective_user.id
    prompt = update.message.text
    await update.message.reply_text("⏳ در حال تولید تصویر...")
    translated_prompt = translate_fa_to_en(prompt)
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN
    output = replicate.run(
        "stability-ai/stable-diffusion:db21e45a3d3703b3ce68c479ec9be29b23a464df1c8c0d3b55b8b427d60e17e3",
        input={"prompt": translated_prompt, "num_outputs": 1}
    )
    if output:
        await update.message.reply_photo(photo=output[0])
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=output[0], caption=f"📤 تصویر کاربر {user_id}")
    else:
        await update.message.reply_text("❌ مشکلی در تولید تصویر پیش اومد.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") != 'photo': return
    user_id = update.effective_user.id
    photo = await update.message.photo[-1].get_file()
    photo_path = f"{user_id}_photo.jpg"
    await photo.download_to_drive(photo_path)
    await update.message.reply_text("⏳ در حال تبدیل عکس به انیمه...")
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN
    output = replicate.run(
        "laksjd/animegan-v2:d5918e02b7353e92b293e38f5584dc86b62b978089f8f6e9f5ef16b7074c35d7",
        input={"image": open(photo_path, "rb")}
    )
    if output:
        await update.message.reply_photo(photo=output[0])
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=output[0], caption=f"🎭 عکس انیمه‌شده از کاربر {user_id}")
    else:
        await update.message.reply_text("❌ مشکلی در تبدیل عکس پیش اومد.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(button))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
