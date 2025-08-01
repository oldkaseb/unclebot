import os
import requests
import replicate
from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

load_dotenv()

# بارگذاری متغیرها از Railway
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_ID = os.getenv("GROUP_ID")
GROUP_LINK = os.getenv("GROUP_LINK")
REPLICATE_TOKEN = os.getenv("REPLICATE_API_TOKEN")
TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN")) * 60

# دیتابیس ساده
user_last_call = {}
blocked_users = set()
user_ids = set()

# ترجمه ساده فارسی به انگلیسی
def translate_to_english(text):
    try:
        response = requests.post("https://libretranslate.de/translate", json={
            "q": text, "source": "fa", "target": "en"
        })
        return response.json()["translatedText"]
    except:
        return text

# بررسی عضویت
async def check_membership(user_id, context: ContextTypes.DEFAULT_TYPE):
    try:
        for chat_id in [CHANNEL_1, CHANNEL_2, GROUP_ID]:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ["member", "administrator", "creator"]:
                return False
        return True
    except:
        return False

# دکمه عضویت
def get_join_buttons():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("کانال ۱", url=CHANNEL_1_LINK),
        InlineKeyboardButton("کانال ۲", url=CHANNEL_2_LINK)
    ], [
        InlineKeyboardButton("گروه اسپانسر", url=GROUP_LINK)
    ], [
        InlineKeyboardButton("✅ عضو شدم", callback_data="joined")
    ]])

# دستورات فقط در چت خصوصی
def private_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type != "private":
            return
        return await func(update, context)
    return wrapper

# پاسخ به /start
@private_only
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    is_member = await check_membership(user.id, context)
    if not is_member:
        await update.message.reply_text(
            "برای استفاده از ربات لطفاً ابتدا در کانال‌ها و گروه زیر عضو شوید 👇",
            reply_markup=get_join_buttons()
        )
        return
    await update.message.reply_text(
        "🎉 به ربات عمو عکسی خوش آمدید!\n\n"
        "📷 با ارسال دستور /prompt یک متن را به عکس تبدیل کنید\n"
        "🎌 با ارسال عکس، آن را به انیمه تبدیل کنید با /anime\n\n"
        "⏱ بین هر درخواست باید حداقل {} دقیقه فاصله باشد.".format(TIME_LIMIT // 60)
    )
    user_ids.add(user.id)

# بررسی دکمه "عضو شدم"
@private_only
async def joined(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    is_member = await check_membership(user.id, context)
    if is_member:
        await query.message.reply_text("✅ عضویت شما تایید شد، حالا می‌تونید از ربات استفاده کنید.")
    else:
        await query.message.reply_text("⛔ هنوز عضو نشدید. لطفاً ابتدا در کانال‌ها و گروه عضو شوید.")

# محدودیت زمانی
def check_limit(user_id):
    from time import time
    now = time()
    if user_id not in user_last_call or now - user_last_call[user_id] > TIME_LIMIT:
        user_last_call[user_id] = now
        return True, 0
    remaining = int(TIME_LIMIT - (now - user_last_call[user_id]))
    return False, remaining

# /prompt برای ساخت عکس از متن
@private_only
async def prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    allowed, remaining = check_limit(user.id)
    if not allowed:
        await update.message.reply_text(f"⏱ لطفاً {remaining} ثانیه صبر کن.")
        return
    await update.message.reply_text("🖼 در حال ساخت تصویر...")
    prompt_text = " ".join(context.args)
    prompt_en = translate_to_english(prompt_text)
    output = replicate.run(
        "stability-ai/stable-diffusion:db21e45a", 
        input={"prompt": prompt_en},
        api_token=REPLICATE_TOKEN
    )
    if output:
        await update.message.reply_photo(output[0])
    else:
        await update.message.reply_text("⚠️ مشکلی در ساخت تصویر پیش آمد.")

# /anime برای تبدیل عکس به انیمه
@private_only
async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📷 لطفاً عکسی را ارسال کنید تا به انیمه تبدیل شود.")

@private_only
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    allowed, remaining = check_limit(user.id)
    if not allowed:
        await update.message.reply_text(f"⏱ لطفاً {remaining} ثانیه صبر کن.")
        return
    photo = update.message.photo[-1]
    file = await photo.get_file()
    await update.message.reply_text("🖼 در حال تبدیل عکس به انیمه...")
    image_url = file.file_path
    output = replicate.run(
        "cjwbw/animeganv2:fc252fcb", 
        input={"image": image_url},
        api_token=REPLICATE_TOKEN
    )
    if output:
        await update.message.reply_photo(output[0])
    else:
        await update.message.reply_text("⚠️ تبدیل موفق نبود.")

# /help
@private_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start - شروع\n"
        "/help - راهنما\n"
        "/prompt [متن] - تبدیل متن به تصویر\n"
        "/anime - تبدیل عکس به انیمه\n"
        "/stats - آمار کاربران (ادمین)"
    )

# /stats فقط برای ادمین
@private_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        f"👥 تعداد کاربران: {len(user_ids)}"
    )

# اجرای ربات
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(joined, pattern="joined"))
    app.add_handler(CommandHandler("prompt", prompt))
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))
    app.run_polling()

if __name__ == "__main__":
    main()
