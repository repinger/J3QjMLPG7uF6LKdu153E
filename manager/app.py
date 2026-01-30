from flask import Flask, render_template, request, redirect, url_for, flash, session
import requests
import sqlite3
import uuid
import smtplib
import base64
import os
from email.mime.text import MIMEText
from functools import wraps
from datetime import datetime, timedelta
from config import Config

app = Flask(__name__)
app.config.from_object(Config)

# --- ANTI-CACHE HEADER ---
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# --- DATABASE INIT ---
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

init_db()

# --- HELPER FUNCTIONS ---

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login_page'))
        if 'admin_manager' not in session.get('roles', []):
            session.clear()
            flash("Access Denied: You are not authorized.", "danger")
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)
    return decorated_function

def get_authentik_headers():
    return {
        "Authorization": f"Bearer {Config.AUTHENTIK_TOKEN}",
        "Content-Type": "application/json"
    }

def get_stalwart_headers():
    creds = f"{Config.STALWART_ADMIN_USER}:{Config.STALWART_ADMIN_PASSWORD}"
    encoded = base64.b64encode(creds.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/json"
    }

def get_authentik_groups():
    try:
        res = requests.get(f"{Config.AUTHENTIK_API_URL}/core/groups/", headers=get_authentik_headers())
        if res.status_code == 200:
            return [{'pk': g['pk'], 'name': g['name']} for g in res.json().get('results', [])]
    except: pass
    return []

def get_authentik_users():
    # 1. Cari PK dari grup 'admin_manager'
    admin_group_pk = None
    try:
        groups = get_authentik_groups()
        for g in groups:
            if g['name'] == 'admin_manager': 
                admin_group_pk = g['pk']
                break
    except: pass

    try:
        res = requests.get(f"{Config.AUTHENTIK_API_URL}/core/users/", headers=get_authentik_headers())
        if res.status_code == 200: 
            all_users = res.json().get('results', [])
            
            # 2. Logic Penandaan (Flagging)
            for u in all_users:
                username = u.get('username', '')
                u['is_protected'] = False # Default: Bisa diedit/hapus
                
                # Cek A: System Users (akadmin & ak-outpost)
                if username == 'akadmin' or username.startswith('ak-outpost-'):
                    u['is_protected'] = True
                    u['role_label'] = 'System'
                
                # Cek B: Admin Users (Anggota grup admin_manager)
                elif admin_group_pk and admin_group_pk in u.get('groups', []):
                    u['is_protected'] = True
                    u['role_label'] = 'Admin'
            
            return all_users # Kembalikan SEMUA user (termasuk yang protected)
    except Exception as e:
        print(f"[!] Get Users Error: {e}")
        pass
    return []

def create_full_user(username, name, email, password, group_pk=None):
    """
    Membuat user di Authentik & Stalwart.
    Revisi: Menambahkan langkah eksplisit set_password untuk Authentik.
    """
    # --- 1. AUTHENTIK: CREATE USER ---
    url_auth_create = f"{Config.AUTHENTIK_API_URL}/core/users/"
    payload_auth = {
        "username": username,
        "name": name,
        "email": email,
        "is_active": True
        # Password dihapus dari sini karena sering diabaikan oleh API
    }
    if group_pk:
        payload_auth["groups"] = [group_pk]

    try:
        # A. Request Create User
        auth_res = requests.post(url_auth_create, json=payload_auth, headers=get_authentik_headers())
        
        if auth_res.status_code in [200, 201]:
            user_data = auth_res.json()
            user_pk = user_data.get('pk') # Ambil Primary Key (UUID) user baru
            
            # B. Request Set Password (Eksplisit)
            if user_pk:
                url_auth_pwd = f"{Config.AUTHENTIK_API_URL}/core/users/{user_pk}/set_password/"
                payload_pwd = {"password": password}
                pwd_res = requests.post(url_auth_pwd, json=payload_pwd, headers=get_authentik_headers())
                
                if pwd_res.status_code != 200:
                    print(f"[!] Authentik Password Set Failed: {pwd_res.text}")
                    # Lanjut dulu, tapi catat error ini
            
            # --- 2. STALWART: CREATE MAILBOX ---
            url_stal = f"{Config.STALWART_API_URL}/api/principal"
            payload_stal = {
                "type": "individual",
                "name": username,
                "description": name,
                "secrets": [password],
                "emails": [email],
                "quota": 0,
                "roles": ["user"] 
            }
            stal_res = requests.post(url_stal, json=payload_stal, headers=get_stalwart_headers())
            
            return True, auth_res, stal_res
        
        # Jika gagal create user di Authentik
        print(f"[!] Authentik Create Failed: {auth_res.text}")
        return False, auth_res, None

    except Exception as e:
        print(f"[!] API Exception: {e}")
        return False, None, None

