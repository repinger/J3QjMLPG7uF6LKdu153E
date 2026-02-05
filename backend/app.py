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
import os
import re
import ipaddress

app = Flask(__name__)

PROM_TARGETS_FILE = "/app/prom_targets/snmp_targets.json"
MANAGER_API_URL = "http://app-manager:5001/api/groups"
SNMP_EXPORTER_URL = "http://snmp-exporter:9116"

HQ_INFO = {
    "lat": None,
    "lng": None,
    "city": "Unknown",
    "region": "",
    "country": "",
    "ip": "Unknown",
    "org": "",
    "is_manual": False  # Tambahkan flag ini untuk frontend
}

def probe_snmp(machine_id, host):
    print(f"[*] Probing SNMP capabilities for {host}...")
    
    time.sleep(2)
    
    try:
        check_url = f"{SNMP_EXPORTER_URL}/snmp"
        params = {
            "target": host,
            "module": "if_mib"
        }
        
        resp = requests.get(check_url, params=params, timeout=10)
        
        if resp.status_code == 200 and len(resp.text) > 0:
            print(f"[+] SNMP DETECTED for {host}! Enabling monitoring...")
            
            conn = get_db_connection()
            conn.execute("UPDATE machines SET use_snmp = 1 WHERE id = ?", (machine_id,))
            conn.commit()
            conn.close()
            
            sync_prometheus_targets()
        else:
            print(f"[-] SNMP Probe failed for {host} (Status: {resp.status_code}). SNMP disabled.")
            
    except Exception as e:
        print(f"[!] SNMP Probe Error for {host}: {str(e)}")

def sync_prometheus_targets():
    conn = get_db_connection()
    try:
        nodes = conn.execute("SELECT id, host, city, province FROM machines WHERE use_snmp = 1").fetchall()
        
        targets_list = []
        
        for node in nodes:
            entry = {
                "targets": [node['host']],
                "labels": {
                    "hostname": node['id'],
                    "city": node['city'] or "Unknown",
                    "province": node['province'] or "Unknown"
                }
            }
            targets_list.append(entry)
            
        os.makedirs(os.path.dirname(PROM_TARGETS_FILE), exist_ok=True)
        
        with open(PROM_TARGETS_FILE, 'w') as f:
            json.dump(targets_list, f, indent=2)
            
        print(f"[*] Prometheus targets updated: {len(targets_list)} nodes.")
        
    except Exception as e:
        print(f"[!] Failed to sync Prometheus targets: {e}")
    finally:
        conn.close()

def is_valid_host_or_ip(target):
    try:
        ipaddress.ip_address(target)
        return True
    except ValueError:
        pass

    if len(target) > 253:
        return False
    
    hostname_regex = r"^([a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$|^localhost$"
    
    if re.match(hostname_regex, target):
        return True
        
    return False

def init_hq_location():
    global HQ_INFO
    try:
        # Cek apakah mode manual aktif di database
        is_manual = get_setting('hq_manual', '0')
        
        if is_manual == '1':
            print("[*] Loading Manual HQ Location from Database...")
            HQ_INFO = {
                "lat": float(get_setting('hq_lat', 0)),
                "lng": float(get_setting('hq_lng', 0)),
                "city": get_setting('hq_city', 'Manual Location'),
                "region": get_setting('hq_region', ''),
                "country": get_setting('hq_country', ''),
                "ip": "Manual Override",
                "org": "Internal",
                "is_manual": True
            }
        else:
            # Jika tidak manual, jalankan deteksi IP seperti biasa
            print("[*] Auto-detecting HQ Location via ipinfo.io...")
            resp = requests.get('https://ipinfo.io/json', timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
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
                    "org": data.get('org', ''),
                    "is_manual": False
                }
                print(f"[*] HQ Location Detected: {HQ_INFO['city']}")
            else:
                print(f"[!] Failed to detect location: {resp.status_code}")
            
    except Exception as e:
        print(f"[!] HQ Init Error: {e}")

