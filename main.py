import os
import openai
import httpx
import asyncio
from PIL import Image
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes)
import aiofiles
import time
import nest_asyncio

# --- تنظیمات ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
CHANNEL_1 = os.getenv("CHANNEL_1")
CHANNEL_2 = os.getenv("CHANNEL_2")
CHANNEL_1_LINK = os.getenv("CHANNEL_1_LINK")
CHANNEL_2_LINK = os.getenv("CHANNEL_2_LINK")
GROUP_LINK = os.getenv("GROUP_LINK")
TIME_LIMIT_MIN = int(os.getenv("TIME_LIMIT_MIN", 15))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

user_last_time = {}
user_edit_state = {}

async def check_user_membership(user_id: int, channel: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=f"@{channel}", user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

async def is_user_member(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    in_channel_1 = await check_user_membership(user_id, CHANNEL_1, context)
    in_channel_2 = await check_user_membership(user_id, CHANNEL_2, context)
    return in_channel_1 and in_channel_2

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_user_member(user_id, context):
        keyboard = [[
            InlineKeyboardButton("عضویت در کانال ۱ ✅", url=CHANNEL_1_LINK),
            InlineKeyboardButton("عضویت در کانال ۲ ✅", url=CHANNEL_2_LINK)
        ], [
            InlineKeyboardButton("عضو شدم ✅", callback_data="check_membership")
        ]]
        if GROUP_LINK:
            keyboard.append([InlineKeyboardButton("گروه اسپانسر 💬", url=GROUP_LINK)])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("برای استفاده از ربات، لطفاً ابتدا در دو کانال زیر عضو شوید:", reply_markup=reply_markup)
        return

    keyboard = [
        [InlineKeyboardButton("🔮 ساخت تصویر از متن", callback_data="create_image")],
        [InlineKeyboardButton("🖌 ویرایش تصویر", callback_data="edit_image")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("به ربات خوش آمدید! یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "check_membership":
        if await is_user_member(user_id, context):
            await start(update, context)
        else:
            await query.edit_message_text("❌ شما هنوز در کانال‌ها عضو نشده‌اید. لطفاً مجدد تلاش کنید.")
    elif query.data == "create_image":
        await query.edit_message_text("لطفا یک توضیح برای تصویر بنویس (مثلا: «یک گربه در حال نواختن گیتار»)")
        context.user_data['awaiting_prompt'] = True
    elif query.data == "edit_image":
        await query.edit_message_text("لطفا یک عکس ارسال کنید که می‌خواهید ویرایش شود.")
        context.user_data['awaiting_image'] = True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if 'awaiting_prompt' in context.user_data:
        prompt = update.message.text
        now = time.time()
        if user_id in user_last_time and now - user_last_time[user_id] < TIME_LIMIT_MIN * 60:
            remaining = TIME_LIMIT_MIN - int((now - user_last_time[user_id]) / 60)
            await update.message.reply_text(f"⏳ لطفا {remaining} دقیقه دیگر تلاش کنید.")
            return

        await update.message.reply_text("در حال ساخت تصویر... ⏳")
        try:
            response = openai.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1
            )
            image_url = response.data[0].url
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=image_url)
            user_last_time[user_id] = now
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در تولید تصویر: {e}")

        context.user_data.pop('awaiting_prompt', None)

    elif 'awaiting_image' in context.user_data:
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            photo_bytes = await photo_file.download_as_bytearray()
            image_path = f"temp/{user_id}_edit.png"
            os.makedirs("temp", exist_ok=True)
            async with aiofiles.open(image_path, "wb") as out_file:
                await out_file.write(photo_bytes)

            user_edit_state[user_id] = image_path
            await update.message.reply_text("✅ عکس دریافت شد. حالا لطفاً توضیحی بنویسید که ربات طبق آن عکس را ویرایش کند.")
            context.user_data.pop('awaiting_image', None)
            context.user_data['awaiting_edit_prompt'] = True
        else:
            await update.message.reply_text("❌ لطفا یک تصویر ارسال کنید.")

    elif 'awaiting_edit_prompt' in context.user_data:
        edit_prompt = update.message.text
        image_path = user_edit_state.get(user_id)
        if not image_path:
            await update.message.reply_text("❌ تصویری برای ویرایش یافت نشد.")
            return

        await update.message.reply_text("در حال ویرایش تصویر... ⏳")
        try:
            with open(image_path, "rb") as img_file:
                response = openai.images.edit(
                    model="dall-e-3",
                    image=img_file,
                    prompt=edit_prompt,
                    size="1024x1024",
                    n=1
                )
            edited_image_url = response.data[0].url
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=edited_image_url)
        except Exception as e:
            await update.message.reply_text(f"❌ خطا در ویرایش تصویر: {e}")

        context.user_data.pop('awaiting_edit_prompt', None)
        user_edit_state.pop(user_id, None)

async def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT | filters.PHOTO, handle_message))

    await app.run_polling(close_loop=False)

if __name__ == '__main__':
    nest_asyncio.apply()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
