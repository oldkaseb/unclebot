# === part 1: imports, env, ui, album cache ===
import os
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
    InputMediaPhoto, BotCommand
)
from aiogram.utils import executor
from aiogram.dispatcher.filters import CommandStart

# ENV
BOT_TOKEN = os.getenv("BOT_TOKEN")
PG_DSN    = os.getenv("DATABASE_URL")
UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY      = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY     = os.getenv("PIXABAY_API_KEY")

CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_3 = os.getenv("CHANNEL_3")
CHANNEL_4 = int(os.getenv("CHANNEL_4"))

CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
CHANNEL_3_LINK = os.getenv("CHANNEL_3_LINK")

INITIAL_ADMIN = int(os.getenv("ADMIN_ID", "0"))

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(bot)

# UI
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

# آلبوم ادمین (برای /send آلبومی)
ALBUM_CACHE = defaultdict(lambda: {"ts": 0, "media": []})
ALBUM_CACHE_TTL = 600  # ثانیه

# --- Search mode state (in-memory) ---
SEARCH_MODE = {}  # user_id -> last_activity_ts
SEARCH_TIMEOUT = 600  # ثانیه؛ بعدش خودکار از مود خارج می‌شه

def enter_search_mode(user_id: int):
    SEARCH_MODE[user_id] = time.time()

def exit_search_mode(user_id: int):
    SEARCH_MODE.pop(user_id, None)

def in_search_mode(user_id: int) -> bool:
    ts = SEARCH_MODE.get(user_id)
    if not ts:
        return False
    if time.time() - ts > SEARCH_TIMEOUT:
        SEARCH_MODE.pop(user_id, None)
        return False
    SEARCH_MODE[user_id] = time.time()  # touch
    return True


# === part 2: database schema + helpers + admin decorator ===
PG_POOL = None

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
  user_id   BIGINT PRIMARY KEY,
  name      TEXT,
  username  TEXT,
  joined_at TIMESTAMPTZ DEFAULT now()
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
CREATE INDEX IF NOT EXISTS idx_search_history_user_query_url ON search_history(user_id, query, url);

