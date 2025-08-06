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
USERS_FILE = "users.json"
USED_PHOTOS_FILE = "used_photos.json"
POSTED_FILE = "posted.json"

forward_mode = False

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

users = load_users()

def load_used_photos():
    if os.path.exists(USED_PHOTOS_FILE):
        with open(USED_PHOTOS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_used_photos(photo_ids):
    with open(USED_PHOTOS_FILE, "w") as f:
        json.dump(list(photo_ids), f)

used_photo_ids = load_used_photos()

def load_posted_ids():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return json.load(f)
    return []

def save_posted_ids(posted_ids):
    with open(POSTED_FILE, "w") as f:
        json.dump(posted_ids, f, indent=2)

posted_ids = load_posted_ids()

@dp.message_handler(commands=["enable_forward_mode"])
async def enable_forward_mode(message: types.Message):
    global forward_mode
    if message.from_user.id != ADMIN_ID:
        return
    forward_mode = True
    await message.answer("📥 حالت فوروارد فعال شد عمو! شروع کن به فوروارد کردن عکس‌ها از کانال.")

@dp.message_handler(commands=["disable_forward_mode"])
async def disable_forward_mode(message: types.Message):
    global forward_mode
    if message.from_user.id != ADMIN_ID:
        return
    forward_mode = False
    await message.answer("✅ حالت فوروارد غیرفعال شد عمو! دیگه چیزی ثبت نمی‌کنم.")

@dp.message_handler(lambda m: m.forward_from_chat and m.forward_from_chat.username == CHANNEL_3.replace("@", "") and forward_mode)
async def handle_forwarded_photo(message: types.Message):
    if not message.photo:
        return
    msg_id = message.message_id
    if msg_id in posted_ids:
        await message.reply("⏩ این یکی قبلاً ثبت شده بود عمو!")
        return
    posted_ids.append(msg_id)
    save_posted_ids(posted_ids)
    await message.reply("📸 اینم ثبت شد عمو! برو عکس بعدی!")

# (تمامی کدهای قبلی بدون تغییر می‌مانند)
# آخر کد

async def on_startup(dp):
    await bot.delete_webhook(drop_pending_updates=True)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
