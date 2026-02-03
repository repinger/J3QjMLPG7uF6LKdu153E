from flask import Flask, jsonify, request
from config import Config
from database import init_db, get_db_connection
from monitoring import monitor_loop
from oidc_service import authenticate_oidc
import threading
import time
import sqlite3
import requests  # [BARU] Pastikan library requests terinstall

app = Flask(__name__)

# Init DB & Monitoring thread
init_db()
threading.Thread(target=monitor_loop, daemon=True).start()

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

# --- HELPER: REVERSE GEOCODING ---
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

# --- AUTH & NOTIFICATION ROUTES (TETAP SAMA SEPERTI SEBELUMNYA) ---
# ... (Kode endpoint login, alerts, dll biarkan seperti semula) ...

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
        # Tangkap error jika masih terjadi
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        # Pastikan koneksi selalu ditutup
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
    machines = conn.execute("SELECT * FROM machines").fetchall()
    
    result = []
    for m in machines:
        m_dict = dict(m)
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

# --- MACHINE ROUTES (UPDATE DI SINI) ---

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

        # [UPDATE] Insert city & province
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

    # [BARU] Auto Detect Location saat Edit
    lat = float(d.get('lat', 0))
    lng = float(d.get('lng', 0))
    city, province = get_location_name(lat, lng)

    conn = get_db_connection()
    try:
        exist_host = conn.execute("SELECT 1 FROM machines WHERE host = ? AND id != ?", (host, m_id)).fetchone()
        if exist_host: return jsonify({"error": f"IP Address '{host}' sudah digunakan node lain!"}), 400

        # [UPDATE] Update query includes city & province
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
