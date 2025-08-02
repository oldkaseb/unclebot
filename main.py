import logging
import os
import replicate
import time
from telegram import (Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile)
from telegram.ext import (ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler)
from deep_translator import GoogleTranslator

# تنظیمات اولیه
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_ID = os.getenv("GROUP_ID")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))

replicate.Client(api_token=REPLICATE_API_TOKEN)
user_last_request_time = {}

# تابع بررسی عضویت
def build_subscription_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("کانال 1", url=CHANNEL_1_LINK),
            InlineKeyboardButton("کانال 2", url=CHANNEL_2_LINK),
        ],
        [
            InlineKeyboardButton("گروه اسپانسر", url=GROUP_LINK)
        ],
        [
            InlineKeyboardButton("عضو شدم ✅", callback_data="check_subscription")
        ]
    ])

async def is_user_member(user_id):
    from telegram.error import BadRequest
    try:
        for channel in [CHANNEL_1, CHANNEL_2]:
            member = await app.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        return True
    except BadRequest:
        return False

async def send_subscription_message(message, bot):
    await bot.send_message(
        chat_id=message.chat.id,
        text="برای استفاده از ربات، لطفاً ابتدا در دو کانال زیر عضو شوید:",
        reply_markup=build_subscription_keyboard()
    )

# شروع ربات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    if not await is_user_member(user_id):
        await send_subscription_message(update.message, context.bot)
        return

    keyboard = [[
        InlineKeyboardButton("🖼 تبدیل متن به عکس", callback_data="text_to_image"),
        InlineKeyboardButton("🎌 تبدیل عکس به انیمه", callback_data="photo_to_anime")
    ]]
    await update.message.reply_text("به ربات عمو عکسی خوش آمدی! یکی از گزینه‌های زیر را انتخاب کن:",
                                    reply_markup=InlineKeyboardMarkup(keyboard))

# کنترل دکمه‌ها
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "check_subscription":
        if await is_user_member(user_id):
            await query.edit_message_text("✅ عضویت شما تأیید شد. حالا یکی از گزینه‌ها رو انتخاب کن:")
            await start(update, context)
        else:
            await query.edit_message_text("⛔️ هنوز در یکی از کانال‌ها عضو نیستی! لطفاً دوباره بررسی کن.",
                                          reply_markup=build_subscription_keyboard())

    elif query.data == "text_to_image":
        context.user_data['mode'] = 'prompt'
        await query.edit_message_text("لطفاً پرامپت (توضیح تصویری) خود را وارد کنید:")

    elif query.data == "photo_to_anime":
        context.user_data['mode'] = 'photo'
        await query.edit_message_text("لطفاً عکس موردنظر را ارسال کنید:")

# هندل پیام متنی
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    if not await is_user_member(user_id):
        await send_subscription_message(update.message, context.bot)
        return

    if context.user_data.get('mode') != 'prompt':
        await update.message.reply_text("لطفاً یکی از گزینه‌های منو را انتخاب کنید.")
        return

    now = time.time()
    last = user_last_request_time.get(user_id, 0)
    if now - last < TIME_LIMIT_MIN * 60:
        remain = int((TIME_LIMIT_MIN * 60 - (now - last)) // 60)
        await update.message.reply_text(f"⏳ لطفاً {remain} دقیقه دیگر دوباره تلاش کن.")
        return

    prompt = update.message.text
    translated = GoogleTranslator(source='auto', target='en').translate(prompt)

    msg = await update.message.reply_text("⏳ در حال تولید تصویر...")
    try:
        output = replicate.run(
            "stability-ai/stable-diffusion",
            input={"prompt": translated}
        )
        await msg.delete()
        await update.message.reply_photo(output[0])
        user_last_request_time[user_id] = now
    except Exception as e:
        logger.error(e)
        await msg.edit_text("❌ مشکلی در تولید تصویر به‌وجود آمد. لطفاً بعداً تلاش کن.")

# هندل عکس ارسالی
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return

    user_id = update.effective_user.id
    if not await is_user_member(user_id):
        await send_subscription_message(update.message, context.bot)
        return

    if context.user_data.get('mode') != 'photo':
        await update.message.reply_text("لطفاً از منو گزینه «تبدیل عکس به انیمه» رو انتخاب کن.")
        return

    now = time.time()
    last = user_last_request_time.get(user_id, 0)
    if now - last < TIME_LIMIT_MIN * 60:
        remain = int((TIME_LIMIT_MIN * 60 - (now - last)) // 60)
        await update.message.reply_text(f"⏳ لطفاً {remain} دقیقه دیگر دوباره تلاش کن.")
        return

    msg = await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        image_url = file.file_path

        output = replicate.run(
            "laksjd/animegan-v2:d5918e02b7353e92b293e38f5584dc86b62b978089f8f6e9f5ef16b7074c35d7",
            input={"image": image_url}
        )
        await msg.delete()
        await update.message.reply_photo(output)
        user_last_request_time[user_id] = now
    except Exception as e:
        logger.error(e)
        await msg.edit_text("❌ تبدیل عکس با خطا مواجه شد. لطفاً عکس دیگری امتحان کن.")

# اجرای ربات
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

if __name__ == '__main__':
    print("ربات اجرا شد...")
    app.run_polling()
