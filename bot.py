import asyncio
import logging
import os

from analytics import build_growth_report, build_portfolio_report, render_growth_chart
from db import save_snapshot, get_channel_snapshots

from snapshot_scheduler import build_scheduler, collect_snapshots_once

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
    BufferedInputFile,
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
    kb.button(text="📉 Рост")
    kb.button(text="📑 Отчёт")
    kb.button(text="➖ Удалить канал")
    kb.button(text="ℹ️ Помощь")
    kb.adjust(2, 2, 2, 1)
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

def format_number(value: int | float) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", " ")
    return f"{value:,}".replace(",", " ")

def format_pct(value: float | None) -> str:
    if value is None:
        return "н/д"
    return f"{value:.2f}%"

def is_report_button_text(text: str | None) -> bool:
    if not text:
        return False
    normalized = text.strip().lower().replace("ё", "е")
    normalized = normalized.removeprefix("📑").strip()
    return normalized in {"отчет", "report"}


async def send_growth_report_for_channel(message: Message, channel_id: str, api_key: str) -> None:
    try:
        st = await fetch_channel_stats(api_key, channel_id)
        title = st.get("title") or channel_id
        await save_snapshot(
            channel_key=channel_id,
            subscribers=st["subscribers"],
            views=st["views"],
            videos=st["videos"],
        )
    except Exception as e:
        await message.answer(f"❌ Не удалось обновить {channel_id}: {e}", reply_markup=main_menu_kb())
        return

    snapshots = await get_channel_snapshots(channel_id)
    report = build_growth_report(snapshots)
    if not report["ok"]:
        await message.answer(
            f"📺 <code>{channel_id}</code>\n"
            f"Недостаточно данных: {report['reason']}",
            reply_markup=main_menu_kb(),
        )
        return

    latest = report["latest"]
    periods = report["periods"]
    acceleration = report["acceleration"]

    text_parts = [
        f"📺 <b>{title}</b> (<code>{channel_id}</code>)",
        f"👥 Подписчики: <b>{format_number(latest['subscribers'])}</b>",
        f"   • 7д: {format_number(periods[7]['subscribers']['growth_abs']) if periods[7]['subscribers'] else 'н/д'}",
        f"   • 30д: {format_number(periods[30]['subscribers']['growth_abs']) if periods[30]['subscribers'] else 'н/д'}",
        f"👁 Просмотры: <b>{format_number(latest['views'])}</b>",
        f"   • 7д: {format_number(periods[7]['views']['growth_abs']) if periods[7]['views'] else 'н/д'}",
        f"   • 30д: {format_number(periods[30]['views']['growth_abs']) if periods[30]['views'] else 'н/д'}",
    ]

    if acceleration:
        text_parts.append(
            f"⚡ Темп подписчиков: <b>{acceleration['trend']}</b> "
            f"({format_number(acceleration['diff_avg_daily_subs'])}/день)"
        )

    await message.answer("\n".join(text_parts), reply_markup=main_menu_kb())

    chart_png = render_growth_chart(snapshots, title)
    if chart_png is not None:
        photo = BufferedInputFile(chart_png, filename=f"{channel_id}_growth.png")
        await message.answer_photo(
            photo=photo,
            caption=f"📊 График роста: <b>{title}</b>",
            reply_markup=main_menu_kb(),
        )


@router.errors()
async def on_error(event: ErrorEvent):
    if isinstance(event.exception, TelegramNetworkError):
        logging.warning("TelegramNetworkError: %s", event.exception)
        return True  # подавили — бот продолжает работать
    return False

@router.message(Command("growth"))
async def growth_command(message: Message):
    await growth_btn(message)


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
        "• /growth — короткий отчёт + графики\n"
        "• /report — полный аналитический отчёт\n\n"
        "Кнопки:\n"
        "• ➕ Добавить канал — добавляет строку (id/url/@handle)\n"
        "• 📊 Мои каналы — показывает список\n\n"
        "Дальше можно подключить YouTube Data API и расписание сборов.",
        reply_markup=main_menu_kb(),
    )


@router.message(F.text == "ℹ️ Помощь")
async def help_btn(message: Message):
    await help_cmd(message)

