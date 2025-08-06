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

forward_mode_enabled = False

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

@dp.message_handler(lambda msg: msg.text.startswith("راهنما") or msg.text.startswith("درباره") or msg.text.startswith("تماس"))
async def static_pages(message: types.Message):
    if "راهنما" in message.text:
        await message.answer("برای دریافت عکس میتونی با متن دلخواه سرچ کنی یا از خود کانال عمو عکسی یه عکس بگیری")
    elif "درباره" in message.text:
        await message.answer("عمو عکسی رو تیم SOULS ساخته")
    elif "تماس" in message.text:
        await message.answer("با مالک صحبت کن: @soulsownerbot")

@dp.message_handler(lambda msg: msg.text == "عکس از کانال عمو")
async def send_random_channel_photo(message: types.Message):
    try:
        candidates = [msg_id for msg_id in posted_ids if str(msg_id) not in used_photo_ids]
        if not candidates:
            await message.answer("هیچ عکس جدیدی پیدا نکردم عمو! همه تکراری بودن 😢")
            return
        msg_id = random.choice(candidates)
        used_photo_ids.add(str(msg_id))
        save_used_photos(used_photo_ids)
        await bot.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_3, message_id=msg_id)
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📸 یه دونه دیگه عمو", callback_data="more_channel_photo")
        )
        await message.answer("عمو یه عکس دیگه می‌خوای؟", reply_markup=keyboard)
    except:
        await message.answer("❌ ارسال عکس از کانال با خطا مواجه شد عمو")

@dp.callback_query_handler(lambda c: c.data == "more_channel_photo")
async def handle_more_channel_photo(callback: types.CallbackQuery):
    await callback.message.delete_reply_markup()
    await send_random_channel_photo(callback.message)

@dp.message_handler(commands=["enable_forward_mode"])
async def enable_forward_mode(message: types.Message):
    global forward_mode_enabled
    if message.from_user.id != ADMIN_ID:
        return
    forward_mode_enabled = True
    await message.answer("🔓 حالت فوروارد فعال شد. حالا می‌تونی عکس‌ها رو فوروارد کنی تا ذخیره بشن.")

@dp.message_handler(commands=["disable_forward_mode"])
async def disable_forward_mode(message: types.Message):
    global forward_mode_enabled
    if message.from_user.id != ADMIN_ID:
        return
    forward_mode_enabled = False
    await message.answer("🔒 حالت فوروارد غیرفعال شد.")

@dp.message_handler(content_types=types.ContentType.PHOTO)
async def handle_forwarded_photo(message: types.Message):
    global forward_mode_enabled
    if message.from_user.id != ADMIN_ID:
        return
    if not forward_mode_enabled:
        return
    if not message.forward_from_chat or not message.forward_from_message_id:
        return
    if message.forward_from_chat.id != int(CHANNEL_3):
        return
    mid = str(message.forward_from_message_id)
    if mid in used_photo_ids:
        await message.answer("⛔️ این عکس قبلاً ثبت شده عمو جون.")
        return
    used_photo_ids.add(mid)
    save_used_photos(used_photo_ids)
    await message.answer("✅ عکس با موفقیت ذخیره شد عمو جون.")