threading.Thread(target=init_hq_location, daemon=True).start()

@app.route('/api/hq', methods=['POST'])
def update_hq_location():
    global HQ_INFO
    data = request.json
    
    try:
        mode = data.get('mode') # 'auto' atau 'manual'
        
        if mode == 'auto':
            # Set setting ke auto dan reload
            set_setting('hq_manual', '0')
            # Panggil fungsi init ulang di thread terpisah atau langsung
            threading.Thread(target=init_hq_location, daemon=True).start()
            return jsonify({"success": True, "message": "Reverting to auto detection..."})
            
        elif mode == 'manual':
            lat = float(data.get('lat'))
            lng = float(data.get('lng'))
            city = data.get('city', 'Manual Location')
            
            # Simpan ke Database (Settings)
            set_setting('hq_manual', '1')
            set_setting('hq_lat', lat)
            set_setting('hq_lng', lng)
            set_setting('hq_city', city)
            set_setting('hq_region', data.get('region', ''))
            set_setting('hq_country', data.get('country', ''))
            
            # Update Memory Global Langsung (agar tidak perlu restart)
            HQ_INFO = {
                "lat": lat,
                "lng": lng,
                "city": city,
                "region": data.get('region', ''),
                "country": data.get('country', ''),
                "ip": "Manual Override",
                "org": "Internal",
                "is_manual": True
            }
            
            return jsonify({"success": True, "message": "HQ Location updated manually"})
            
        return jsonify({"error": "Invalid mode"}), 400

    except Exception as e:
        print(f"[!] Update HQ Error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/hq', methods=['GET'])
def get_hq_info():
    return jsonify(HQ_INFO)

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

def get_allowed_provinces(conn, user_groups):
    if not user_groups:
        return []
    
    placeholders = ','.join(['?'] * len(user_groups))
    query = f"""
        SELECT DISTINCT province 
        FROM province_rules 
        WHERE group_pk IN ({placeholders}) 
           OR group_name IN ({placeholders})
    """
    params = user_groups + user_groups
    rows = conn.execute(query, params).fetchall()
    return [r['province'] for r in rows]

@app.route('/api/settings', methods=['GET'])
def get_settings():
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

def get_location_name(lat, lng):
    if not lat or not lng or lat == 0 or lng == 0:
        return "", ""
    
    try:
        url = f"https://nominatim.openstreetmap.org/reverse?format=json&lat={lat}&lon={lng}"
        headers = {'User-Agent': 'Repinger-Monitor/1.0'}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            address = data.get('address', {})
            
            city = address.get('city') or address.get('town') or address.get('village') or address.get('county') or ""
            state = address.get('state') or ""
            
            city = city.replace("Kota ", "").replace("Kabupaten ", "")
            
            return city, state
    except Exception as e:
        print(f"[!] Geocoding Error: {e}")
    
    return "", ""

@app.route('/api/admin/authentik-groups', methods=['GET'])
def get_authentik_groups():
    try:
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
    # 1. Ambil Context User
    current_user = request.headers.get('X-User-Name')
    user_role = request.headers.get('X-User-Role', 'user')
    user_groups_str = request.headers.get('X-User-Groups', '[]')
    
    if not current_user:
        return jsonify({"alerts": [], "unread_count": 0})

    try:
        user_groups = json.loads(user_groups_str)
    except:
        user_groups = []

    conn = get_db_connection()
    
    province_filter_sql = ""
    province_params = []
    
    if user_role != 'admin':
        allowed = get_allowed_provinces(conn, user_groups)
        if not allowed:
            conn.close()
            return jsonify({"alerts": [], "unread_count": 0})
        
        placeholders = ','.join(['?'] * len(allowed))
        province_filter_sql = f"AND m.province IN ({placeholders})"
        province_params = allowed

    query = f"""
        SELECT a.id, a.machine_id, a.type, a.message, a.time,
               m.host, m.city, m.province,
               COALESCE(s.is_read, 0) as is_read
        FROM app_alerts a
        JOIN machines m ON a.machine_id = m.id
        LEFT JOIN alert_status s ON a.id = s.alert_id AND s.username = ?
        WHERE (s.is_cleared IS NULL OR s.is_cleared = 0)
        {province_filter_sql}
        ORDER BY a.id DESC LIMIT 20
    """
    
    params = [current_user] + province_params
    alerts = conn.execute(query, params).fetchall()
    
    unread_query = f"""
        SELECT COUNT(*)
        FROM app_alerts a
        JOIN machines m ON a.machine_id = m.id
        LEFT JOIN alert_status s ON a.id = s.alert_id AND s.username = ?
        WHERE (s.is_read IS NULL OR s.is_read = 0)
          AND (s.is_cleared IS NULL OR s.is_cleared = 0)
          {province_filter_sql}
    """
    unread = conn.execute(unread_query, params).fetchone()[0]
    
    conn.close()
    return jsonify({"alerts": [dict(a) for a in alerts], "unread_count": unread})

@app.route('/api/alerts/read', methods=['POST'])
def mark_alerts_read():
    current_user = request.headers.get('X-User-Name')
    user_role = request.headers.get('X-User-Role', 'user')
    user_groups_str = request.headers.get('X-User-Groups', '[]')
    
    if not current_user: return jsonify({"success": False, "error": "No User Context"}), 403

    conn = get_db_connection()
    try:
        province_join = ""
        province_where = ""
        province_params = []
        
        if user_role != 'admin':
            user_groups = json.loads(user_groups_str) if user_groups_str else []
            allowed = get_allowed_provinces(conn, user_groups)
            if not allowed:
                return jsonify({"success": True})
            
            placeholders = ','.join(['?'] * len(allowed))
            province_join = "JOIN machines m ON a.machine_id = m.id"
            province_where = f"AND m.province IN ({placeholders})"
            province_params = allowed

        query_ids = f"""
            SELECT a.id FROM app_alerts a
            {province_join}
            LEFT JOIN alert_status s ON a.id = s.alert_id AND s.username = ?
            WHERE (s.is_cleared IS NULL OR s.is_cleared = 0)
            {province_where}
        """
        params_select = [current_user] + province_params
        
        pending_alerts = conn.execute(query_ids, params_select).fetchall()

        for row in pending_alerts:
            aid = row['id']
            exists = conn.execute("SELECT 1 FROM alert_status WHERE alert_id=? AND username=?", (aid, current_user)).fetchone()
            if exists:
                conn.execute("UPDATE alert_status SET is_read=1 WHERE alert_id=? AND username=?", (aid, current_user))
            else:
                conn.execute("INSERT INTO alert_status (alert_id, username, is_read, is_cleared) VALUES (?, ?, 1, 0)", (aid, current_user))
        
        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/alerts/clear', methods=['POST'])
def clear_alerts():
    current_user = request.headers.get('X-User-Name')
    user_role = request.headers.get('X-User-Role', 'user')
    user_groups_str = request.headers.get('X-User-Groups', '[]')
    
    if not current_user: return jsonify({"success": False, "error": "No User Context"}), 403

    conn = get_db_connection()
    try:
        province_join = ""
        province_where = ""
        province_params = []
        
        if user_role != 'admin':
            user_groups = json.loads(user_groups_str) if user_groups_str else []
            allowed = get_allowed_provinces(conn, user_groups)
            if not allowed: return jsonify({"success": True})
            
            placeholders = ','.join(['?'] * len(allowed))
            province_join = "JOIN machines m ON a.machine_id = m.id"
            province_where = f"AND m.province IN ({placeholders})"
            province_params = allowed

        query_ids = f"""
            SELECT a.id FROM app_alerts a
            {province_join}
            WHERE 1=1 {province_where}
        """
        pending_alerts = conn.execute(query_ids, province_params).fetchall()
        
        for row in pending_alerts:
            aid = row['id']
            exists = conn.execute("SELECT 1 FROM alert_status WHERE alert_id=? AND username=?", (aid, current_user)).fetchone()
            if exists:
                conn.execute("UPDATE alert_status SET is_cleared=1 WHERE alert_id=? AND username=?", (aid, current_user))
            else:
                conn.execute("INSERT INTO alert_status (alert_id, username, is_read, is_cleared) VALUES (?, ?, 1, 1)", (aid, current_user))

        conn.commit()
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()

@app.route('/api/status', methods=['GET'])
def get_status():
    conn = get_db_connection()
    user_role = request.headers.get('X-User-Role', 'user')
    user_groups_str = request.headers.get('X-User-Groups', '[]')
    try:
        user_groups = json.loads(user_groups_str)
    except:
        user_groups = []

    machines = conn.execute("SELECT * FROM machines").fetchall()
    filtered_machines = []
    
    if user_role == 'admin':
        filtered_machines = machines
    else:
        allowed_provinces = get_allowed_provinces(conn, user_groups)
        
        for m in machines:
            if m['province'] in allowed_provinces:
                filtered_machines.append(m)
    
    result = []
    for m in filtered_machines:
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

@app.route('/add', methods=['POST'])
@app.route('/api/add', methods=['POST'])
def add_machine():
    d = request.json
    if not d.get('id') or not d.get('host'):
        return jsonify({"error": "ID and Host required"}), 400

    m_id = str(d['id']).strip()
    host = str(d['host']).strip()

    if not is_valid_host_or_ip(host):
        return jsonify({"error": "Format Host atau IP Address tidak valid. Harap gunakan IP (misal: 192.168.1.1) atau Domain (misal: example.com)."}), 400

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
        
        use_snmp = 0 
        
        n_down = int(d.get('notify_down', 1))
        n_traf = int(d.get('notify_traffic', 1))
        n_email = int(d.get('notify_email', 0))

        conn.execute('''INSERT INTO machines 
            (id, host, type, icon, use_snmp, lat, lng, notify_down, notify_traffic, notify_email, online, city, province) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)''', 
            (m_id, host, m_type, icon, use_snmp, lat, lng, n_down, n_traf, n_email, city, province))
        
        conn.commit()
        
        threading.Thread(target=probe_snmp, args=(m_id, host), daemon=True).start()

        return jsonify({"message": f"Node Added. Detecting SNMP..."})
        
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

    if not is_valid_host_or_ip(host):
        return jsonify({"error": "Format Host atau IP Address tidak valid."}), 400
    
    conn = get_db_connection()
    old_data = conn.execute("SELECT host, use_snmp FROM machines WHERE id=?", (m_id,)).fetchone()
    conn.close()
    
    should_reprobe = False
    use_snmp = int(old_data['use_snmp']) if old_data else 0
    
    if old_data and old_data['host'] != host:
        # IP Berubah, reset SNMP status dan probe ulang
        use_snmp = 0 
        should_reprobe = True

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
            (host, d['type'], d.get('icon'), use_snmp, lat, lng,
             int(d.get('notify_down', 1)), int(d.get('notify_traffic', 1)), int(d.get('notify_email', 0)),
             city, province,
             m_id))
        conn.commit()
        
        if should_reprobe:
            sync_prometheus_targets() 
            threading.Thread(target=probe_snmp, args=(m_id, host), daemon=True).start()
        elif use_snmp == 1:
            sync_prometheus_targets()
        
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
        
        sync_prometheus_targets()
        
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
    init_db()

    threading.Thread(target=monitor_loop, daemon=True).start()
    threading.Thread(target=init_hq_location, daemon=True).start()
    try:
        sync_prometheus_targets()
    except:
        pass
    app.run(host=Config.FLASK_HOST, port=Config.FLASK_PORT)
