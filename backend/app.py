from flask import Flask, jsonify, request
from config import Config
from database import init_db, get_db_connection
from monitoring import monitor_loop
from ldap_service import authenticate_ldap
import threading
import time
import sqlite3

app = Flask(__name__)

# Init DB & Monitoring thread
init_db()
threading.Thread(target=monitor_loop, daemon=True).start()

# --- AUTH ROUTES ---
@app.route('/login', methods=['POST'])      # Handle stripped URL
@app.route('/api/auth/login', methods=['POST']) # Handle full URL
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user_info = authenticate_ldap(username, password)
    
    if user_info:
        return jsonify({"success": True, "user": user_info})
    else:
        return jsonify({"success": False, "message": "Invalid credentials"}), 401

# --- NOTIFICATION ROUTES ---
@app.route('/alerts', methods=['GET'])
@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    conn = get_db_connection()
    alerts = conn.execute("SELECT * FROM app_alerts ORDER BY id DESC LIMIT 10").fetchall()
    unread = conn.execute("SELECT COUNT(*) FROM app_alerts WHERE is_read = 0").fetchone()[0]
    conn.close()
    return jsonify({
        "alerts": [dict(a) for a in alerts],
        "unread_count": unread
    })

@app.route('/alerts/read', methods=['POST'])
@app.route('/api/alerts/read', methods=['POST'])
def mark_alerts_read():
    conn = get_db_connection()
    conn.execute("UPDATE app_alerts SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# --- MACHINE ROUTES (STATUS & HISTORY) ---
@app.route('/status', methods=['GET'])
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

@app.route('/history', methods=['POST'])
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

# --- CRUD ROUTES (ADD/EDIT/REMOVE) ---
# [FIXED] Tambahkan route '/add' (tanpa api) untuk menangani request dari gateway
@app.route('/add', methods=['POST'])
@app.route('/api/add', methods=['POST'])
def add_machine():
    d = request.json
    
    # Validasi input
    if not d.get('id') or not d.get('host'):
        return jsonify({"error": "ID and Host required"}), 400

    conn = get_db_connection()
    try:
        # Konversi data
        m_id = str(d['id']).strip()
        host = str(d['host']).strip()
        m_type = str(d.get('type', 'Device'))
        icon = str(d.get('icon', 'fa-server'))
        use_snmp = int(d.get('use_snmp', 0))
        lat = float(d.get('lat', 0))
        lng = float(d.get('lng', 0))
        n_down = int(d.get('notify_down', 1))
        n_traf = int(d.get('notify_traffic', 1))
        n_email = int(d.get('notify_email', 0))

        conn.execute('''INSERT INTO machines 
            (id, host, type, icon, use_snmp, lat, lng, notify_down, notify_traffic, notify_email, online) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)''', 
            (m_id, host, m_type, icon, use_snmp, lat, lng, n_down, n_traf, n_email))
        
        conn.commit()
        return jsonify({"message": "Node Added"})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Node ID already exists"}), 400
    except ValueError:
        return jsonify({"error": "Invalid data format"}), 400
    except Exception as e:
        print(f"[!] Add Error: {e}")
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()

@app.route('/edit', methods=['POST'])
@app.route('/api/edit', methods=['POST'])
def edit_machine():
    d = request.json
    conn = get_db_connection()
    try:
        conn.execute('''UPDATE machines SET 
            host=?, type=?, icon=?, use_snmp=?, lat=?, lng=?,
            notify_down=?, notify_traffic=?, notify_email=?
            WHERE id=?''', 
            (d['host'], d['type'], d.get('icon'), int(d.get('use_snmp',0)), d['lat'], d['lng'],
             int(d.get('notify_down', 1)), int(d.get('notify_traffic', 1)), int(d.get('notify_email', 0)),
             d['id']))
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
    conn.execute("DELETE FROM machines WHERE id=?", (d['id'],))
    conn.commit()
    conn.close()
    return jsonify({"message": "Node Removed"})

# --- USER ROUTES ---
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
