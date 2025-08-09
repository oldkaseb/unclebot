import os
import json  # فقط اگه جایی بخوای بک‌آپ/لاگ ساده بنویسی؛ استفاده اصلی نداریم
import random
import time
import asyncio
import aiohttp
import asyncpg

from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, InputMediaVideo, InputMediaDocument
)
from aiogram.utils import executor
from aiogram.dispatcher.filters import CommandStart

# ====== ENV ======
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

PG_DSN = os.getenv("DATABASE_URL")
PG_POOL = None  # asyncpg pool (بعداً مقداردهی می‌شه)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ====== UI ======
main_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(
    KeyboardButton("📸 عکس به سلیقه عمو"),
    KeyboardButton("🔍 جستجوی دلخواه"),
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

# کش موقت برای آلبوم ادمین (برای /send همه‌چیزخور)
ALBUM_CACHE = defaultdict(lambda: {"ts": 0, "media": []})
ALBUM_CACHE_TTL = 600  # ثانیه

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
  user_id    BIGINT PRIMARY KEY,
  name       TEXT,
  username   TEXT,
  joined_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS posted_photos (
  message_id BIGINT PRIMARY KEY,
  added_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS used_photos (
  user_id    BIGINT,
  message_id BIGINT,
  used_at    TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (user_id, message_id),
  FOREIGN KEY (message_id) REFERENCES posted_photos(message_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_used_photos_user ON used_photos(user_id);

CREATE TABLE IF NOT EXISTS search_history (
  user_id BIGINT,
  query   TEXT,
  url     TEXT,
  seen_at TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (user_id, query, url)
);
CREATE INDEX IF NOT EXISTS idx_search_history_user_query ON search_history(user_id, query);
"""

async def init_db():
    global PG_POOL
    PG_POOL = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=5)
    async with PG_POOL.acquire() as conn:
        await conn.execute(SCHEMA_SQL)

async def db_execute(sql, *args):
    async with PG_POOL.acquire() as conn:
        return await conn.execute(sql, *args)

async def db_fetch(sql, *args):
    async with PG_POOL.acquire() as conn:
        return await conn.fetch(sql, *args)

# ====== CRUD ======
async def upsert_user(u: types.User):
    await db_execute(
        """INSERT INTO users(user_id,name,username)
           VALUES($1,$2,$3)
           ON CONFLICT (user_id) DO UPDATE
             SET name=EXCLUDED.name, username=EXCLUDED.username""",
        u.id, u.full_name, u.username
    )

async def add_posted_photo(message_id: int):
    await db_execute(
        "INSERT INTO posted_photos(message_id) VALUES($1) ON CONFLICT DO NOTHING",
        message_id
    )

async def pick_unseen_for_user(user_id: int, limit: int = 3):
    rows = await db_fetch(
        """
        SELECT p.message_id
        FROM posted_photos p
        LEFT JOIN used_photos u
          ON u.message_id = p.message_id AND u.user_id = $1
        WHERE u.message_id IS NULL
        ORDER BY random()
        LIMIT $2
        """,
        user_id, limit
    )
    return [r["message_id"] for r in rows]

async def mark_used(user_id: int, message_id: int):
    await db_execute(
        "INSERT INTO used_photos(user_id,message_id) VALUES($1,$2) ON CONFLICT DO NOTHING",
        user_id, message_id
    )

async def has_seen_url(user_id: int, query: str, url: str) -> bool:
    rows = await db_fetch(
        "SELECT 1 FROM search_history WHERE user_id=$1 AND query=$2 AND url=$3",
        user_id, query, url
    )
    return len(rows) > 0

async def store_seen_urls(user_id: int, query: str, urls: list):
    if not urls:
        return
    async with PG_POOL.acquire() as conn:
        async with conn.transaction():
            for u in urls:
                await conn.execute(
                    "INSERT INTO search_history(user_id,query,url) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                    user_id, query, u
                )

async def check_membership(user_id):
    ok = True
    for channel in [CHANNEL_1, CHANNEL_2]:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status in ["left", "kicked"]:
                ok = False
        except:
            ok = False
    return ok

@dp.message_handler(CommandStart())
async def start(message: types.Message):
    await upsert_user(message.from_user)
    if await check_membership(message.from_user.id):
        await message.answer("🎉 سلام عمو! یکی از دکمه‌ها رو بزن:", reply_markup=main_kb)
    else:
        await message.answer("👋 اول باید عضو هر دوتا کانال زیر بشی:", reply_markup=join_keyboard())

@dp.callback_query_handler(lambda c: c.data == "check_join")
async def check_join(call: types.CallbackQuery):
    if await check_membership(call.from_user.id):
        await call.message.answer("✅ آفرین! حالا یکی از دکمه‌های پایین رو بزن:", reply_markup=main_kb)
    else:
        await call.message.answer("⛔️ هنوز عضو هر دو کانال نشدی!", reply_markup=join_keyboard())

# کش آلبوم‌های ادمین (فقط عکس)
@dp.message_handler(content_types=['photo'])
async def cache_admin_album(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.media_group_id:
        return
    gid = str(message.media_group_id)
    now = time.time()
    # پاکسازی کش‌های قدیمی
    for k in list(ALBUM_CACHE.keys()):
        if now - ALBUM_CACHE[k]["ts"] > ALBUM_CACHE_TTL:
            del ALBUM_CACHE[k]

    file_id = message.photo[-1].file_id
    caption = message.caption or ""
    ALBUM_CACHE[gid]["ts"] = now
    # فقط عکس‌ها (InputMediaPhoto). اگر خواستی ویدیو/سند هم اضافه می‌کنیم.
    ALBUM_CACHE[gid]["media"].append(InputMediaPhoto(file_id, caption=caption if len(ALBUM_CACHE[gid]["media"]) == 0 else None))

@dp.message_handler(commands=["help"])
async def help_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.reply("""
📚 راهنمای ادمین:

/stats - تعداد کاربران
/addphoto - ریپلای روی عکس؛ به کانال 4 کپی و به خزانه اضافه می‌کند
/delphoto - پاکسازی عکس‌های حذف‌شده از کانال 4 از خزانه
/send - ریپلای روی هر پیام/آلبوم و ارسال به همه
""")

@dp.message_handler(commands=["stats"])
async def stats_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    rows = await db_fetch("SELECT COUNT(*) c FROM users")
    c = rows[0]["c"] if rows else 0
    await message.reply(f"📊 کاربران ثبت‌شده: {c} نفر")

@dp.message_handler(commands=["addphoto"])
async def addphoto(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("⛔️ باید روی یک عکس ریپلای کنی.")
        return
    try:
        sent = await bot.copy_message(
            chat_id=CHANNEL_4,
            from_chat_id=message.chat.id,
            message_id=message.reply_to_message.message_id
        )
        await add_posted_photo(int(sent.message_id))
        await message.reply("📥 اضافه شد به خزانه.")
    except Exception as e:
        await message.reply(f"❌ خطا در افزودن: {e}")

@dp.message_handler(commands=["delphoto"])
async def delphoto(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    rows = await db_fetch("SELECT message_id FROM posted_photos")
    deleted = 0
    for r in rows:
        mid = int(r["message_id"])
        try:
            # چک زنده بودن پیام با forward (اگر پاک شده باشد خطا می‌دهد)
            await bot.forward_message(chat_id=message.chat.id, from_chat_id=CHANNEL_4, message_id=mid)
        except Exception:
            await db_execute("DELETE FROM posted_photos WHERE message_id=$1", mid)
            # used_photos با ON DELETE CASCADE پاک می‌شود
            deleted += 1
    await message.reply(f"🧹 پاکسازی انجام شد. حذف‌شده: {deleted}")

@dp.message_handler(commands=["send"])
async def send_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        await message.reply("⛔️ باید روی یک پیام (یا یکی از عکس‌های آلبوم) ریپلای کنی.")
        return

    # دریافت همه یوزرها
    rows = await db_fetch("SELECT user_id FROM users")
    user_ids = [int(r["user_id"]) for r in rows]
    sent_count = 0
    error_count = 0

    await message.reply("📤 در حال ارسال به همه...")

    r = message.reply_to_message
    if r.media_group_id:
        gid = str(r.media_group_id)
        album = ALBUM_CACHE.get(gid)
        if album and album["media"]:
            media_group = album["media"][:10]  # تلگرام حداکثر 10
            for uid in user_ids:
                try:
                    await bot.send_media_group(chat_id=uid, media=media_group)
                    sent_count += 1
                except:
                    error_count += 1
            # تمیزکاری کش (اختیاری)
            del ALBUM_CACHE[gid]
        else:
            # اگر کش نبود، fallback: copy همان پیام
            for uid in user_ids:
                try:
                    await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=r.message_id)
                    sent_count += 1
                except:
                    error_count += 1
    else:
        # تک‌پیام: متن/عکس/ویدیو/دست‌نوشته/...
        for uid in user_ids:
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=r.message_id)
                sent_count += 1
            except:
                error_count += 1

    await message.reply(f"✅ ارسال شد به {sent_count} نفر\n❌ ناموفق: {error_count}")

@dp.callback_query_handler(lambda c: c.data in ["random", "search"])
async def retry_handler(call: types.CallbackQuery):
    if not await check_membership(call.from_user.id):
        await call.message.answer("⛔️ اول عضو هر دو کانال شو.", reply_markup=join_keyboard())
        return
    if call.data == "random":
        await send_random(call.message, call.from_user.id)
    elif call.data == "search":
        await call.message.answer("🔎 یه کلمه بفرست تا برات عکساشو بیارم!")

async def send_random(message, user_id):
    picks = await pick_unseen_for_user(int(user_id), limit=3)
    if not picks:
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📡 رفتن به کانال عمو عکسی", url=CHANNEL_3_LINK)
        )
        await message.answer("😅 فعلاً عکس جدیدی ندارم. یه سر به کانال بزن!", reply_markup=kb)
        return

    sent_any = False
    for mid in picks:
        try:
            await bot.copy_message(chat_id=int(user_id), from_chat_id=CHANNEL_4, message_id=int(mid))
            await mark_used(int(user_id), int(mid))
            sent_any = True
        except:
            # اگر پیام پاک شده، از DB حذفش کن
            await db_execute("DELETE FROM posted_photos WHERE message_id=$1", int(mid))

    if sent_any:
        await message.answer("🎁 اینم سه‌تایی از سلیقه عمو 😎", reply_markup=retry_keyboard("random"))
    else:
        await message.answer("⛔️ مشکلی پیش اومد، بعداً دوباره امتحان کن.")

@dp.message_handler()
async def handle_message(message: types.Message):
    uid = int(message.from_user.id)
    txt = (message.text or "").strip()

    if txt == "📸 عکس به سلیقه عمو":
        if not await check_membership(uid):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard())
            return
        await send_random(message, uid)

    elif txt == "🔍 جستجوی دلخواه":
        if not await check_membership(uid):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard())
            return
        await message.reply("🔎 خب عمو، یه کلمه بفرست برات عکس بیارم!")

    elif txt == "ℹ️ درباره من":
        await message.reply("👴 من عمو عکسی‌ام! هر عکسی بخوای دارم—با حال‌ترین ربات فارسی!")

    elif txt == "💬 تماس با مالک عمو عکسی":
        await message.reply("📮 برای صحبت با صاحب عمو عکسی، به این آیدی پیام بده: @soulsownerbot")

    else:
        # هر متن دیگه‌ای = تلاش برای جستجو
        if not await check_membership(uid):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard())
            return
        await message.reply("⏳ صبر کن... دارم عکسای ناب پیدا می‌کنم...")
        await handle_search(message)

async def handle_search(message: types.Message):
    uid = int(message.from_user.id)
    query = message.text.strip().lower()

    # برای تنوع، صفحه تصادفی
    page = random.randint(1, 5)
    all_photos = await search_photos(query, page=page)

    unique_now = []
    for u in all_photos:
        if not await has_seen_url(uid, query, u) and u not in unique_now:
            unique_now.append(u)

    if not unique_now:
        page2 = random.randint(6, 10)
        all_photos2 = await search_photos(query, page=page2)
        for u in all_photos2:
            if not await has_seen_url(uid, query, u) and u not in unique_now:
                unique_now.append(u)

    if not unique_now:
        await message.reply("😕 برای این موضوع عکس جدید ندارم. یه چیز دیگه سرچ کن!", reply_markup=retry_keyboard("search"))
        return

    await store_seen_urls(uid, query, unique_now)

    media = [InputMediaPhoto(url) for url in unique_now[:10]]
    await message.answer_media_group(media)
    await message.answer("📷 اینا رو تونستم برات پیدا کنم. بازم بزن!", reply_markup=retry_keyboard("search"))

async def search_photos(query, page=1):
    urls = []
    async with aiohttp.ClientSession() as s:
        # Unsplash
        try:
            u = f"https://api.unsplash.com/search/photos?query={query}&page={page}&per_page=10&client_id={UNSPLASH_ACCESS_KEY}"
            async with s.get(u) as r:
                data = await r.json()
                for d in data.get('results', []):
                    urls.append(d['urls']['regular'])
        except:
            pass
        # Pexels
        try:
            h = {"Authorization": PEXELS_API_KEY}
            u = f"https://api.pexels.com/v1/search?query={query}&per_page=10&page={page}"
            async with s.get(u, headers=h) as r:
                data = await r.json()
                for p in data.get('photos', []):
                    urls.append(p['src']['medium'])
        except:
            pass
        # Pixabay
        try:
            u = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&per_page=10&page={page}"
            async with s.get(u) as r:
                data = await r.json()
                for h in data.get('hits', []):
                    urls.append(h['webformatURL'])
        except:
            pass

    # حذف تکرار داخل همین نوبت
    seen = set()
    unique = []
    for u in urls:
        if u not in seen:
            unique.append(u)
            seen.add(u)
    return unique
async def on_startup(dp):
    await init_db()

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
