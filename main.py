import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.dispatcher.filters import CommandStart
from aiogram.contrib.middlewares.i18n import I18nMiddleware
from aiogram.utils.callback_data import CallbackData

# Logging
logging.basicConfig(level=logging.INFO)

# Environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

# Bot and Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Language storage
user_lang = {}

# Callback data factories
lang_cb = CallbackData("lang", "code")
category_cb = CallbackData("cat", "gender", "sub")

# --- Language Selection ---
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    lang_code = message.from_user.language_code

    if lang_code.startswith("fa"):
        user_lang[user_id] = "fa"
    else:
        user_lang[user_id] = "en"

    await show_language_menu(message)

async def show_language_menu(message):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("فارسی", callback_data=lang_cb.new(code="fa")),
        InlineKeyboardButton("English", callback_data=lang_cb.new(code="en"))
    )
    await message.answer("Choose your language | زبان را انتخاب کنید", reply_markup=keyboard)

@dp.callback_query_handler(lang_cb.filter())
async def set_language(callback: types.CallbackQuery, callback_data: dict):
    user_id = callback.from_user.id
    user_lang[user_id] = callback_data["code"]
    await callback.message.delete()
    await show_subscription_check(callback.message)

# --- Subscription Check ---
async def show_subscription_check(message):
    lang = user_lang.get(message.from_user.id, "en")
    text = {
        "fa": "برای استفاده از ربات، لطفاً در کانال‌ها عضو شوید:",
        "en": "Please join the channels to use the bot:"
    }[lang]

    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("کانال 1 | Channel 1", url=CHANNEL_1_LINK),
        InlineKeyboardButton("کانال 2 | Channel 2", url=CHANNEL_2_LINK),
        InlineKeyboardButton("عضو شدم ✅", callback_data="check_subs"),
        InlineKeyboardButton("💬 گروه تیم راینو | Group", url=GROUP_LINK)
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

# --- Main Menu ---
async def show_main_menu(message):
    lang = user_lang.get(message.from_user.id, "en")
    text = {
        "fa": "به ربات عمو عکسی خوش آمدی! یکی از گزینه‌ها را انتخاب کن:",
        "en": "Welcome to Uncle Pici! Choose an option:"
    }[lang]

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

# --- Language Change ---
@dp.message_handler(lambda msg: "زبان" in msg.text or "Language" in msg.text)
async def change_lang(message: types.Message):
    await show_language_menu(message)

# --- Help / About / Contact / Group ---
@dp.message_handler(lambda msg: msg.text.startswith("❓") or msg.text.startswith("ℹ️") or msg.text.startswith("📞"))
async def static_pages(message: types.Message):
    lang = user_lang.get(message.from_user.id, "en")
    if "❓" in message.text:
        await message.answer("📘 راهنمای استفاده از ربات..." if lang == "fa" else "📘 Help guide coming soon...")
    elif "ℹ️" in message.text:
        await message.answer("🤖 ربات عمو عکسی، ساخته شده توسط تیم Rhino..." if lang == "fa" else "🤖 Uncle Pici bot, made by Team Rhino...")
    elif "📞" in message.text:
        await message.answer("📬 تماس با ما: @whitewolf.has5" if lang == "fa" else "📬 Contact us: @whitewolf.has5")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
