import aiosqlite
from pathlib import Path

DB_PATH = Path("bot.db")


async def init_db() -> None:
    """Создаёт файл БД и таблицы, если их ещё нет."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")

        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,          -- telegram user_id
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_key TEXT NOT NULL UNIQUE, -- UC... или @handle или url (что выберешь хранить)
            created_at TEXT DEFAULT (datetime('now'))
        );
        """)

        await db.execute("""
        CREATE TABLE IF NOT EXISTS user_channels (
            user_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            created_at TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, channel_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE
        );
        """)

        await db.commit()


async def add_user(user_id: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        await db.execute("INSERT OR IGNORE INTO users(id) VALUES (?);", (user_id,))
        await db.commit()


async def add_channel_for_user(user_id: int, channel_key: str) -> None:
    channel_key = channel_key.strip()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")

        # гарантируем пользователя
        await db.execute("INSERT OR IGNORE INTO users(id) VALUES (?);", (user_id,))

        # гарантируем канал
        await db.execute(
            "INSERT OR IGNORE INTO channels(channel_key) VALUES (?);",
            (channel_key,),
        )

        # получаем channel_id
        async with db.execute(
            "SELECT id FROM channels WHERE channel_key = ?;",
            (channel_key,),
        ) as cur:
            row = await cur.fetchone()
            if row is None:
                raise RuntimeError("Failed to fetch channel id after insert.")
            channel_id = row[0]

        # связываем пользователя с каналом
        await db.execute(
            "INSERT OR IGNORE INTO user_channels(user_id, channel_id) VALUES (?, ?);",
            (user_id, channel_id),
        )

        await db.commit()


async def list_user_channels(user_id: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        async with db.execute("""
            SELECT c.channel_key
            FROM user_channels uc
            JOIN channels c ON c.id = uc.channel_id
            WHERE uc.user_id = ?
            ORDER BY uc.created_at DESC;
        """, (user_id,)) as cur:
            rows = await cur.fetchall()
            return [r[0] for r in rows]


async def remove_channel_for_user(user_id: int, channel_key: str) -> None:
    channel_key = channel_key.strip()

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")

        # найти channel_id
        async with db.execute(
            "SELECT id FROM channels WHERE channel_key = ?;",
            (channel_key,),
        ) as cur:
            row = await cur.fetchone()
            if row is None:
                return
            channel_id = row[0]

        # удалить связь пользователь-канал
        await db.execute(
            "DELETE FROM user_channels WHERE user_id = ? AND channel_id = ?;",
            (user_id, channel_id),
        )

        # опционально: подчистить "сиротские" каналы, которые не привязаны ни к одному пользователю
        await db.execute("""
            DELETE FROM channels
            WHERE id = ?
              AND NOT EXISTS (SELECT 1 FROM user_channels WHERE channel_id = ?);
        """, (channel_id, channel_id))

        await db.commit()