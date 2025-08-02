import logging
import os
import random
import requests
from PIL import Image
from io import BytesIO
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher.filters import CommandStart

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

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await show_subscription_check(message)

async def show_subscription_check(message):
    text = "لطفاً ابتدا در کانال‌های زیر عضو شوید ⬇️"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("کانال 1", url=CHANNEL_1_LINK),
        InlineKeyboardButton("کانال 2", url=CHANNEL_2_LINK),
        InlineKeyboardButton("✅ عضو شدم", callback_data="check_subs"),
        InlineKeyboardButton("💬 گروه چت سازنده", url=GROUP_LINK)
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
    text = "به ربات عمو عکسی خوش آمدی! یک گزینه رو انتخاب کن:"
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("📷 انتخاب پروفایل"),
        KeyboardButton("🔍 جستجو"),
        KeyboardButton("ℹ️ درباره")
    ).add(
        KeyboardButton("❓ راهنما"),
        KeyboardButton("📞 ارتباط با سازنده")
    )
    await message.answer(text, reply_markup=keyboard)

@dp.message_handler(lambda msg: msg.text.startswith("❓") or msg.text.startswith("ℹ️") or msg.text.startswith("📞"))
async def static_pages(message: types.Message):
    if "❓" in message.text:
        await message.answer("📘 راهنمای استفاده از ربات:\n1. ابتدا در کانال‌ها عضو شو\n2. روی \"انتخاب پروفایل\" یا \"جستجو\" بزن\n3. دسته‌بندی یا موضوع رو انتخاب کن\n4. پروفایل‌ت رو دریافت کن!")
    elif "ℹ️" in message.text:
        await message.answer("🤖 این ربات توسط تیم راینو ساخته شده تا برای پروفایل تلگرام عکس‌های جذاب و مربعی فراهم کنه. بدون چهره، با کیفیت بالا، در سبک‌های متنوع!")
    elif "📞" in message.text:
        await message.answer("📬 تماس با ما: @oldkaseb")

@dp.message_handler(lambda msg: "پروفایل" in msg.text)
async def choose_profile_category(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("👦 پسرانه", callback_data="cat_boy"),
        InlineKeyboardButton("👧 دخترانه", callback_data="cat_girl"),
        InlineKeyboardButton("🎲 تصادفی", callback_data="cat_random")
    )
    await message.answer("یک دسته‌بندی انتخاب کن:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("cat_"))
async def send_category_based_image(callback: types.CallbackQuery):
    category = callback.data.split("_")[1]
    if category == "boy":
        query = "dark aesthetic male faceless profile background"
    elif category == "girl":
        query = "dreamy girl faceless aesthetic profile background"
    else:
        query = random.choice([
            "minimal abstract profile background",
            "anime faceless aesthetic",
            "soft color faceless pfp"
        ])
    await fetch_and_send_images(callback.message, query)

@dp.message_handler(lambda msg: "جستجو" in msg.text)
async def ask_for_keyword(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("🌌 استایل تیره بدون چهره", callback_data="q_dark"),
        InlineKeyboardButton("🧚‍♀️ دختر فانتزی پشت به دوربین", callback_data="q_fantasy"),
        InlineKeyboardButton("🎴 انیمه مینیمال", callback_data="q_anime"),
        InlineKeyboardButton("🌀 مینیمال هنری", callback_data="q_minimal"),
        InlineKeyboardButton("🎨 ترکیب رنگی آرام", callback_data="q_soft")
    )
    await message.answer("یا انتخاب کن، یا خودت بنویس:", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("q_"))
async def handle_suggested_query(callback: types.CallbackQuery):
    mapping = {
        "q_dark": "dark aesthetic faceless profile",
        "q_fantasy": "fantasy girl back silhouette",
        "q_anime": "faceless anime aesthetic pfp",
        "q_minimal": "minimal abstract aesthetic profile",
        "q_soft": "soft pastel background faceless"
    }
    query = mapping.get(callback.data, "faceless profile")
    await fetch_and_send_images(callback.message, query)

@dp.message_handler(content_types=types.ContentType.TEXT)
async def handle_custom_query(message: types.Message):
    if message.text.lower().startswith("/"):
        return
    await fetch_and_send_images(message, message.text)

def unsplash_fetch(query):
    try:
        url = f"https://api.unsplash.com/search/photos?query={query}&per_page=5&orientation=squarish&content_filter=high&client_id={UNSPLASH_KEY}"
        r = requests.get(url)
        data = r.json()
        return [item["urls"]["regular"] for item in data.get("results", [])]
    except:
        return []

def pexels_fetch(query):
    try:
        url = f"https://api.pexels.com/v1/search?query={query}&per_page=5"
        headers = {"Authorization": PEXELS_KEY}
        r = requests.get(url, headers=headers)
        data = r.json()
        return [item["src"]["medium"] for item in data.get("photos", []) if "face" not in item.get("alt", "").lower()]
    except:
        return []

def pixabay_fetch(query):
    try:
        url = f"https://pixabay.com/api/?key={PIXABAY_KEY}&q={query}&image_type=photo&category=backgrounds&safesearch=true&editors_choice=true&per_page=5"
        r = requests.get(url)
        data = r.json()
        return [item["largeImageURL"] for item in data.get("hits", []) if not item.get("userImageURL")]
    except:
        return []

def make_square_image_from_url(url):
    try:
        response = requests.get(url)
        img = Image.open(BytesIO(response.content)).convert("RGB")
        min_side = min(img.size)
        left = (img.width - min_side) // 2
        top = (img.height - min_side) // 2
        right = left + min_side
        bottom = top + min_side
        cropped = img.crop((left, top, right, bottom))
        output = BytesIO()
        output.name = "profile.jpg"
        cropped.save(output, format="JPEG")
        output.seek(0)
        return output
    except:
        return None

async def fetch_and_send_images(message, query):
    await message.answer("🔄 در حال دریافت عکس‌های با کیفیت و بدون چهره ...")
    imgs = unsplash_fetch(query) + pexels_fetch(query) + pixabay_fetch(query)
    if not imgs:
        await message.answer("متأسفم! عکسی پیدا نشد.")
        return
    sample = random.sample(imgs, min(3, len(imgs)))
    for url in sample:
        file = make_square_image_from_url(url)
        if file:
            await message.answer_photo(photo=file)
    await message.answer("✅ ارسال عکس‌ها به پایان رسید. از عکس‌ها لذت ببر!")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
