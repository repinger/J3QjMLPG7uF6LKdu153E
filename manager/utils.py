from functools import wraps
from flask import session, redirect, url_for, flash

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            # Mengarah ke 'routes.login_page' karena kita akan pakai Blueprint
            return redirect(url_for('routes.login_page'))
        if 'admin_manager' not in session.get('roles', []):
            session.clear()
            flash("Access Denied: You are not authorized.", "danger")
            return redirect(url_for('routes.login_page'))
        return f(*args, **kwargs)
    return decorated_function
