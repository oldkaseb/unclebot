import os
import time
import logging
import replicate
import requests
from deep_translator import GoogleTranslator
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN")) * 60
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

user_last_call = {}

def is_private_chat(update: Update) -> bool:
    return update.effective_chat.type == "private"

async def check_membership(user_id, context):
    async def is_member(chat_id):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            return member.status in ["member", "administrator", "creator"]
        except:
            return False

    return await is_member(CHANNEL_1) and await is_member(CHANNEL_2)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return

    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📢 کانال ۱", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("🎨 کانال ۲", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("✅ عضو شدم", callback_data="check_joined")],
            [InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)],
        ]
        await update.message.reply_text(
            "برای استفاده از ربات، لطفاً ابتدا عضو کانال‌ها شوید 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    await show_main_menu(update, context)

async def check_joined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await check_membership(user_id, context):
        await update.callback_query.message.delete()
        await show_main_menu(update, context)
    else:
        await update.callback_query.answer("❌ هنوز عضو نیستید!", show_alert=True)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🖼 ساخت عکس از متن", callback_data="text_to_image")],
        [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data="photo_to_anime")],
    ]
    welcome = (
        "🎉 خوش آمدید!\n\n"
        "با این ربات می‌تونید از متن عکس بسازید یا عکس‌هاتون رو به استایل انیمه تبدیل کنید.\n\n"
        "⚠️ برای حفظ کیفیت، بین هر درخواست ۲۰ دقیقه فاصله باید باشه."
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=welcome,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return

    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    now = time.time()

    if user_id in user_last_call and now - user_last_call[user_id] < TIME_LIMIT:
        remaining = int((TIME_LIMIT - (now - user_last_call[user_id])) // 60)
        await query.edit_message_text(f"⏳ لطفاً {remaining} دقیقه صبر کنید.")
        return

    user_last_call[user_id] = now

    if query.data == "text_to_image":
        await query.edit_message_text("📝 لطفاً یک متن بفرستید.")
        context.user_data["mode"] = "text"

    elif query.data == "photo_to_anime":
        await query.edit_message_text("📤 لطفاً یک عکس بفرستید.")
        context.user_data["mode"] = "photo"

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return

    if context.user_data.get("mode") != "text":
        return

    user_id = update.effective_user.id
    prompt = update.message.text
    prompt_en = GoogleTranslator(source='auto', target='en').translate(prompt)

    await update.message.reply_text("🎨 در حال ساخت تصویر...")

    output = replicate.run(
        "stability-ai/stable-diffusion",
        input={
            "prompt": prompt_en,
            "num_outputs": 1,
            "guidance_scale": 7.5,
            "num_inference_steps": 50,
        },
        api_token=REPLICATE_API_TOKEN
    )

    image_url = output[0]
    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_url, caption=f"📤 از {user_id}")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return

    if context.user_data.get("mode") != "photo":
        return

    user_id = update.effective_user.id
    photo = await update.message.photo[-1].get_file()
    path = f"{user_id}_photo.jpg"
    await photo.download_to_drive(path)

    await update.message.reply_text("✨ در حال تبدیل عکس به انیمه...")

    output = replicate.run(
        "laksjd/animegan-v2:d5918e02b7353e92b293e38f5584dc86b62b978089f8f6e9f5ef16b7074c35d7",
        input={"image": open(path, "rb")},
        api_token=REPLICATE_API_TOKEN
    )

    image_url = output
    if isinstance(image_url, list):
        image_url = image_url[0]

    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)
    await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_url, caption=f"🎭 از {user_id}")

async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("یک آیدی بده.")
        return

    target_id = int(context.args[0])
    user_last_call[target_id] = time.time() + 999999
    await update.message.reply_text(f"❌ کاربر {target_id} مسدود شد.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("block", block_command))
    app.add_handler(CallbackQueryHandler(check_joined, pattern="^check_joined$"))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    app.run_polling()
