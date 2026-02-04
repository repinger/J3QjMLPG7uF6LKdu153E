from flask import Flask, jsonify, request
from config import Config
from database import init_db, get_db_connection
from monitoring import monitor_loop
from oidc_service import authenticate_oidc
import threading
import time
import sqlite3
import requests
import json

app = Flask(__name__)

MANAGER_API_URL = "http://app-manager:5001/api/groups"

# Init DB & Monitoring thread
init_db()
threading.Thread(target=monitor_loop, daemon=True).start()

# --- [BARU] GLOBAL VAR & THREAD UNTUK DETEKSI PUBLIC IP (IPINFO.IO) ---
HQ_INFO = {
    "lat": None,
    "lng": None,
    "city": "Unknown",
    "ip": "Unknown",
    "org": ""
}

def detect_hq_location():
    """
    Mendeteksi Public IP dan Lokasi Server menggunakan ipinfo.io.
    Dijalankan di background thread saat startup.
    """
    global HQ_INFO
    try:
        # Request ke ipinfo.io
        resp = requests.get('https://ipinfo.io/json', timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            # ipinfo mengembalikan "loc": "lat,lng" (string), perlu dipisah
            loc_str = data.get('loc', '')
            lat, lng = 0, 0
            if ',' in loc_str:
                try:
                    parts = loc_str.split(',')
                    lat = float(parts[0])
                    lng = float(parts[1])
                except ValueError:
                    pass

            HQ_INFO = {
                "lat": lat,
                "lng": lng,
                "city": data.get('city', 'Unknown'),
                "region": data.get('region', ''),
                "country": data.get('country', ''),
                "ip": data.get('ip', 'Unknown'),
                "org": data.get('org', '') # Nama ISP / Organisasi
            }
            print(f"[*] HQ Location Detected (ipinfo.io): {HQ_INFO['city']}, {HQ_INFO['region']} ({HQ_INFO['ip']})")
        else:
            print(f"[!] Failed to detect location: {resp.status_code}")
            
    except Exception as e:
        print(f"[!] HQ Detection Error: {e}")

# Jalankan deteksi lokasi sekali saat startup
threading.Thread(target=detect_hq_location, daemon=True).start()

@app.route('/api/hq', methods=['GET'])
def get_hq_info():
    """Endpoint untuk memberikan info lokasi server pusat"""
    return jsonify(HQ_INFO)

# --------------------------------------------------------------------

def get_setting(key, default_val):
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default_val

def set_setting(key, value):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

@app.route('/api/settings', methods=['GET'])
def get_settings():
    # Ambil dari DB, fallback ke Config default jika error
    lat_thresh = int(get_setting('latency_threshold', 100))
    bw_thresh = int(get_setting('bandwidth_threshold', 10000))
    return jsonify({
        "latency_threshold": lat_thresh,
        "bandwidth_threshold": bw_thresh
    })

@app.route('/api/settings', methods=['POST'])
def update_settings():
    data = request.json
    try:
        if 'latency_threshold' in data:
            set_setting('latency_threshold', int(data['latency_threshold']))
        if 'bandwidth_threshold' in data:
            set_setting('bandwidth_threshold', int(data['bandwidth_threshold']))
        return jsonify({"success": True, "message": "Settings updated"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# --- HELPER: REVERSE GEOCODING (Nominatim - untuk Node biasa) ---
def get_location_name(lat, lng):
    """
    Mengambil nama Kota dan Provinsi berdasarkan koordinat
    menggunakan OpenStreetMap Nominatim API (Gratis).
    """
    if not lat or not lng or lat == 0 or lng == 0:
        return "", ""
    
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}"
        # Wajib menyertakan User-Agent agar tidak diblokir oleh OSM
        headers = {'User-Agent': 'Repinger-Monitor/1.0'}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})
            
            # Cari nama kota (bisa city, town, village, atau county)
            city = address.get('city') or address.get('town') or address.get('village') or address.get('county') or ""
            # Cari nama provinsi
            state = address.get('state') or ""
            
            # Bersihkan string (misal: "Kota Surabaya" -> "Surabaya")
            city = city.replace("Kota ", "").replace("Kabupaten ", "")
            
            return city, state
    except Exception as e:
        print(f"[!] Geocoding Error: {e}")
    
    return "", ""

