# === main.py — Final with robust Postgres handling ===
import os
import random
import time
import aiohttp
import asyncpg
import logging
import ssl
from urllib.parse import urlparse

from collections import defaultdict
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto, BotCommand
)
from aiogram.utils import executor
from aiogram.dispatcher.filters import CommandStart

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)

# ---------- ENV ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
PG_DSN    = os.getenv("DATABASE_URL")

UNSPLASH_ACCESS_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_API_KEY      = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY     = os.getenv("PIXABAY_API_KEY")

CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_3 = os.getenv("CHANNEL_3")
CHANNEL_4 = int(os.getenv("CHANNEL_4"))  # numeric

CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
CHANNEL_3_LINK = os.getenv("CHANNEL_3_LINK")

INITIAL_ADMIN = int(os.getenv("ADMIN_ID", "0"))  # numeric user_id

# ---------- Bot ----------
bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(bot)

# ---------- UI ----------
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
ALBUM_CACHE_TTL = 600  # seconds

# ---------- Search Mode (in-memory) ----------
SEARCH_MODE = {}         # user_id -> last_activity_ts
SEARCH_TIMEOUT = 600     # seconds

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

# ---------- Helpers ----------
def _is_english(text: str) -> bool:
    # اگر تمام کاراکترها ASCII باشند، متن را انگلیسی در نظر می‌گیریم
    return all(ch.isascii() for ch in (text or ""))

# ---------- DB ----------
PG_POOL = None
DB_READY = False
LAST_DB_ERROR = None  # برای /pgdiag

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

def _build_dsn_from_parts():
    """اگر DATABASE_URL نبود، از متغیرهای تکی DSN بساز."""
    host = os.getenv("PGHOST")
    port = os.getenv("PGPORT", "5432")
    db   = os.getenv("PGDATABASE")
    user = os.getenv("PGUSER")
    pwd  = os.getenv("PGPASSWORD")
    if host and db and user and pwd:
        return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"
    return None

def _mask_dsn(dsn: str) -> str:
    try:
        u = urlparse(dsn)
        masked_user = (u.username or "")
        return f"{u.scheme}://{masked_user}:***@{u.hostname}:{u.port}{u.path}"
    except:
        return "***"

async def _create_pool(dsn: str, ssl_ctx):
    # پارامترهای پایداری برای جلوگیری از reset by peer
    return await asyncpg.create_pool(
        dsn,
        min_size=1,
        max_size=5,
        ssl=ssl_ctx,
        command_timeout=30,
        max_inactive_connection_lifetime=60,
        statement_cache_size=0,
    )

async def safe_init_db():
    """Init DB safely with SSL/Non-SSL fallback and clear logs."""
    global DB_READY, PG_DSN, LAST_DB_ERROR, PG_POOL
    LAST_DB_ERROR = None

    # اگر DATABASE_URL نبود، از قطعات بساز
    if not PG_DSN:
        PG_DSN = _build_dsn_from_parts()

    if not PG_DSN:
        DB_READY = False
        LAST_DB_ERROR = "DATABASE_URL/PGHOST… تعریف نشده."
        logging.error("DATABASE_URL not set and no PGHOST/PGUSER/… found.")
        return

    masked = _mask_dsn(PG_DSN)
    logging.info("Trying DB connect: %s", masked)

    # 1) تست با SSL
    try:
        ssl_ctx = ssl.create_default_context()
        PG_POOL = await _create_pool(PG_DSN, ssl_ctx)
        async with PG_POOL.acquire() as conn:
            await conn.execute("SELECT 1")
        DB_READY = True
        logging.info("DB connected with SSL.")
        return
    except Exception as e_ssl:
        logging.warning("DB SSL connect failed: %s", e_ssl)
        LAST_DB_ERROR = f"SSL connect failed: {e_ssl}"

    # 2) تست بدون SSL
    try:
        PG_POOL = await _create_pool(PG_DSN, None)
        async with PG_POOL.acquire() as conn:
            await conn.execute("SELECT 1")
        DB_READY = True
        LAST_DB_ERROR = None
        logging.info("DB connected WITHOUT SSL.")
        return
    except Exception as e_nossl:
        DB_READY = False
        LAST_DB_ERROR = f"Non-SSL connect failed: {e_nossl}"
        logging.exception("DB init failed (no SSL): %s", e_nossl)

