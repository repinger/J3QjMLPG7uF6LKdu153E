import time
import subprocess
import platform
import requests
from datetime import datetime, timedelta
from config import Config
from database import get_db_connection
from alerts import check_alerts  # Import Baru

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

    except Exception as e:
        print(f"[!] Prometheus Error: {e}")
    
    return metrics

def update_machines_status():
    conn = get_db_connection()
    # Select * agar kolom notify_xxx terambil
    machines = conn.execute("SELECT * FROM machines").fetchall()
    prom_metrics = get_network_metrics()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for m in machines:
        mid, host = m['id'], m['host']
        use_snmp = m['use_snmp']
        
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

        status_str = "ONLINE" if is_online else "OFFLINE"
        conn.execute("INSERT INTO history (machine_id, status, time, latency, rx, tx) VALUES (?, ?, ?, ?, ?, ?)", 
                     (mid, status_str, timestamp, latency, rx, tx))
        
        # 4. CEK NOTIFIKASI
        check_alerts(m, is_online, rx, tx)

    # CLEANUP HISTORY LAMA
    cutoff = (datetime.now() - timedelta(days=Config.RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M:%S")
    conn.execute("DELETE FROM history WHERE time < ?", (cutoff,))
    conn.commit()
    conn.close()

def monitor_loop():
    print("[*] Monitoring loop started...")
    while True:
        try:
            update_machines_status()
        except Exception as e:
            print(f"[!] Error in monitoring loop: {e}")
        time.sleep(Config.PING_INTERVAL)
