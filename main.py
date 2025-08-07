import os
import json
import random
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.utils import executor
from aiogram.dispatcher.filters import CommandStart, CommandHelp

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_3 = os.getenv("CHANNEL_3")
CHANNEL_4 = int(os.getenv("CHANNEL_4"))

CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
CHANNEL_3_LINK = os.getenv("CHANNEL_3_LINK")

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

POSTED_FILE = "posted.json"
USED_FILE = "used_photos.json"
USERS_FILE = "users.json"
STATE_FILE = "search_state.json"

def load_json(file):
    try:
        with open(file, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f)

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

main_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("📸 عکس به سلیقه عمو"),
    KeyboardButton("🔍 جستجوی دلخواه"),
    KeyboardButton("ℹ️ درباره من"),
    KeyboardButton("💬 تماس با مالک عمو عکسی")
)

def retry_keyboard(mode):
    kb = InlineKeyboardMarkup()
    if mode == "random":
        kb.add(InlineKeyboardButton("🔁 درخواست مجدد", callback_data="random"))
    elif mode == "search":
        kb.add(InlineKeyboardButton("🔁 جستجوی مجدد", callback_data="search"))
    return kb

def join_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 کانال 1", url=CHANNEL_1_LINK))
    kb.add(InlineKeyboardButton("📢 کانال 2", url=CHANNEL_2_LINK))
    kb.add(InlineKeyboardButton("✅ عضو شدم عمو جون", callback_data="check_join"))
    return kb

@dp.message_handler(CommandStart())
async def start(message: types.Message):
    uid = str(message.from_user.id)
    users = load_json(USERS_FILE)
    if uid not in users:
        users[uid] = {
            "name": message.from_user.full_name,
            "username": message.from_user.username,
            "joined": message.date.isoformat()
        }
        save_json(USERS_FILE, users)

    if await check_membership(message.from_user.id):
        await message.answer("🎉 سلام عمو! عمو عکسی اینجاست که برات عکسای خفن بیاره! یکی از دکمه‌های پایین رو بزن:", reply_markup=main_kb)
    else:
        await message.answer("👋 عمو جون! اول باید عضو هر دوتا کانال زیر بشی تا بیام کمکت!", reply_markup=join_keyboard())

@dp.callback_query_handler(lambda c: c.data == "check_join")
async def check_join(call: types.CallbackQuery):
    if await check_membership(call.from_user.id):
        await call.message.answer("✅ آفرین عمو! حالا یکی از دکمه‌های پایین رو بزن:", reply_markup=main_kb)
    else:
        await call.message.answer("⛔️ هنوز عضو هر دو کانال نشدی عمو اذیت نکن خب!", reply_markup=join_keyboard())

@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.reply("""
📚 راهنمای ادمین عمو عکسی:

/stats - نمایش تعداد کاربران
/send - ارسال پیام همگانی (ریپلای روی پیام الزامی‌ست)
/addphoto - افزودن عکس به حافظه ربات (باید روی عکس ریپلای کنی)
        """)

@dp.message_handler(commands=["stats"])
async def stats_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        users = load_json(USERS_FILE)
        await message.reply(f"📊 کاربران ثبت‌شده: {len(users)} نفر!")

