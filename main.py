import os
import time
import logging
import replicate
import requests
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from deep_translator import GoogleTranslator

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 20))
TIME_LIMIT = TIME_LIMIT_MIN * 60

replicate.Client(api_token=REPLICATE_API_TOKEN)

user_last_call = {}
user_blocked = set()

# ---------- بررسی عضویت فقط در دو کانال ----------
async def check_membership(user_id, context):
    async def is_member(chat_id):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            return member.status in ["member", "administrator", "creator"]
        except:
            return False
    return await is_member(CHANNEL_1) and await is_member(CHANNEL_2)

# ---------- پیام خوش‌آمد ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📢 عضویت در کانال اول", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("📢 عضویت در کانال دوم", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("💬 گروه اسپانسر (اختیاری)", url=GROUP_LINK)],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_joined")]
        ]
        await update.message.reply_text(
            "🌟 برای استفاده از ربات لطفاً ابتدا در کانال‌های زیر عضو شوید:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    keyboard = [
        [InlineKeyboardButton("🎨 ساخت عکس از متن", callback_data="text_to_image")],
        [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data="photo_to_anime")]
    ]
    await update.message.reply_text(
        f"سلام {update.effective_user.first_name} عزیز! 🙌\n\n"
        "به ربات ساخت تصویر خوش اومدی.\n"
        "برای حفظ کیفیت ربات، بین هر درخواست باید حداقل ۲۰ دقیقه فاصله باشه.\n"
        "لطفاً یکی از گزینه‌های زیر رو انتخاب کن 👇",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ---------- دکمه "عضو شدم" ----------
async def check_joined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await check_membership(query.from_user.id, context):
        await query.edit_message_text("❗ هنوز در هر دو کانال عضو نشدید. لطفاً دوباره بررسی کنید.")
    else:
        await start(update, context)

# ---------- کنترل دکمه‌ها ----------
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query.data == "check_joined":
        await check_joined(update, context)
        return

    user_id = update.effective_user.id
    if user_id in user_blocked:
        await update.callback_query.answer("⛔ شما مسدود شده‌اید.")
        return

    if not await check_membership(user_id, context):
        await update.callback_query.answer("❗ ابتدا باید در کانال‌ها عضو شوید.")
        return

    now = time.time()
    if user_id in user_last_call and now - user_last_call[user_id] < TIME_LIMIT:
        wait = int((TIME_LIMIT - (now - user_last_call[user_id])) // 60)
        await update.callback_query.answer(f"⏳ لطفاً {wait} دقیقه دیگر امتحان کن.", show_alert=True)
        return

    user_last_call[user_id] = now
    context.user_data['mode'] = update.callback_query.data

    if update.callback_query.data == "text_to_image":
        await update.callback_query.edit_message_text("📝 لطفاً پرامپت متنی خود را ارسال کنید.")
    elif update.callback_query.data == "photo_to_anime":
        await update.callback_query.edit_message_text("📤 لطفاً یک عکس برای تبدیل ارسال کنید.")

# ---------- متن ارسالی کاربر ----------
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    if context.user_data.get('mode') != "text":
        return
    prompt = update.message.text
    prompt_en = GoogleTranslator(source='auto', target='en').translate(prompt)
    await update.message.reply_text("🎨 در حال ساخت تصویر...")

    try:
        output = replicate.run(
            "stability-ai/stable-diffusion",
            input={"prompt": prompt_en, "num_outputs": 1, "guidance_scale": 7.5, "num_inference_steps": 50}
        )
        image_url = output[0]
        await update.message.reply_photo(photo=image_url)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_url, caption=f"📨 از کاربر {user_id}")
    except Exception as e:
        await update.message.reply_text("❌ مشکلی در ساخت تصویر پیش آمد.")

# ---------- عکس ارسالی برای تبدیل ----------
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    if context.user_data.get('mode') != "photo":
        return

    photo_file = await update.message.photo[-1].get_file()
    image_path = f"{user_id}_photo.jpg"
    await photo_file.download_to_drive(image_path)

    await update.message.reply_text("🎭 در حال تبدیل به انیمه...")

    try:
        output = replicate.run(
            "laksjd/animegan-v2",
            input={"image": open(image_path, "rb")}
        )
        image_url = output[0]
        await update.message.reply_photo(photo=image_url)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_url, caption=f"🎭 عکس تبدیل‌شده از کاربر {user_id}")
    except Exception as e:
        await update.message.reply_text("❌ مشکلی در تبدیل عکس به انیمه پیش آمد.")

# ---------- دستور بلاک ----------
async def block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    try:
        blocked_id = int(context.args[0])
        user_blocked.add(blocked_id)
        await update.message.reply_text(f"⛔ کاربر {blocked_id} مسدود شد.")
    except:
        await update.message.reply_text("❗ لطفاً یک آی‌دی معتبر وارد کنید.")

# ---------- هشدار کم‌شدن اعتبار ----------
async def notify_low_credits():
    try:
        usage = replicate.client.get("/account/usage").json()
        remaining = usage["monthly_usage"]["remaining"]
        if remaining < 20:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ فقط {remaining} استفاده از API باقی مانده.")
    except:
        pass

# ---------- اجرای اصلی ----------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("block", block))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.run_polling()