async def _recreate_pool():
    global PG_POOL
    if PG_POOL:
        try:
            await PG_POOL.close()
        except:
            pass
    PG_POOL = None
    await safe_init_db()

async def db_execute(sql, *args):
    try:
        async with PG_POOL.acquire() as conn:
            return await conn.execute(sql, *args)
    except (asyncpg.PostgresError, ConnectionError, OSError) as e:
        logging.warning("db_execute retry after pool recreate: %s", e)
        await _recreate_pool()
        async with PG_POOL.acquire() as conn:
            return await conn.execute(sql, *args)

async def db_fetch(sql, *args):
    try:
        async with PG_POOL.acquire() as conn:
            return await conn.fetch(sql, *args)
    except (asyncpg.PostgresError, ConnectionError, OSError) as e:
        logging.warning("db_fetch retry after pool recreate: %s", e)
        await _recreate_pool()
        async with PG_POOL.acquire() as conn:
            return await conn.fetch(sql, *args)

async def db_fetchval(sql, *args):
    try:
        async with PG_POOL.acquire() as conn:
            return await conn.fetchval(sql, *args)
    except (asyncpg.PostgresError, ConnectionError, OSError) as e:
        logging.warning("db_fetchval retry after pool recreate: %s", e)
        await _recreate_pool()
        async with PG_POOL.acquire() as conn:
            return await conn.fetchval(sql, *args)

# CRUD helpers
async def upsert_user(u: types.User):
    if not DB_READY: return
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
    if not DB_READY:
        return False
    r = await db_fetch("SELECT 1 FROM admins WHERE user_id=$1", user_id)
    return bool(r)

def admin_only(fn):
    async def wrapper(message: types.Message, *a, **kw):
        if not await is_admin(message.from_user.id):
            await message.reply("⛔️ این دستور فقط برای ادمین‌هاست. /whoami رو بزن تا وضعیتت رو ببینی.")
            return
        try:
            # نـگـذرانـدن **kw تا state و... ارور ندن
            return await fn(message, *a)
        except Exception as e:
            logging.exception("Admin command failed: %s", e)
            await message.reply(f"❌ خطا در اجرای دستور: {e}")
    return wrapper

def require_db(fn):
    async def wrapper(message: types.Message, *a, **kw):
        if not DB_READY:
            await message.reply("⛔️ دیتابیس در دسترس نیست. `DATABASE_URL` را تنظیم کن و ری‌دیپلوی کن. /pgdiag و /debug را هم بزن.")
            return
        try:
            # اینجا هم **kw پاس نده
            return await fn(message, *a)
        except Exception as e:
            logging.exception("DB-backed command failed: %s", e)
            await message.reply(f"❌ خطای دیتابیس: {e}")
    return wrapper

# ---------- Membership ----------
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

# ---------- Commands ----------
@dp.message_handler(CommandStart())
async def start(message: types.Message):
    await upsert_user(message.from_user)  # no-op if DB not ready
    if await check_membership(message.from_user.id):
        await message.answer("🎉 سلام عمو! یکی از دکمه‌ها رو بزن:", reply_markup=main_kb)
    else:
        await message.answer("👋 اول باید عضو هر دو کانال شی:", reply_markup=join_keyboard())

@dp.message_handler(commands=['ping'])
async def ping_cmd(message: types.Message):
    await message.reply("🏓 pong")

