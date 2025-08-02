import logging
import os
import random
import requests
from PIL import Image
from io import BytesIO
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, InputMediaPhoto
from aiogram.utils.exceptions import BadRequest

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
PEXELS_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

sent_cache = {}  # user_id: set of image URLs

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    sent_cache[message.from_user.id] = set()
    await show_subscription_check(message)

async def show_subscription_check(message):
    text = "لطفاً ابتدا در کانال‌های زیر عضو شوید ⬇️"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("کانال 1", url=CHANNEL_1_LINK),
        InlineKeyboardButton("کانال 2", url=CHANNEL_2_LINK),
        InlineKeyboardButton("✅ عضو شدم", callback_data="check_subs"),
        InlineKeyboardButton("گروه چت اسپانسر", url=GROUP_LINK)
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

    if await is_member(CHANNEL_1) and await is_member(CHANNEL_2):
        await show_main_menu(callback.message)
    else:
        await callback.answer("عضویت کامل نیست ❌", show_alert=True)

async def show_main_menu(message):
    text = "به ربات عمو عکسی خوش آمدی! فقط جستجو کن یا یکی از شماره‌های پیشنهادی رو بزن."
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("🔍 جستجو"),
        KeyboardButton("ℹ️ درباره"),
        KeyboardButton("❓ راهنما")
    ).add(
        KeyboardButton("📞 ارتباط با سازنده")
    )
    await message.answer(text, reply_markup=keyboard)

@dp.message_handler(lambda msg: msg.text.startswith("❓") or msg.text.startswith("ℹ️") or msg.text.startswith("📞"))
async def static_pages(message: types.Message):
    if "❓" in message.text:
        await message.answer("📘 فقط کلمه‌ای مثل 'دختر انیمه' یا 'پروفایل تاریک' تایپ کن یا یکی از شماره‌های پیشنهادی رو بزن.")
    elif "ℹ️" in message.text:
        await message.answer("🤖 ربات عمو عکسی توسط تیم راینو ساخته شده برای ارسال عکس‌های با کیفیت و مناسب پروفایل.")
    elif "📞" in message.text:
        await message.answer("📬 تماس با ما: @oldkaseb")

@dp.message_handler(lambda msg: "جستجو" in msg.text)
async def suggest_keywords(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=4)
    for i in range(1, 81):
        keyboard.insert(InlineKeyboardButton(str(i), callback_data=f"q_{i}"))
    await message.answer("🔢 یکی از گزینه‌های پیشنهادی رو انتخاب کن یا متن مورد نظرتو تایپ کن:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("q_"))
async def handle_suggested_query(callback: types.CallbackQuery):
    number = callback.data[2:]
    query = f"پروفایل شماره {number}"
    await fetch_and_send_images(callback.message, query, callback.from_user.id)
    try:
        await callback.message.edit_reply_markup()
    except BadRequest:
        pass
    await show_retry_button(callback.message)

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_custom_query(message: types.Message):
    if message.text.lower().startswith("/"):
        return
    await fetch_and_send_images(message, message.text, message.from_user.id)
    await show_retry_button(message)

async def show_retry_button(message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔍 جستجوی مجدد", callback_data="again"))
    await message.answer("می‌تونی دوباره جستجو کنی:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data == "again")
async def retry_suggestions(callback: types.CallbackQuery):
    await suggest_keywords(callback.message)


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

async def fetch_and_send_images(message, query, user_id):
    await message.answer("🔄 در حال دریافت عکس‌های با کیفیت ...")
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
        await message.answer("✅ عکس‌ها ارسال شدند.")
    else:
        await message.answer("متأسفم! عکسی با کیفیت مناسب پیدا نشد.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
