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

REQUIRED_ENV_VARS = ["BOT_TOKEN", "CHANNEL_1", "CHANNEL_2", "CHANNEL_3", "CHANNEL_1_LINK", "CHANNEL_2_LINK", "CHANNEL_3_LINK", "ADMIN_ID"]
for var in REQUIRED_ENV_VARS:
    if not os.getenv(var):
        raise ValueError(f"Missing required environment variable: {var}")

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
user_input_mode = {}

USERS_FILE = "users.json"
USED_PHOTOS_FILE = "used_photos.json"
POSTED_FILE = "posted.json"


def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)

def load_used_photos():
    if os.path.exists(USED_PHOTOS_FILE):
        with open(USED_PHOTOS_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_used_photos(photo_ids):
    with open(USED_PHOTOS_FILE, "w") as f:
        json.dump(list(photo_ids), f)

def load_posted_ids():
    if os.path.exists(POSTED_FILE):
        with open(POSTED_FILE, "r") as f:
            return json.load(f)
    return []

def save_posted_ids(posted_ids):
    with open(POSTED_FILE, "w") as f:
        json.dump(posted_ids, f, indent=2)


users = load_users()
used_photo_ids = load_used_photos()
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
        # پیام‌هایی که ارسال نشده‌اند را انتخاب کنیم
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

async def show_forwarding_control(message):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("شروع فوروارد", callback_data="start_forwarding"),
        InlineKeyboardButton("بستن فوروارد", callback_data="stop_forwarding")
    )
    await message.answer("کنترل فوروارد پیام‌ها", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "start_forwarding")
async def start_forwarding_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("فوروارد کردن پیام‌ها شروع شد.")

@dp.callback_query_handler(lambda c: c.data == "stop_forwarding")
async def stop_forwarding_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("فوروارد کردن پیام‌ها متوقف شد.")

@dp.callback_query_handler(lambda c: c.data == "more_channel_photo")
async def handle_more_channel_photo(callback: types.CallbackQuery):
    await callback.message.delete_reply_markup()
    await send_random_channel_photo(callback.message)

@dp.message_handler(lambda msg: msg.text == "جستجوی دلخواه")
async def ask_for_custom_query_text(message: types.Message):
    await message.answer("چی پیدا کنم برات عمو جون بخواه فداتشم تایپ کن من میرم میارم")
    user_input_mode[message.from_user.id] = True

async def fetch_and_send_images(message, query, user_id):
    await message.answer("عمو داره سرچ میکنه...")
    imgs = unsplash_fetch(query) + pexels_fetch(query) + pixabay_fetch(query)
    random.shuffle(imgs)
    new_imgs = []
    seen = sent_cache.setdefault(user_id, set())
    for url in imgs[:100]:
        if url in seen:
            continue
        file = make_square_image_from_url(url)
        if file:
            new_imgs.append(InputMediaPhoto(media=file))
            seen.add(url)
        if len(new_imgs) >= 10:
            break
    if new_imgs:
        try:
            await bot.send_media_group(message.chat.id, new_imgs)
        except:
            await message.answer("❌ عمو نتونست عکس بفرسته، دوباره امتحان کن")
            return
        await message.answer("عمو برات عکس اورده")
        keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("🔁 عمو عمو دوباره", callback_data="retry_search"))
        await message.answer("میخوای دوباره جست‌وجو کنی عمو؟", reply_markup=keyboard)
    else:
        await message.answer("چیز به درد بخوری پیدا نکردم عمو")

@dp.callback_query_handler(lambda c: c.data == "retry_search")
async def retry_search(callback: types.CallbackQuery):
    await callback.message.delete_reply_markup()
    await callback.message.answer("چی پیدا کنم برات عمو جون بخواه فداتشم تایپ کن من میرم میارم")
    user_id = callback.from_user.id
    sent_cache[user_id] = set()
    user_input_mode[user_id] = True

def unsplash_fetch(query):
    try:
        url = f"https://api.unsplash.com/search/photos?query={query}&per_page=30&orientation=squarish&content_filter=high&client_id={UNSPLASH_KEY}"
        r = requests.get(url)
        data = r.json()
        return [item["urls"]["regular"] for item in data.get("results", []) if item.get("width", 0) >= 600 and item.get("height", 0) >= 600]
    except:
        return []

