import logging
import os
import random
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

user_lang = {}

# Sample image links (to replace later with real sources or APIs)
boy_links = [
    "https://i.pinimg.com/736x/1a/3c/f2/sample1.jpg",
    "https://i.pinimg.com/736x/3b/6e/ab/sample2.jpg",
]
girl_links = [
    "https://i.pinimg.com/736x/cc/7e/2a/sample3.jpg",
    "https://i.pinimg.com/736x/bf/2a/d1/sample4.jpg",
]
random_links = boy_links + girl_links

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    lang_code = message.from_user.language_code
    user_lang[user_id] = "fa" if lang_code.startswith("fa") else "en"
    await show_language_menu(message)

async def show_language_menu(message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("فارسی", callback_data="lang_fa"),
        InlineKeyboardButton("English", callback_data="lang_en")
    )
    await message.answer("زبان را انتخاب کنید | Choose your language", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("lang_"))
async def set_language(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    lang = callback.data.split("_")[1]
    user_lang[user_id] = lang
    await callback.message.delete()
    await show_subscription_check(callback.message, user_id)

async def show_subscription_check(message, user_id):
    lang = user_lang.get(user_id, "en")
    text = "لطفاً ابتدا در کانال‌های زیر عضو شوید ⬇️" if lang == "fa" else "Please join the following channels first ⬇️"
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("کانال 1 | Channel 1", url=CHANNEL_1_LINK),
        InlineKeyboardButton("کانال 2 | Channel 2", url=CHANNEL_2_LINK),
        InlineKeyboardButton("✅ عضو شدم", callback_data="check_subs"),
        InlineKeyboardButton("💬 گروه چت سازنده | Group", url=GROUP_LINK)
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
        await callback.answer("عضویت کامل نیست ❌" if user_lang.get(user_id, "fa") == "fa" else "You haven't joined all channels ❌", show_alert=True)

async def show_main_menu(message):
    lang = user_lang.get(message.from_user.id, "en")
    text = "به ربات عمو عکسی خوش آمدی! یک گزینه رو انتخاب کن:" if lang == "fa" else "Welcome to Uncle Pici! Choose an option:"

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton("📷 انتخاب پروفایل / Choose Profile"),
        KeyboardButton("ℹ️ درباره / About"),
        KeyboardButton("❓ راهنما / Help")
    ).add(
        KeyboardButton("🗣 تغییر زبان / Language"),
        KeyboardButton("📞 ارتباط با سازنده / Contact")
    )

    await message.answer(text, reply_markup=keyboard)

@dp.message_handler(lambda msg: "زبان" in msg.text or "Language" in msg.text)
async def change_lang(message: types.Message):
    await show_language_menu(message)

@dp.message_handler(lambda msg: msg.text.startswith("❓") or msg.text.startswith("ℹ️") or msg.text.startswith("📞"))
async def static_pages(message: types.Message):
    lang = user_lang.get(message.from_user.id, "en")
    if "❓" in message.text:
        txt = "📘 راهنمای استفاده از ربات:\n1. ابتدا زبان و عضویت را کامل کن\n2. روی \"انتخاب پروفایل\" بزن\n3. دسته‌بندی عکس رو انتخاب کن\n4. پروفایل‌ت رو دریافت کن!" if lang == "fa" else "📘 How to use the bot:\n1. Choose your language and join channels\n2. Tap 'Choose Profile'\n3. Select category\n4. Receive your profile pic!"
        await message.answer(txt)
    elif "ℹ️" in message.text:
        txt = "🤖 این ربات توسط تیم راینو ساخته شده تا برای پروفایل تلگرام و شبکه‌های اجتماعی‌ات عکس‌های مربعی و جذاب فراهم کنه.\nپشتیبانی از دسته‌بندی پسرانه، دخترانه، تصادفی و موارد بیشتر در راه هست!" if lang == "fa" else "🤖 This bot is built by Team Rhino to give you stylish square profile pics for Telegram and social media.\nSupport for male, female, and random categories – more coming soon!"
        await message.answer(txt)
    elif "📞" in message.text:
        txt = "📬 تماس با ما: @oldkaseb" if lang == "fa" else "📬 Contact us: @oldkaseb"
        await message.answer(txt)

@dp.message_handler(lambda msg: "پروفایل" in msg.text or "Profile" in msg.text)
async def choose_profile_category(message: types.Message):
    lang = user_lang.get(message.from_user.id, "en")
    text = "دسته‌بندی پروفایل رو انتخاب کن:" if lang == "fa" else "Select a profile category:"
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("👦 پسرانه", callback_data="cat_boy"),
        InlineKeyboardButton("👧 دخترانه", callback_data="cat_girl"),
        InlineKeyboardButton("🎲 تصادفی", callback_data="cat_random")
    )
    await message.answer(text, reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("cat_"))
async def send_profile_image(callback: types.CallbackQuery):
    cat = callback.data.split("_")[1]
    if cat == "boy":
        url = random.choice(boy_links)
    elif cat == "girl":
        url = random.choice(girl_links)
    else:
        url = random.choice(random_links)

    lang = user_lang.get(callback.from_user.id, "en")
    caption = "پروفایل انتخابی شما 👇" if lang == "fa" else "Here is your profile picture 👇"
    await callback.message.answer_photo(url, caption=caption)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
