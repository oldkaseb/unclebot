import os
import json
import random
import aiohttp
import replicate
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from aiogram.utils import executor
from aiogram.dispatcher.filters import CommandStart, CommandHelp

# دریافت متغیرها از Railway
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
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
replicate_client = replicate.Client(api_token=REPLICATE_API_TOKEN)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# فایل‌های داده
POSTED_FILE = "posted.json"
USED_FILE = "used_photos.json"
USERS_FILE = "users.json"
STATE_FILE = "search_state.json"
HISTORY_FILE = "search_history.json"
TEXT2IMG_STATE = "text2img_state.json"

# توابع ذخیره‌سازی و بارگذاری
def load_json(file):
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_json(file, data):
    with open(file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())

def ensure_file(file, default):
    if not os.path.exists(file):
        save_json(file, default)

# اطمینان از اینکه فایل‌های موردنیاز از قبل ساخته شدن
for file, default in [
    (POSTED_FILE, {"photo_ids": []}),
    (USED_FILE, {}),
    (USERS_FILE, {}),
    (STATE_FILE, {}),
    (HISTORY_FILE, {}),
    (TEXT2IMG_STATE, {})
]:
    ensure_file(file, default)

# کیبوردها
main_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("📸 عکس به سلیقه عمو"),
    KeyboardButton("🔍 جستجوی دلخواه"),
    KeyboardButton("🖌️ تبدیل متن به عکس"),
    KeyboardButton("ℹ️ درباره من"),
    KeyboardButton("💬 تماس با مالک عمو عکسی")
)

def retry_keyboard(mode):
    kb = InlineKeyboardMarkup()
    if mode == "random":
        kb.add(
            InlineKeyboardButton("🔁 درخواست مجدد", callback_data="random"),
            InlineKeyboardButton("📡 رفتن به کانال عمو", url=CHANNEL_3_LINK)
        )
    elif mode == "search":
        kb.add(
            InlineKeyboardButton("🔁 جستجوی مجدد", callback_data="search"),
            InlineKeyboardButton("📡 رفتن به کانال عمو", url=CHANNEL_3_LINK)
        )
    return kb

def join_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 کانال 1", url=CHANNEL_1_LINK))
    kb.add(InlineKeyboardButton("📢 کانال 2", url=CHANNEL_2_LINK))
    kb.add(InlineKeyboardButton("✅ عضو شدم عمو جون", callback_data="check_join"))
    return kb

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
/delphoto - پاکسازی عکس‌های حذف‌شده از کانال
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
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("⛔️ باید روی یه عکس ریپلای کنی نوب جان!")
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

