import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Config

# Cache sederhana untuk Cooldown di memori
cooldown_cache = {}

def check_cooldown(machine_id, alert_type):
    key = f"{machine_id}_{alert_type}"
    last_time = cooldown_cache.get(key, 0)
    now = time.time()
    return (now - last_time) > Config.ALERT_COOLDOWN

def update_cooldown(machine_id, alert_type):
    key = f"{machine_id}_{alert_type}"
    cooldown_cache[key] = time.time()

def send_email_alert(machine_id, alert_type, message):
    if not Config.SMTP_SERVER or not Config.ALERT_RECIPIENT:
        print("[!] Email Config Missing")
        return False

    if not check_cooldown(machine_id, alert_type):
        return False

    # Siapkan Email
    msg = MIMEMultipart()
    msg['From'] = Config.SMTP_EMAIL or "monitorr@localhost"
    msg['To'] = Config.ALERT_RECIPIENT
    msg['Subject'] = f"[Monitorr] Alert: {machine_id} is {alert_type.upper()}"

    body = f"""
    Sistem Monitoring mendeteksi masalah:
    
    Node ID   : {machine_id}
    Status    : {alert_type.upper()}
    Pesan     : {message}
    Waktu     : {time.ctime()}
    
    Cek dashboard untuk detail.
    """
    msg.attach(MIMEText(body, 'plain'))

    server = None
    try:
        # Inisialisasi Koneksi (Tanpa Timeout di Constructor untuk stabilitas)
        server = smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT, timeout=10)
        server.ehlo()

        # [SKIP TLS] Sesuai konfigurasi yang bekerja
        # server.starttls()
        
        # Login dengan Fallback (Graceful)
        if Config.SMTP_EMAIL and Config.SMTP_PASSWORD:
            try:
                server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
            except smtplib.SMTPNotSupportedError:
                pass # Server tidak support auth, lanjut kirim (relay)
            except Exception as e:
                print(f"[!] SMTP Login Failed: {e}")
                return False

        # Kirim
        server.sendmail(msg['From'], msg['To'], msg.as_string())
        print(f"[*] Email sent to {Config.ALERT_RECIPIENT} ({machine_id}: {alert_type})")
        
        update_cooldown(machine_id, alert_type)
        return True

    except Exception as e:
        print(f"[!] Email Send Error: {e}")
        return False
        
    finally:
        if server:
            try:
                server.quit()
            except:
                pass
