import sqlite3
from config import Config

def init_db():
    try:
        conn = sqlite3.connect(Config.MANAGER_DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS invites 
                     (token TEXT PRIMARY KEY, 
                      email TEXT, 
                      group_pk TEXT, 
                      created_at TIMESTAMP, 
                      used INTEGER DEFAULT 0)''')
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] Database Init Error: {e}")

def get_db():
    conn = sqlite3.connect(Config.MANAGER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