@router.message(F.text == "📉 Рост")
async def growth_btn(message: Message):
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

    if len(channels) == 1:
        await message.answer("⏳ Обновляю снапшот и готовлю краткий отчёт...")
        await send_growth_report_for_channel(message, channels[0], api_key)
        return

    channel_titles: dict[str, str] = {}
    title_tasks = [fetch_channel_stats(api_key, channel_id) for channel_id in channels]
    title_results = await asyncio.gather(*title_tasks, return_exceptions=True)
    for channel_id, result in zip(channels, title_results):
        if isinstance(result, Exception):
            channel_titles[channel_id] = channel_id
        else:
            channel_titles[channel_id] = (result.get("title") or channel_id).strip()

    kb = InlineKeyboardBuilder()
    for idx, channel_id in enumerate(channels, start=1):
        title = channel_titles.get(channel_id, channel_id)
        short_title = title if len(title) <= 28 else f"{title[:28]}..."
        kb.button(text=f"{idx}) {short_title}", callback_data=f"growth:{channel_id}")
    kb.adjust(1)

    await message.answer(
        "Выбери канал для отчёта по росту:",
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("growth:"))
async def growth_channel_pick(call: CallbackQuery):
    if call.from_user is None:
        await call.answer("Не смог определить пользователя.", show_alert=True)
        return

    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        await call.answer("Не найден YOUTUBE_API_KEY", show_alert=True)
        return

    channel_id = (call.data or "").split(":", 1)[1]
    allowed_channels = await list_user_channels(call.from_user.id)
    if channel_id not in allowed_channels:
        await call.answer("Канал не найден в твоём списке.", show_alert=True)
        return

    await call.answer("Готовлю отчёт...")
    if call.message:
        await call.message.edit_reply_markup(reply_markup=None)
        await send_growth_report_for_channel(call.message, channel_id, api_key)


@router.message(lambda message: is_report_button_text(message.text))
@router.message(Command("report"))
async def report_btn(message: Message):
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

    await message.answer("⏳ Формирую полный аналитический отчёт...")

    channel_titles: dict[str, str] = {}
    for channel_id in channels:
        try:
            st = await fetch_channel_stats(api_key, channel_id)
            channel_titles[channel_id] = st.get("title") or channel_id
            await save_snapshot(
                channel_key=channel_id,
                subscribers=st["subscribers"],
                views=st["views"],
                videos=st["videos"],
            )
        except Exception as e:
            await message.answer(f"❌ Не удалось обновить {channel_id}: {e}")

    channel_reports = []
    for channel_id in channels:
        snapshots = await get_channel_snapshots(channel_id)
        channel_reports.append(
            {
                "channel_id": channel_id,
                "title": channel_titles.get(channel_id, channel_id),
                "report": build_growth_report(snapshots),
            }
        )

    portfolio = build_portfolio_report(channel_reports)
    if not portfolio["ok"]:
        await message.answer(f"❌ {portfolio['reason']}", reply_markup=main_menu_kb())
        return

    def top_block(title: str, items: list[dict]) -> list[str]:
        lines = [f"<b>{title}</b>"]
        if not items:
            lines.append("• недостаточно данных")
            return lines
        for idx, item in enumerate(items, start=1):
            lines.append(
                f"{idx}) <b>{item['title']}</b>: "
                f"{format_number(item['growth_abs'])} "
                f"(ср/день {format_number(item['avg_daily'])}, {format_pct(item['pct_growth'])})"
            )
        return lines

    summary_lines = [
        "📈 <b>Аналитический отчёт</b>",
        f"Каналов: {portfolio['channels_total']}, с данными: {portfolio['channels_with_data']}",
        "",
    ]
    summary_lines.extend(top_block("Топ роста подписчиков за 7д", portfolio["top_subs_7"]))
    summary_lines.append("")
    summary_lines.extend(top_block("Топ роста подписчиков за 30д", portfolio["top_subs_30"]))
    summary_lines.append("")
    summary_lines.extend(top_block("Топ роста просмотров за 7д", portfolio["top_views_7"]))
    summary_lines.append("")
    summary_lines.extend(top_block("Топ роста просмотров за 30д", portfolio["top_views_30"]))
    summary_lines.append("")
    summary_lines.extend(top_block("Ускоряются (подписчики)", portfolio["accelerating"]))
    summary_lines.append("")
    summary_lines.extend(top_block("Замедляются (подписчики)", portfolio["slowing"]))

    await message.answer("\n".join(summary_lines), reply_markup=main_menu_kb())


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

    tg_proxy = os.getenv("TG_PROXY")
    if tg_proxy:
        logging.info("Using Telegram proxy from TG_PROXY")

    session = AiohttpSession(proxy=tg_proxy, timeout=120)

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )

    await init_db()

    # Планировщик снапшотов
    scheduler = build_scheduler()
    scheduler.start()

    # Опционально: один раз собрать снапшоты сразу при старте
    try:
        await collect_snapshots_once()
    except Exception as e:
        logging.warning("Initial snapshot collection failed: %s", e)

    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)



if __name__ == "__main__":
    asyncio.run(main())