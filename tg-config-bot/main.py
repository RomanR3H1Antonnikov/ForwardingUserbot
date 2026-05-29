import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message
from dotenv import load_dotenv

from keyboards import back_keyboard, confirm_keyboard, paused_keyboard, running_keyboard
from launcher import (
    create_pause_flag,
    is_process_alive,
    launch_userbot,
    remove_pause_flag,
    status_info,
    stop_process,
)
from link_parser import parse_tme_link
from states import SetupFlow

load_dotenv(Path(__file__).parent / ".env")

BOT_TOKEN = os.environ["BOT_TOKEN"]
USERBOT_DIR = os.getenv("USERBOT_DIR", "..")
_raw_ids = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_IDS: set[int] = {int(x.strip()) for x in _raw_ids.split(",") if x.strip()}

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

_SOURCE_PROMPT = (
    "Скиньте ссылку на сообщение в нужной группе нужного топика, "
    "<b>откуда</b> будет происходить пересылка.\n\n"
    "Пересылка выполнится от этого сообщения включительно до самого старого."
)
_DEST_PROMPT = (
    "Скиньте ссылку на <b>любое</b> сообщение из нужного топика нужной группы, "
    "<b>куда</b> будет всё скидываться."
)
_BAD_LINK = (
    "Не распознал ссылку. Нужна ссылка вида:\n"
    "<code>https://t.me/c/1234567890/42/100</code>"
)
_NO_TOPIC = (
    "В ссылке не найден топик. Убедитесь, что ссылка ведёт на сообщение "
    "внутри топика — формат: <code>.../топик/сообщение</code>"
)


def _allowed(user_id: int) -> bool:
    return not ALLOWED_IDS or user_id in ALLOWED_IDS


async def _resolve_chat_id(parsed, bot: Bot) -> tuple[int | None, str | None]:
    """Returns (chat_id, error_text). error_text is None on success."""
    if parsed.chat_id is not None:
        return parsed.chat_id, None
    try:
        chat = await bot.get_chat(f"@{parsed.username}")
        return chat.id, None
    except Exception as exc:
        return None, f"Не удалось найти группу @{parsed.username}: {exc}"


# ── /start ──────────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if not _allowed(message.from_user.id):
        return
    await state.clear()
    await state.set_state(SetupFlow.source_link)
    await message.answer(_SOURCE_PROMPT, parse_mode="HTML")


# ── Step 1: source link ──────────────────────────────────────────────────────

@dp.message(SetupFlow.source_link)
async def handle_source_link(message: Message, state: FSMContext):
    parsed = parse_tme_link(message.text or "")
    if not parsed:
        await message.answer(_BAD_LINK, parse_mode="HTML")
        return
    if parsed.topic_id is None:
        await message.answer(_NO_TOPIC, parse_mode="HTML")
        return

    chat_id, err = await _resolve_chat_id(parsed, bot)
    if err:
        await message.answer(err)
        return

    await state.update_data(
        source_chat=chat_id,
        source_topic=parsed.topic_id,
        source_from_msg=parsed.message_id,
    )
    await state.set_state(SetupFlow.dest_link)
    await message.answer(_DEST_PROMPT, parse_mode="HTML", reply_markup=back_keyboard())


# ── Step 2: dest link ────────────────────────────────────────────────────────

@dp.message(SetupFlow.dest_link)
async def handle_dest_link(message: Message, state: FSMContext):
    parsed = parse_tme_link(message.text or "")
    if not parsed:
        await message.answer(_BAD_LINK, parse_mode="HTML")
        return
    if parsed.topic_id is None:
        await message.answer(_NO_TOPIC, parse_mode="HTML")
        return

    chat_id, err = await _resolve_chat_id(parsed, bot)
    if err:
        await message.answer(err)
        return

    await state.update_data(dest_chat=chat_id, dest_topic=parsed.topic_id)
    data = await state.get_data()
    await state.set_state(SetupFlow.confirm)

    summary = (
        "<b>Конфигурация зеркала:</b>\n\n"
        "📥 <b>Источник</b>\n"
        f"  Группа:       <code>{data['source_chat']}</code>\n"
        f"  Топик:        <code>{data['source_topic']}</code>\n"
        f"  С сообщения:  <code>{data['source_from_msg']}</code> (включительно, до самого старого)\n\n"
        "📤 <b>Назначение</b>\n"
        f"  Группа:       <code>{data['dest_chat']}</code>\n"
        f"  Топик:        <code>{data['dest_topic']}</code>\n\n"
        "Запустить юзербот с этими параметрами?"
    )
    await message.answer(summary, parse_mode="HTML", reply_markup=confirm_keyboard())


# ── Back buttons ─────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "back", SetupFlow.dest_link)
async def back_to_source(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetupFlow.source_link)
    await callback.message.answer(_SOURCE_PROMPT, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "back", SetupFlow.confirm)
async def back_to_dest(callback: CallbackQuery, state: FSMContext):
    await state.set_state(SetupFlow.dest_link)
    await callback.message.answer(_DEST_PROMPT, parse_mode="HTML", reply_markup=back_keyboard())
    await callback.answer()


