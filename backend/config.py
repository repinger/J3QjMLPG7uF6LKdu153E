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
    "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY",
    "OIDC_REDIRECT_URI", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET",
    "OIDC_LOGOUT_URL", "OIDC_USERINFO_URL", "OIDC_AUTH_URL",
    "OIDC_TOKEN_URL", "OIDC_ADMIN_GROUP"
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

    # Turnstile
    TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY")

    OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID")
    OIDC_CLIENT_SECRET = os.getenv("OIDC_CLIENT_SECRET")
    OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI", "http://localhost:3000/auth/callback")
    
    OIDC_AUTH_URL = os.getenv("OIDC_AUTH_URL", "https://auth.localhost/application/o/authorize/")
    OIDC_TOKEN_URL = os.getenv("OIDC_TOKEN_URL", "https://auth.localhost/application/o/token/")
    OIDC_USERINFO_URL = os.getenv("OIDC_USERINFO_URL", "https://auth.localhost/application/o/userinfo/")
    
    OIDC_ADMIN_GROUP = os.getenv("OIDC_ADMIN_GROUP", "Admins")
