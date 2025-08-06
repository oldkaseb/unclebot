import logging
import os
import random
import requests
import json
from datetime import datetime
from PIL import Image
from io import BytesIO
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from aiogram.utils.exceptions import BadRequest

logging.basicConfig(level=logging.INFO)

REQUIRED_ENV_VARS = ["BOT_TOKEN", "CHANNEL_1", "CHANNEL_2", "CHANNEL_3", "CHANNEL_1_LINK", "CHANNEL_2_LINK", "CHANNEL_3_LINK", "ADMIN_ID"]
for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        raise ValueError(f"Missing required environment variable: {var}")

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_3 = os.getenv("CHANNEL_3")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
CHANNEL_3_LINK = os.getenv("CHANNEL_3_LINK")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

sent_cache = {}
user_input_mode = {}

USERS_FILE = "users.json"
USED_PHOTOS_FILE = "used_photos.json"
POSTED_FILE = "posted.json"
FORWARD_MODE_FILE = "forward_mode.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def load_used_photos():
    if os.path.exists(USED_PHOTOS_FILE):
        with open(USED_PHOTOS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_used_photos(photo_ids):
    with open(USED_PHOTOS_FILE, "w") as f:
        json.dump(list(photo_ids), f)

def load_posted_ids():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return json.load(f)
    return []

def save_posted_ids(posted_ids):
    with open(POSTED_FILE, "w") as f:
        json.dump(posted_ids, f, indent=2)

def load_forward_mode():
    if os.path.exists(FORWARD_MODE_FILE):
        with open(FORWARD_MODE_FILE, "r") as f:
            return json.load(f).get("enabled", False)
    return False

def save_forward_mode(status):
    with open(FORWARD_MODE_FILE, "w") as f:
        json.dump({"enabled": status}, f)

users = load_users()
used_photo_ids = load_used_photos()
posted_ids = load_posted_ids()
forward_mode = load_forward_mode()

@dp.message_handler(commands=["openforward"])
async def open_forward_mode(message: types.Message):
    global forward_mode
    if message.from_user.id != ADMIN_ID:
        return
    forward_mode = True
    save_forward_mode(True)
    await message.answer("✅ حالت دریافت فوروارد باز شد عمو")

@dp.message_handler(commands=["closeforward"])
async def close_forward_mode(message: types.Message):
    global forward_mode
    if message.from_user.id != ADMIN_ID:
        return
    forward_mode = False
    save_forward_mode(False)
    await message.answer("❌ حالت دریافت فوروارد بسته شد عمو")

@dp.message_handler(lambda m: m.forward_from_chat and str(m.forward_from_chat.id) == str(CHANNEL_3))
async def auto_add_forwarded_photo(message: types.Message):
    global forward_mode
    if not forward_mode:
        return
    if message.from_user.id != ADMIN_ID:
        return
    msg_id = message.forward_from_message_id
    if msg_id in posted_ids:
        await message.answer("این عکس قبلاً تو لیست بود عمو 👴")
        return
    posted_ids.append(msg_id)
    save_posted_ids(posted_ids)
    await message.answer("✅ این یکی هم رفت تو آرشیو عمو! 😎")

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = str(message.from_user.id)
    if user_id not in users:
        users[user_id] = {
            "name": message.from_user.full_name,
            "username": message.from_user.username,
            "joined_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_users(users)
    sent_cache[message.from_user.id] = set()
    await show_subscription_check(message)

async def show_subscription_check(message):
    text = "اول تو کانالا عضو شو عمو جون"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("کانال دکتر گشاد", url=CHANNEL_1_LINK),
        InlineKeyboardButton("کانال تیم", url=CHANNEL_2_LINK),
        InlineKeyboardButton("کانال خود عمو عکسی", url=CHANNEL_3_LINK),
        InlineKeyboardButton("عضو شدم عمو جون", callback_data="check_subs")
    )
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "check_subs")
async def check_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    async def is_member(channel):
        try:
            member = await bot.get_chat_member(channel, user_id)
            return member.status in ["member", "creator", "administrator"]
        except:
            return False
    if await is_member(CHANNEL_1) and await is_member(CHANNEL_2) and await is_member(CHANNEL_3):
        await show_main_menu(callback.message)
    else:
        await callback.answer("عضویت کامل نیست عمو جون لطفا عضو شو.", show_alert=True)

async def show_main_menu(message):
    text = "به ربات عمو عکسی خوش اومدی!"
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("عکس از کانال عمو"),
        KeyboardButton("جستجوی دلخواه")
    ).add(
        KeyboardButton("درباره من"),
        KeyboardButton("تماس با مالک عمو عکسی")
    )
    await message.answer(text, reply_markup=keyboard)

# [ادامه کد بدون تغییر می‌ماند ... فقط قسمت‌های مربوط به حالت فوروارد افزوده شدند]

async def on_startup(dp):
    await bot.delete_webhook(drop_pending_updates=True)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
