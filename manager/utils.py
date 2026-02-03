from functools import wraps
from flask import session, redirect, url_for
import secrets
import string

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('routes.login_page'))

        return f(*args, **kwargs)
    return decorated_function

def generate_authentik_key(length=40):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))