@dp.message_handler(commands=['help'])
async def help_cmd(message: types.Message):
    if await is_admin(message.from_user.id):
        await message.reply(
            "🛠 راهنمای ادمین:\n"
            "• /whoami — نمایش آیدی و وضعیت ادمین\n"
            "• /whoadmins — لیست ادمین‌ها\n"
            "• /addadmin <user_id> — افزودن ادمین\n"
            "• /deladmin <user_id> — حذف ادمین\n"
            "• /send — ارسال همگانی (روی پیام/آلبوم ریپلای کنید)\n"
            "• /addphoto — افزودن عکس به خزانه (روی عکس ریپلای)\n"
            "• /delphoto — پاکسازی عکس‌های حذف‌شدهٔ کانال ۴ از خزانه\n"
            "• /dbstats — آمار دیتابیس\n"
            "• /topqueries — برترین جستجوها (۷ روز)\n"
            "• /cancel — خروج از حالت جستجو\n"
            "• /debug — وضعیت ادمین/کانال/DB\n"
            "• /pgdiag — عیب‌یابی اتصال دیتابیس\n\n"
            "کلیدها:\n"
            "📸 عکس به سلیقه عمو — ۳ عکس تصادفی جدید\n"
            "🔍 جستجوی دلخواه — جستجو با استایل هنری/سینمایی و بدون تکرار"
        )
    else:
        await message.reply(
            "سلام 👋\n"
            "از دکمه‌ها استفاده کن:\n"
            "• 📸 عکس به سلیقه عمو — ۳ عکس جدید از کانال\n"
            "• 🔍 جستجوی دلخواه — جستجو با حال‌و‌هوای هنری/سینمایی\n"
            "• ℹ️ درباره من — معرفی کوتاه\n"
            "• 💬 تماس با مالک عمو عکسی — راه تماس\n"
            "برای خروج از حالت جستجو: /cancel"
        )

@dp.message_handler(commands=['whoami'])
async def whoami(message: types.Message):
    admin = await is_admin(message.from_user.id)
    await message.reply(f"👤 user_id: {message.from_user.id}\n👮 admin: {'YES' if admin else 'NO'}")

@dp.message_handler(commands=['debug'])
async def debug_cmd(message: types.Message):
    uid = message.from_user.id
    admin = await is_admin(uid)
    try:
        member_ok = await check_membership(uid)
    except Exception:
        member_ok = False
    db_ok = DB_READY
    if DB_READY:
        try:
            await db_fetchval("SELECT 1")
        except Exception:
            db_ok = False
    await message.reply(
        "🔎 DEBUG\n"
        f"• user_id: {uid}\n"
        f"• admin: {'YES' if admin else 'NO'}\n"
        f"• channels joined: {'YES' if member_ok else 'NO'}\n"
        f"• db: {'OK' if db_ok else 'ERROR'}"
    )

@dp.message_handler(commands=['pgdiag'])
async def pgdiag(message: types.Message):
    masked = _mask_dsn(os.getenv("DATABASE_URL") or _build_dsn_from_parts() or "")
    details = [
        f"DB_READY: {'YES' if DB_READY else 'NO'}",
        f"DSN: {masked or '(not set)'}",
        f"LAST_DB_ERROR: {LAST_DB_ERROR or '(none)'}",
    ]
    await message.reply("🩺 PG Diag:\n" + "\n".join(details))

@dp.callback_query_handler(lambda c: c.data == "check_join")
async def check_join(call: types.CallbackQuery):
    if await check_membership(call.from_user.id):
        await call.message.answer("✅ به به آفرین حالا از دکمه ها استفاده کن عمو", reply_markup=main_kb)
    else:
        await call.message.answer("⛔️ هنوز عضو هر دو کانال نشدی عمو!", reply_markup=join_keyboard())

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

# --- Admin management ---
@dp.message_handler(commands=['whoadmins'])
@admin_only
@require_db
async def whoadmins(message: types.Message):
    rows = await db_fetch("SELECT user_id, added_at FROM admins ORDER BY added_at ASC")
    if not rows:
        await message.reply("لیست ادمین‌ها خالیه.")
        return
    msg = "\n".join([f"• {r['user_id']}  (since {r['added_at']:%Y-%m-%d})" for r in rows])
    await message.reply("👮 Admins:\n" + msg)

