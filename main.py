import logging
import os
import time
import replicate
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, CallbackQueryHandler

# لاگ
logging.basicConfig(level=logging.INFO)

# مقادیر محیطی
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_ID = os.getenv("GROUP_ID")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", "15"))

replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

user_last_request_time = {}

# دکمه‌ها
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("👁‍🗨 تبدیل عکس به انیمه", callback_data="anime")],
        [InlineKeyboardButton("🖼️ تبدیل متن به عکس", callback_data="prompt")]
    ]
    return InlineKeyboardMarkup(keyboard)

# بررسی عضویت
async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        for channel in [CHANNEL_1, CHANNEL_2]:
            chat_member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
            if chat_member.status not in ['member', 'creator', 'administrator']:
                return False
        return True
    except:
        return False

# بررسی محدودیت زمانی
def is_time_allowed(user_id: int) -> bool:
    now = time.time()
    last_time = user_last_request_time.get(user_id, 0)
    return now - last_time >= TIME_LIMIT_MIN * 60

# ذخیره زمان درخواست
def update_user_time(user_id: int):
    user_last_request_time[user_id] = time.time()

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id
    if not await is_user_member(user_id, context):
        keyboard = [
            [InlineKeyboardButton("📢 کانال اول", url=CHANNEL_1_LINK)],
            [InlineKeyboardButton("📢 کانال دوم", url=CHANNEL_2_LINK)],
            [InlineKeyboardButton("عضو شدم ✅", callback_data="check_membership")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("برای استفاده از ربات لطفاً ابتدا در کانال‌های زیر عضو شوید:", reply_markup=reply_markup)
        return
    await update.message.reply_text("به ربات عمو عکسی خوش آمدی! یکی از گزینه‌های زیر را انتخاب کن:", reply_markup=get_main_menu())

# دکمه‌ها
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "check_membership":
        if not await is_user_member(user_id, context):
            await query.edit_message_text("❌ هنوز عضو کانال‌ها نیستی. لطفاً ابتدا عضو شو.")
            return
        await query.edit_message_text("✅ عضویت شما تأیید شد.")
        await context.bot.send_message(chat_id=user_id, text="یکی از گزینه‌های زیر را انتخاب کن:", reply_markup=get_main_menu())

    elif query.data == "prompt":
        context.user_data["mode"] = "prompt"
        await context.bot.send_message(chat_id=user_id, text="لطفاً پرامپت (توضیح تصویری) خود را وارد کنید:")

    elif query.data == "anime":
        context.user_data["mode"] = "anime"
        await context.bot.send_message(chat_id=user_id, text="لطفاً عکس موردنظر را ارسال کنید:")

# پیام‌ها
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != "private":
        return
    user_id = update.effective_user.id

    if not await is_user_member(user_id, context):
        await update.message.reply_text("❌ برای استفاده از ربات باید عضو کانال‌ها باشید.")
        return

    if not is_time_allowed(user_id):
        await update.message.reply_text(f"⏳ لطفاً {TIME_LIMIT_MIN} دقیقه صبر کن و بعد دوباره امتحان کن.")
        return

    mode = context.user_data.get("mode")
    if mode == "prompt":
        prompt = update.message.text
        await update.message.reply_text("⏳ در حال تولید تصویر...")
        try:
            output = replicate_client.run(
                "stability-ai/stable-diffusion:db21e45a3d3703b3ce68c479ec9be29b23a464df1c8c0d3b55b8b427d60e17e3",
                input={"prompt": prompt}
            )
            update_user_time(user_id)
            await update.message.reply_photo(photo=output[0])
        except:
            await update.message.reply_text("❌ مشکلی در تولید تصویر به‌وجود آمد. لطفاً بعداً تلاش کن.")
    elif mode == "anime" and update.message.photo:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        image_url = file.file_path
        await update.message.reply_text("🎨 در حال تبدیل عکس به انیمه...")
        try:
            output = replicate_client.run(
                "laksjd/animegan-v2:d5918e02b7353e92b293e38f5584dc86b62b978089f8f6e9f5ef16b7074c35d7",
                input={"image": image_url}
            )
            update_user_time(user_id)
            await update.message.reply_photo(photo=output)
        except:
            await update.message.reply_text("❌ تبدیل عکس با خطا مواجه شد. لطفاً عکس دیگری امتحان کن.")

        # ارسال برای ادمین با دکمه بلاک
        keyboard = [[InlineKeyboardButton("⛔ بلاک", callback_data=f"block_{user_id}")]]
        caption = f"عکس از کاربر {user_id}"
        await context.bot.send_photo(chat_id=ADMIN_ID, photo=image_url, caption=caption, reply_markup=InlineKeyboardMarkup(keyboard))

# بلاک
async def block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if str(update.effective_user.id) != str(ADMIN_ID):
        return
    if query.data.startswith("block_"):
        blocked_user = query.data.replace("block_", "")
        await query.answer("⛔ کاربر بلاک شد.")
        await query.edit_message_caption(caption=f"کاربر {blocked_user} بلاک شد.")

# /stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    count = len(user_last_request_time)
    await update.message.reply_text(f"📊 تعداد کاربران فعال: {count}")

# اجرای ربات
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(CallbackQueryHandler(block_user))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, message_handler))
    print("ربات با موفقیت راه‌اندازی شد.")
    await app.run_polling(close_loop=False)

# اجرای امن در Railway و محیط‌های دارای حلقه فعال
if __name__ == '__main__':
    import nest_asyncio
    import asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())
