import os
import json
import random
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.utils import executor
from aiogram.dispatcher.filters import CommandStart, CommandHelp

# بارگیری متغیرهای محیطی
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
USED_FILE = "used_photos.json"
USERS_FILE = "users.json"
STATE_FILE = "search_state.json"

# توابع کمکی

def load_json(filename):
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f)

# بررسی عضویت در 2 کانال
async def check_membership(user_id):
    result = True
    for channel in [CHANNEL_1, CHANNEL_2]:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                result = False
        except:
            result = False
    return result

# کیبورد عضویت

def join_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 کانال 1", url=CHANNEL_1_LINK))
    kb.add(InlineKeyboardButton("📢 کانال 2", url=CHANNEL_2_LINK))
    kb.add(InlineKeyboardButton("✅ عضو شدم عمو جون", callback_data="check_join"))
    return kb

# منوی اصلی

def main_menu():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📸 عکس به سلیقه عمو", callback_data="random"))
    kb.add(InlineKeyboardButton("🔍 جستجوی دلخواه", callback_data="search"))
    kb.add(InlineKeyboardButton("ℹ️ درباره من", callback_data="about"))
    kb.add(InlineKeyboardButton("💬 تماس با مالک عمو عکسی", url=f"https://t.me/{CHANNEL_3_LINK.replace('@', '')}"))
    return kb

# دکمه های درخواست مجدد

def retry_keyboard(mode):
    kb = InlineKeyboardMarkup()
    if mode == "random":
        kb.add(InlineKeyboardButton("🔁 درخواست مجدد", callback_data="random"))
    else:
        kb.add(InlineKeyboardButton("🔁 جستجوی مجدد", callback_data="search"))
    kb.add(InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="menu"))
    return kb

# /start
@dp.message_handler(CommandStart())
async def start(message: types.Message):
    users = load_json(USERS_FILE)
    uid = str(message.from_user.id)
    if uid not in users:
        users[uid] = {
            "name": message.from_user.full_name,
            "username": message.from_user.username,
            "joined": message.date.isoformat()
        }
        save_json(USERS_FILE, users)
    if await check_membership(message.from_user.id):
        await message.answer("🌟 به عمو عکسی خوش اومدی! یه کاری بکن:", reply_markup=main_menu())
    else:
        await message.answer("اول باید عضو دو کانال بشی:", reply_markup=join_keyboard())

# /help
@dp.message_handler(CommandHelp())
async def help_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("/stats /send /addphoto /post")

# /stats
@dp.message_handler(commands=["stats"])
async def stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    users = load_json(USERS_FILE)
    await message.answer(f"📈 تعداد کاربر: {len(users)}")

# /send
@dp.message_handler(commands=["send"])
async def send_all(message: types.Message):
    if message.from_user.id != ADMIN_ID or not message.reply_to_message:
        return
    users = load_json(USERS_FILE)
    for uid in users:
        try:
            await message.copy_to(chat_id=int(uid), from_chat_id=message.chat.id, message_id=message.reply_to_message.message_id)
        except:
            pass
    await message.answer("ارسال شد.")

# /addphoto
@dp.message_handler(commands=["addphoto"])
async def add_photo(message: types.Message):
    if message.from_user.id != ADMIN_ID or not message.reply_to_message:
        return
    posted = load_json(POSTED_FILE)
    posted.setdefault("photo_ids", []).append(str(message.reply_to_message.message_id))
    save_json(POSTED_FILE, posted)
    await message.answer("ثبت شد.")

# /post
@dp.message_handler(commands=["post"])
async def post_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID or not message.reply_to_message:
        return
    sent = await message.copy_to(chat_id=CHANNEL_3, from_chat_id=message.chat.id, message_id=message.reply_to_message.message_id)
    posted = load_json(POSTED_FILE)
    posted.setdefault("photo_ids", []).append(str(sent.message_id))
    save_json(POSTED_FILE, posted)
    await message.answer("ارسال شد به کانال.")

# Callback handlers
@dp.callback_query_handler()
async def callbacks(call: types.CallbackQuery):
    uid = call.from_user.id
    if not await check_membership(uid):
        await call.message.edit_text("اول عضو شو!", reply_markup=join_keyboard())
        return
    if call.data == "check_join":
        await call.message.edit_text("عضو شدی آفرین!", reply_markup=main_menu())
    elif call.data == "menu":
        await call.message.edit_text("🌟 به منوی اصلی خوش امدی", reply_markup=main_menu())
    elif call.data == "about":
        await call.message.edit_text("📸 ربات عمو عکسی ویژه عکسای باحاله.", reply_markup=retry_keyboard("menu"))
    elif call.data == "random":
        await send_random_photo(uid, call.message)
    elif call.data == "search":
        state = load_json(STATE_FILE)
        state[str(uid)] = True
        save_json(STATE_FILE, state)
        await call.message.edit_text("یه کلمه بفرست:")

# ارسال عکس صدفی
async def send_random_photo(user_id, message):
    posted = load_json(POSTED_FILE).get("photo_ids", [])
    used = load_json(USED_FILE)
    available = list(set(posted) - set(used.get(str(user_id), [])))
    if not available:
        await message.edit_text("فعلا عکس ندارم.")
        return
    selected = random.choice(available)
    await bot.copy_message(chat_id=user_id, from_chat_id=CHANNEL_3, message_id=int(selected))
    used.setdefault(str(user_id), []).append(selected)
    save_json(USED_FILE, used)
    await message.answer("اینم عکست:", reply_markup=retry_keyboard("random"))

# پیام کاربر برای جستجو
@dp.message_handler()
async def handle_search(message: types.Message):
    state = load_json(STATE_FILE)
    uid = str(message.from_user.id)
    if not state.get(uid):
        return
    state[uid] = False
    save_json(STATE_FILE, state)
    photos = await search_photos(message.text)
    if photos:
        media = [InputMediaPhoto(url) for url in photos]
        await message.answer_media_group(media)
        await message.answer("پایان جستجو:", reply_markup=retry_keyboard("search"))
    else:
        await message.answer("کاری نتونستم بکنم.", reply_markup=retry_keyboard("search"))

# جستجو در API
async def search_photos(query):
    urls = []
    async with aiohttp.ClientSession() as s:
        try:
            u_url = f"https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}&count=3"
            async with s.get(u_url) as r:
                data = await r.json()
                urls.extend([i['urls']['regular'] for i in data])
        except: pass
        try:
            px_h = {"Authorization": PEXELS_API_KEY}
            px_url = f"https://api.pexels.com/v1/search?query={query}&per_page=3"
            async with s.get(px_url, headers=px_h) as r:
                data = await r.json()
                urls.extend([p['src']['medium'] for p in data.get('photos', [])])
        except: pass
        try:
            pb_url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&per_page=3"
            async with s.get(pb_url) as r:
                data = await r.json()
                urls.extend([h['webformatURL'] for h in data.get('hits', [])])
        except: pass
    return urls[:10]

# start polling
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