@dp.message_handler(commands=['addadmin'])
@admin_only
@require_db
async def addadmin(message: types.Message):
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("استفاده: /addadmin <user_id>")
        return
    uid = int(parts[1])
    await message.reply("⌛ در حال افزودن ادمین...")
    await db_execute("INSERT INTO admins(user_id) VALUES($1) ON CONFLICT DO NOTHING", uid)
    await message.reply(f"✅ {uid} اضافه شد.")

@dp.message_handler(commands=['deladmin'])
@admin_only
@require_db
async def deladmin(message: types.Message):
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("استفاده: /deladmin <user_id>")
        return
    uid = int(parts[1])
    await message.reply("⌛ در حال حذف ادمین...")
    await db_execute("DELETE FROM admins WHERE user_id=$1", uid)
    await message.reply(f"🗑 {uid} حذف شد.")

# --- Broadcast (single/album) ---
@dp.message_handler(commands=["send"])
@admin_only
@require_db
async def send_cmd(message: types.Message):
    if not message.reply_to_message:
        await message.reply("⛔️ باید روی یک پیام (یا یکی از عکس‌های آلبوم) ریپلای کنی.")
        return
    await message.reply("⌛ دارم ارسال همگانی رو شروع می‌کنم...")
    rows = await db_fetch("SELECT user_id FROM users")
    user_ids = [int(r["user_id"]) for r in rows]
    sent_count = 0
    error_count = 0

    r = message.reply_to_message
    if r.media_group_id:
        gid = str(r.media_group_id)
        album = ALBUM_CACHE.get(gid)
        if album and album["media"]:
            media_group = album["media"][:10]  # Telegram limit per send
            for uid in user_ids:
                try:
                    await bot.send_media_group(chat_id=uid, media=media_group)
                    sent_count += 1
                except Exception as e:
                    logging.warning("Broadcast album to %s failed: %s", uid, e)
                    error_count += 1
            if gid in ALBUM_CACHE:
                del ALBUM_CACHE[gid]
        else:
            for uid in user_ids:
                try:
                    await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=r.message_id)
                    sent_count += 1
                except Exception as e:
                    logging.warning("Broadcast copy to %s failed: %s", uid, e)
                    error_count += 1
    else:
        for uid in user_ids:
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=message.chat.id, message_id=r.message_id)
                sent_count += 1
            except Exception as e:
                logging.warning("Broadcast copy to %s failed: %s", uid, e)
                error_count += 1
    await message.reply(f"✅ {sent_count} نفر\n❌ {error_count} ناموفق")

# --- Add/cleanup photos in Channel 4 ---
@dp.message_handler(commands=["addphoto"])
@admin_only
@require_db
async def addphoto(message: types.Message):
    if not message.reply_to_message or not message.reply_to_message.photo:
        await message.reply("⛔️ باید روی یک عکس ریپلای کنی.")
        return
    await message.reply("⌛ در حال افزودن عکس به خزانه...")
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

@dp.message_handler(commands=["delphoto"])
@admin_only
@require_db
async def delphoto(message: types.Message):
    await message.reply("⌛ در حال بررسی عکس‌های حذف‌شده...")
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

