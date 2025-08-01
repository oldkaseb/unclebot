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
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
from googletrans import Translator

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN")) * 60

os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

user_last_call = {}

# بررسی عضویت در کانال‌ها
async def check_membership(user_id, context):
    async def is_member(chat_id):
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            return member.status in ['member', 'administrator', 'creator']
        except:
            return False
    return all([
        await is_member(CHANNEL_1),
        await is_member(CHANNEL_2)
    ])

# شروع ربات
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    if not await check_membership(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📢 عضویت در کانال ۱", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("🎨 عضویت در کانال ۲", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)],
            [InlineKeyboardButton("🔁 عضو شدم، بررسی کن", callback_data='check_join')]
        ]
        await update.message.reply_text("برای استفاده از ربات، لطفاً در کانال‌ها عضو شوید 👇", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    keyboard = [
        [InlineKeyboardButton("🖼 ساخت عکس از متن", callback_data='text_to_image')],
        [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data='photo_to_anime')]
    ]
    welcome = "سلام دوست عزیز! 🌟\nبه ربات تولید تصویر خوش اومدی.\n⏳ به‌خاطر حفظ کیفیت، بین هر درخواست باید ۲۰ دقیقه صبر کنی.\n\n👇 یکی از گزینه‌ها رو انتخاب کن:"
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard))

# هندل دکمه‌ها
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    current_time = time.time()

    if query.data == 'check_join':
        if await check_membership(user_id, context):
            await start(update, context)
        else:
            await query.edit_message_text("❌ هنوز عضو نیستید. لطفاً عضو شید و دوباره تلاش کنید.")
        return

    if current_time - user_last_call.get(user_id, 0) < TIME_LIMIT:
        remaining = int(TIME_LIMIT - (current_time - user_last_call[user_id])) // 60
        await query.edit_message_text(f"⏳ لطفاً {remaining} دقیقه صبر کنید.")
        return

    user_last_call[user_id] = current_time

    if query.data == 'text_to_image':
        context.user_data['mode'] = 'text'
        await query.edit_message_text("📝 لطفاً یک پرامپت متنی ارسال کنید.")
    elif query.data == 'photo_to_anime':
        context.user_data['mode'] = 'photo'
        await query.edit_message_text("📷 لطفاً یک عکس ارسال کنید.")

# ساخت عکس از متن
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    if context.user_data.get('mode') != 'text':
        return

    prompt = update.message.text
    await update.message.reply_text("⏳ در حال ساخت تصویر...")

    # ترجمه فارسی به انگلیسی
    translator = Translator()
    prompt_en = translator.translate(prompt, dest="en").text

    try:
        version = replicate.models.get("stability-ai/stable-diffusion").versions.get(
            "db21e45a3d3703b3ce68c479ec9be29b23a464df1c8c0d3b55b8b427d60e17e3")
        output = version.predict(prompt=prompt_en, num_outputs=1, guidance_scale=7.5, num_inference_steps=50)
        image_url = output[0]
        await update.message.reply_photo(photo=image_url)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_url, caption=f"🖼 از کاربر {user_id}")
    except Exception as e:
        await update.message.reply_text("❌ مشکلی در تولید تصویر پیش آمد.")

# تبدیل عکس به انیمه
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    if context.user_data.get('mode') != 'photo':
        return

    photo = await update.message.photo[-1].get_file()
    image_path = f"{user_id}_photo.jpg"
    await photo.download_to_drive(image_path)

    await update.message.reply_text("🎨 در حال تبدیل به انیمه...")

    try:
        output = replicate.run(
            "laksjd/animegan-v2:d5918e02b7353e92b293e38f5584dc86b62b978089f8f6e9f5ef16b7074c35d7",
            input={"image": open(image_path, "rb")}
        )
        anime_url = output
        await update.message.reply_photo(photo=anime_url)
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=anime_url, caption=f"🎭 انیمه از کاربر {user_id}")
    except Exception as e:
        await update.message.reply_text("❌ تبدیل به انیمه با خطا مواجه شد.")

# دستور بلاک
async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    user_id = int(context.args[0])
    user_last_call[user_id] = time.time() + 10**9
    await update.message.reply_text(f"❌ کاربر {user_id} بلاک شد.")

# بررسی مانده کرِدیت
async def check_credits(app):
    import aiohttp
    while True:
        await asyncio.sleep(3600)
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Token {REPLICATE_API_TOKEN}"}
            async with session.get("https://api.replicate.com/v1/account/usage", headers=headers) as resp:
                data = await resp.json()
                remaining = data.get("credits", {}).get("remaining", 999)
                if remaining < 20:
                    await app.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ فقط {remaining} کرِدیت باقی مانده!")

# اجرای برنامه
if __name__ == '__main__':
    import asyncio
    logging.basicConfig(level=logging.INFO)
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("block", block_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    asyncio.create_task(check_credits(app))
    app.run_polling()
