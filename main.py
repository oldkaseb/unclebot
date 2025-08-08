import os
import json
import random
import aiohttp
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)
from aiogram.utils import executor
from aiogram.dispatcher.filters import CommandStart

# دریافت متغیرهای محیطی از Railway
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

# فایل‌های ذخیره‌سازی داده
POSTED_FILE = "posted.json"
USED_FILE = "used_photos.json"
USERS_FILE = "users.json"
STATE_FILE = "search_state.json"
HISTORY_FILE = "search_history.json"
TEXT2IMG_STATE = "text2img_state.json"

# توابع فایل
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

# اطمینان از ایجاد فایل‌های موردنیاز
for file, default in [
    (POSTED_FILE, {"photo_ids": []}),
    (USED_FILE, {}),
    (USERS_FILE, {}),
    (STATE_FILE, {}),
    (HISTORY_FILE, {}),
    (TEXT2IMG_STATE, {})
]:
    ensure_file(file, default)

# کیبورد اصلی
main_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("📸 عکس به سلیقه عمو"),
    KeyboardButton("🔍 جستجوی دلخواه"),
    KeyboardButton("🖌️ تبدیل متن به عکس"),
    KeyboardButton("ℹ️ درباره من"),
    KeyboardButton("💬 تماس با مالک عمو عکسی")
)

# دکمه‌های چک عضویت و دکمه درخواست مجدد
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
    elif mode == "text2img":
        kb.add(
            InlineKeyboardButton("🎲 پرامپت رندوم", callback_data="random_prompt"),
            InlineKeyboardButton("📡 رفتن به کانال عمو", url=CHANNEL_3_LINK)
        )
    return kb

def join_keyboard():
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("📢 کانال 1", url=CHANNEL_1_LINK))
    kb.add(InlineKeyboardButton("📢 کانال 2", url=CHANNEL_2_LINK))
    kb.add(InlineKeyboardButton("✅ عضو شدم عمو جون", callback_data="check_join"))
    return kb

# بررسی عضویت
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

# پیام استارت
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

# چک عضویت با دکمه ✅ عضو شدم
@dp.callback_query_handler(lambda c: c.data == "check_join")
async def check_join(call: types.CallbackQuery):
    if await check_membership(call.from_user.id):
        await call.message.answer("✅ آفرین عمو! حالا یکی از دکمه‌های پایین رو بزن:", reply_markup=main_kb)
    else:
        await call.message.answer("⛔️ هنوز عضو هر دو کانال نشدی عمو اذیت نکن خب!", reply_markup=join_keyboard())

# دکمه پرامپت رندوم
@dp.callback_query_handler(lambda c: c.data == "random_prompt")
async def random_prompt(call: types.CallbackQuery):
    prompt = random.choice([
        "A futuristic city skyline at sunset",
        "A dreamy forest with glowing mushrooms",
        "A cute robot reading a book",
        "A fantasy castle in the sky",
        "A cyberpunk girl walking in neon streets",
        "A magical fox in a snowy landscape",
        "An astronaut relaxing on the moon"
    ])
    state = load_json(TEXT2IMG_STATE)
    state[str(call.from_user.id)] = False
    save_json(TEXT2IMG_STATE, state)
    fake_message = types.Message(
        message_id=call.message.message_id,
        from_user=call.from_user,
        chat=call.message.chat,
        date=call.message.date,
        text=prompt
    )
    await call.message.answer("✨ اینم یه پرامپت پیشنهادی عمو! دارم می‌سازمش برات...")
    await handle_text2img(fake_message)

# مدیریت درخواست‌های جستجو و عکس تصادفی
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

# ارسال عکس به سلیقه عمو
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

# مدیریت دکمه‌ها و متون دریافتی
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
        t2i = load_json(TEXT2IMG_STATE)
        t2i[uid] = True
        save_json(TEXT2IMG_STATE, t2i)
        await message.reply("🎨 خب عمو، یه جمله انگلیسی بده تا با هوش مصنوعی برات یه عکس توپ بسازم!\n\n📌 جمله باید انگلیسی باشه تا درست کار کنه!", reply_markup=retry_keyboard("text2img"))

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

# جستجو و جلوگیری از عکس تکراری
async def handle_search(message: types.Message):
    uid = str(message.from_user.id)
    query = message.text.strip().lower()
    all_photos = await search_photos(query)

    history = load_json(HISTORY_FILE)
    if uid not in history:
        history[uid] = {}
    if query not in history[uid]:
        history[uid][query] = []

    seen_urls = set(history[uid][query])
    new_photos = [url for url in all_photos if url not in seen_urls]

    if not new_photos:
        await message.reply("😕 عکسی جدید برای این موضوع ندارم عمو. یه چیز دیگه بفرست!", reply_markup=retry_keyboard("search"))
        return

    history[uid][query].extend(new_photos)
    save_json(HISTORY_FILE, history)

    media = [InputMediaPhoto(url) for url in new_photos[:10]]
    await message.answer_media_group(media)
    await message.answer("📷 اینا رو تونستم برات پیدا کنم صفا باشه عمو!", reply_markup=retry_keyboard("search"))

# سرچ در Unsplash و Pexels و Pixabay
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

# تبدیل متن به عکس
async def handle_text2img(message: types.Message):
    prompt = message.text.strip()

    await message.answer("🎨 دارم با هوش مصنوعی عکس می‌سازم برات... یه لحظه صبر کن عمو!")

    url = "https://stablediffusionapi.com/api/v3/text2img"
    payload = {
        "prompt": prompt,
        "negative_prompt": "low quality, blurry, bad anatomy",
        "width": "512",
        "height": "512",
        "samples": "1",
        "num_inference_steps": "30",
        "guidance_scale": 7.5,
        "seed": None
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                result = await resp.json()
                image_url = result.get("output", [None])[0]

                if image_url:
                    await message.answer_photo(photo=image_url)
                    await message.answer("✨ اینم تصویرت عمو! اگه بازم می‌خوای، جمله بعدی رو بفرست!", reply_markup=retry_keyboard("text2img"))
                else:
                    await message.answer("😕 عکسی ساخته نشد عمو. یه جمله دیگه امتحان کن!")
    except Exception as e:
        await message.answer(f"❌ ارور در ساخت تصویر: {e}")

# اجرای ربات
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
