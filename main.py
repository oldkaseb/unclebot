import os
import replicate
import logging
import asyncio
from dotenv import load_dotenv
from deep_translator import GoogleTranslator
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))

user_last_request = {}

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Membership check
async def check_membership(user_id, bot):
    try:
        chat_member1 = await bot.get_chat_member(chat_id=CHANNEL_1, user_id=user_id)
        chat_member2 = await bot.get_chat_member(chat_id=CHANNEL_2, user_id=user_id)
        return chat_member1.status in ['member', 'administrator', 'creator'] and                chat_member2.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.warning(f"Membership check error: {e}")
        return False

# Main menu
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("🧠 تبدیل متن به عکس", callback_data="prompt")],
        [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data="anime")],
        [InlineKeyboardButton("📢 راهنما", callback_data="help")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Join check buttons
def get_join_buttons():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("کانال ۱", url=CHANNEL_1_LINK)],
        [InlineKeyboardButton("کانال ۲", url=CHANNEL_2_LINK)],
        [InlineKeyboardButton("گروه اسپانسر", url=GROUP_LINK)],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="joined")]
    ])

def is_private_chat(update: Update):
    return update.effective_chat.type == "private"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return
    user_id = update.effective_user.id
    if not await check_membership(user_id, context.bot):
        await update.message.reply_text(
            "برای استفاده از ربات لطفاً ابتدا در کانال‌ها عضو شوید:",
            reply_markup=get_join_buttons()
        )
        return
    await update.message.reply_text("خوش آمدید 🎉", reply_markup=get_main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return

    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "joined":
        if not await check_membership(user_id, context.bot):
            await query.message.reply_text("⛔️ هنوز عضو نشدید. لطفاً ابتدا در کانال‌ها عضو شوید.")
        else:
            await query.message.reply_text("✅ خوش آمدید!", reply_markup=get_main_menu())

    elif query.data == "prompt":
        context.user_data["mode"] = "text"
        await query.message.reply_text("📝 لطفاً یک متن بفرستید.", reply_markup=ReplyKeyboardRemove())

    elif query.data == "anime":
        context.user_data["mode"] = "anime"
        await query.message.reply_text("📸 لطفاً یک عکس ارسال کنید.", reply_markup=ReplyKeyboardRemove())

    elif query.data == "help":
        await query.message.reply_text(
            "📌 راهنمای استفاده:
"
            "- عکس آپلود کن، تبدیل میشه به انیمه: /anime
"
            "- متن بده، عکس تحویلت می‌دیم: /prompt
"
            "- فاصله بین درخواست‌ها طبق محدودیت تعیین‌شده توسط ادمینه.",
            reply_markup=get_main_menu()
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return

    if context.user_data.get("mode") != "text":
        return

    user_id = update.effective_user.id
    now = asyncio.get_event_loop().time()
    last = user_last_request.get(user_id, 0)
    if now - last < TIME_LIMIT_MIN * 60:
        wait_sec = int(TIME_LIMIT_MIN * 60 - (now - last))
        await update.message.reply_text(f"⏳ لطفاً {wait_sec} ثانیه صبر کن.")
        return
    user_last_request[user_id] = now

    prompt = update.message.text
    prompt_en = GoogleTranslator(source='auto', target='en').translate(prompt)

    await update.message.reply_text("🎨 در حال ساخت تصویر...")

    try:
        output = replicate.run(
            "stability-ai/stable-diffusion",
            input={"prompt": prompt_en, "num_outputs": 1, "guidance_scale": 7.5, "num_inference_steps": 40},
            api_token=REPLICATE_API_TOKEN
        )
        if output and isinstance(output, list):
            await context.bot.send_photo(chat_id=user_id, photo=output[0])
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=output[0], caption=f"🎨 Text2Image توسط کاربر {user_id}")
        else:
            await update.message.reply_text("⚠️ خطا در دریافت عکس از سرور.")
    except Exception as e:
        logger.error(f"Replicate error: {e}")
        await update.message.reply_text("❌ مشکلی در پردازش پیش آمد.")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return

    if context.user_data.get("mode") != "anime":
        return

    user_id = update.effective_user.id
    now = asyncio.get_event_loop().time()
    last = user_last_request.get(user_id, 0)
    if now - last < TIME_LIMIT_MIN * 60:
        wait_sec = int(TIME_LIMIT_MIN * 60 - (now - last))
        await update.message.reply_text(f"⏳ لطفاً {wait_sec} صبر کن.")
        return
    user_last_request[user_id] = now

    await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")

    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        image_url = file.file_path

        output = replicate.run(
            "laksjd/animegan-v2",
            input={"image": image_url},
            api_token=REPLICATE_API_TOKEN
        )
        if output and isinstance(output, str):
            await context.bot.send_photo(chat_id=user_id, photo=output)
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=output, caption=f"🖼️ Anime توسط کاربر {user_id}")
        else:
            await update.message.reply_text("⚠️ مشکلی در دریافت عکس انیمه به وجود آمد.")
    except Exception as e:
        logger.error(f"Anime error: {e}")
        await update.message.reply_text("❌ مشکلی در پردازش پیش آمد.")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    users = len(user_last_request)
    await update.message.reply_text(f"📊 تعداد کاربران فعال: {users}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("prompt", lambda u, c: c.bot.send_message(chat_id=u.effective_chat.id, text="📝 لطفاً یک متن بفرستید.")))
    app.add_handler(CommandHandler("anime", lambda u, c: c.bot.send_message(chat_id=u.effective_chat.id, text="📸 لطفاً یک عکس ارسال کنید.")))
    app.add_handler(CommandHandler("help", lambda u, c: c.bot.send_message(chat_id=u.effective_chat.id, text="📌 راهنمای استفاده:
- /prompt و /anime")))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.PRIVATE, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO & filters.PRIVATE, handle_photo))

    print("ربات در حال اجراست...")
    app.run_polling()

if __name__ == "__main__":
    main()
