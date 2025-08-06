import logging
import os
import random
import json
from datetime import datetime
from PIL import Image
from io import BytesIO
import requests
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
GROUP_LINK = os.getenv("GROUP_LINK")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY")

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

sent_cache = {}
CHANNEL_PHOTO_CACHE = set()
allow_search = set()
USERS_FILE = "users.json"

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

users = load_users()

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
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("کانال دکتر گشاد", url=CHANNEL_1_LINK),
        InlineKeyboardButton("کانال تیم", url=CHANNEL_2_LINK),
        InlineKeyboardButton("کانال عکس و بیو", url=CHANNEL_3_LINK),
        InlineKeyboardButton("عضو شدم عمو جون", callback_data="check_subs")
    )
    await message.answer("اول تو کانالا عضو شو عمو جون", reply_markup=keyboard)

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
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("عکس از کانال عمو"),
        KeyboardButton("جستجوی دلخواه")
    ).add(
        KeyboardButton("درباره من"),
        KeyboardButton("تماس با مالک عمو عکسی")
    )
    await message.answer("به ربات عمو عکسی خوش اومدی بریم با هم دنبال عکس با متنی که میدی بگردیم یا از گزینه‌های زیر استفاده کن", reply_markup=keyboard)

@dp.message_handler(lambda msg: msg.text.startswith("درباره"))
async def about(message: types.Message):
    await message.answer("عمو عکسی رو تیم SOULS ساخته برای راحت تر کردن سرچ عکس ها")

@dp.message_handler(lambda msg: msg.text.startswith("تماس"))
async def contact(message: types.Message):
    await message.answer("با مالک عمو عکسی حرف بزن: @soulsownerbot")

@dp.message_handler(lambda msg: msg.text == "عکس از کانال عمو")
async def send_random_channel_photo(message: types.Message):
    try:
        messages = await bot.get_chat_history(chat_id=CHANNEL_3, limit=100)
        candidates = [m for m in messages if m.photo and str(m.message_id) not in CHANNEL_PHOTO_CACHE]
        if not candidates:
            await message.answer("عکسی برای ارسال پیدا نکردم یا همه تکراری بودن عمو جون 😢")
            return
        msg = random.choice(candidates)
        CHANNEL_PHOTO_CACHE.add(str(msg.message_id))
        await bot.copy_message(chat_id=message.chat.id, from_chat_id=CHANNEL_3, message_id=msg.message_id)
        keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("یدونه دیگه عمو", callback_data="again_photo"))
        await message.answer("یه عکس دیگه میخوای؟", reply_markup=keyboard)
    except:
        await message.answer("ارسال عکس از کانال با خطا مواجه شد عمو ❌")

@dp.callback_query_handler(lambda c: c.data == "again_photo")
async def send_another_photo(callback: types.CallbackQuery):
    await callback.message.delete_reply_markup()
    await send_random_channel_photo(callback.message)

@dp.message_handler(lambda msg: msg.text == "جستجوی دلخواه")
async def ask_for_custom_query(message: types.Message):
    allow_search.add(message.from_user.id)
    await message.answer("چی پیدا کنم برات عمو جون بخواه فداتشم|تایپ کن من میرم میارم")

@dp.callback_query_handler(lambda c: c.data == "again")
async def retry_suggestions(callback: types.CallbackQuery):
    allow_search.add(callback.from_user.id)
    await callback.message.delete_reply_markup()
    await callback.message.answer("چی پیدا کنم برات عمو جون بخواه فداتشم|تایپ کن من میرم میارم")

@dp.message_handler(commands=["stats"])
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer(f"تعداد کل کاربران: {len(users)}")

@dp.message_handler(commands=["forall"])
async def broadcast_entry(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        await message.reply("برای ارسال همگانی باید روی پیام ریپلای کنی.")
        return
    count = 0
    for uid in users:
        try:
            await message.reply_to_message.copy_to(chat_id=int(uid))
            count += 1
        except:
            continue
    await message.reply(f"پیام به {count} کاربر ارسال شد.")

@dp.message_handler(commands=["post"])
async def post_to_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        await message.reply("برای ارسال به کانال باید روی پیام ریپلای کنی.")
        return
    try:
        await message.reply_to_message.copy_to(chat_id=CHANNEL_3)
        await message.reply("پست با موفقیت در کانال منتشر شد.")
    except:
        await message.reply("ارسال پست به کانال ناموفق بود.")

@dp.message_handler(commands=["help"])
async def help_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply(
        "/stats - آمار کاربران\n"
        "/forall - ارسال پیام همگانی (ریپلای کن)\n"
        "/post - ارسال پست در کانال (ریپلای کن)"
    )

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_custom_query(message: types.Message):
    if message.text.startswith("/") or message.from_user.id not in allow_search:
        return
    allow_search.discard(message.from_user.id)
    await fetch_and_send_images(message, message.text, message.from_user.id)
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("عمو عمو دوباره", callback_data="again"))
    await message.answer("میخوای دوباره جستوجو کنی عمو؟", reply_markup=keyboard)

def unsplash_fetch(query):
    try:
        url = f"https://api.unsplash.com/search/photos?query={query}&per_page=30&client_id={UNSPLASH_KEY}"
        r = requests.get(url)
        data = r.json()
        return [item["urls"]["regular"] for item in data.get("results", [])]
    except:
        return []

def pexels_fetch(query):
    try:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=30"
        headers = {"Authorization": PEXELS_KEY}
        r = requests.get(url, headers=headers)
        data = r.json()
        return [item["src"]["large"] for item in data.get("photos", [])]
    except:
        return []

def pixabay_fetch(query):
    try:
        url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={query}&image_type=photo&per_page=30"
        r = requests.get(url)
        data = r.json()
        return [item["largeImageURL"] for item in data.get("hits", [])]
    except:
        return []

def make_square_image_from_url(url):
    try:
        response = requests.get(url)
        if len(response.content) < 100 * 1024:
            return None
        img = Image.open(BytesIO(response.content)).convert("RGB")
        min_side = min(img.size)
        left = (img.width - min_side) // 2
        top = (img.height - min_side) // 2
        cropped = img.crop((left, top, left + min_side, top + min_side))
        output = BytesIO()
        output.name = "profile.jpg"
        cropped.save(output, format="JPEG")
        output.seek(0)
        return output
    except:
        return None

async def fetch_and_send_images(message, query, user_id):
    await message.answer("عمو داره سرچ میکنه...")
    imgs = unsplash_fetch(query) + pexels_fetch(query) + pixabay_fetch(query)
    random.shuffle(imgs)
    new_imgs = []
    seen = sent_cache.setdefault(user_id, set())

    for url in imgs:
        if url in seen:
            continue
        file = make_square_image_from_url(url)
        if file:
            new_imgs.append(InputMediaPhoto(media=file))
            seen.add(url)
        if len(new_imgs) >= 10:
            break

    if new_imgs:
        await bot.send_media_group(message.chat.id, new_imgs)
        await message.answer("عمو برات عکس اورده")
    else:
        await message.answer("چیز به درد بخوری پیدا نکردم عمو")

# حذف وبهوک
import asyncio
async def on_startup(dp):
    await bot.delete_webhook(drop_pending_updates=True)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
