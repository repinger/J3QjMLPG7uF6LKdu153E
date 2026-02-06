from functools import wraps
from flask import session, redirect, url_for
import secrets
import string
import re
from datetime import datetime

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

def validate_phone(phone):
    """
    Validasi nomor telepon Indonesia (mulai 08 atau 62).
    Minimal 10 digit, maksimal 13 digit.
    """
    pattern = r"^(^\+62|62|^08)(\d{3,4}-?){2}\d{3,4}$"
    if re.match(pattern, phone):
        return True
    return False

def generate_nip(division_code, dob_obj, existing_users_in_division=0):
    div_str = str(division_code).zfill(2)
    
    dob_str = dob_obj.strftime("%Y%m%d")
    
    sequence = str(existing_users_in_division + 1).zfill(2)
    
    nip = f"{div_str}{dob_str}{sequence}"
    return nip
