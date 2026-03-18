import asyncio
import logging
import os

from aiogram.types import ErrorEvent
from aiogram.exceptions import TelegramNetworkError
from aiogram.client.default import DefaultBotProperties
from aiogram import Bot, Dispatcher, Router, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiohttp import ClientTimeout
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import (
    Message,
    CallbackQuery,
)
from db import (
    init_db,
    add_user,
    add_channel_for_user,
    list_user_channels,
    remove_channel_for_user,
    remove_all_channels_for_user,
)
from youtube_api import resolve_channel_id, fetch_channel_stats, YouTubeApiError

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass



# ----------------------------
# FSM states
# ----------------------------
class AddChannelFlow(StatesGroup):
    waiting_for_channel = State()


class DeleteChannelFlow(StatesGroup):
    waiting_for_channel_delete = State()

# ----------------------------
# Keyboards
# ----------------------------
def main_menu_kb():
    kb = ReplyKeyboardBuilder()
    kb.button(text="➕ Добавить канал")
    kb.button(text="📊 Мои каналы")
    kb.button(text="📈 Статистика")
    kb.button(text="➖ Удалить канал")
    kb.button(text="ℹ️ Помощь")
    kb.adjust(2, 2, 1)
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


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")

# ----------------------------
# Router / Handlers
# ----------------------------
router = Router()


@router.errors()
async def on_error(event: ErrorEvent):
    if isinstance(event.exception, TelegramNetworkError):
        logging.warning("TelegramNetworkError: %s", event.exception)
        return True  # подавили — бот продолжает работать
    return False

@router.message(CommandStart())
async def start(message: Message):
    if message.from_user is None:
        await message.answer("Не смог определить пользователя.")
        return

    await add_user(message.from_user.id)

    await message.answer(
        "Привет! Я бот-заготовка на *aiogram v3*.\n\n"
        "Кнопки ниже помогут добавить и посмотреть каналы.\n"
        "Теперь каналы хранятся в SQLite.",
        reply_markup=main_menu_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )
    await message.answer("Быстрые действия:", reply_markup=inline_actions_kb())


@router.message(Command("stats"))
async def stats_command(message: Message):
    await stats_btn(message)


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


@router.message(F.text == "📈 Статистика")
async def stats_btn(message: Message):
    if message.from_user is None:
        await message.answer("Не смог определить пользователя.")
        return

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        await message.answer("❌ В .env не найден YOUTUBE_API_KEY")
        return

    user_id = message.from_user.id
    channels = await list_user_channels(user_id)

    if not channels:
        await message.answer(
            "У тебя пока нет добавленных каналов.\nНажми «➕ Добавить канал».",
            reply_markup=main_menu_kb(),
        )
        return

    await message.answer("⏳ Собираю статистику по каналам...")

    tasks = [fetch_channel_stats(api_key, ch_id) for ch_id in channels]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    blocks = []

    for ch_id, result in zip(channels, results):
        if isinstance(result, Exception):
            blocks.append(
                f"❌ <code>{ch_id}</code>\n"
                f"Ошибка: {result}"
            )
            continue

        subscribers_text = (
            "скрыты"
            if result["hidden_subs"]
            else format_number(result["subscribers"])
        )

        block = (
            f"📺 <b>{result['title']}</b>\n"
            f"🆔 <code>{result['channel_id']}</code>\n"
            f"👥 Подписчики: <b>{subscribers_text}</b>\n"
            f"👁 Просмотры: <b>{format_number(result['views'])}</b>\n"
            f"🎞 Видео: <b>{format_number(result['videos'])}</b>"
        )
        blocks.append(block)

    text = "\n\n".join(blocks)

    if len(text) <= 4000:
        await message.answer(text, reply_markup=main_menu_kb())
    else:
        chunk = ""
        for block in blocks:
            if len(chunk) + len(block) + 2 > 4000:
                await message.answer(chunk, reply_markup=main_menu_kb())
                chunk = block
            else:
                if chunk:
                    chunk += "\n\n"
                chunk += block

        if chunk:
            await message.answer(chunk, reply_markup=main_menu_kb())
            

@router.message(F.text == "➖ Удалить канал")
async def delete_channel_btn(message: Message, state: FSMContext):
    if message.from_user is None:
        await message.answer("Не смог определить пользователя.")
        return

    user_id = message.from_user.id
    channels = await list_user_channels(user_id)

    if not channels:
        await message.answer(
            "У тебя пока нет каналов для удаления.",
            reply_markup=main_menu_kb(),
        )
        return

    lines = "\n".join([f"{i+1}) {ch}" for i, ch in enumerate(channels)])
    await state.set_state(DeleteChannelFlow.waiting_for_channel_delete)

    await message.answer(
        "Отправь channel_id канала, который хочешь удалить:\n\n"
        f"{lines}\n\n"
        "Чтобы отменить — нажми ✖️ Отмена.",
        reply_markup=cancel_kb(),
    )


