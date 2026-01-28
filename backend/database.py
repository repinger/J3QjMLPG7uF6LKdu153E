import sqlite3
from config import Config

def get_db_connection():
    conn = sqlite3.connect(Config.DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def add_column_if_not_exists(cursor, table, column, col_type):
    """Fungsi aman untuk migrasi database tanpa menghapus data"""
    try:
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
    except sqlite3.OperationalError:
        print(f"[*] Migrating: Adding column '{column}' to table '{table}'...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # 1. Buat Tabel Utama jika belum ada
    c.execute('''
        CREATE TABLE IF NOT EXISTS machines (
            id TEXT PRIMARY KEY,
            host TEXT NOT NULL,
            type TEXT DEFAULT 'server',
            icon TEXT DEFAULT 'fa-server',
            use_snmp INTEGER DEFAULT 0, 
            lat REAL DEFAULT 0,
            lng REAL DEFAULT 0,
            online BOOLEAN DEFAULT 0,
            latency_ms REAL DEFAULT 0,
            rx_rate REAL DEFAULT 0,
            tx_rate REAL DEFAULT 0,
            last_seen TEXT DEFAULT 'Never'
        )
    ''')

    # 2. Migrasi: Tambahkan kolom notifikasi satu per satu (Safety Check)
    add_column_if_not_exists(c, "machines", "notify_down", "BOOLEAN DEFAULT 1")
    add_column_if_not_exists(c, "machines", "notify_traffic", "BOOLEAN DEFAULT 1")
    add_column_if_not_exists(c, "machines", "notify_email", "BOOLEAN DEFAULT 0")

    # 3. Tabel History
    c.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT,
            status TEXT,
            time TEXT,
            latency REAL DEFAULT 0,
            rx REAL DEFAULT 0,
            tx REAL DEFAULT 0,
            FOREIGN KEY(machine_id) REFERENCES machines(id) ON DELETE CASCADE
        )
    ''')

    # 4. Tabel App Alerts
    c.execute('''
        CREATE TABLE IF NOT EXISTS app_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            machine_id TEXT,
            type TEXT, 
            message TEXT,
            time TEXT,
            is_read BOOLEAN DEFAULT 0,
            FOREIGN KEY(machine_id) REFERENCES machines(id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    conn.close()
    print("[*] Database initialized & checked.")
