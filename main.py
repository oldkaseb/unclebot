import os
import json
import random
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from aiogram.utils import executor
from aiogram.dispatcher.filters import CommandStart, CommandHelp

# Load environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_3 = os.getenv("CHANNEL_3")

CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
CHANNEL_3_LINK = os.getenv("CHANNEL_3_LINK")

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# فایل‌های ذخیره‌سازی
POSTED_FILE = "posted.json"
USED_PHOTOS_FILE = "used_photos.json"
USERS_FILE = "users.json"

# توابع کمکی برای خواندن و نوشتن فایل
def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)

# بررسی عضویت کاربر در دو کانال
async def check_membership(user_id):
    for channel in [CHANNEL_1, CHANNEL_2]:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                return False
        except:
            return False
    return True

# کیبورد بررسی عضویت
def join_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📢 کانال 1", url=CHANNEL_1_LINK))
    keyboard.add(InlineKeyboardButton("📢 کانال 2", url=CHANNEL_2_LINK))
    keyboard.add(InlineKeyboardButton("✅ عضو شدم عمو جون", callback_data="check_join"))
    return keyboard

# منوی اصلی
def main_menu():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("📸 عکس به سلیقه عمو", callback_data="random_photo"))
    keyboard.add(InlineKeyboardButton("🔍 جستجوی دلخواه", callback_data="search"))
    keyboard.add(InlineKeyboardButton("ℹ️ درباره من", callback_data="about"))
    keyboard.add(InlineKeyboardButton("💬 تماس با مالک عمو عکسی", url=f"https://t.me/{CHANNEL_3_LINK.replace('@','')}"))
    return keyboard

# شروع ربات
@dp.message_handler(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    users = load_json(USERS_FILE)
    if str(user_id) not in users:
        users[str(user_id)] = {
            "name": message.from_user.full_name,
            "username": message.from_user.username,
            "joined": message.date.isoformat()
        }
        save_json(USERS_FILE, users)

    if await check_membership(user_id):
        await message.answer("سلام به عمو عکسی خوش اومدی! 📸\nیه عکس توپ برات دارم، یکیو انتخاب کن:", reply_markup=main_menu())
    else:
        await message.answer("برای استفاده از ربات باید تو کانال‌های زیر عضو بشی:", reply_markup=join_keyboard())

# بررسی مجدد عضویت
@dp.callback_query_handler(lambda c: c.data == "check_join")
async def check_join(callback: types.CallbackQuery):
    if await check_membership(callback.from_user.id):
        await callback.message.edit_text("عضویتت تایید شد، بیا عکس بگیریم! 🎉", reply_markup=main_menu())
    else:
        await callback.answer("هنوز عضو نشدی 😕", show_alert=True)

# درباره من
@dp.callback_query_handler(lambda c: c.data == "about")
async def about(callback: types.CallbackQuery):
    text = "📸 ربات عمو عکسی برای ارسال عکس‌های باحال و خاص ساخته شده.\nتوسعه‌دهنده: @whitewolf.has5\nمنبع عکس‌ها: Unsplash، Pexels، Pixabay"
    await callback.message.edit_text(text, reply_markup=main_menu())

# ارسال عکس تصادفی از لیست ذخیره شده توسط ادمین
@dp.callback_query_handler(lambda c: c.data == "random_photo")
async def random_photo(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    posted = load_json(POSTED_FILE).get("photo_ids", [])
    used = load_json(USED_PHOTOS_FILE)

    available = list(set(posted) - set(used.get(user_id, [])))
    if not available:
        await callback.message.answer("فعلاً عکس جدیدی ندارم! 🙈")
        return

    selected = random.choice(available)
    await bot.copy_message(chat_id=user_id, from_chat_id=CHANNEL_3, message_id=int(selected))

    used.setdefault(user_id, []).append(selected)
    save_json(USED_PHOTOS_FILE, used)

# دریافت کلمه جستجو
@dp.callback_query_handler(lambda c: c.data == "search")
async def ask_search(callback: types.CallbackQuery):
    await callback.message.answer("یه کلمه بفرست تا برات عکساشو پیدا کنم 📸")

@dp.message_handler(lambda message: not message.text.startswith("/"))
async def search_photo(message: types.Message):
    query = message.text
    photos = await fetch_photos(query)
    if photos:
        media = [InputMediaPhoto(url) for url in photos]
        await message.answer_media_group(media)
    else:
        await message.answer("چیزی پیدا نکردم 😞 دوباره امتحان کن.")

# جستجو در API ها
async def fetch_photos(query):
    urls = []
    async with aiohttp.ClientSession() as session:
        # Unsplash
        u_url = f"https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}&count=3"
        async with session.get(u_url) as resp:
            if resp.status == 200:
                data = await resp.json()
                urls.extend([item['urls']['regular'] for item in data])

        # Pexels
        pex_headers = {"Authorization": PEXELS_API_KEY}
        p_url = f"https://api.pexels.com/v1/search?query={query}&per_page=3"
        async with session.get(p_url, headers=pex_headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                urls.extend([photo['src']['medium'] for photo in data.get('photos', [])])

        # Pixabay
        pb_url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&per_page=3"
        async with session.get(pb_url) as resp:
            if resp.status == 200:
                data = await resp.json()
                urls.extend([hit['webformatURL'] for hit in data.get('hits', [])])

    return urls

# دستورات ادمینی
@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = "/stats - آمار کاربران\n/send - پیام همگانی (ریپلای کن)\n/addphoto - افزودن عکس به ربات\n/post - ارسال به کانال سوم"
    await message.answer(text)

@dp.message_handler(commands=["stats"])
async def stats_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = load_json(USERS_FILE)
    await message.answer(f"👥 تعداد کاربران: {len(users)}")

@dp.message_handler(commands=["send"])
async def send_all(message: types.Message):
    if message.from_user.id != ADMIN_ID or not message.reply_to_message:
        return
    users = load_json(USERS_FILE)
    for user_id in users.keys():
        try:
            await message.copy_to(chat_id=int(user_id), from_chat_id=message.chat.id, message_id=message.reply_to_message.message_id)
        except:
            pass
    await message.answer("📤 پیام همگانی ارسال شد.")

@dp.message_handler(commands=["addphoto"])
async def add_photo(message: types.Message):
    if message.from_user.id != ADMIN_ID or not message.reply_to_message:
        return
    posted = load_json(POSTED_FILE)
    photo_ids = posted.get("photo_ids", [])
    photo_ids.append(str(message.reply_to_message.message_id))
    posted["photo_ids"] = list(set(photo_ids))
    save_json(POSTED_FILE, posted)
    await message.answer("✅ عکس ثبت شد.")

@dp.message_handler(commands=["post"])
async def post_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID or not message.reply_to_message:
        return
    sent = await message.copy_to(chat_id=CHANNEL_3, from_chat_id=message.chat.id, message_id=message.reply_to_message.message_id)
    posted = load_json(POSTED_FILE)
    posted.setdefault("photo_ids", []).append(str(sent.message_id))
    save_json(POSTED_FILE, posted)
    await message.answer("📤 به کانال سوم ارسال شد.")

# اجرا
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