# --- Stats ---
@dp.message_handler(commands=['dbstats'])
@admin_only
@require_db
async def dbstats(message: types.Message):
    await message.reply("⌛ جمع‌آوری آمار...")
    try:
        total_users  = await db_fetchval("SELECT COUNT(*) FROM users")
        total_posted = await db_fetchval("SELECT COUNT(*) FROM posted_photos")
        total_used   = await db_fetchval("SELECT COUNT(*) FROM used_photos")
        total_hist   = await db_fetchval("SELECT COUNT(*) FROM search_history")
        today_hist   = await db_fetchval("SELECT COUNT(*) FROM search_history WHERE seen_at::date = now()::date")
        week_hist    = await db_fetchval("SELECT COUNT(*) FROM search_history WHERE seen_at >= now() - interval '7 days'")
        await message.reply(
            "📊 آمار دیتابیس:\n"
            f"👥 Users: {total_users or 0}\n"
            f"🖼 Posted: {total_posted or 0}\n"
            f"✅ Used: {total_used or 0}\n"
            f"🔎 History: {total_hist or 0}\n"
            f"   • امروز: {today_hist or 0}\n"
            f"   • ۷ روز اخیر: {week_hist or 0}"
        )
    except Exception as e:
        logging.exception("dbstats failed: %s", e)
        await message.reply(f"❌ خطا در آمار: {e}\n"
                            "🔧 /pgdiag را بزن تا وضعیت اتصال مشخص شود.")

@dp.message_handler(commands=['topqueries'])
@admin_only
@require_db
async def topqueries(message: types.Message):
    await message.reply("⌛ محاسبهٔ برترین جستجوها...")
    rows = await db_fetch("""
        SELECT query, COUNT(*) c
        FROM search_history
        WHERE seen_at >= now() - interval '7 days'
        GROUP BY query
        ORDER BY c DESC
        LIMIT 10
    """)
    if not rows:
        await message.reply("🔎 این هفته جستجویی نداریم.")
        return
    lines = [f"{i+1}. {r['query']} — {r['c']}" for i, r in enumerate(rows)]
    await message.reply("🏆 Top queries (7d):\n" + "\n".join(lines))

# ---------- Artistic/Cinematic Search ----------
async def search_photos(query, page=1):
    # استایل ثابت فقط برای کوئری‌های انگلیسی اضافه می‌شود
    suffix = ", "
    q = f"{query}{suffix}" if _is_english(query) else query

    urls = []
    async with aiohttp.ClientSession() as s:
        # Unsplash
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
        except Exception as e:
            logging.warning("Unsplash fail: %s", e)

        # Pexels
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
        except Exception as e:
            logging.warning("Pexels fail: %s", e)

        # Pixabay
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
        except Exception as e:
            logging.warning("Pixabay fail: %s", e)

    # حذف تکراری‌های همین نوبت
    seen, unique = set(), []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            unique.append(u)
    return unique

@require_db
async def handle_search(message: types.Message):
    # تمدید تایم‌اوت مود جستجو
    SEARCH_MODE[message.from_user.id] = time.time()

    uid = int(message.from_user.id)
    query = (message.text or "").strip().lower()

    # صفحه رندوم اول
    page = random.randint(1, 5)
    batch1 = await search_photos(query, page=page)

    # فیلتر با تاریخچه دیتابیس (عدم تکرار)
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
    await message.answer("🎬 اگه بازم می‌خوای، دوباره جستجو کن", reply_markup=retry_keyboard("search"))

# ---------- Callbacks / Random ----------
@dp.callback_query_handler(lambda c: c.data in ["random", "search"])
async def retry_handler(call: types.CallbackQuery):
    if not await check_membership(call.from_user.id):
        await call.message.answer("⛔️ اول عضو هر دو کانال شو.", reply_markup=join_keyboard())
        return
    if call.data == "random":
        await send_random(call.message, call.from_user.id)
    elif call.data == "search":
        enter_search_mode(call.from_user.id)
        await call.message.answer("🔎 یه کلمه بفرست تا برات عکساشو بیارم! انگلیسی باشه بهتره")

@require_db
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
        except Exception as e:
            logging.warning("random send failed mid=%s: %s", mid, e)
            await db_execute("DELETE FROM posted_photos WHERE message_id=$1", int(mid))
    if sent_any:
        await message.answer("🎁 اینم از کانال عمو عکسی 😎", reply_markup=retry_keyboard("random"))
    else:
        await message.answer("⛔️ مشکلی پیش اومد، دوباره امتحان کن")

# ---------- Cancel search ----------
@dp.message_handler(commands=['cancel'])
async def cancel_search(message: types.Message):
    exit_search_mode(message.from_user.id)
    await message.reply("✅ از حالت جستجو خارج شدی.", reply_markup=main_kb)

