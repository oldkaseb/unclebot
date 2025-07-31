import os import time import logging import requests from datetime import datetime from dotenv import load_dotenv from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN") ADMIN_ID = int(os.getenv("ADMIN_ID")) TIME_LIMIT = int(os.getenv("TIME_LIMIT_MIN")) * 60 GROUP_ID = os.getenv("GROUP_ID") CHANNEL_1 = os.getenv("CHANNEL_1") CHANNEL_2 = os.getenv("CHANNEL_2") GROUP_LINK = os.getenv("GROUP_LINK") REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")

user_last_call = {} blocked_users = set() user_ids = set()

------------------ ترجمه فارسی به انگلیسی ------------------
def translate_to_english(text): try: response = requests.post("https://libretranslate.de/translate", data={ "q": text, "source": "fa", "target": "en", "format": "text" }) return response.json().get("translatedText", text) except: return text # fallback

------------------ Replicate API ------------------
def generate_image(prompt): prompt_en = translate_to_english(prompt) url = "https://api.replicate.com/v1/predictions" headers = { "Authorization": f"Token {REPLICATE_API_TOKEN}", "Content-Type": "application/json" } data = { "version": "db21e45d3d6946f8a3b01b6109b5ff960c8b6b9fb24dc3b00a7a63196e1c6531", "input": {"prompt": prompt_en} } response = requests.post(url, json=data, headers=headers).json() return response.get("urls", {}).get("get")

def convert_to_anime(image_url): url = "https://api.replicate.com/v1/predictions" headers = { "Authorization": f"Token {REPLICATE_API_TOKEN}", "Content-Type": "application/json" } data = { "version": "e214055e2d22c1a749ee8f74964ba2e556099fcbd81cbfb8a2d849258ddcd837", "input": {"image": image_url} } response = requests.post(url, json=data, headers=headers).json() return response.get("urls", {}).get("get")

def check_replicate_usage(context): usage = requests.get("https://api.replicate.com/v1/account/usage", headers={ "Authorization": f"Token {REPLICATE_API_TOKEN}" }).json() remaining = usage.get("total_usage", {}).get("remaining", 999) if remaining < 20: context.bot.send_message(chat_id=ADMIN_ID, text=f"⚠️ فقط {remaining} استفاده از Replicate باقی مونده!")

------------------ عضویت ------------------
async def check_membership(user_id, context): async def is_member(chat_id): if not chat_id: return False try: member = await context.bot.get_chat_member(chat_id, user_id) return member.status in ["member", "administrator", "creator"] except: return False return all([ await is_member(CHANNEL_1), await is_member(CHANNEL_2), await is_member(GROUP_ID) ])

------------------ /start ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE): user_id = update.effective_user.id user_ids.add(user_id) if user_id in blocked_users: return

if not await check_membership(user_id, context):
    keyboard = [
        [InlineKeyboardButton("📸 عضویت در کانال ۱", url=f"https://t.me/{CHANNEL_1}")],
        [InlineKeyboardButton("🎨 عضویت در کانال ۲", url=f"https://t.me/{CHANNEL_2}")],
        [InlineKeyboardButton("💬 گروه اسپانسر", url=GROUP_LINK)]
    ]
    await update.message.reply_text("لطفاً ابتدا عضو کانال‌ها و گروه اسپانسر شوید 👇", reply_markup=InlineKeyboardMarkup(keyboard))
    return

keyboard = [
    [InlineKeyboardButton("🖼 ساخت تصویر از متن", callback_data='text_to_image')],
    [InlineKeyboardButton("🎭 تبدیل عکس به انیمه", callback_data='photo_to_anime')],
    [InlineKeyboardButton("ℹ️ راهنما", callback_data='help')]
]
await update.message.reply_text(
    "سلام دوست عزیز! 🌟\n"
    "به ربات هوشمند تولید تصویر خوش اومدی 👋\n\n"
    "📌 لطفاً یکی از گزینه‌های زیر رو انتخاب کن تا شروع کنیم:\n"
    "⏳ برای حفظ کیفیت ربات، بین هر درخواست ۲۰ دقیقه فاصله در نظر گرفته شده.\n"
    "ممنون از صبر و همراهی‌تون ❤️",
    reply_markup=InlineKeyboardMarkup(keyboard)
)