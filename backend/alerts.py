import smtplib
import threading
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from config import Config
from database import get_db_connection

# Cache untuk cooldown notifikasi: {'machine_id': {'down': timestamp, 'traffic': timestamp}}
last_alert_times = {}

def create_app_alert(machine_id, alert_type, message):
    """Simpan notifikasi ke database agar muncul di lonceng dashboard"""
    try:
        conn = get_db_connection()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute("INSERT INTO app_alerts (machine_id, type, message, time) VALUES (?, ?, ?, ?)",
                     (machine_id, alert_type, message, timestamp))
        conn.commit()
        conn.close()
        print(f"[!] Alert DB Saved: {message}")
    except Exception as e:
        print(f"[!] Alert DB Error: {e}")

def send_email(subject, body):
    """Kirim email via SMTP"""
    if not Config.SMTP_SERVER or not Config.ALERT_RECIPIENT:
        return

    try:
        msg = MIMEMultipart()
        msg['From'] = Config.SMTP_EMAIL
        msg['To'] = Config.ALERT_RECIPIENT
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT)
        server.ehlo()
        if Config.SMTP_PASSWORD:
            server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
        
        server.send_message(msg)
        server.quit()
        print(f"[✓] Email Sent: {subject}")
    except Exception as e:
        print(f"[!] Email Failed: {e}")

def process_alert(machine, alert_type, current_val=0):
    mid = machine['id']
    host = machine['host']
    
    # Init cooldown record
    if mid not in last_alert_times:
        last_alert_times[mid] = {'down': 0, 'traffic': 0}
    
    now = time.time()
    last_sent = last_alert_times[mid].get(alert_type, 0)

    # Cek Cooldown (Misal: Config.ALERT_COOLDOWN detik)
    if (now - last_sent) > Config.ALERT_COOLDOWN:
        last_alert_times[mid][alert_type] = now
        
        subject = ""
        message = ""
        
        if alert_type == 'down':
            subject = f"[MONITORR] ALERT: Node {mid} DOWN"
            message = f"CRITICAL: Node {mid} ({host}) tidak dapat dihubungi (Offline)."
        elif alert_type == 'traffic':
            gbps = round(current_val / 1000000, 2)
            subject = f"[MONITORR] WARN: High Traffic on {mid}"
            message = f"WARNING: Bandwidth tinggi terdeteksi pada {mid} ({host}). Current: {gbps} Mbps."

        # 1. Selalu simpan ke Notifikasi Aplikasi (Lonceng)
        threading.Thread(target=create_app_alert, args=(mid, alert_type, message)).start()

        # 2. Kirim Email HANYA jika dicentang user
        if machine['notify_email']:
            threading.Thread(target=send_email, args=(subject, message)).start()

def check_alerts(machine, is_online, rx, tx):
    """Fungsi utama yang dipanggil monitoring loop"""
    
    # 1. Alert Down
    if not is_online and machine['notify_down']:
        process_alert(machine, 'down')
        
    # 2. Alert Traffic (Hanya jika online dan pakai SNMP)
    if is_online and machine['use_snmp'] and machine['notify_traffic']:
        limit = Config.BANDWIDTH_THRESHOLD
        # Cek jika RX atau TX melebihi limit
        if rx > limit or tx > limit:
            val = max(rx, tx)
            process_alert(machine, 'traffic', val)