# ---------- Unknown command feedback ----------
@dp.message_handler(lambda m: m.text and m.text.startswith('/') and m.text.split()[0] not in [
    '/start','/help','/whoami','/dbstats','/topqueries','/addadmin','/deladmin',
    '/send','/addphoto','/delphoto','/cancel','/ping','/debug','/whoadmins','/pgdiag'
])
async def unknown_command(message: types.Message):
    await message.reply(f"❓ این دستور شناخته نشد: {message.text}\n/help رو بزن.")

# ---------- Main text handler (non-command only) ----------
@dp.message_handler(lambda m: m.text and not m.text.startswith('/'))
async def handle_text(message: types.Message):
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
        await message.reply("🔎 خب عمو، یه کلمه بفرست برات عکسای خفن بیارم (انگلیسی باشه بهتره)")
        return

    elif txt == "ℹ️ درباره من":
        exit_search_mode(uid)
        await message.reply("👴 من عمو عکسی‌ام! دنیای بینهایتی از عکس دارم؛ همه‌چیز بستگی به سلیقهٔ جستجوی تو داره.")
        return

    elif txt == "💬 تماس با مالک عمو عکسی":
        exit_search_mode(uid)
        await message.reply("📮 برای صحبت با مالک عمو عکسی: @soulsownerbot")
        return

    if in_search_mode(uid):
        if not await check_membership(uid):
            await message.reply("⛔️ اول باید عضو کانالا باشی!", reply_markup=join_keyboard()); return
        await message.reply("⏳ صبر کن... دارم عکسای ناب پیدا می‌کنم...")
        await handle_search(message)
        return

    await message.reply("برای جستجو دکمه «🔍 جستجوی دلخواه» رو بزن یا /help رو ببین.", reply_markup=main_kb)

# ---------- Global error handler ----------
@dp.errors_handler()
async def global_errors_handler(update, error):
    try:
        if hasattr(update, "message") and update.message:
            await update.message.reply(f"⚠️ یه خطای غیرمنتظره رخ داد: {error}")
    except:
        pass
    logging.exception("Unhandled error: %s", error)
    return True

# ---------- Startup ----------
async def on_startup(dp):
    await safe_init_db()

    await bot.set_my_commands([
        BotCommand("start", "شروع"),
        BotCommand("help", "راهنما"),
        BotCommand("whoami", "نمایش آیدی و وضعیت ادمین"),
        BotCommand("debug", "وضعیت ادمین/کانال/DB"),
        BotCommand("pgdiag", "عیب‌یابی اتصال دیتابیس"),
        BotCommand("cancel", "خروج از حالت جستجو"),
        BotCommand("send", "ارسال همگانی (ادمین)"),
        BotCommand("addphoto", "افزودن عکس به خزانه (ادمین)"),
        BotCommand("delphoto", "پاکسازی لیست عکس‌ها (ادمین)"),
        BotCommand("whoadmins", "لیست ادمین‌ها (ادمین)"),
        BotCommand("addadmin", "افزودن ادمین (ادمین)"),
        BotCommand("deladmin", "حذف ادمین (ادمین)"),
        BotCommand("dbstats", "آمار دیتابیس (ادمین)"),
        BotCommand("topqueries", "برترین جستجوها (ادمین)"),
        BotCommand("ping", "تست زنده بودن ربات"),
    ])

    # notify initial admin
    try:
        if INITIAL_ADMIN:
            if DB_READY:
                await bot.send_message(INITIAL_ADMIN, "✅ Bot started. DB: OK\n/whoami /pgdiag /debug /help")
            else:
                await bot.send_message(INITIAL_ADMIN, "⚠️ Bot started **without DB**. `DATABASE_URL` را ست کن و ری‌دیپلوی کن.\n/pgdiag /whoami /debug /help")
    except Exception as e:
        logging.exception("Failed to DM initial admin: %s", e)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