@app.route('/api/admin/authentik-groups', methods=['GET'])
def get_authentik_groups():
    """
    Proxy untuk mengambil daftar grup dari App Manager.
    """
    try:
        # Panggil endpoint yang baru kita buat di Langkah 1
        resp = requests.get(MANAGER_API_URL, timeout=5)
        if resp.status_code == 200:
            return jsonify(resp.json())
        else:
            return jsonify({"error": "Failed to fetch groups from manager", "status": resp.status_code}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/admin/provinces', methods=['GET'])
def get_available_provinces():
    conn = get_db_connection()
    try:
        rows = conn.execute("SELECT DISTINCT province FROM machines WHERE province IS NOT NULL AND province != '' ORDER BY province ASC").fetchall()
        provinces = [row['province'] for row in rows]
        return jsonify(provinces)
    finally:
        conn.close()

@app.route('/api/admin/province-rules', methods=['GET', 'POST'])
def manage_province_rules():
    conn = get_db_connection()
    try:
        if request.method == 'GET':
            rules = conn.execute("SELECT group_pk, group_name, province FROM province_rules").fetchall()

            result = {}
            for r in rules:
                pk = r['group_pk']
                if pk not in result:
                    result[pk] = {"name": r['group_name'], "provinces": []}
                result[pk]["provinces"].append(r['province'])
            
            return jsonify(result)

        elif request.method == 'POST':
            data = request.json
            
            group_pk = data.get('group_pk')
            group_name = data.get('group_name')
            provinces = data.get('provinces', [])
            
            if not group_pk:
                return jsonify({"error": "Group PK required"}), 400

            conn.execute("DELETE FROM province_rules WHERE group_pk = ?", (group_pk,))
            
            for prov in provinces:
                conn.execute(
                    "INSERT INTO province_rules (group_pk, group_name, province) VALUES (?, ?, ?)",
                    (group_pk, group_name, prov)
                )
            
            conn.commit()
            return jsonify({"success": True, "message": "Rules updated"})

    except Exception as e:
        print(f"[!] Rule Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

# --- AUTH & NOTIFICATION ROUTES (TETAP SAMA) ---

@app.route('/login', methods=['POST'])      
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    auth_code = data.get('code')
    if not auth_code:
        return jsonify({"success": False, "message": "Authorization code missing"}), 400
    user_info = authenticate_oidc(auth_code)
    if user_info:
        return jsonify({"success": True, "user": user_info})
    else:
        return jsonify({"success": False, "message": "Authentication failed"}), 401

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    conn = get_db_connection()
    alerts = conn.execute("SELECT * FROM app_alerts ORDER BY id DESC LIMIT 10").fetchall()
    unread = conn.execute("SELECT COUNT(*) FROM app_alerts WHERE is_read = 0").fetchone()[0]
    conn.close()
    return jsonify({"alerts": [dict(a) for a in alerts], "unread_count": unread})

@app.route('/api/alerts/read', methods=['POST'])
def mark_alerts_read():
    conn = get_db_connection()
    try:
        conn.execute('UPDATE app_alerts SET is_read = 1')
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/alerts/clear', methods=['POST'])
def clear_alerts():
    try:
        conn = get_db_connection()
        conn.execute('DELETE FROM app_alerts')
        conn.commit()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    conn = get_db_connection()
    
    # 1. Ambil Context dari Header
    user_role = request.headers.get('X-User-Role', 'user')
    user_groups_str = request.headers.get('X-User-Groups', '[]')
    
    try:
        user_groups = json.loads(user_groups_str)
    except:
        user_groups = []

    # 2. Query Data Machines
    machines = conn.execute("SELECT * FROM machines").fetchall()
    
    # 3. Filtering Logic
    filtered_machines = []
    
    if user_role == 'admin':
        # Admin melihat semua
        filtered_machines = machines
    else:
        # User Biasa: Cek Province Rules
        if not user_groups:
            # Jika user tidak punya group, atau header gagal terkirim -> Tidak lihat apa-apa
            allowed_provinces = []
            print("[DEBUG] User has no groups, viewing nothing.")
        else:
            # Cari provinsi yang boleh dilihat oleh group user ini
            # Menggunakan parameter binding untuk keamanan (mencegah SQL Injection via header)
            placeholders = ','.join(['?'] * len(user_groups))
            
            # Kita cek berdasarkan group_pk ATAU group_name (untuk fleksibilitas)
            query = f"""
                SELECT DISTINCT province 
                FROM province_rules 
                WHERE group_pk IN ({placeholders}) 
                   OR group_name IN ({placeholders})
            """
            # Parameter dikirim dua kali karena ada dua klausa IN
            params = user_groups + user_groups
            
            rules = conn.execute(query, params).fetchall()
            allowed_provinces = [r['province'] for r in rules]
            print(f"[DEBUG] User Groups: {user_groups} -> Allowed: {allowed_provinces}")

        # Filter array machines
        for m in machines:
            if m['province'] in allowed_provinces:
                filtered_machines.append(m)

    # 4. Format Output & History
    result = []
    for m in filtered_machines:
        m_dict = dict(m)
        # Ambil history hanya untuk machine yang lolos filter
        history = conn.execute("SELECT time, status, latency, rx, tx FROM history WHERE machine_id=? ORDER BY id DESC LIMIT 60", (m['id'],)).fetchall()
        m_dict['history'] = [dict(h) for h in reversed(history)]
        result.append(m_dict)
    
    conn.close()
    return jsonify(result)

@app.route('/api/history', methods=['POST'])
def get_history():
    data = request.json
    mid = data.get('id')
    minutes = data.get('minutes', 60)
    conn = get_db_connection()
    limit = minutes * (60 // Config.PING_INTERVAL) 
    rows = conn.execute("SELECT time, status, latency, rx, tx FROM history WHERE machine_id=? ORDER BY id DESC LIMIT ?", (mid, limit)).fetchall()
    conn.close()
    return jsonify([dict(r) for r in reversed(rows)])

# --- MACHINE ROUTES ---

@app.route('/add', methods=['POST'])
@app.route('/api/add', methods=['POST'])
def add_machine():
    d = request.json
    if not d.get('id') or not d.get('host'):
        return jsonify({"error": "ID and Host required"}), 400

    m_id = str(d['id']).strip()
    host = str(d['host']).strip()

    # [BARU] Auto Detect Location
    lat = float(d.get('lat', 0))
    lng = float(d.get('lng', 0))
    city, province = get_location_name(lat, lng)

    conn = get_db_connection()
    try:
        exist_id = conn.execute("SELECT 1 FROM machines WHERE id = ?", (m_id,)).fetchone()
        if exist_id: return jsonify({"error": f"Node ID '{m_id}' sudah digunakan!"}), 400

        exist_host = conn.execute("SELECT 1 FROM machines WHERE host = ?", (host,)).fetchone()
        if exist_host: return jsonify({"error": f"IP Address '{host}' sudah digunakan node lain!"}), 400

        m_type = str(d.get('type', 'Device'))
        icon = str(d.get('icon', 'fa-server'))
        use_snmp = int(d.get('use_snmp', 0))
        n_down = int(d.get('notify_down', 1))
        n_traf = int(d.get('notify_traffic', 1))
        n_email = int(d.get('notify_email', 0))

        conn.execute('''INSERT INTO machines 
            (id, host, type, icon, use_snmp, lat, lng, notify_down, notify_traffic, notify_email, online, city, province) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)''', 
            (m_id, host, m_type, icon, use_snmp, lat, lng, n_down, n_traf, n_email, city, province))
        
        conn.commit()
        return jsonify({"message": f"Node Added at {city}, {province}" if city else "Node Added"})
        
    except Exception as e:
        print(f"[!] Add Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/edit', methods=['POST'])
@app.route('/api/edit', methods=['POST'])
def edit_machine():
    d = request.json
    m_id = d.get('id')
    host = d.get('host')

    lat = float(d.get('lat', 0))
    lng = float(d.get('lng', 0))
    city, province = get_location_name(lat, lng)

    conn = get_db_connection()
    try:
        exist_host = conn.execute("SELECT 1 FROM machines WHERE host = ? AND id != ?", (host, m_id)).fetchone()
        if exist_host: return jsonify({"error": f"IP Address '{host}' sudah digunakan node lain!"}), 400

        conn.execute('''UPDATE machines SET 
            host=?, type=?, icon=?, use_snmp=?, lat=?, lng=?,
            notify_down=?, notify_traffic=?, notify_email=?,
            city=?, province=?
            WHERE id=?''', 
            (host, d['type'], d.get('icon'), int(d.get('use_snmp',0)), lat, lng,
             int(d.get('notify_down', 1)), int(d.get('notify_traffic', 1)), int(d.get('notify_email', 0)),
             city, province,
             m_id))
        conn.commit()
        return jsonify({"message": "Node Updated"})
    except Exception as e:
        print(f"[!] Edit Error: {e}")
        return jsonify({"error": "Update failed"}), 500
    finally:
        conn.close()

@app.route('/remove', methods=['POST'])
@app.route('/api/remove', methods=['POST'])
def remove_machine():
    d = request.json
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM machines WHERE id=?", (d['id'],))
        conn.commit()
        return jsonify({"message": "Node Removed"})
    except Exception as e:
        print(f"[!] Remove Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/users', methods=['GET'])
@app.route('/api/users', methods=['GET'])
def list_users():
    return jsonify([])

@app.route('/me', methods=['GET'])
@app.route('/api/me', methods=['GET'])
def get_me():
    return jsonify({"username": "dev", "role": "admin"})

if __name__ == '__main__':
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT)
