import os
import logging
import replicate
import asyncio
import aiohttp
import base64
import nest_asyncio

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, CallbackQueryHandler, ContextTypes
)

nest_asyncio.apply()
logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁️ تبدیل عکس به انیمه", callback_data='anime')],
        [InlineKeyboardButton("🖼️ تولید عکس انیمه از متن", callback_data='prompt')]
    ])

async def check_user_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat1 = await context.bot.get_chat_member(CHANNEL_1, user_id)
        chat2 = await context.bot.get_chat_member(CHANNEL_2, user_id)
        valid_status = {"member", "administrator", "creator"}
        return chat1.status in valid_status and chat2.status in valid_status
    except:
        return False

async def upload_to_imgbb(image_bytes):
    encoded = base64.b64encode(image_bytes).decode("utf-8")
    async with aiohttp.ClientSession() as session:
        data = {"key": IMGBB_API_KEY, "image": encoded}
        async with session.post("https://api.imgbb.com/1/upload", data=data) as resp:
            result = await resp.json()
            return result.get("data", {}).get("url")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    user_id = update.effective_user.id
    if not await check_user_membership(user_id, context):
        keyboard = [
            [InlineKeyboardButton("عضویت در کانال ۱", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("عضویت در کانال ۲", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("عضو شدم ✅", callback_data="check_join")]
        ]
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا عضو کانال‌ها شو:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    context.user_data["state"] = None
    await update.message.reply_text("به ربات خوش آمدی! یکی از گزینه‌های زیر رو انتخاب کن:", reply_markup=get_main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "check_join":
        if await check_user_membership(query.from_user.id, context):
            await query.edit_message_text("✅ عضویت تأیید شد! از منو انتخاب کن:", reply_markup=get_main_menu())
        else:
            await query.edit_message_text("❌ هنوز عضو نشدی. لطفاً عضو شو و دوباره امتحان کن.")
    elif query.data == "anime":
        context.user_data["state"] = "anime"
        await query.message.reply_text("📸 لطفاً عکس رو ارسال کن:")
    elif query.data == "prompt":
        context.user_data["state"] = "prompt"
        await query.message.reply_text("📝 لطفاً توضیح تصویری رو وارد کن:")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != "anime":
        return
    await update.message.reply_text("📤 در حال آپلود تصویر...")
    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    public_url = await upload_to_imgbb(image_bytes)
    if not public_url:
        await update.message.reply_text("❌ مشکل در آپلود تصویر بود.")
        return
    await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")
    try:
        output = await asyncio.to_thread(replicate_client.run,
            "cjwbw/animegan2",
            input={"image": public_url}
        )
        if isinstance(output, list) and output:
            await update.message.reply_photo(photo=output[0])
        else:
            await update.message.reply_text("❌ خروجی معتبری دریافت نشد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در تبدیل: {e}")

async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("state") != "prompt":
        return
    prompt = update.message.text
    await update.message.reply_text("🧠 در حال تولید تصویر انیمه...")
    try:
        output = await asyncio.to_thread(replicate_client.run,
            "andite/anything-v4",
            input={"prompt": prompt}
        )
        if isinstance(output, list) and output:
            await update.message.reply_photo(photo=output[0])
        else:
            await update.message.reply_text("❌ تصویر تولید نشد.")
    except Exception as e:
        await update.message.reply_text(f"❌ خطا در تولید تصویر: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("دستورهای موجود:\n/start\n/anime\n/prompt")

async def prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "prompt"
    await update.message.reply_text("📝 لطفاً توضیح تصویری‌ت رو وارد کن:")

async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "anime"
    await update.message.reply_text("📸 لطفاً عکس موردنظرت رو بفرست:")

async def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("prompt", prompt_command))
    app.add_handler(CommandHandler("anime", anime_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_prompt))
    await app.run_polling(close_loop=False)

try:
    asyncio.get_event_loop().run_until_complete(main())
except RuntimeError as e:
    if str(e).startswith("This event loop is already running"):
        import threading
        threading.Thread(target=lambda: asyncio.run(main())).start()
    else:
        raise
