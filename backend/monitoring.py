import time
import subprocess
import platform
import requests
from datetime import datetime, timedelta
from config import Config
from database import get_db_connection
from alerts import send_email_alert, check_cooldown, update_cooldown

def get_network_metrics():
    """Mengambil data bandwidth dari Prometheus"""
    if not Config.PROMETHEUS_URL:
        return {}

    metrics = {}
    try:
        # Query RX
        rx_query = 'rate(node_network_receive_bytes_total[1m]) * 8' 
        rx_res = requests.get(f"{Config.PROMETHEUS_URL}/api/v1/query", params={'query': rx_query}, timeout=2)
        if rx_res.status_code == 200:
            for item in rx_res.json()['data']['result']:
                instance = item['metric'].get('instance', '').split(':')[0]
                val = float(item['value'][1])
                if instance not in metrics: metrics[instance] = {'rx': 0, 'tx': 0}
                metrics[instance]['rx'] += val / 1000 # Convert to Kbps

        # Query TX
        tx_query = 'rate(node_network_transmit_bytes_total[1m]) * 8'
        tx_res = requests.get(f"{Config.PROMETHEUS_URL}/api/v1/query", params={'query': tx_query}, timeout=2)
        if tx_res.status_code == 200:
            for item in tx_res.json()['data']['result']:
                instance = item['metric'].get('instance', '').split(':')[0]
                val = float(item['value'][1])
                if instance not in metrics: metrics[instance] = {'rx': 0, 'tx': 0}
                metrics[instance]['tx'] += val / 1000 # Convert to Kbps

    except Exception:
        pass # Silent error untuk metrics
    
    return metrics

def update_machines_status():
    conn = get_db_connection()
    machines = conn.execute("SELECT * FROM machines").fetchall()
    prom_metrics = get_network_metrics()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for m in machines:
        mid, host = m['id'], m['host']
        use_snmp = m['use_snmp']
        prev_online_status = m['online']
        
        # 1. PING CHECK
        is_online = False
        latency = 0
        try:
            param = '-n' if platform.system().lower() == 'windows' else '-c'
            cmd = ['ping', param, '1', '-w', '1000', host]
            start = time.time()
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if res.returncode == 0:
                is_online = True
                latency = round((time.time() - start) * 1000, 2)
        except Exception:
            is_online = False

        # 2. TRAFFIC CHECK
        rx, tx = 0, 0
        if is_online and use_snmp:
            stats = prom_metrics.get(host, {})
            rx = round(stats.get('rx', 0), 2)
            tx = round(stats.get('tx', 0), 2)

        # 3. UPDATE DB
        if is_online:
            conn.execute("UPDATE machines SET online=1, latency_ms=?, rx_rate=?, tx_rate=?, last_seen=? WHERE id=?", 
                         (latency, rx, tx, timestamp, mid))
        else:
            conn.execute("UPDATE machines SET online=0, latency_ms=0, rx_rate=0, tx_rate=0, last_seen=? WHERE id=?", 
                         (timestamp, mid))

        conn.execute("INSERT INTO history (machine_id, status, time, latency, rx, tx) VALUES (?, ?, ?, ?, ?, ?)", 
                     (mid, "ONLINE" if is_online else "OFFLINE", timestamp, latency, rx, tx))
        
        # 4. ALERTS
        
        # A. Node Down (State Change - Tidak butuh cooldown karena trigger by change)
        if prev_online_status == 1 and not is_online:
            msg = f"Node unreachable. Ping Timeout."
            if m['notify_down']:
                conn.execute("INSERT INTO app_alerts (machine_id, type, message, time) VALUES (?, ?, ?, ?)", 
                             (mid, 'down', msg, timestamp))
                
            if m['notify_down'] and m['notify_email']:
                send_email_alert(mid, 'down', msg)

        # B. High Traffic (Continuous Value - BUTUH Cooldown)
        threshold_kbps = Config.BANDWIDTH_THRESHOLD / 1000 
        if is_online and use_snmp and m['notify_traffic']:
            if rx > threshold_kbps or tx > threshold_kbps:
                # [FIX] Cek Cooldown untuk Dashboard Alert
                # Kita gunakan key khusus 'traffic_db' agar tidak bentrok dengan key email
                if check_cooldown(mid, 'traffic_db'):
                    msg = f"Traffic Spike: RX {rx} Kbps / TX {tx} Kbps"
                    
                    # 1. Masukkan notifikasi ke DB
                    conn.execute("INSERT INTO app_alerts (machine_id, type, message, time) VALUES (?, ?, ?, ?)", 
                                 (mid, 'traffic', msg, timestamp))
                    
                    # 2. Update cooldown DB agar tidak insert lagi dalam waktu dekat
                    update_cooldown(mid, 'traffic_db')
                    
                    # 3. Kirim Email (send_email_alert punya cooldown sendiri dengan key 'traffic')
                    if m['notify_email']:
                        send_email_alert(mid, 'traffic', msg)

    # Cleanup Old History
    cutoff = (datetime.now() - timedelta(days=Config.RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM history WHERE time < ?", (cutoff,))
    
    conn.commit()
    conn.close()

def monitor_loop():
    print("[*] Monitoring Service Started")
    print(f"[*] Threshold: {Config.BANDWIDTH_THRESHOLD} bps | Recipient: {Config.ALERT_RECIPIENT}")
    
    while True:
        try:
            update_machines_status()
        except Exception as e:
            print(f"[!] Monitor Loop Error: {e}")
        time.sleep(Config.PING_INTERVAL)
