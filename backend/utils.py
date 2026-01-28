import requests
from config import Config

def verify_turnstile(token):
    if not Config.TURNSTILE_SECRET_KEY:
        return True # Bypass mode dev
    
    if not token:
        return False

    url = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    payload = {
        'secret': Config.TURNSTILE_SECRET_KEY,
        'response': token
    }
    
    try:
        res = requests.post(url, data=payload, timeout=5)
        outcome = res.json()
        return outcome.get('success', False)
    except Exception as e:
        print(f"[!] Turnstile Error: {e}")
        return False