# ── Launch ───────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "launch", SetupFlow.confirm)
async def handle_launch(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await callback.answer()
    await callback.message.answer("⏳ Запускаю юзербот...")
    try:
        mirror_name = f"Mirror {datetime.now():%Y-%m-%d %H:%M}"
        process = launch_userbot(
            source_chat=data["source_chat"],
            source_topic=data["source_topic"],
            source_from_msg=data["source_from_msg"],
            dest_chat=data["dest_chat"],
            dest_topic=data["dest_topic"],
            userbot_dir=USERBOT_DIR,
            name=mirror_name,
        )
        await state.update_data(pid=process.pid, mirror_name=mirror_name)
        await state.set_state(SetupFlow.running)
        await callback.message.answer(
            f"✅ Юзербот запущен (PID <code>{process.pid}</code>)\n\n"
            "Дамп идёт — сообщения копируются из источника в назначение.",
            parse_mode="HTML",
            reply_markup=running_keyboard(),
        )
    except Exception as exc:
        await callback.message.answer(f"❌ Ошибка при запуске:\n<code>{exc}</code>", parse_mode="HTML")


# ── Running state controls ────────────────────────────────────────────────────

@dp.callback_query(F.data == "status")
async def handle_status(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pid = data.get("pid")
    name = data.get("mirror_name")
    if not name:
        await callback.answer("Нет активного дампа.")
        return

    info = status_info(USERBOT_DIR, name)
    await callback.answer()

    if info["done"]:
        await state.clear()
        await callback.message.answer(
            "✅ <b>Дамп завершён!</b>\n\n"
            f"📊 Задампленно: <b>{info['count']}</b> сообщений\n\n"
            "Для новой настройки — /start",
            parse_mode="HTML",
        )
        return

    alive = is_process_alive(pid) if pid else False
    status_str = f"✅ Работает (PID <code>{pid}</code>)" if alive else f"❌ Остановлен (PID <code>{pid}</code>)"
    current = f"<code>{info['current_id']}</code>" if info["current_id"] else "—"
    kb = paused_keyboard() if info["is_paused"] else running_keyboard()

    await callback.message.answer(
        f"📊 <b>Статус дампа:</b>\n\n"
        f"Процесс: {status_str}\n"
        f"Задампленно: <b>{info['count']}</b> сообщений\n"
        f"Последнее сообщение: {current}",
        parse_mode="HTML",
        reply_markup=kb,
    )


@dp.callback_query(F.data == "pause", SetupFlow.running)
async def handle_pause(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    create_pause_flag(USERBOT_DIR, data["mirror_name"])
    await state.set_state(SetupFlow.paused)
    await callback.answer()

    info = status_info(USERBOT_DIR, data["mirror_name"])
    current = f"<code>{info['current_id']}</code>" if info["current_id"] else "—"

    await callback.message.answer(
        "⏸ <b>Пауза поставлена</b>\n\n"
        f"Задампленно: <b>{info['count']}</b> сообщений\n"
        f"Последнее: {current}\n\n"
        "Юзербот остановится после текущего сообщения.",
        parse_mode="HTML",
        reply_markup=paused_keyboard(),
    )


@dp.callback_query(F.data == "resume", SetupFlow.paused)
async def handle_resume(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    remove_pause_flag(USERBOT_DIR, data["mirror_name"])
    await callback.answer()

    try:
        process = launch_userbot(
            source_chat=data["source_chat"],
            source_topic=data["source_topic"],
            source_from_msg=data["source_from_msg"],
            dest_chat=data["dest_chat"],
            dest_topic=data["dest_topic"],
            userbot_dir=USERBOT_DIR,
            name=data["mirror_name"],  # same name => same progress file => resume
        )
        await state.update_data(pid=process.pid)
        await state.set_state(SetupFlow.running)
        await callback.message.answer(
            f"▶ <b>Возобновлено</b> (PID <code>{process.pid}</code>)",
            parse_mode="HTML",
            reply_markup=running_keyboard(),
        )
    except Exception as exc:
        await callback.message.answer(f"❌ Ошибка при возобновлении:\n<code>{exc}</code>", parse_mode="HTML")


@dp.callback_query(F.data == "stop")
async def handle_stop(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    pid = data.get("pid")
    name = data.get("mirror_name")

    if pid:
        stop_process(pid)
    if name:
        remove_pause_flag(USERBOT_DIR, name)

    info = status_info(USERBOT_DIR, name) if name else {}
    await state.clear()
    await callback.answer()

    current = f"<code>{info.get('current_id')}</code>" if info.get("current_id") else "—"
    await callback.message.answer(
        "⏹ <b>Дамп остановлен</b>\n\n"
        f"📊 Задампленно: <b>{info.get('count', '—')}</b> сообщений\n"
        f"Последнее сообщение: {current}\n\n"
        "Для новой настройки — /start",
        parse_mode="HTML",
    )


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
