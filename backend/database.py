import sqlite3
from config import Config

def get_db_connection():
    conn = sqlite3.connect(Config.DB_FILE, check_same_thread=False, timeout=30)
    
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL") 
    
    return conn

def add_column_if_not_exists(cursor, table, column, col_type):
    try:
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
    except sqlite3.OperationalError:
        print(f"[*] Migrating: Adding column '{column}' to table '{table}'...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # 1. Tabel Machines
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
    try:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_machines_host ON machines(host)")
    except Exception as e:
        print(f"[!] Index creation warning: {e}")

    add_column_if_not_exists(c, "machines", "notify_down", "BOOLEAN DEFAULT 1")
    add_column_if_not_exists(c, "machines", "notify_traffic", "BOOLEAN DEFAULT 1")
    add_column_if_not_exists(c, "machines", "notify_email", "BOOLEAN DEFAULT 0")
    add_column_if_not_exists(c, "machines", "city", "TEXT DEFAULT ''")
    add_column_if_not_exists(c, "machines", "province", "TEXT DEFAULT ''")

    # 2. Tabel History & Alerts (Sama seperti sebelumnya)
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

    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')

    conn.execute('''
        CREATE TABLE IF NOT EXISTS province_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_pk TEXT NOT NULL,
            group_name TEXT,
            province TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(group_pk, province)
        )
    ''')

    # Seed Default Settings jika belum ada
    default_settings = [
        ('latency_threshold', '100'),      # ms
        ('bandwidth_threshold', '10000')   # Kbps (10 Mbps)
    ]
    for key, val in default_settings:
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, val))

    conn.commit()
    conn.close()
    print("[*] Database initialized & checked.")