@dp.message_handler(commands=["addphoto"])
async def addphoto(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message:
        await message.reply("⛔️ ریپ بزن کصخل نوب!")
        return

    if not message.reply_to_message.photo:
        await message.reply("📛 باید عکس باشه کص مغز")
        return

    try:
        sent = await bot.copy_message(
            chat_id=CHANNEL_4,
            from_chat_id=message.chat.id,
            message_id=message.reply_to_message.message_id
        )

        posted = load_json(POSTED_FILE)
        posted.setdefault("photo_ids", []).append(str(sent.message_id))
        save_json(POSTED_FILE, posted)

        await message.reply("📥با موفقیت رفت توش🙌")
    except Exception as e:
        await message.reply(f"❌ عمو کشید بالا نتونستم بکنمش: {e}")

@dp.message_handler(commands=["send"])
async def send_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return

    if not message.reply_to_message:
        await message.reply("⛔️ هر بار یادت میره ریپ بزنی کصخلی یا ادا در میاری؟")
        return

    users = load_json(USERS_FILE)
    sent_count = 0
    error_count = 0

    await message.reply("📤 دارم میدم دستشون عمو زیادن کصکشا...")

    for uid in users:
        try:
            await bot.copy_message(
                chat_id=int(uid),
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.message_id
            )
            sent_count += 1
        except Exception as e:
            print(f"❌ نشد {uid}: {e}")
            error_count += 1

    await message.reply(f"✅ دادمش دست {sent_count} نفر جات خالی\n❌ بلاک کردن بیناموسا {error_count} نفر.")

@dp.callback_query_handler(lambda c: c.data in ["random", "search"])
async def retry_handler(call: types.CallbackQuery):
    if not await check_membership(call.from_user.id):
        await call.message.answer("⛔️ اول باید عضو هر دو کانال بشی!", reply_markup=join_keyboard())
        return
    if call.data == "random":
        await send_random(call.message, call.from_user.id)
    elif call.data == "search":
        state = load_json(STATE_FILE)
        state[str(call.from_user.id)] = True
        save_json(STATE_FILE, state)
        await call.message.answer("🔎 خب عمو جون! حالا یه کلمه بفرست تا برات عکساشو بیارم!")

async def send_random(message, user_id):
    posted = load_json(POSTED_FILE).get("photo_ids", [])
    used = load_json(USED_FILE)
    available = list(set(posted) - set(used.get(str(user_id), [])))

    if not available:
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📡 رفتن به کانال عمو عکسی", url=CHANNEL_3_LINK)
        )
        await message.answer("😅 تموم دیگه عمو عکس عمه منو نمیخوای؟ بریم تو کانالم یه دوری بزنیم پر عکسه", reply_markup=kb)
        return

    selected = random.choice(available)
    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=CHANNEL_4,
            message_id=int(selected)
        )
        used.setdefault(str(user_id), []).append(selected)
        save_json(USED_FILE, used)
        await message.answer("🎁 اینم یه عکس به سلیقه عمو عکسی برو برا رفیقات تعریف کن", reply_markup=retry_keyboard("random"))
    except Exception as e:
        await message.answer(f"⛔️ مشکلی پیش اومد عمو: {e}")

@dp.message_handler()
async def handle_message(message: types.Message):
    if message.text == "📸 عکس به سلیقه عمو":
        if not await check_membership(message.from_user.id):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard())
            return
        await send_random(message, message.from_user.id)

    elif message.text == "🔍 جستجوی دلخواه":
        if not await check_membership(message.from_user.id):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard())
            return
        state = load_json(STATE_FILE)
        state[str(message.from_user.id)] = True
        save_json(STATE_FILE, state)
        await message.reply("🔍 خب عمو، یه کلمه بفرست برات عکس بیارم!")

    elif message.text == "ℹ️ درباره من":
        await message.reply("👴 من عمو عکسی‌ام که هر عکسی بخوای دارم! باحال‌ترین ربات دنیای فارسی!")

    elif message.text == "💬 تماس با مالک عمو عکسی":
        await message.reply("📮 برای صحبت با صاحب عمو عکسی، به این ربات پیام بده: @soulsownerbot")

    else:
        state = load_json(STATE_FILE)
        if state.get(str(message.from_user.id)):
            state[str(message.from_user.id)] = False
            save_json(STATE_FILE, state)
            await message.reply("⏳ صبر کن عمو... دارم عکسای ناب برات پیدا می‌کنم...")
            await handle_search(message)

async def handle_search(message: types.Message):
    query = message.text
    photos = await search_photos(query)
    if photos:
        media = [InputMediaPhoto(url) for url in photos]
        await message.answer_media_group(media)
        await message.answer("📷 اینا رو تونستم برات پیدا کنم صفا باشه عمو!", reply_markup=retry_keyboard("search"))
    else:
        await message.answer("😢 چیزی پیدا نکردم. یه کلمه دیگه بفرست یا دوباره تلاش کن!", reply_markup=retry_keyboard("search"))

async def search_photos(query):
    urls = []
    async with aiohttp.ClientSession() as s:
        try:
            u = f"https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}&count=3"
            async with s.get(u) as r:
                data = await r.json()
                urls += [d['urls']['regular'] for d in data]
        except: pass
        try:
            h = {"Authorization": PEXELS_API_KEY}
            u = f"https://api.pexels.com/v1/search?query={query}&per_page=3"
            async with s.get(u, headers=h) as r:
                data = await r.json()
                urls += [p['src']['medium'] for p in data.get('photos', [])]
        except: pass
        try:
            u = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&per_page=3"
            async with s.get(u) as r:
                data = await r.json()
                urls += [h['webformatURL'] for h in data.get('hits', [])]
        except: pass
    return urls[:10]

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
