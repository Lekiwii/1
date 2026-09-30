"""Stockage SQLite : liste de cartes surveillées et annonces déjà signalées."""
import sqlite3

DEFAULT_WATCHLIST = [
    "Charizard Base Set 4/102",
    "Charizard VMAX Shiny 074/073",
    "Umbreon VMAX Alt Art 215/203",
    "Moonbreon 215/203",
    "Lugia V Alt Art 186/195",
    "Giratina V Alt Art 186/196",
    "Pikachu Illustrator",
    "Charizard ex 199/165",
    "Mew ex 232/091",
    "Rayquaza VMAX Alt Art 218/203",
]


class Storage:
    def __init__(self, path: str):
        self._db = sqlite3.connect(path)
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS watch (query TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS alerted (
                item_id TEXT PRIMARY KEY,
                price REAL NOT NULL,
                at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )
        if self._db.execute("SELECT value FROM meta WHERE key='seeded'").fetchone() is None:
            self._db.executemany("INSERT OR IGNORE INTO watch VALUES (?)", [(q,) for q in DEFAULT_WATCHLIST])
            self._db.execute("INSERT INTO meta VALUES ('seeded', '1')")
        self._db.commit()

    def watchlist(self) -> list[str]:
        return [row[0] for row in self._db.execute("SELECT query FROM watch ORDER BY query")]

    def add_watch(self, query: str) -> None:
        self._db.execute("INSERT OR IGNORE INTO watch VALUES (?)", (query,))
        self._db.commit()

    def remove_watch(self, query: str) -> bool:
        cur = self._db.execute("DELETE FROM watch WHERE lower(query) = lower(?)", (query,))
        self._db.commit()
        return cur.rowcount > 0

    def is_new_alert(self, item_id: str, price: float) -> bool:
        """Vrai si l'annonce n'a jamais été signalée, ou si son prix a baissé depuis."""
        row = self._db.execute("SELECT price FROM alerted WHERE item_id = ?", (item_id,)).fetchone()
        return row is None or price < row[0]

    def mark_alerted(self, item_id: str, price: float) -> None:
        self._db.execute(
            "INSERT INTO alerted (item_id, price) VALUES (?, ?) "
            "ON CONFLICT(item_id) DO UPDATE SET price = excluded.price, at = CURRENT_TIMESTAMP",
            (item_id, price),
        )
        self._db.commit()
