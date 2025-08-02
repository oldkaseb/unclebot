async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    await query.answer()

    if query.data == "check_subscription":
        if await is_user_member(user_id):
            keyboard = [[
                InlineKeyboardButton("🖼 تبدیل متن به عکس", callback_data="text_to_image"),
                InlineKeyboardButton("🎌 تبدیل عکس به انیمه", callback_data="photo_to_anime")
            ]]
            await query.edit_message_text(
                "✅ عضویت شما تأیید شد. حالا یکی از گزینه‌ها رو انتخاب کن:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(
                "⛔️ هنوز در یکی از کانال‌ها عضو نیستی! لطفاً دوباره بررسی کن.",
                reply_markup=build_subscription_keyboard()
            )

    elif query.data == "text_to_image":
        context.user_data['mode'] = 'prompt'
        await query.edit_message_text("لطفاً پرامپت (توضیح تصویری) خود را وارد کنید:")

    elif query.data == "photo_to_anime":
        context.user_data['mode'] = 'photo'
        await query.edit_message_text("لطفاً عکس موردنظر را ارسال کنید:")
