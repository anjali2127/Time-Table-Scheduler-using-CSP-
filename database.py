import sqlite3

DB_NAME = "timetable.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row      # access columns by name
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS teachers (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS subjects (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        name              TEXT NOT NULL,
        teacher_id        INTEGER NOT NULL,
        lectures_per_week INTEGER NOT NULL DEFAULT 3,
        is_lab            INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id)
    );

    CREATE TABLE IF NOT EXISTS rooms (
        id     INTEGER PRIMARY KEY AUTOINCREMENT,
        name   TEXT NOT NULL UNIQUE,
        is_lab INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS divisions (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS availability (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        teacher_id INTEGER NOT NULL,
        day        TEXT NOT NULL,
        slot       TEXT NOT NULL,
        FOREIGN KEY (teacher_id) REFERENCES teachers(id)
    );

    CREATE TABLE IF NOT EXISTS timetables (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        name       TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS timetable_entries (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        timetable_id INTEGER NOT NULL,
        division     TEXT NOT NULL,
        subject      TEXT NOT NULL,
        day          TEXT NOT NULL,
        slot         TEXT NOT NULL,
        room         TEXT NOT NULL,
        FOREIGN KEY (timetable_id) REFERENCES timetables(id)
    );
    """)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print("Database created.")