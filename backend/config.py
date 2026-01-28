import os
import sys
from dotenv import load_dotenv

# --- 1. SETUP PATH & LOAD .ENV ---
# Dapatkan folder tempat file config.py berada
basedir = os.path.dirname(os.path.abspath(__file__))

# Path kemungkinan file .env
env_paths = [
    os.path.join(basedir, '.env'),       # Prioritas 1: Satu folder dengan app (Docker: /app/.env)
    os.path.join(basedir, '..', '.env')  # Prioritas 2: Folder parent (Local Dev)
]

loaded_path = "None"
for path in env_paths:
    if os.path.exists(path):
        load_dotenv(path)
        loaded_path = path
        break

# --- 2. DEBUG PRINT (REQUESTED) ---
print("\n" + "="*50)
print("[DEBUG] CHECKING ENVIRONMENT VARIABLES")
print("="*50)
print(f"[*] Current Working Dir : {os.getcwd()}")
print(f"[*] Config Script Dir   : {basedir}")
print(f"[*] Loaded .env File    : {loaded_path}")

# Daftar variabel krusial yang harus dicek
check_keys = [
    "FLASK_HOST", "FLASK_PORT", 
    "LDAP_BASE_DN", "LDAP_HOST",
    "LDAP_BIND_USER", "LDAP_BIND_PASSWORD", "LDAP_ADMIN_GROUP",
    "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY"
]

missing_count = 0
for key in check_keys:
    val = os.getenv(key)
    if val is None:
        print(f"[!] {key:<20} : MISSING / NONE")
        missing_count += 1
    else:
        # Masking password untuk keamanan log, tapi memberi tahu value ada
        display_val = val
        if "PASSWORD" in key or "SECRET" in key:
            display_val = f"****** (Length: {len(val)})"
        elif "KEY" in key:
            display_val = val[:5] + "..." + val[-5:]
        
        print(f"[OK] {key:<20} : {display_val}")

print("="*50 + "\n")

if missing_count > 0:
    print(f"[CRITICAL WARNING] {missing_count} variable(s) are missing! App might fail.\n")

# --- 3. CONFIG CLASS ---
class Config:
    # App Config
    DB_FILE = os.getenv("DB_FILE", "monitor.db")
    PROMETHEUS_URL = os.getenv("PROMETHEUS_URL")
    PING_INTERVAL = int(os.getenv("PING_INTERVAL", 10))
    RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", 7))
    MAX_DB_HISTORY = int(os.getenv("MAX_DB_HISTORY", 70000))
    FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
    FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
    
    # Email Config
    BANDWIDTH_THRESHOLD = int(os.getenv("BANDWIDTH_THRESHOLD", 10000000))
    ALERT_COOLDOWN = int(os.getenv("ALERT_COOLDOWN", 3600))
    ALERT_RECIPIENT = os.getenv("ALERT_RECIPIENT")
    SMTP_SERVER = os.getenv("SMTP_SERVER")
    SMTP_PORT = int(os.getenv("SMTP_PORT", 25))
    SMTP_EMAIL = os.getenv("SMTP_EMAIL")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    
    # LDAP Config
    LDAP_HOST = os.environ.get('LDAP_HOST', 'ldap://localhost:389')
    LDAP_USE_SSL = str(os.getenv("LDAP_USE_SSL", "False")).lower() == "true"
    LDAP_BASE_DN = os.getenv("LDAP_BASE_DN")
    LDAP_BIND_USER = os.getenv("LDAP_BIND_USER")
    LDAP_BIND_PASSWORD = os.getenv("LDAP_BIND_PASSWORD")

    LDAP_ADMIN_GROUP = os.getenv("LDAP_ADMIN_GROUP", "Admins")
    LDAP_USER_GROUP = os.getenv("LDAP_USER_GROUP", "user_monitorr")

    # Turnstile
    TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")
