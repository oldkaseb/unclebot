# ✅ فایل نهایی main.py با امکانات:
# - ساخت تصویر از متن (DALL-E 3)
# - ادیت تصویر از طریق OpenAI
# - بدون Replicate و ترجمه
# - عضویت اجباری دو کانال و گروه اسپانسر غیراجباری

import os
import openai
import logging
import aiofiles
import httpx
from PIL import Image
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# 📌 فعال‌سازی لاگ
logging.basicConfig(level=logging.INFO)

# 📌 متغیرهای محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

user_last_prompt_time = {}
user_states = {}

# ============================ توابع عضویت ============================
async def is_user_member(user_id):
    async with httpx.AsyncClient() as client:
        for channel in [CHANNEL_1, CHANNEL_2]:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
            params = {"chat_id": f"@{channel}", "user_id": user_id}
            response = await client.post(url, data=params)
            if 'left' in response.text or 'Bad Request' in response.text:
                return False
    return True

async def force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("عضویت در کانال اول", url=CHANNEL_1_LINK)],
                [InlineKeyboardButton("عضویت در کانال دوم", url=CHANNEL_2_LINK)],
                [InlineKeyboardButton("بررسی عضویت ✅", callback_data="check_membership")]]
    if GROUP_LINK:
        keyboard.append([InlineKeyboardButton("گروه اسپانسر 💬", url=GROUP_LINK)])
    await update.message.reply_text("برای استفاده از ربات ابتدا در دو کانال زیر عضو شوید:", reply_markup=InlineKeyboardMarkup(keyboard))

# ============================ شروع ربات ============================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_member(user_id):
        return await force_join(update, context)

    keyboard = [[InlineKeyboardButton("🎨 ساخت تصویر از متن", callback_data="text_to_image")],
                [InlineKeyboardButton("🖌 ادیت عکس", callback_data="edit_image")]]
    await update.message.reply_text("به ربات خوش آمدید. یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

# ============================ هندل دکمه‌ها ============================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_membership":
        if await is_user_member(user_id):
            return await query.edit_message_text("✅ عضویت شما تایید شد. یکی از گزینه‌های زیر را انتخاب کنید:",
                                                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎨 ساخت تصویر از متن", callback_data="text_to_image")],
                                                                                   [InlineKeyboardButton("🖌 ادیت عکس", callback_data="edit_image")]]))
        else:
            return await query.answer("❗ هنوز عضو هر دو کانال نشده‌اید!", show_alert=True)

    if query.data == "text_to_image":
        user_states[user_id] = "awaiting_prompt"
        return await query.edit_message_text("لطفا یک توضیح برای تصویر بنویس (مثلا: «یک گربه در حال نواختن گیتار»)")

    if query.data == "edit_image":
        user_states[user_id] = "awaiting_image"
        return await query.edit_message_text("لطفا عکسی که می‌خواهید ادیت شود را ارسال کنید.")

# ============================ ساخت تصویر از متن ============================
async def generate_image_from_text(prompt: str):
    response = openai.images.generate(
        model="dall-e-3",
        prompt=prompt,
        n=1,
        size="1024x1024"
    )
    return response.data[0].url

# ============================ ادیت تصویر ============================
async def edit_image(file_path, prompt):
    with open(file_path, "rb") as image_file:
        response = openai.images.edit(
            model="dall-e-3",
            image=image_file,
            prompt=prompt,
            size="1024x1024"
        )
        return response.data[0].url

# ============================ هندل پیام‌ها ============================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id)

    # محدودیت زمانی
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    if user_id in user_last_prompt_time and state == "awaiting_prompt":
        elapsed = now - user_last_prompt_time[user_id]
        if elapsed < timedelta(minutes=TIME_LIMIT_MIN):
            remain = TIME_LIMIT_MIN - int(elapsed.total_seconds() / 60)
            return await update.message.reply_text(f"⏳ لطفا {remain} دقیقه دیگر صبر کنید.")

    if state == "awaiting_prompt":
        await update.message.reply_text("⏱ در حال ساخت تصویر برای شما...")
        url = await generate_image_from_text(update.message.text)
        await update.message.reply_photo(photo=url)
        user_last_prompt_time[user_id] = now
        user_states.pop(user_id, None)

    elif state == "awaiting_caption":
        file_path = context.user_data.get("edit_file")
        url = await edit_image(file_path, update.message.text)
        await update.message.reply_photo(photo=url)
        user_states.pop(user_id, None)

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_states.get(user_id)
    if state != "awaiting_image":
        return

    await update.message.reply_text("📸 عکس دریافت شد. حالا یک توضیح بده که چه تغییری روی عکس اعمال بشه.")
    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    file_bytes = await file.download_as_bytearray()

    path = f"temp/{user_id}.png"
    os.makedirs("temp", exist_ok=True)
    async with aiofiles.open(path, "wb") as f:
        await f.write(file_bytes)

    context.user_data["edit_file"] = path
    user_states[user_id] = "awaiting_caption"

# ============================ اجرا ============================
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    print("ربات با موفقیت راه‌اندازی شد.")
    await app.run_polling(close_loop=False)

if __name__ == '__main__':
    import asyncio
    try:
        asyncio.run(main())
    except RuntimeError:
        import nest_asyncio
        nest_asyncio.apply()
        asyncio.get_event_loop().run_until_complete(main())