def delete_authentik_user(pk):
    return requests.delete(f"{Config.AUTHENTIK_API_URL}/core/users/{pk}/", headers=get_authentik_headers())

def delete_stalwart_user(username):
    import urllib.parse
    safe_username = urllib.parse.quote(username)
    return requests.delete(f"{Config.STALWART_API_URL}/api/principal/{safe_username}", headers=get_stalwart_headers())

# --- ROUTES ---

@app.route('/login')
def login():
    redirect_uri = Config.OIDC_REDIRECT_URI
    auth_url = (f"{Config.OIDC_AUTH_URL}?client_id={Config.OIDC_CLIENT_ID}"
                f"&response_type=code&redirect_uri={redirect_uri}&scope=openid profile email groups")
    return redirect(auth_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code: return "No code", 400

    data = {
        'grant_type': 'authorization_code', 'code': code,
        'redirect_uri': Config.OIDC_REDIRECT_URI,
        'client_id': Config.OIDC_CLIENT_ID, 'client_secret': Config.OIDC_CLIENT_SECRET
    }
    try:
        res = requests.post(Config.OIDC_TOKEN_URL, data=data)
        if res.status_code != 200: return f"Token Error: {res.text}", 400
        
        access_token = res.json().get('access_token')
        user_res = requests.get(Config.OIDC_USERINFO_URL, headers={'Authorization': f'Bearer {access_token}'})
        user_info = user_res.json()
        
        groups = user_info.get('groups', [])
        if 'admin_manager' not in groups:
            flash("Login failed: Unauthorized.", "danger")
            return redirect(url_for('login_page'))

        session['user'] = user_info.get('preferred_username')
        session['roles'] = groups
        return redirect(url_for('dashboard'))
    except Exception as e:
        return f"Auth Error: {e}", 500

@app.route('/logout')
def logout():
    session.clear()
    if Config.OIDC_LOGOUT_URL: return redirect(Config.OIDC_LOGOUT_URL)
    return redirect(url_for('login_page'))

@app.route('/')
def login_page():
    if 'user' in session: return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    users = get_authentik_users()
    groups = get_authentik_groups()
    return render_template('dashboard.html', users=users, groups=groups)

@app.route('/invite', methods=['POST'])
@login_required
def invite():
    email_recipient = request.form.get('email')
    group_pk = request.form.get('group')
    
    if not email_recipient or not group_pk:
        flash("Error: You MUST provide an email AND assign a group.", "danger")
        return redirect(url_for('dashboard'))

    token = str(uuid.uuid4())
    created_at = datetime.now()
    
    conn = sqlite3.connect(Config.MANAGER_DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO invites (token, email, group_pk, created_at, used) VALUES (?, ?, ?, ?, 0)", 
              (token, email_recipient, group_pk, created_at))
    conn.commit()
    conn.close()
    
    invite_link = f"http://manager.localhost/register?token={token}"
    
    # --- PESAN EMAIL REVISI (Hanya Link) ---
    msg_content = f"""Hello,

You have been invited to create an account on the User Manager platform.
To get started, please click the link below to set up your username and password:

{invite_link}

This invitation link is valid for 12 hours.

Best regards,
System Administrator
"""
    
    msg = MIMEText(msg_content)
    msg['Subject'] = "Action Required: Complete your Account Registration"
    msg['From'] = Config.SMTP_EMAIL
    msg['To'] = email_recipient
    
    try:
        with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
            server.ehlo()
            if server.has_extn('STARTTLS'):
                server.starttls()
                server.ehlo()
            
            if Config.SMTP_PASSWORD:
                if server.has_extn('AUTH'):
                    server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
            
            server.send_message(msg)
        flash(f"Invitation sent to {email_recipient}", "success")
    except Exception as e:
        flash(f"Failed to send email: {e}", "danger")
        
    return redirect(url_for('dashboard'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    token = request.args.get('token') or request.form.get('token')
    if not token: return render_template('error.html', message="Missing Token"), 400

    conn = sqlite3.connect(Config.MANAGER_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT email, group_pk, created_at, used FROM invites WHERE token = ?", (token,))
    row = c.fetchone()
    conn.close()
    
    if not row: return render_template('error.html', message="Invalid Token"), 404
    email_db, group_pk_db, created_at_str, used = row
    
    if used == 1: return render_template('error.html', message="Token Used"), 403
    
    try:
        created_at = datetime.fromisoformat(str(created_at_str))
        if datetime.now() - created_at > timedelta(hours=12):
            return render_template('error.html', message="Token Expired"), 403
    except: pass
    
    if request.method == 'GET':
        return render_template('register.html', token=token, email=email_db)
    
    username = request.form.get('username')
    password = request.form.get('password')
    confirm = request.form.get('confirm_password')
    
    # 1. VALIDASI BARU: Panjang Password
    if len(password) < 8:
        flash("Password must be at least 8 characters long!", "danger")
        return render_template('register.html', token=token, email=email_db)
    
    if password != confirm:
        flash("Passwords do not match!", "danger")
        return render_template('register.html', token=token, email=email_db)
    
    # --- LOGIC UTAMA PERUBAHAN EMAIL ---
    # Jangan pakai email_db (email luar). Generate email internal.
    system_email = f"{username}@{Config.MAIL_DOMAIN}"
    
    success, auth_res, stal_res = create_full_user(username, username, system_email, password, group_pk_db)
    
    if success:
        conn = sqlite3.connect(Config.MANAGER_DB_PATH)
        conn.execute("UPDATE invites SET used = 1 WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return render_template('success.html', username=username)
    else:
        err = auth_res.text if auth_res else "Error"
        flash(f"Failed: {err}", "danger")
        return render_template('register.html', token=token, email=email_db)

@app.route('/create', methods=['POST'])
def create():
    username = request.form.get('username')
    password = request.form.get('password')
    confirm = request.form.get('confirm_password') # Asumsi sudah ada dari update sebelumnya
    group_pk = request.form.get('group')
    
    # 2. VALIDASI BARU: Panjang Password
    if len(password) < 8:
        flash("Error: Password must be at least 8 characters long!", "danger")
        return redirect(url_for('dashboard'))

    if password != confirm:
        flash("Error: Passwords do not match!", "danger")
        return redirect(url_for('dashboard'))

    # Generate Email
    system_email = f"{username}@{Config.MAIL_DOMAIN}"
    
    success, auth_res, stal_res = create_full_user(username, username, system_email, password, group_pk)
    
    if success:
        flash(f"User {username} created ({system_email}).", "success")
    else:
        flash(f"Failed: {auth_res.text if auth_res else 'Error'}", "danger")
        
    return redirect(url_for('dashboard'))

@app.route('/delete/<int:pk>', methods=['POST'])
@login_required
def delete(pk):
    username = request.form.get('username_hidden')
    
    # --- SECURITY CHECK ---
    # Mencegah penghapusan System User via request langsung
    if username == 'akadmin' or (username and username.startswith('ak-outpost-')):
        flash("Action Failed: System users cannot be deleted.", "danger")
        return redirect(url_for('dashboard'))
    
    delete_authentik_user(pk)
    if username: delete_stalwart_user(username)
    flash("User deleted.", "info")
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
