# bot.py
# Aiogram v3 async Telegram bot with a couple of buttons + FSM (async)
# Run:
#   1) pip install -U aiogram python-dotenv
#   2) create .env with BOT_TOKEN=123:ABC...
#   3) python bot.py

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

from aiogram.client.default import DefaultBotProperties
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
)
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ----------------------------
# Simple in-memory "storage"
# ----------------------------
@dataclass
class Channel:
    raw: str  # what user entered (id/url/handle)


USER_CHANNELS: Dict[int, List[Channel]] = {}


# ----------------------------
# FSM states
# ----------------------------
class AddChannelFlow(StatesGroup):
    waiting_for_channel = State()


# ----------------------------
# Keyboards
# ----------------------------
def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="➕ Добавить канал")
    kb.button(text="📊 Мои каналы")
    kb.button(text="ℹ️ Помощь")
    kb.adjust(2, 1)
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=False)


def cancel_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="✖️ Отмена")
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def inline_actions_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🏓 Ping", callback_data="ping")
    kb.button(text="🧹 Очистить мои каналы", callback_data="clear_channels")
    kb.adjust(1, 1)
    return kb.as_markup()


# ----------------------------
# Router / Handlers
# ----------------------------
router = Router()


@router.message(CommandStart())
async def start(message: Message):
    await message.answer(
        "Привет! Я бот-заготовка на *aiogram v3*.\n\n"
        "Кнопки ниже помогут добавить и посмотреть каналы.\n"
        "Пока я храню каналы в памяти (после перезапуска список очистится).",
        reply_markup=main_menu_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )
    await message.answer("Быстрые действия:", reply_markup=inline_actions_kb())


@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "Команды:\n"
        "• /start — меню\n"
        "• /help — помощь\n\n"
        "Кнопки:\n"
        "• ➕ Добавить канал — добавляет строку (id/url/@handle)\n"
        "• 📊 Мои каналы — показывает список\n\n"
        "Дальше можно подключить YouTube Data API и расписание сборов.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "ℹ️ Помощь")
async def help_btn(message: Message):
    await help_cmd(message)


@router.message(F.text == "➕ Добавить канал")
async def add_channel_btn(message: Message, state: FSMContext):
    await state.set_state(AddChannelFlow.waiting_for_channel)
    await message.answer(
        "Пришли *channel_id* или ссылку на канал (или @handle).\n\n"
        "Примеры:\n"
        "• UC_x5XG1OV2P6uZZ5FSM9Ttw\n"
        "• https://www.youtube.com/@somehandle\n"
        "• https://www.youtube.com/channel/UC...\n\n"
        "Чтобы отменить — нажми ✖️ Отмена.",
        reply_markup=cancel_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(AddChannelFlow.waiting_for_channel, F.text == "✖️ Отмена")
async def cancel_add(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Ок, отменил.", reply_markup=main_menu_kb())


@router.message(AddChannelFlow.waiting_for_channel, F.text)
async def add_channel_input(message: Message, state: FSMContext):
    if message.from_user is None or message.text is None:
        await message.answer("Не смог прочитать сообщение. Попробуй ещё раз.")
        return

    user_id = message.from_user.id
    raw = message.text.strip()

    USER_CHANNELS.setdefault(user_id, []).append(Channel(raw=raw))

    await state.clear()
    await message.answer(
        f"✅ Добавил: `{raw}`\n\nТеперь можешь посмотреть список в «📊 Мои каналы».",
        reply_markup=main_menu_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(F.text == "📊 Мои каналы")
async def my_channels(message: Message):
    if message.from_user is None:
        await message.answer("Не смог определить пользователя.")
        return

    user_id = message.from_user.id
    channels = USER_CHANNELS.get(user_id, [])

    if not channels:
        await message.answer(
            "У тебя пока нет добавленных каналов.\nНажми «➕ Добавить канал».",
            reply_markup=main_menu_kb(),
        )
        return

    lines = "\n".join([f"{i+1}) {c.raw}" for i, c in enumerate(channels)])
    await message.answer(
        "📊 *Твои каналы:*\n" + lines,
        reply_markup=main_menu_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.callback_query(F.data == "ping")
async def ping_cb(call: CallbackQuery):
    await call.answer("Pong!")

    # call.message может быть None
    if call.message:
        await call.message.reply("🏓 Pong (inline callback обработан).")


@router.callback_query(F.data == "clear_channels")
async def clear_channels_cb(call: CallbackQuery):
    user_id = call.from_user.id
    USER_CHANNELS.pop(user_id, None)

    await call.answer("Готово")
    if call.message:
        await call.message.reply("🧹 Список каналов очищен.")


@router.message()
async def fallback(message: Message):
    # Any other message
    await message.answer(
        "Я не понял команду. Нажми кнопку в меню или /help.",
        reply_markup=main_menu_kb(),
    )


# ----------------------------
# Entrypoint
# ----------------------------
async def main():
    logging.basicConfig(level=logging.INFO)

    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN not found. Set it in env or .env file.")

    bot = Bot(
    token=token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Long polling (async)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())