import os
import logging
import asyncio
import httpx
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

# لاگ‌گیری
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_ID = os.getenv("GROUP_ID")
GROUP_LINK = os.getenv("GROUP_LINK")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "dall-e-3")

# دیکشنری زمان آخرین درخواست
user_last_request = {}

# بررسی عضویت در کانال‌ها
async def is_user_member(user_id):
    async with httpx.AsyncClient() as client:
        for channel in [CHANNEL_1, CHANNEL_2]:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id=@{channel}&user_id={user_id}"
            resp = await client.get(url)
            data = resp.json()
            if data.get("result", {}).get("status") in ["left", "kicked"]:
                return False
    return True

# پیام شروع
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_member(user_id):
        keyboard = [
            [InlineKeyboardButton("عضویت در کانال اول 📢", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("عضویت در کانال دوم 📢", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("بررسی عضویت ✅", callback_data="check_membership")]
        ]
        await update.message.reply_text(
            "🚫 برای استفاده از ربات، ابتدا در دو کانال زیر عضو شو و سپس روی 'بررسی عضویت ✅' بزن:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    keyboard = [
        [InlineKeyboardButton("🔍 جستجوی عکس پروفایل", switch_inline_query_current_chat="")],
        [InlineKeyboardButton("🎨 ساخت تصویر از متن", callback_data="create_image")],
        [InlineKeyboardButton("🖌️ ویرایش عکس", callback_data="edit_image")],
    ]
    if GROUP_LINK:
        keyboard.append([InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)])

    await update.message.reply_text("به ربات خوش آمدی! یکی از گزینه‌ها رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))

# بررسی عضویت پس از کلیک
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "check_membership":
        user_id = query.from_user.id
        if await is_user_member(user_id):
            keyboard = [
                [InlineKeyboardButton("🔍 جستجوی عکس پروفایل", switch_inline_query_current_chat="")],
                [InlineKeyboardButton("🎨 ساخت تصویر از متن", callback_data="create_image")],
                [InlineKeyboardButton("🖌️ ویرایش عکس", callback_data="edit_image")],
            ]
            if GROUP_LINK:
                keyboard.append([InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)])

            await query.edit_message_text("✅ عضویت تایید شد. یکی از گزینه‌های زیر رو انتخاب کن:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.edit_message_text("❌ هنوز در یکی از کانال‌ها عضو نشدی. لطفا مجددا عضو شو و دکمه بررسی عضویت رو بزن.")

    elif query.data == "create_image":
        context.user_data['mode'] = "text_to_image"
        await query.edit_message_text("لطفا یک توضیح برای تصویر بنویس (مثلا: «یک گربه در حال نواختن گیتار»)")

    elif query.data == "edit_image":
        context.user_data['mode'] = "edit_image"
        await query.edit_message_text("لطفا عکسی که می‌خوای ادیت بشه رو ارسال کن.")

# ساخت عکس از متن با OpenAI
async def generate_image_from_text(prompt: str):
    url = "https://api.openai.com/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    json_data = {
        "model": OPENAI_MODEL,
        "prompt": prompt,
        "n": 1,
        "size": "1024x1024"
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, headers=headers, json=json_data)
        if response.status_code == 200:
            return response.json()["data"][0]["url"]
        else:
            logger.error(f"OpenAI Image Error: {response.text}")
            return None

# ویرایش عکس (شبیه‌سازی ساده با prompt جدید)
async def edit_image_with_prompt(image_url: str, prompt: str):
    return await generate_image_from_text(prompt + " با سبک تصویر قبلی")

# دریافت پیام از کاربر
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = asyncio.get_event_loop().time()
    last_time = user_last_request.get(user_id, 0)
    if now - last_time < TIME_LIMIT_MIN * 60:
        await update.message.reply_text("⏳ لطفا کمی صبر کن. هنوز زمان لازم از آخرین درخواستت نگذشته.")
        return

    mode = context.user_data.get("mode")
    if mode == "text_to_image":
        prompt = update.message.text
        await update.message.reply_text("⏳ در حال ساخت تصویر، لطفا منتظر بمان...")
        image_url = await generate_image_from_text(prompt)
        if image_url:
            await update.message.reply_photo(image_url)
        else:
            await update.message.reply_text("❌ خطایی در تولید تصویر رخ داد.")
        user_last_request[user_id] = now

    elif mode == "edit_image_waiting_prompt":
        image_url = context.user_data.get("image_url")
        prompt = update.message.text
        await update.message.reply_text("⏳ در حال ویرایش تصویر...")
        edited_url = await edit_image_with_prompt(image_url, prompt)
        if edited_url:
            await update.message.reply_photo(edited_url)
        else:
            await update.message.reply_text("❌ خطا در ویرایش تصویر.")
        context.user_data.pop("image_url", None)
        context.user_data.pop("mode", None)
        user_last_request[user_id] = now

# دریافت عکس برای ادیت
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") == "edit_image":
        photo = update.message.photo[-1]
        file = await photo.get_file()
        image_url = file.file_path
        context.user_data['image_url'] = image_url
        context.user_data['mode'] = "edit_image_waiting_prompt"
        await update.message.reply_text("لطفا توضیحی برای ویرایش این عکس بنویس (مثلا: «رنگ لباس آبی بشه»)")

# اجرای اصلی
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    await app.run_polling(close_loop=False)

if __name__ == '__main__':
    asyncio.run(main())