CREATE TABLE IF NOT EXISTS admins (
  user_id  BIGINT PRIMARY KEY,
  added_at TIMESTAMPTZ DEFAULT now()
);
"""

async def init_db():
    global PG_POOL
    PG_POOL = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=5)
    async with PG_POOL.acquire() as conn:
        await conn.execute(SCHEMA_SQL)

async def ensure_initial_admin():
    if INITIAL_ADMIN:
        await db_execute("INSERT INTO admins(user_id) VALUES($1) ON CONFLICT DO NOTHING", INITIAL_ADMIN)

async def db_execute(sql, *args):
    async with PG_POOL.acquire() as conn:
        return await conn.execute(sql, *args)

async def db_fetch(sql, *args):
    async with PG_POOL.acquire() as conn:
        return await conn.fetch(sql, *args)

# CRUD helpers
async def upsert_user(u: types.User):
    await db_execute(
        """INSERT INTO users(user_id,name,username)
           VALUES($1,$2,$3)
           ON CONFLICT (user_id) DO UPDATE SET name=EXCLUDED.name, username=EXCLUDED.username""",
        u.id, u.full_name, u.username
    )

async def add_posted_photo(message_id: int):
    await db_execute("INSERT INTO posted_photos(message_id) VALUES($1) ON CONFLICT DO NOTHING", message_id)

async def pick_unseen_for_user(user_id: int, limit: int = 3):
    rows = await db_fetch(
        """SELECT p.message_id
           FROM posted_photos p
           LEFT JOIN used_photos u ON u.message_id=p.message_id AND u.user_id=$1
           WHERE u.message_id IS NULL
           ORDER BY random()
           LIMIT $2""",
        user_id, limit
    )
    return [r["message_id"] for r in rows]

async def mark_used(user_id: int, message_id: int):
    await db_execute("INSERT INTO used_photos(user_id,message_id) VALUES($1,$2) ON CONFLICT DO NOTHING", user_id, message_id)

async def has_seen_url(user_id: int, query: str, url: str) -> bool:
    rows = await db_fetch("SELECT 1 FROM search_history WHERE user_id=$1 AND query=$2 AND url=$3", user_id, query, url)
    return bool(rows)

async def store_seen_urls(user_id: int, query: str, urls: list):
    if not urls: return
    async with PG_POOL.acquire() as conn:
        async with conn.transaction():
            for u in urls:
                await conn.execute(
                    "INSERT INTO search_history(user_id,query,url) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",
                    user_id, query, u
                )

# admin helpers
async def is_admin(user_id: int) -> bool:
    r = await db_fetch("SELECT 1 FROM admins WHERE user_id=$1", user_id)
    return bool(r)

def admin_only(fn):
    async def wrapper(message: types.Message, *a, **kw):
        if not await is_admin(message.from_user.id):
            return
        return await fn(message, *a, **kw)
    return wrapper


# === part 3: membership, start, album cache, admin commands ===
async def check_membership(user_id):
    ok = True
    for ch in [CHANNEL_1, CHANNEL_2]:
        try:
            member = await bot.get_chat_member(chat_id=ch, user_id=user_id)
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
        await message.answer("👋 اول باید عضو هر دو کانال شی:", reply_markup=join_keyboard())

@dp.message_handler(commands=['help'])
async def help_cmd(message: types.Message):
    if await is_admin(message.from_user.id):
        await message.reply(
            "🛠 راهنمای ادمین:\n"
            "/whoami — نمایش آیدی و وضعیت ادمین\n"
            "/whoadmins — لیست ادمین‌ها\n"
            "/addadmin <user_id> — افزودن ادمین\n"
            "/deladmin <user_id> — حذف ادمین\n"
            "/send — ارسال همگانی (روی پیام ریپلای کنید؛ آلبوم هم پشتیبانی)\n"
            "/addphoto — افزودن عکس به خزانه (روی عکس ریپلای)\n"
            "/delphoto — پاکسازی عکس‌های حذف‌شدهٔ کانال ۴\n"
            "/dbstats — آمار دیتابیس\n"
            "/topqueries — برترین جستجوها (۷ روز)\n"
            "/cancel — خروج از حالت جستجو"
        )
    else:
        await message.reply(
            "سلام 👋\n"
            "از دکمه‌ها استفاده کن:\n"
            "• 📸 عکس به سلیقه عمو\n"
            "• 🔍 جستجوی دلخواه\n"
            "• ℹ️ درباره من\n"
            "• 💬 تماس با مالک عمو عکسی\n"
            "و هر وقت خواستی از حالت جستجو بیای بیرون: /cancel"
        )

@dp.message_handler(commands=['whoami'])
async def whoami(message: types.Message):
    admin = await is_admin(message.from_user.id)
    await message.reply(f"👤 user_id: {message.from_user.id}\n👮 admin: {'YES' if admin else 'NO'}")

@dp.callback_query_handler(lambda c: c.data == "check_join")
async def check_join(call: types.CallbackQuery):
    if await check_membership(call.from_user.id):
        await call.message.answer("✅ درسته! بزن بریم:", reply_markup=main_kb)
    else:
        await call.message.answer("⛔️ هنوز عضو هر دو کانال نشدی!", reply_markup=join_keyboard())

# آلبوم ادمین برای /send
@dp.message_handler(content_types=['photo'])
async def cache_admin_album(message: types.Message):
    if not await is_admin(message.from_user.id):
        return
    if not message.media_group_id:
        return
    gid = str(message.media_group_id)
    now = time.time()
    for k in list(ALBUM_CACHE.keys()):
        if now - ALBUM_CACHE[k]["ts"] > ALBUM_CACHE_TTL:
            del ALBUM_CACHE[k]
    file_id = message.photo[-1].file_id
    caption = message.caption if not ALBUM_CACHE[gid]["media"] else None
    ALBUM_CACHE[gid]["ts"] = now
    ALBUM_CACHE[gid]["media"].append(InputMediaPhoto(file_id, caption=caption))

# ————— مدیریت ادمین‌ها
@dp.message_handler(commands=['whoadmins'])
@admin_only
async def whoadmins(message: types.Message):
    rows = await db_fetch("SELECT user_id, added_at FROM admins ORDER BY added_at ASC")
    if not rows:
        await message.reply("لیست ادمین‌ها خالیه.")
        return
    msg = "\n".join([f"• {r['user_id']}  (since {r['added_at']:%Y-%m-%d})" for r in rows])
    await message.reply("👮 Admins:\n" + msg)

@dp.message_handler(commands=['addadmin'])
@admin_only
async def addadmin(message: types.Message):
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("استفاده: /addadmin <user_id>")
        return
    uid = int(parts[1])
    await db_execute("INSERT INTO admins(user_id) VALUES($1) ON CONFLICT DO NOTHING", uid)
    await message.reply(f"✅ {uid} اضافه شد.")

@dp.message_handler(commands=['deladmin'])
@admin_only
async def deladmin(message: types.Message):
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("استفاده: /deladmin <user_id>")
        return
    uid = int(parts[1])
    await db_execute("DELETE FROM admins WHERE user_id=$1", uid)
    await message.reply(f"🗑 {uid} حذف شد.")

# ————— ارسال همگانی (تکی/آلبوم)
@dp.message_handler(commands=["send"])
@admin_only
async def send_cmd(message: types.Message):
    if not message.reply_to_message:
        await message.reply("⛔️ باید روی یک پیام (یا یکی از عکس‌های آلبوم) ریپلای کنی.")
        return
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
            media_group = album["media"][:10]  # محدودیت تلگرام
            for uid in user_ids:
                try:
                    await bot.send_media_group(chat_id=uid, media=media_group)
                    sent_count += 1
                except:
                    error_count += 1
            del ALBUM_CACHE[gid]
        else:
            for uid in user_ids:
                try:
                    await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=r.message_id)
                    sent_count += 1
                except:
                    error_count += 1
    else:
        for uid in user_ids:
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=r.message_id)
                sent_count += 1
            except:
                error_count += 1
    await message.reply(f"✅ {sent_count} نفر\n❌ {error_count} ناموفق")

# ————— افزودن عکس به خزانه از کانال ۴
@dp.message_handler(commands=["addphoto"])
@admin_only
async def addphoto(message: types.Message):
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
        await message.reply("📥 اضافه شد.")
    except Exception as e:
        await message.reply(f"❌ خطا: {e}")

# ————— پاکسازی عکس‌های حذف‌شده از کانال ۴
@dp.message_handler(commands=["delphoto"])
@admin_only
async def delphoto(message: types.Message):
    rows = await db_fetch("SELECT message_id FROM posted_photos")
    deleted = 0
    for r in rows:
        mid = int(r["message_id"])
        try:
            await bot.forward_message(chat_id=message.chat.id, from_chat_id=CHANNEL_4, message_id=mid)
        except Exception:
            await db_execute("DELETE FROM posted_photos WHERE message_id=$1", mid)
            deleted += 1
    await message.reply(f"🧹 حذف‌شده‌ها پاک شد: {deleted}")

# ————— آمار کامل‌تر
@dp.message_handler(commands=['dbstats'])
@admin_only
async def dbstats(message: types.Message):
    total_users   = (await db_fetch("SELECT COUNT(*) c FROM users"))[0]['c']
    total_posted  = (await db_fetch("SELECT COUNT(*) c FROM posted_photos"))[0]['c']
    total_used    = (await db_fetch("SELECT COUNT(*) c FROM used_photos"))[0]['c']
    total_hist    = (await db_fetch("SELECT COUNT(*) c FROM search_history"))[0]['c']
    today_hist    = (await db_fetch("SELECT COUNT(*) c FROM search_history WHERE seen_at::date=now()::date"))[0]['c']
    week_hist     = (await db_fetch("SELECT COUNT(*) c FROM search_history WHERE seen_at>=now()-interval '7 days'"))[0]['c']
    await message.reply(
        "📊 آمار دیتابیس:\n"
        f"👥 Users: {total_users}\n"
        f"🖼 Posted: {total_posted}\n"
        f"✅ Used: {total_used}\n"
        f"🔎 History: {total_hist}\n"
        f"   • امروز: {today_hist}\n"
        f"   • ۷ روز اخیر: {week_hist}"
    )

@dp.message_handler(commands=['topqueries'])
@admin_only
async def topqueries(message: types.Message):
    rows = await db_fetch("""
        SELECT query, COUNT(*) c
        FROM search_history
        WHERE seen_at >= now() - interval '7 days'
        GROUP BY query
        ORDER BY c DESC
        LIMIT 10
    """)
    if not rows:
        await message.reply("🔎 این هفته نداریم.")
        return
    lines = [f"{i+1}. {r['query']} — {r['c']}" for i, r in enumerate(rows)]
    await message.reply("🏆 Top queries (7d):\n" + "\n".join(lines))


# === part 4: artistic/cinematic search (no portrait/orientation) ===
async def search_photos(query, page=1):
    # استایل ثابت هنری/سینمایی (بدون هیچ ضدچهره‌ای و بدون محدودیت orientation)
    suffix = ", aesthetic, cinematic, soft lighting, bokeh, shallow depth of field, film look"
    q = f"{query}{suffix}"

    urls = []
    async with aiohttp.ClientSession() as s:
        # ---- Unsplash ----
        try:
            u = (
                "https://api.unsplash.com/search/photos"
                f"?query={q}&page={page}&per_page=12"
                "&order_by=relevant&content_filter=high"
                f"&client_id={UNSPLASH_ACCESS_KEY}"
            )
            async with s.get(u) as r:
                data = await r.json()
                for d in data.get("results", []):
                    ureg = d.get("urls", {}).get("regular")
                    if ureg:
                        urls.append(ureg)
        except:
            pass

        # ---- Pexels ----
        try:
            headers = {"Authorization": PEXELS_API_KEY}
            u = (
                "https://api.pexels.com/v1/search"
                f"?query={q}&page={page}&per_page=12"
                "&size=large"
            )
            async with s.get(u, headers=headers) as r:
                data = await r.json()
                for p in data.get("photos", []):
                    urls.append(p["src"].get("large") or p["src"].get("medium"))
        except:
            pass

        # ---- Pixabay ----
        try:
            u = (
                "https://pixabay.com/api/"
                f"?key={PIXABAY_API_KEY}&q={q}"
                f"&page={page}&per_page=12"
                "&image_type=photo&safesearch=true&order=popular&editors_choice=true"
            )
            async with s.get(u) as r:
                data = await r.json()
                for h in data.get("hits", []):
                    if h.get("webformatURL"):
                        urls.append(h["webformatURL"])
        except:
            pass

    # حذف تکراری‌های همین نوبت
    seen, unique = set(), []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            unique.append(u)
    return unique


async def handle_search(message: types.Message):
    # تمدید تایم‌اوت مود جستجو
    SEARCH_MODE[message.from_user.id] = time.time()

    uid = int(message.from_user.id)
    query = (message.text or "").strip().lower()

    # اول یک صفحه رندوم
    page = random.randint(1, 5)
    batch1 = await search_photos(query, page=page)

    # فیلتر با تاریخچه دیتابیس (هیچ‌وقت تکراری نشه)
    fresh = [u for u in batch1 if not await has_seen_url(uid, query, u)]
    if not fresh:
        page2 = random.randint(6, 12)
        batch2 = await search_photos(query, page=page2)
        fresh = [u for u in batch2 if not await has_seen_url(uid, query, u)]

    if not fresh:
        await message.reply("😕 برای این موضوع عکس تازه ندارم. یه چیز دیگه جستجو کن!", reply_markup=retry_keyboard("search"))
        return

    await store_seen_urls(uid, query, fresh)

    media = [InputMediaPhoto(u) for u in fresh[:10]]
    await message.answer_media_group(media)
    await message.answer("🎬اگه بازم می‌خوای، دوباره جستجو کن", reply_markup=retry_keyboard("search"))


# === part 5: random three + callbacks + main text handler ===
@dp.callback_query_handler(lambda c: c.data in ["random", "search"])
async def retry_handler(call: types.CallbackQuery):
    if not await check_membership(call.from_user.id):
        await call.message.answer("⛔️ اول عضو هر دو کانال شو.", reply_markup=join_keyboard())
        return
    if call.data == "random":
        await send_random(call.message, call.from_user.id)
    elif call.data == "search":
        enter_search_mode(call.from_user.id)
        await call.message.answer("🔎 یه کلمه بفرست تا برات عکساشو بیارم!")

async def send_random(message, user_id):
    picks = await pick_unseen_for_user(int(user_id), limit=3)
    if not picks:
        kb = InlineKeyboardMarkup().add(
            InlineKeyboardButton("📡 رفتن به کانال عمو عکسی", url=CHANNEL_3_LINK)
        )
        await message.answer("😅 مونده عکس عمه عکسی رو ببینی دیگه. یه سر به کانال بزن!", reply_markup=kb)
        return
    sent_any = False
    for mid in picks:
        try:
            await bot.copy_message(chat_id=int(user_id), from_chat_id=CHANNEL_4, message_id=int(mid))
            await mark_used(int(user_id), int(mid))
            sent_any = True
        except:
            await db_execute("DELETE FROM posted_photos WHERE message_id=$1", int(mid))
    if sent_any:
        await message.answer("🎁 اینم از کانال عمو عکسی 😎", reply_markup=retry_keyboard("random"))
    else:
        await message.answer("⛔️ مشکلی پیش اومد، دوباره امتحان کن")

@dp.message_handler(commands=['cancel'])
async def cancel_search(message: types.Message):
    exit_search_mode(message.from_user.id)
    await message.reply("✅ از حالت جستجو خارج شدی.", reply_markup=main_kb)

# ⚠️ دیباگ: ببینیم اصلاً کامند به ربات می‌رسه یا نه
@dp.message_handler(lambda m: m.text and m.text.startswith('/'))
async def debug_commands(message: types.Message):
    # اگر /help یا /whoami توسط هندلر خودش گرفته نشه، اینجا حداقل جواب می‌ده
    if message.text not in ['/help', '/whoami', '/dbstats', '/topqueries', '/addadmin', '/deladmin', '/send', '/addphoto', '/delphoto', '/cancel', '/start']:
        await message.reply(f"DBG got command: {message.text}")

@dp.message_handler()
async def handle_message(message: types.Message):
    uid = int(message.from_user.id)
    txt = (message.text or "").strip()

    if txt == "📸 عکس به سلیقه عمو":
        exit_search_mode(uid)
        if not await check_membership(uid):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard()); return
        await send_random(message, uid)
        return

    elif txt == "🔍 جستجوی دلخواه":
        if not await check_membership(uid):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard()); return
        enter_search_mode(uid)
        await message.reply("🔎 خب عمو، یه کلمه بفرست برات عکسای خفن بیارم")
        return

    elif txt == "ℹ️ درباره من":
        exit_search_mode(uid)
        await message.reply("👴 من عمو عکسی‌ام! دنیای بینهایتی از عکس دارم همش به سبک جستجوی تو بستگی داره")
        return

    elif txt == "💬 تماس با مالک عمو عکسی":
        exit_search_mode(uid)
        await message.reply("📮 برای صحبت با مالک عمو عکسی: @soulsownerbot")
        return

    # فقط وقتی در حالت جستجو هست، هر متنِ آزاد = کوئری
    if in_search_mode(uid):
        if not await check_membership(uid):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard()); return
        await message.reply("⏳ صبر کن... دارم عکسای ناب پیدا می‌کنم...")
        await handle_search(message)
        return

    # خارج از حالت جستجو: پیام آزاد → راهنمایی
    await message.reply("برای جستجو دکمه «🔍 جستجوی دلخواه» رو بزن یا /cancel برای خروج از مودها.", reply_markup=main_kb)


# === part 6: startup ===
async def on_startup(dp):
    await init_db()
    await ensure_initial_admin()
    # منو/کامندها رو ست کن تا تو کلاینت دیده بشن
    await bot.set_my_commands([
        BotCommand("start", "شروع"),
        BotCommand("help", "راهنما"),
        BotCommand("whoami", "نمایش آیدی و وضعیت ادمین"),
        BotCommand("cancel", "خروج از حالت جستجو"),
        BotCommand("send", "ارسال همگانی (ادمین)"),
        BotCommand("addphoto", "افزودن عکس به خزانه (ادمین)"),
        BotCommand("delphoto", "پاکسازی لیست عکس‌ها (ادمین)"),
        BotCommand("whoadmins", "لیست ادمین‌ها (ادمین)"),
        BotCommand("addadmin", "افزودن ادمین (ادمین)"),
        BotCommand("deladmin", "حذف ادمین (ادمین)"),
        BotCommand("dbstats", "آمار دیتابیس (ادمین)"),
        BotCommand("topqueries", "برترین جستجوها (ادمین)")
    ])

if __name__ == "__main__":
    # مطمئن شو فقط یک سرویس با همین BOT_TOKEN فعاله
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
