from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
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