def pexels_fetch(query):
    try:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=30"
        headers = {"Authorization": PEXELS_KEY}
        r = requests.get(url, headers=headers)
        data = r.json()
        return [item["src"]["large"] for item in data.get("photos", []) if "face" not in item.get("alt", "").lower()]
    except:
        return []

def pixabay_fetch(query):
    try:
        url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={query}&image_type=photo&category=backgrounds&safesearch=true&editors_choice=true&per_page=30"
        r = requests.get(url)
        data = r.json()
        return [item["largeImageURL"] for item in data.get("hits", []) if not item.get("userImageURL") and "face" not in item.get("tags", "").lower()]
    except:
        return []

def make_square_image_from_url(url):
    try:
        response = requests.get(url)
        if len(response.content) < 100 * 1024:
            return None
        img = Image.open(BytesIO(response.content)).convert("RGB")
        if img.width < 600 or img.height < 600:
            return None
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

@dp.message_handler(commands=["help"])
async def show_help(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    await message.answer("""دستورات:
/start — شروع
/help — لیست دستورات
/stats — آمار کاربران
/send — پیام همگانی (با ریپلای)
/post — پست کردن عکس توی کانال سوم""")

@dp.message_handler(commands=["stats"])
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    total = len(users)
    await message.answer(f"تعداد کاربران: {total}")

@dp.message_handler(commands=["send"])
async def broadcast_command(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        await message.answer("هزار بار گفتم ریپ بزن کیرت بشکنه")
        return
    count = 0
    for uid in users.keys():
        try:
            await bot.copy_message(
                chat_id=int(uid),
                from_chat_id=message.chat.id,
                message_id=message.reply_to_message.message_id
            )
            count += 1
        except:
            pass
    await message.answer(f"📢 پیام برای {count} نفر فرستاده شد.")

@dp.message_handler(commands=["start_forwarding"])
async def start_forwarding(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    # شروع فوروارد کردن پیام‌ها
    await message.answer("حالا می‌تونی پیام‌ها رو فوروارد کنی عمو.")

@dp.message_handler(commands=["stop_forwarding"])
async def stop_forwarding(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    # متوقف کردن فوروارد کردن پیام‌ها
    await message.answer("فوروارد کردن پیام‌ها متوقف شد عمو.")

@dp.message_handler(content_types=types.ContentType.TEXT)
async def forward_message_handler(message: types.Message):
    if message.forward_from_chat and message.forward_from_chat.id == CHANNEL_3:
        # اگر پیام فوروارد شده از کانال عمو عکسی بود، ذخیره کنیم
        posted_ids.append(message.message_id)
        save_posted_ids(posted_ids)
        await message.answer("پیام فوروارد شد عمو. ممنون که فرستادی!")

@dp.message_handler(commands=["post"])
async def post_to_channel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    if not message.reply_to_message:
        await message.answer("عمو جون ریپلای کن روی پیامی که می‌خوای بفرستم تو کانال!")
        return
    try:
        sent = await bot.copy_message(
            chat_id=CHANNEL_3,
            from_chat_id=message.chat.id,
            message_id=message.reply_to_message.message_id
        )
        posted_ids.append(sent.message_id)
        save_posted_ids(posted_ids)
        await message.answer("✅ تو کانال فرستادم عمو!")
    except Exception as e:
        await message.answer(f"نشد عمو کیرت تو چرخ گوشت:\n\n`{e}`", parse_mode="Markdown")

@dp.message_handler()
async def catch_text(message: types.Message):
    user_id = message.from_user.id
    if user_input_mode.get(user_id, False):
        await fetch_and_send_images(message, message.text, user_id)
        user_input_mode[user_id] = False

@dp.message_handler(lambda msg: msg.chat.type != "private")
async def ignore_group_messages(message: types.Message):
    return

async def on_startup(dp):
    await bot.delete_webhook(drop_pending_updates=True)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
