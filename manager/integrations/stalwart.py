import requests
import base64
from config import Config

def get_headers():
    creds = f"{Config.STALWART_ADMIN_USER}:{Config.STALWART_ADMIN_PASSWORD}"
    encoded = base64.b64encode(creds.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json"
    }

def create_mailbox(username, name, password, email):
    url = f"{Config.STALWART_API_URL}/api/principal"
    payload = {
        "type": "individual",
        "name": username,
        "description": name,
        "secrets": [password],
        "emails": [email],
        "quota": 0,
        "roles": ["user"] 
    }
    return requests.post(url, json=payload, headers=get_headers())

def delete_mailbox(username):
    import urllib.parse
    safe = urllib.parse.quote(username)
    return requests.delete(f"{Config.STALWART_API_URL}/api/principal/{safe}", headers=get_headers())
