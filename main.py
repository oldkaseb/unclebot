import os
import replicate
import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("🖼️ تبدیل متن به عکس", callback_data="prompt")],
        [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data="anime")],
        [InlineKeyboardButton("📌 راهنما", callback_data="help")]
    ]
    await update.message.reply_text(
        "🌟 به ربات خوش اومدی!\nبا من می‌تونی متن رو تبدیل به عکس کنی یا عکس‌تو تبدیل به انیمه کنی!\nاز دکمه‌ها استفاده کن 😊",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 راهنمای استفاده:\n"
        "- عکس آپلود کن، تبدیل میشه به انیمه: /anime\n"
        "- متن بده، عکس تحویلت می‌دیم: /prompt\n"
        "- فاصله بین درخواست‌ها طبق محدودیت تعیین‌شده توسط ادمینه."
    )

async def prompt_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = update.message.text
    await update.message.reply_text("🎨 در حال ساخت تصویر...")
    try:
        output = replicate_client.run(
            "stability-ai/stable-diffusion",
            input={
                "prompt": prompt,
                "num_outputs": 1,
                "guidance_scale": 7.5,
                "num_inference_steps": 50
            }
        )
        logging.info("Replicate response: %s", output)
        await update.message.reply_photo(photo=output[0])
    except Exception as e:
        logging.error("Replicate prompt error: %s", str(e))
        await update.message.reply_text("❌ ساخت تصویر با خطا مواجه شد.")
        await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ خطا در /prompt:\n{str(e)}\nUser ID: {update.effective_user.id}")

async def anime_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("📭 لطفاً یک عکس ارسال کن.")
        return
    await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه... ⏳")
    try:
        file = await context.bot.get_file(update.message.photo[-1].file_id)
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file.file_path}"
        logging.info("File URL: %s", file_url)
        output = replicate_client.run(
            "laksjd/animegan-v2",
            input={"image": file_url}
        )
        logging.info("Replicate anime response: %s", output)
        await update.message.reply_photo(photo=output[0])
    except Exception as e:
        logging.error("Replicate anime error: %s", str(e))
        await update.message.reply_text("❌ تبدیل تصویر با خطا مواجه شد.")
        try:
            await context.bot.send_photo(chat_id=ADMIN_ID, photo=update.message.photo[-1].file_id,
                                         caption=f"⚠️ خطا در /anime:\n{str(e)}\nUser ID: {update.effective_user.id}")
        except:
            await context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ خطای بدون عکس در /anime:\n{str(e)}\nUser ID: {update.effective_user.id}")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("prompt", prompt_handler))
    app.add_handler(CommandHandler("anime", anime_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), prompt_handler))
    app.add_handler(MessageHandler(filters.PHOTO, anime_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
