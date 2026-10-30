from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="← Назад", callback_data="back")],
    ])


def source_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📁 Группа", callback_data="src_type:group"),
            InlineKeyboardButton(text="📌 Топик в группе", callback_data="src_type:topic"),
            InlineKeyboardButton(text="📢 Канал", callback_data="src_type:channel"),
        ],
        [InlineKeyboardButton(text="← Назад", callback_data="back")],
    ])


def dest_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📁 Группа", callback_data="dst_type:group"),
            InlineKeyboardButton(text="📌 Топик в группе", callback_data="dst_type:topic"),
        ],
        [InlineKeyboardButton(text="← Назад", callback_data="back")],
    ])


def media_filter_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📦 Всё", callback_data="media:all")],
        [InlineKeyboardButton(text="🖼 Только фото", callback_data="media:photo")],
        [InlineKeyboardButton(text="🎬 Только видео", callback_data="media:video")],
        [InlineKeyboardButton(text="← Назад", callback_data="back")],
    ])


def direction_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ К старым", callback_data="direction:older")],
        [InlineKeyboardButton(text="⬇️ К новым", callback_data="direction:newer")],
        [InlineKeyboardButton(text="← Назад", callback_data="back")],
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Запустить", callback_data="launch")],
        [InlineKeyboardButton(text="← Назад", callback_data="back")],
    ])


def running_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏸ Пауза", callback_data="pause"),
            InlineKeyboardButton(text="⏹ Остановить", callback_data="stop"),
        ],
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")],
    ])


def paused_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="▶ Возобновить", callback_data="resume"),
            InlineKeyboardButton(text="⏹ Остановить", callback_data="stop"),
        ],
        [InlineKeyboardButton(text="📊 Статус", callback_data="status")],
    ])