@router.message(DeleteChannelFlow.waiting_for_channel_delete, F.text == "✖️ Отмена")
async def cancel_delete(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Удаление отменено.", reply_markup=main_menu_kb())


@router.message(DeleteChannelFlow.waiting_for_channel_delete, F.text)
async def delete_channel_input(message: Message, state: FSMContext):
    if message.from_user is None or message.text is None:
        await message.answer("Не смог прочитать сообщение. Попробуй ещё раз.")
        return

    user_id = message.from_user.id
    channel_key = message.text.strip()

    deleted = await remove_channel_for_user(user_id, channel_key)

    await state.clear()

    if deleted:
        await message.answer(
            f"✅ Канал удалён: <code>{channel_key}</code>",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(
            "❌ Такой канал не найден в твоём списке.",
            reply_markup=main_menu_kb(),
        )


@router.message(AddChannelFlow.waiting_for_channel, F.text)
async def add_channel_input(message: Message, state: FSMContext):
    if message.from_user is None or message.text is None:
        await message.answer("Не смог прочитать сообщение. Попробуй ещё раз.")
        return

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        await message.answer("❌ В .env не найден YOUTUBE_API_KEY")
        return

    user_id = message.from_user.id
    raw_input = message.text.strip()

    try:
        channel_id, title = await resolve_channel_id(api_key, raw_input)
    except YouTubeApiError as e:
        await message.answer(f"❌ Ошибка поиска канала:\n{e}")
        return

    await add_channel_for_user(user_id, channel_id)
    await state.clear()

    if title:
        await message.answer(
            f"✅ Канал добавлен:\n"
            f"<b>{title}</b>\n"
            f"<code>{channel_id}</code>",
            reply_markup=main_menu_kb(),
        )
    else:
        await message.answer(
            f"✅ Канал добавлен:\n<code>{channel_id}</code>",
            reply_markup=main_menu_kb(),
        )


@router.message(F.text == "📊 Мои каналы")
async def my_channels(message: Message):
    if message.from_user is None:
        await message.answer("Не смог определить пользователя.")
        return

    user_id = message.from_user.id
    channels = await list_user_channels(user_id)

    if not channels:
        await message.answer(
            "У тебя пока нет добавленных каналов.\nНажми «➕ Добавить канал».",
            reply_markup=main_menu_kb(),
        )
        return

    lines = "\n".join([f"{i+1}) {ch}" for i, ch in enumerate(channels)])
    await message.answer(
        "📊 *Твои каналы:*\n" + lines,
        reply_markup=main_menu_kb(),
        parse_mode=ParseMode.MARKDOWN,
    )


@router.message(F.text == "📈 Статистика")
async def stats_btn(message: Message):
    if message.from_user is None:
        await message.answer("Не смог определить пользователя.")
        return

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        await message.answer("Не найден YOUTUBE_API_KEY в .env")
        return

    user_id = message.from_user.id
    channels = await list_user_channels(user_id)

    # MVP: пока работаем только с UC... ID
    channel_ids = [c for c in channels if c.startswith("UC")]

    if not channel_ids:
        await message.answer("Добавь channel_id вида UC... через «➕ Добавить канал».")
        return

    await message.answer("Собираю статистику, секунду…")

    lines = []
    for ch_id in channel_ids[:10]:  # ограничим, чтобы не спамить
        try:
            st = await fetch_channel_stats(api_key, ch_id)
            lines.append(
                f"📺 <b>{st['title']}</b>\n"
                f"ID: <code>{st['channel_id']}</code>\n"
                f"👥 Подписчики: <b>{st['subscribers']:,}</b>\n"
                f"👁 Просмотры: <b>{st['views']:,}</b>\n"
                f"🎞 Видео: <b>{st['videos']:,}</b>\n"
            )
        except YouTubeApiError as e:
            lines.append(f"❌ <code>{ch_id}</code>: {e}")

    await message.answer("\n\n".join(lines))


@router.callback_query(F.data == "ping")
async def ping_cb(call: CallbackQuery):
    await call.answer("Pong!")

    # call.message может быть None
    if call.message:
        await call.message.reply("🏓 Pong (inline callback обработан).")


@router.callback_query(F.data == "clear_channels")
async def clear_channels_cb(call: CallbackQuery):
    user_id = call.from_user.id
    deleted_count = await remove_all_channels_for_user(user_id)

    await call.answer("Готово")
    if call.message:
        await call.message.reply(f"🧹 Удалено каналов: {deleted_count}")

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

    session = AiohttpSession(timeout=120)  # <-- ВАЖНО: число, не ClientTimeout

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )

    await init_db()

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    await dp.start_polling(bot)



if __name__ == "__main__":
    asyncio.run(main())