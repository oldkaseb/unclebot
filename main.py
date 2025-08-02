import os
import logging
import replicate
import nest_asyncio
import asyncio
import aiohttp

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
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")  # ⚠️ اینو باید تو Railway وارد کنی
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

def get_main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👁️ تبدیل عکس به انیمه", callback_data='anime')],
        [InlineKeyboardButton("🖼️ تبدیل متن به عکس", callback_data='prompt')]
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
    async with aiohttp.ClientSession() as session:
        data = {
            "key": IMGBB_API_KEY,
            "image": image_bytes.hex()
        }
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
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا در کانال‌ها عضو شو:", reply_markup=InlineKeyboardMarkup(keyboard))
        return
    context.user_data["state"] = None
    await update.message.reply_text("به ربات خوش آمدی! از منو انتخاب کن:", reply_markup=get_main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_join":
        if await check_user_membership(user_id, context):
            await query.edit_message_text("✅ عضویت تأیید شد! حالا از منو گزینه‌ای رو انتخاب کن:", reply_markup=get_main_menu())
        else:
            await query.edit_message_text("❌ هنوز عضو نشدی. لطفاً عضو شو و دوباره امتحان کن.")
    elif query.data == "anime":
        context.user_data["state"] = "anime"
        await query.message.reply_text("📸 لطفاً تصویرت رو بفرست:")
    elif query.data == "prompt":
        context.user_data["state"] = "prompt"
        await query.message.reply_text("📝 لطفاً توضیحت رو برای تولید تصویر وارد کن:")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    if context.user_data.get("state") != "anime":
        return

    await update.message.reply_text("📤 در حال آپلود تصویر...")

    photo_file = await update.message.photo[-1].get_file()
    image_bytes = await photo_file.download_as_bytearray()
    public_url = await upload_to_imgbb(image_bytes)

    if not public_url:
        await update.message.reply_text("❌ مشکلی در آپلود تصویر بود.")
        return

    await update.message.reply_text("🎨 در حال تبدیل به انیمه...")

    try:
        output = await asyncio.to_thread(replicate_client.run,
            "laksjd/animegan-v2:d5918e02b7353e92b293e38f5584dc86b62b978089f8f6e9f5ef16b7074c35d7",
            input={"image": public_url}
        )
        if isinstance(output, list) and output:
            await update.message.reply_photo(photo=output[0])
        else:
            await update.message.reply_text("❌ تبدیل موفق نبود. دوباره تلاش کن.")
    except Exception as e:
        logging.error(f"خطا در تبدیل: {e}")
        await update.message.reply_text("❌ خطایی رخ داد. لطفاً تصویر دیگه‌ای امتحان کن.")

async def handle_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type != "private":
        return
    if context.user_data.get("state") != "prompt":
        return

    prompt = update.message.text
    await update.message.reply_text("🧠 در حال تولید تصویر...")

    try:
        output = await asyncio.to_thread(replicate_client.run,
            "stability-ai/stable-diffusion:db21e45a3d3703b3ce68c479ec9be29b23a464df1c8c0d3b55b8b427d60e17e3",
            input={"prompt": prompt}
        )
        if isinstance(output, list) and output:
            await update.message.reply_photo(photo=output[0])
        else:
            await update.message.reply_text("❌ تصویری ساخته نشد. پرامت رو عوض کن و دوباره امتحان کن.")
    except Exception as e:
        logging.error(f"خطا در تولید تصویر: {e}")
        await update.message.reply_text("❌ خطایی پیش آمد. لطفاً دوباره تلاش کن.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("دستورها:\n/anime - تبدیل عکس به انیمه\n/prompt - تولید عکس از توضیح\n/start - منوی اصلی")

async def prompt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "prompt"
    await update.message.reply_text("📝 لطفاً توضیح تصویری‌ت رو وارد کن:")

async def anime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["state"] = "anime"
    await update.message.reply_text("📸 لطفاً تصویر موردنظرت رو ارسال کن:")

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

# اجرای مطمئن در Railway یا محیط‌های دارای event loop
try:
    asyncio.get_event_loop().run_until_complete(main())
except RuntimeError as e:
    if str(e).startswith("This event loop is already running"):
        import threading
        threading.Thread(target=lambda: asyncio.run(main())).start()
    else:
        raise
