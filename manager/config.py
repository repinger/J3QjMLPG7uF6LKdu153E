import os
from dotenv import load_dotenv

basedir = os.path.dirname(os.path.abspath(__file__))
env_paths = [os.path.join(basedir, '.env'), os.path.join(basedir, '..', '.env')]
for path in env_paths:
    if os.path.exists(path):
        load_dotenv(path)
        break

class Config:
    SECRET_KEY = os.getenv("MANAGER_SECRET_KEY", "super-secret-key-change-me")
    
    _raw_url = os.getenv("AUTHENTIK_API_URL", "http://authentik-server:9000/api/v3")
    AUTHENTIK_API_URL = _raw_url.rstrip('/')
    AUTHENTIK_TOKEN = os.getenv("AUTHENTIK_TOKEN") 
    
    STALWART_API_URL = os.getenv("STALWART_API_URL", "http://email:8080")
    STALWART_ADMIN_USER = os.getenv("STALWART_ADMIN_USER", "admin")
    STALWART_ADMIN_PASSWORD = os.getenv("STALWART_ADMIN_PASSWORD", os.getenv("SMTP_PASSWORD"))

    OIDC_CLIENT_ID = os.getenv("MANAGER_CLIENT_ID")
    OIDC_CLIENT_SECRET = os.getenv("MANAGER_CLIENT_SECRET")
    OIDC_REDIRECT_URI = os.getenv("OIDC_REDIRECT_URI_MANAGER", "http://manager.localhost/callback")
    OIDC_AUTH_URL = os.getenv("OIDC_AUTH_URL_MANAGER")
    OIDC_TOKEN_URL = os.getenv("OIDC_TOKEN_URL_MANAGER")
    OIDC_USERINFO_URL = os.getenv("OIDC_USERINFO_URL_MANAGER")
    OIDC_LOGOUT_URL = os.getenv("OIDC_LOGOUT_URL_MANAGER")

    SMTP_SERVER = os.getenv("SMTP_SERVER_MANAGER", "email") 
    SMTP_PORT = int(os.getenv("SMTP_PORT_MANAGER", 25))
    SMTP_EMAIL = os.getenv("SMTP_EMAIL_MANAGER", "noreply@localhost")     
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD_MANAGER")
    
    MANAGER_DB_PATH = os.getenv("MANAGER_DB_PATH", "invites.db")
    
    MAIL_DOMAIN = os.getenv("MAIL_DOMAIN", "localhost")
