import os
import logging
import asyncio
import openai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (ApplicationBuilder, CommandHandler, ContextTypes,
                          MessageHandler, CallbackQueryHandler, filters)

# فعال‌سازی لاگ‌ها
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# بارگذاری متغیرها از Railway
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
openai.api_key = OPENAI_API_KEY

# ذخیره‌سازی آخرین زمان استفاده کاربران
user_last_prompt_time = {}

# بررسی عضویت کاربر
async def is_user_member(user_id: int) -> bool:
    try:
        chat1 = await app.bot.get_chat_member(chat_id=f"@{CHANNEL_1}", user_id=user_id)
        chat2 = await app.bot.get_chat_member(chat_id=f"@{CHANNEL_2}", user_id=user_id)
        return chat1.status in ["member", "creator", "administrator"] and chat2.status in ["member", "creator", "administrator"]
    except:
        return False

# شروع ربات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_member(user_id):
        keyboard = [[
            InlineKeyboardButton("عضویت در کانال 1", url=CHANNEL_1_LINK),
            InlineKeyboardButton("عضویت در کانال 2", url=CHANNEL_2_LINK)
        ], [
            InlineKeyboardButton("عضو شدم ✅", callback_data="check_membership")
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("👋 برای استفاده از ربات لطفاً در کانال‌های زیر عضو شوید:", reply_markup=reply_markup)
        return

    keyboard = [[
        InlineKeyboardButton("🖼 ساخت عکس از متن", callback_data="generate_image"),
        InlineKeyboardButton("✏️ ویرایش عکس", callback_data="edit_image")
    ], [
        InlineKeyboardButton("🔁 جستجوی تصویر", callback_data="search_image")
    ], [
        InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("به ربات ساخت و ویرایش عکس خوش آمدید! 👇 یکی از گزینه‌ها رو انتخاب کن:", reply_markup=reply_markup)

# بررسی عضویت پس از کلیک روی دکمه
async def check_membership(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()
    if await is_user_member(user_id):
        await query.edit_message_text("✅ عضویت شما تایید شد. یکی از گزینه‌ها رو انتخاب کن:")
        return await start(update, context)
    else:
        await query.edit_message_text("❌ هنوز عضو نیستی. لطفا مجدد تلاش کن.")

# فراخوانی ساخت تصویر از متن
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    now = asyncio.get_event_loop().time()
    last_time = user_last_prompt_time.get(user_id, 0)
    if now - last_time < TIME_LIMIT_MIN * 60:
        remain = int(TIME_LIMIT_MIN - (now - last_time) / 60)
        await update.message.reply_text(f"⏳ لطفا {remain} دقیقه صبر کن و دوباره تلاش کن.")
        return

    prompt = update.message.text
    await update.message.reply_text("⏱ در حال تولید تصویر، لطفا صبر کنید...")
    try:
        response = openai.images.generate(
            model=OPENAI_MODEL,
            prompt=prompt,
            n=1,
            size="1024x1024"
        )
        image_url = response.data[0].url
        await update.message.reply_photo(photo=image_url)
        user_last_prompt_time[user_id] = now
    except Exception as e:
        await update.message.reply_text("❌ خطا در ساخت تصویر: " + str(e))

# حالت دریافت تصویر برای ویرایش
editing_users = {}

async def edit_image_step1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("لطفا یک عکس بفرست تا ویرایش کنم ✏️")
    editing_users[update.effective_user.id] = "waiting_for_photo"

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if editing_users.get(user_id) != "waiting_for_photo":
        return
    photo_file = update.message.photo[-1]
    file = await photo_file.get_file()
    file_path = f"temp_{user_id}.jpg"
    await file.download_to_drive(file_path)
    editing_users[user_id] = file_path
    await update.message.reply_text("✅ عکس دریافت شد. حالا دستور ویرایش رو بنویس (مثلاً: پس‌زمینه رو ساحل کن)")

async def handle_edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in editing_users or not editing_users[user_id].endswith(".jpg"):
        return
    file_path = editing_users[user_id]
    prompt = update.message.text
    await update.message.reply_text("در حال ویرایش تصویر...")
    try:
        with open(file_path, "rb") as f:
            response = openai.images.edit(
                image=f,
                prompt=prompt,
                model=OPENAI_MODEL
            )
        image_url = response.data[0].url
        await update.message.reply_photo(photo=image_url)
    except Exception as e:
        await update.message.reply_text("❌ خطا در ویرایش تصویر: " + str(e))
    editing_users.pop(user_id, None)

# توابع انتخاب حالت از دکمه‌ها
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    await query.answer()
    if data == "check_membership":
        return await check_membership(update, context)
    elif data == "generate_image":
        await query.edit_message_text("لطفا یک توضیح برای تصویر بنویس (مثلا: "یک گربه در حال نواختن گیتار")")
    elif data == "edit_image":
        return await edit_image_step1(update, context)
    elif data == "search_image":
        await query.edit_message_text("🔍 این قابلیت به‌زودی فعال خواهد شد...")

# اجرای اصلی
async def main():
    global app
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & filters.UpdateType.MESSAGE, handle_edit_prompt))

    print("🤖 ربات با موفقیت راه‌اندازی شد.")
    await app.run_polling(close_loop=False)

import nest_asyncio
nest_asyncio.apply()

asyncio.run(main())