@dp.message_handler(commands=["delphoto"])
async def delphoto(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    posted = load_json(POSTED_FILE).get("photo_ids", [])
    alive = []
    deleted = 0
    for pid in posted:
        try:
            await bot.forward_message(message.chat.id, CHANNEL_4, int(pid))
            alive.append(pid)
        except:
            deleted += 1
    save_json(POSTED_FILE, {"photo_ids": alive})
    await message.reply(f"🧹 تموم شد! {deleted} عکس پاک‌شده از لیست حذف شد.")

@dp.message_handler(commands=["send"])
async def send_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        await message.reply("⛔️ هر بار یادت میره ریپ بزنی؟")
        return
    users = load_json(USERS_FILE)
    sent_count = 0
    error_count = 0
    await message.reply("📤 دارم میدم دستشون عمو زیادن...")
    for uid in users:
        try:
            await bot.copy_message(
                chat_id=int(uid),
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.message_id
            )
            sent_count += 1
        except:
            error_count += 1
    await message.reply(f"✅ ارسال شد به {sent_count} نفر\n❌ ارور در {error_count} مورد.")

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

    while available:
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
            return
        except:
            available.remove(selected)

    kb = InlineKeyboardMarkup().add(
        InlineKeyboardButton("📡 رفتن به کانال عمو عکسی", url=CHANNEL_3_LINK)
    )
    await message.answer("😅 تموم شد عمو! دیگه عکسی نمونده که قبلاً ندیده باشی. بریم یه چرخی تو کانالم بزنیم؟", reply_markup=kb)

@dp.message_handler()
async def handle_message(message: types.Message):
    uid = str(message.from_user.id)
    if message.text == "📸 عکس به سلیقه عمو":
        if not await check_membership(message.from_user.id):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard())
            return
        await send_random(message, uid)

    elif message.text == "🔍 جستجوی دلخواه":
        if not await check_membership(message.from_user.id):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard())
            return
        state = load_json(STATE_FILE)
        state[uid] = True
        save_json(STATE_FILE, state)
        await message.reply("🔍 خب عمو، یه کلمه بفرست برات عکس بیارم!")

    elif message.text == "🖌️ تبدیل متن به عکس":
        state = load_json(TEXT2IMG_STATE)
        state[uid] = True
        save_json(TEXT2IMG_STATE, state)
        await message.reply("🎨 خب عمو، یه جمله بهم بده تا با هوش مصنوعی برات یه عکس توپ بسازم!")

    elif message.text == "ℹ️ درباره من":
        await message.reply("👴 من عمو عکسی‌ام که هر عکسی بخوای دارم! باحال‌ترین ربات دنیای فارسی!")

    elif message.text == "💬 تماس با مالک عمو عکسی":
        await message.reply("📮 برای صحبت با صاحب عمو عکسی، به این ربات پیام بده: @soulsownerbot")

    else:
        state = load_json(STATE_FILE)
        if state.get(uid):
            state[uid] = False
            save_json(STATE_FILE, state)
            await message.reply("⏳ صبر کن عمو... دارم عکسای ناب برات پیدا می‌کنم...")
            await handle_search(message)
            return

        t2i = load_json(TEXT2IMG_STATE)
        if t2i.get(uid):
            t2i[uid] = False
            save_json(TEXT2IMG_STATE, t2i)
            await message.reply("🧠 دارم فکر می‌کنم...")
            await handle_text2img(message)

async def handle_search(message: types.Message):
    uid = str(message.from_user.id)
    query = message.text.strip().lower()

    all_photos = await search_photos(query)

    history = load_json(HISTORY_FILE)
    user_history = history.get(uid, {}).get(query, [])

    # فیلتر عکس‌های جدیدی که قبلاً برای این کاربر در این جستجو فرستاده نشده بودن
    new_photos = [url for url in all_photos if url not in user_history]

    if not new_photos:
        await message.reply("😕 عکسی جدید برای این موضوع ندارم عمو. یه چیز دیگه بفرست!", reply_markup=retry_keyboard("search"))
        return

    # ذخیره عکس‌های جدید
    history.setdefault(uid, {}).setdefault(query, []).extend(new_photos)
    save_json(HISTORY_FILE, history)

    media = [InputMediaPhoto(url) for url in new_photos[:10]]
    await message.answer_media_group(media)
    await message.answer("📷 اینا رو تونستم برات پیدا کنم صفا باشه عمو!", reply_markup=retry_keyboard("search"))


async def search_photos(query):
    urls = []
    async with aiohttp.ClientSession() as s:
        try:
            u = f"https://api.unsplash.com/photos/random?query={query}&client_id={UNSPLASH_ACCESS_KEY}&count=3"
            async with s.get(u) as r:
                data = await r.json()
                urls += [d['urls']['regular'] for d in data if 'urls' in d]
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

async def handle_text2img(message: types.Message):
    prompt = message.text
    try:
        output = replicate_client.run(
            "stability-ai/stable-diffusion:a9758cbf8cf71812e1b45d1ddfb774d957f25c1e579b9e992af287f840a5f926",
            input={"prompt": prompt}
        )
        if isinstance(output, list):
            for url in output:
                await message.answer_photo(photo=url)
            await message.answer("🎨 اینم تصویرت با هوش مصنوعی عمو! بازم می‌خوای بفرست جمله بعدی رو.", reply_markup=retry_keyboard("search"))
        else:
            await message.answer("😓 نتونستم عکس بسازم. یه بار دیگه امتحان کن!")
    except Exception as e:
        await message.answer(f"❌ ارور در ساخت عکس: {e}")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
