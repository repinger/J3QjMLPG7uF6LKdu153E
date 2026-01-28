from ldap3 import Server, Connection, ALL, SUBTREE
from config import Config

def authenticate_ldap(username_or_email, password):
    """
    Autentikasi Khusus LLDAP (Light LDAP).
    Flow: Cari User -> Bind Password -> Cari Grup (groupOfUniqueNames).
    """
    # Bypass Mode Dev
    if not Config.LDAP_HOST:
        if username_or_email == "admin" and password == "admin":
            return {"username": "admin", "role": "admin", "email": "admin@local"}
        if username_or_email == "user" and password == "user":
            return {"username": "user", "role": "user", "email": "user@local"}
        return None

    try:
        # 1. KONEKSI PENCARIAN
        server = Server(Config.LDAP_HOST, get_info=ALL)
        conn = Connection(server, user=Config.LDAP_BIND_USER, password=Config.LDAP_BIND_PASSWORD, auto_bind=True)

        # 2. CARI USER
        # LLDAP standar biasanya menggunakan uid atau mail
        search_filter = f"(|(mail={username_or_email})(uid={username_or_email})(cn={username_or_email}))"
        
        conn.search(
            search_base=Config.LDAP_BASE_DN,
            search_filter=search_filter,
            attributes=['cn', 'uid', 'mail'],
            search_scope=SUBTREE
        )

        if not conn.entries:
            print(f"[LLDAP] User not found: {username_or_email}")
            return None

        user_entry = conn.entries[0]
        user_dn = user_entry.entry_dn
        
        # Ambil UID/CN dan Email
        clean_username = str(user_entry.uid) if 'uid' in user_entry else str(user_entry.cn)
        user_email = str(user_entry.mail) if 'mail' in user_entry else ""

        # 3. VERIFIKASI PASSWORD (BIND)
        user_conn = Connection(server, user=user_dn, password=password)
        if not user_conn.bind():
            print(f"[LLDAP] Password failed for: {clean_username}")
            return None
        
        user_conn.unbind()
        
        # 4. CARI GRUP (KHUSUS LLDAP)
        # LLDAP menggunakan 'groupOfUniqueNames' dimana 'uniqueMember' berisi DN user.
        # Kita hapus 'posixGroup' yang menyebabkan error.
        
        group_filter = f"(&(objectClass=groupOfUniqueNames)(uniqueMember={user_dn}))"
        
        conn.search(
            search_base=Config.LDAP_BASE_DN,
            search_filter=group_filter,
            attributes=['cn'], # Ambil nama grup
            search_scope=SUBTREE
        )
        
        # Kumpulkan nama grup
        user_groups = []
        for entry in conn.entries:
            if 'cn' in entry:
                user_groups.append(str(entry.cn).lower())
        
        conn.unbind()
        
        # 5. TENTUKAN ROLE
        role = "user"
        target_admin_group = Config.LDAP_ADMIN_GROUP.lower()
        
        # Cek apakah nama grup dari config ada di dalam list grup user
        if any(target_admin_group in g for g in user_groups):
            role = "admin"
            
        # Fallback hardcode (opsional)
        if clean_username == "admin":
            role = "admin"

        print(f"[LLDAP] Success: {clean_username} | Groups: {user_groups} | Role: {role}")
        
        return {
            "username": clean_username,
            "role": role,
            "email": user_email
        }

    except Exception as e:
        print(f"[LLDAP] Error: {e}")
        return None
