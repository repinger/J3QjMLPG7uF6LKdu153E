import sqlite3
from config import Config

def get_db():
    conn = sqlite3.connect(Config.MANAGER_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
                      
        c.execute('''CREATE TABLE IF NOT EXISTS divisions 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      name TEXT NOT NULL, 
                      code TEXT NOT NULL UNIQUE)''')
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] Database Init Error: {e}")


def get_all_divisions():
    conn = get_db()
    divs = conn.execute("SELECT * FROM divisions ORDER BY code ASC").fetchall()
    conn.close()
    return divs

def add_division(name, code):
    try:
        conn = get_db()
        conn.execute("INSERT INTO divisions (name, code) VALUES (?, ?)", (name, code))
        conn.commit()
        conn.close()
        return True, "Division added."
    except sqlite3.IntegrityError:
        return False, "Division code must be unique."
    except Exception as e:
        return False, str(e)

def delete_division(div_id):
    conn = get_db()
    conn.execute("DELETE FROM divisions WHERE id = ?", (div_id,))
    conn.commit()
    conn.close()
