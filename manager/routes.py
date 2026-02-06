from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from config import Config
from utils import login_required
from database import get_db, get_all_divisions, add_division, delete_division
from integrations import authentik, stalwart
from actions import create_full_user_action, create_oidc_app_action
import requests
import uuid
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from utils import validate_phone, generate_nip

# Definisikan Blueprint 'routes'
bp = Blueprint('routes', __name__)

# --- HELPER: ROBUST EMAIL SENDER ---
def send_email(recipient, subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = Config.SMTP_EMAIL
    msg['To'] = recipient
    
    try:
        # 1. Connect (jangan gunakan context manager 'with' dulu agar bisa handle exception lebih detail)
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
        
        # 2. Identify yourself (EHLO)
        server.ehlo()
        
        # 3. Try STARTTLS (Upgrade connection to secure if server supports it)
        if server.has_extn('STARTTLS'):
            server.starttls()
            server.ehlo() # Re-identify after TLS handshake
        
        # 4. Login (Only if password provided AND server supports AUTH)
        if Config.SMTP_PASSWORD:
            if server.has_extn('AUTH'):
                server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
            else:
                print(f"[WARN] SMTP Password set but server at {Config.SMTP_SERVER}:{Config.SMTP_PORT} does not support AUTH. Sending anonymously.")
        
        # 5. Send & Quit
        server.send_message(msg)
        server.quit()
        return True, "Email sent successfully"
    except Exception as e:
        print(f"[!] Email Error: {e}")
        return False, str(e)

# --- ROUTES ---

@bp.route('/login')
def login():
    redirect_uri = Config.OIDC_REDIRECT_URI
    auth_url = (f"{Config.OIDC_AUTH_URL}?client_id={Config.OIDC_CLIENT_ID}"
                f"&response_type=code&redirect_uri={redirect_uri}&scope=openid profile email groups")
    return redirect(auth_url)

@bp.route('/callback')
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
        
        session['user'] = user_info.get('preferred_username')
        session['roles'] = groups
        return redirect(url_for('routes.dashboard'))
    except Exception as e:
        return f"Auth Error: {e}", 500

@bp.route('/logout')
def logout():
    session.clear()
    if Config.OIDC_LOGOUT_URL:
        return redirect(Config.OIDC_LOGOUT_URL)
    return redirect(url_for('routes.login_page'))

@bp.route('/')
def login_page():
    if 'user' in session: return redirect(url_for('routes.dashboard'))
    return render_template('login.html')

# ... imports ... (tidak berubah)

@bp.route('/dashboard')
@login_required
def dashboard():
    users = authentik.get_users()
    all_raw_groups = authentik.get_groups()
    apps = authentik.get_apps()
    providers = authentik.get_oauth_providers()
    divisions = get_all_divisions()
    
    provider_dict = {p['pk']: p for p in providers}
    for app in apps:
        prov_id = app.get('provider')
        prov_obj = provider_dict.get(prov_id)
        if prov_obj:
            app['client_id'] = prov_obj.get('client_id')
            app['client_secret'] = prov_obj.get('client_secret')
            urls = [u.get('url') for u in prov_obj.get('redirect_uris', [])]
            app['redirect_uris_str'] = "\n".join(urls)
        else:
            app['client_id'] = "-"
            app['client_secret'] = "-"
            app['redirect_uris_str'] = ""
        
        oidc_conf = authentik.get_oidc_configuration(app['slug'])
        app['endpoints'] = {
            'issuer': oidc_conf.get('issuer', 'Unavailable'),
            'authorize': oidc_conf.get('authorization_endpoint', '-'),
            'token': oidc_conf.get('token_endpoint', '-'),
            'userinfo': oidc_conf.get('userinfo_endpoint', '-')
        }

        bindings = authentik.get_policy_bindings_by_target(app['pk'])
        app['bound_group_ids'] = [b.get('group') for b in bindings if b.get('group')]
        bound_names = []
        for bg_id in app['bound_group_ids']:
            g_obj = next((g for g in all_raw_groups if g['pk'] == bg_id), None)
            if g_obj: bound_names.append(g_obj['name'])
        app['bound_group_names'] = ", ".join(bound_names)

    
    current_user = session.get('user')
    current_roles = session.get('roles', []) 
    manager_client_id = Config.OIDC_CLIENT_ID

    if current_user:
        users = [u for u in users if u.get('username') != current_user]

    # 2. Filter Groups untuk TABEL (Sembunyikan System & Own Groups)
    system_hidden_names = ["authentik Admins", "authentik Read-only"]
    
    # Variabel 'groups' ini KHUSUS untuk Tabel di Tab "Groups"
    # Isinya HANYA grup user biasa.
    groups_for_table = [
        g for g in all_raw_groups 
        if g['name'] not in system_hidden_names 
        and g['name'] not in current_roles
    ]

    group_map = {g['pk']: g['name'] for g in all_raw_groups}

    for g in groups_for_table:
        parent_names = []
        current_parents = g.get('parents', [])
        
        for p_pk in current_parents:
            p_name = group_map.get(p_pk)
            if p_name:
                parent_names.append(p_name)
        g['parent_names_str'] = ", ".join(parent_names) if parent_names else "-"

    apps = [a for a in apps if a.get('client_id') != manager_client_id]
    providers = [p for p in providers if p.get('client_id') != manager_client_id]

    return render_template('dashboard.html', 
                           users=users, 
                           groups=groups_for_table,
                           all_groups=all_raw_groups, 
                           apps=apps,
                           divisions=divisions)

@bp.route('/invite', methods=['POST'])
@login_required
def invite():
    email = request.form.get('email')
    group_pk = request.form.get('group')
    if not email or not group_pk:
        flash("Email and Group are required.", "danger")
        return redirect(url_for('routes.dashboard'))

    token = str(uuid.uuid4())
    conn = get_db()
    conn.execute("INSERT INTO invites (token, email, group_pk, created_at, used) VALUES (?, ?, ?, ?, 0)", 
              (token, email, group_pk, datetime.now()))
    conn.commit()
    conn.close()
    
    invite_link = f"http://manager.localhost/register?token={token}"
    
    msg_body = f"""Hello,

You have been invited to create an account on the User Manager platform.
Please click the link below to set up your username and password:

{invite_link}

This invitation is valid for 24 hours.
"""
    
    success, msg = send_email(email, "Invitation to User Manager", msg_body)
    
    if success:
        flash(f"Invitation sent to {email}", "success")
    else:
        flash(f"Failed to send email: {msg}", "danger")
        
    return redirect(url_for('routes.dashboard'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    token = request.args.get('token') or request.form.get('token')

    if not token: return render_template('error.html', message="Missing Token"), 400
    
    conn = get_db()
    cursor = conn.cursor()
    row = cursor.execute("SELECT email, group_pk, created_at, used FROM invites WHERE token = ?", (token,)).fetchone()
    conn.close()
    
    if not row or row[3] == 1: return render_template('error.html', message="Invalid/Used Token"), 403

    divisions = get_all_divisions()

    if request.method == 'GET': 
        return render_template('register.html', token=token, email=row[0], divisions=divisions)
    
    name = request.form.get('name')
    username = request.form.get('username')
    password = request.form.get('password')
    confirm = request.form.get('confirm_password')
    phone = request.form.get('phone')
    division_code = request.form.get('division')
    dob_str = request.form.get('dob')
    
    # VALIDASI 1: Cek Password Match
    if password != confirm:
        flash("Passwords do not match. Please try again.", "danger")
        return render_template('register.html', token=token, email=row[0])

    # VALIDASI 2: Panjang Password
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return render_template('register.html', token=token, email=row[0])
    
    if not validate_phone(phone):
        flash("Invalid phone number format. Use 08... or +62...", "danger")
        return render_template('register.html', token=token, email=row[0])
    
    valid_codes = [d['code'] for d in divisions]
    if division_code not in valid_codes:
         flash("Invalid Division selected.", "danger")
         return render_template('register.html', token=token, email=row[0], divisions=divisions)
    
    try:
        dob_obj = datetime.strptime(dob_str, '%Y-%m-%d')
    except ValueError:
        flash("Invalid Date of Birth.", "danger")
        return render_template('register.html', token=token, email=row[0], divisions=divisions)
    
    count_division = 0 
    nip = generate_nip(division_code, dob_obj, count_division)

    system_email = f"{username}@{Config.MAIL_DOMAIN}"
    success, _, _ = create_full_user_action(
        username, name, system_email, password, row[1], 
        phone=phone, nip=nip
    )
    
    if success:
        conn = get_db()
        conn.execute("UPDATE invites SET used = 1 WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return render_template('success.html', username=username)
    else:
        flash("Registration failed. Username might be taken.", "danger")
        return render_template('register.html', token=token, email=row[0])

@bp.route('/division/create', methods=['POST'])
@login_required
def division_create():
    name = request.form.get('name')
    code = request.form.get('code')
    
    # Validasi input sederhana
    if not name or not code:
        flash("Name and Code are required.", "danger")
        return redirect(url_for('routes.dashboard'))
        
    if len(code) != 2 or not code.isdigit():
        flash("Code must be exactly 2 digits (e.g., 01, 99).", "danger")
        return redirect(url_for('routes.dashboard'))

    success, msg = add_division(name, code)
    if success:
        flash(f"Division '{name}' added.", "success")
    else:
        flash(f"Error: {msg}", "danger")
        
    return redirect(url_for('routes.dashboard'))

@bp.route('/division/delete/<int:id>', methods=['POST'])
@login_required
def division_delete(id):
    delete_division(id)
    flash("Division deleted.", "success")
    return redirect(url_for('routes.dashboard'))

@bp.route('/create', methods=['POST'])
@login_required
def create():
    username = request.form.get('username')
    password = request.form.get('password')
    confirm = request.form.get('confirm_password')
    group_pk = request.form.get('group')
    
    if password != confirm:
        flash("Failed: Passwords do not match!", "danger")
        return redirect(url_for('routes.dashboard'))
        
    system_email = f"{username}@{Config.MAIL_DOMAIN}"
    
    success, auth_res, _ = create_full_user_action(username, username, system_email, password, group_pk)
    
    if success: 
        flash(f"User {username} created successfully.", "success")
    else: 
        error_msg = "Unknown Error"
        if auth_res:
            try:
                err_data = auth_res.json()
                if isinstance(err_data, dict):
                    first_key = next(iter(err_data))
                    first_val = err_data[first_key]
                    if isinstance(first_val, list):
                        error_msg = f"{first_key}: {first_val[0]}"
                    else:
                        error_msg = f"{first_key}: {first_val}"
                else:
                    error_msg = auth_res.text
            except:
                error_msg = auth_res.text if auth_res.text else f"Status Code {auth_res.status_code}"

        flash(f"Failed to create user: {error_msg}", "danger")
        
    return redirect(url_for('routes.dashboard'))

@bp.route('/delete/<int:pk>', methods=['POST'])
@login_required
def delete(pk):
    username = request.form.get('username_hidden')
    if username == 'akadmin' or (username and username.startswith('ak-outpost-')):
        flash("Cannot delete system users.", "danger")
    else:
        authentik.delete_user(pk)
        if username: stalwart.delete_mailbox(username)
        flash("User deleted.", "info")
    return redirect(url_for('routes.dashboard'))

@bp.route('/user/edit/<pk>', methods=['POST'])
@login_required
def edit_user(pk):
    res = authentik.update_user(pk, request.form)
    if res.status_code in [200, 201]: flash("User updated.", "success")
    else: flash(f"Update failed: {res.text}", "danger")
    return redirect(url_for('routes.dashboard'))

@bp.route('/group/create', methods=['POST'])
@login_required
def group_create():
    name = request.form.get('name')
    parent_pks = request.form.getlist('parents') # [BARU] Ambil list input parents
    
    res = authentik.create_group(name, parent_pks)
    
    if res.status_code == 201: flash("Group created.", "success")
    else: flash(f"Error: {res.text}", "danger")
    return redirect(url_for('routes.dashboard'))

@bp.route('/group/delete/<pk>', methods=['POST'])
@login_required
def group_delete(pk):
    res = authentik.delete_group(pk)
    if res.status_code == 204: flash("Group deleted.", "success")
    else: flash("Failed to delete group.", "danger")
    return redirect(url_for('routes.dashboard'))

@bp.route('/group/edit/<pk>', methods=['POST'])
@login_required
def group_edit(pk):
    name = request.form.get('name')
    parent_pks = request.form.getlist('parents') # [BARU] Ambil list input parents
    
    if not name:
        flash("Group name is required.", "danger")
        return redirect(url_for('routes.dashboard'))
    
    res = authentik.update_group(pk, name, parent_pks)
    
    if res.status_code == 200:
        flash(f"Group updated to '{name}'.", "success")
    else:
        flash(f"Failed to update group: {res.text}", "danger")
    return redirect(url_for('routes.dashboard'))

@bp.route('/app/create', methods=['POST'])
@login_required
def app_create():
    name = request.form.get('name')
    redirect_uri = request.form.get('redirect_uri') or request.form.get('redirect_uris')
    launch_url = request.form.get('launch_url')
    client_type = request.form.get('client_type')
    auth_flow_mode = request.form.get('auth_flow')
    
    # [BARU] Ambil list group yang dipilih (multiple select)
    selected_groups = request.form.getlist('groups') 

    # 1. Buat App & Provider (menggunakan action yang sudah ada)
    success, msg = create_oidc_app_action(
        name, redirect_uri, launch_url, client_type, flow_mode=auth_flow_mode
    )
    
    if success:
        # 2. Cari App PK yang baru saja dibuat (berdasarkan slug/nama)
        # Note: create_oidc_app_action idealnya me-return PK, tapi jika tidak, kita cari manual:
        all_apps = authentik.get_apps()
        # Cari app dengan nama yang sama (ini pendekatan naif, idealnya pakai slug return dari action)
        new_app = next((a for a in all_apps if a['name'] == name), None)
        
        if new_app and selected_groups:
            for grp_pk in selected_groups:
                authentik.create_policy_binding(new_app['pk'], grp_pk)
        
        flash("Application created with bindings.", "success")
    else:
        flash(msg, "danger")
        
    return redirect(url_for('routes.dashboard'))

def ensure_url(url):
    if not url: return ""
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return f"https://{url}"
    return url

@bp.route('/app/edit/<pk>', methods=['POST'])
@login_required
def app_edit(pk):
    name = request.form.get('name')
    launch_url = ensure_url(request.form.get('launch_url'))
    redirect_uris_raw = request.form.get('redirect_uris')
    
    submitted_group_ids = set(request.form.getlist('groups'))

    redirect_uris_list = None
    if redirect_uris_raw:
        redirect_uris_list = [ensure_url(u) for u in redirect_uris_raw.replace('\r\n', '\n').split('\n') if u.strip()]

    res = authentik.update_application(pk, name, launch_url, redirect_uris=redirect_uris_list)
    
    if res.status_code == 200:
        current_bindings = authentik.get_policy_bindings_by_target(pk)
        
        existing_map = {b.get('group'): b.get('pk') for b in current_bindings if b.get('group')}
        existing_group_ids = set(existing_map.keys())
        
        to_add = submitted_group_ids - existing_group_ids
        to_delete = existing_group_ids - submitted_group_ids
        
        for g_id in to_delete:
            binding_pk = existing_map[g_id]
            authentik.delete_policy_binding(binding_pk)
            
        for g_id in to_add:
            authentik.create_policy_binding(pk, g_id)

        flash("App and access groups updated successfully.", "success")
    else:
        flash(f"Failed update info: {res.text}", "danger")

    return redirect(url_for('routes.dashboard'))

@bp.route('/app/delete/<pk>', methods=['POST'])
@login_required
def app_delete(pk):
    res = authentik.delete_application(pk)
    
    if res.status_code == 204:
        flash("Application deleted successfully.", "success")
    else:
        flash(f"Failed to delete application. API Response: {res.status_code} {res.text}", "danger")
        
    return redirect(url_for('routes.dashboard'))

@bp.route('/api/groups', methods=['GET'])
def api_get_groups():
    """
    Endpoint internal untuk memberikan daftar grup Authentik ke Backend App.
    """
    # Menggunakan fungsi existing dari integrasi authentik
    groups = authentik.get_groups()
    return jsonify(groups)
