import requests
from config import Config

def authenticate_oidc(authorization_code):
    """
    Menukar Authorization Code dengan Access Token, lalu mengambil User Info.
    Melakukan mapping Group Authentik ke Role aplikasi.
    """
    try:
        # 1. Exchange Code for Token
        token_data = {
            'grant_type': 'authorization_code',
            'code': authorization_code,
            'client_id': Config.OIDC_CLIENT_ID,
            'client_secret': Config.OIDC_CLIENT_SECRET,
            'redirect_uri': Config.OIDC_REDIRECT_URI
        }
        
        # Request ke Token Endpoint
        token_res = requests.post(Config.OIDC_TOKEN_URL, data=token_data)
        
        if token_res.status_code != 200:
            print(f"[OIDC] Token Exchange Failed: {token_res.text}")
            return None
            
        access_token = token_res.json().get('access_token')
        
        # 2. Get User Info
        headers = {'Authorization': f'Bearer {access_token}'}
        user_res = requests.get(Config.OIDC_USERINFO_URL, headers=headers)
        
        if user_res.status_code != 200:
            print(f"[OIDC] User Info Failed: {user_res.text}")
            return None
            
        user_data = user_res.json()
        
        # 3. Role Mapping & Extraction
        # Pastikan Scope di Authentik menyertakan 'groups'
        # Struktur user_data biasanya: {'sub': '...', 'preferred_username': '...', 'groups': ['Admins', 'Users']}
        
        username = user_data.get('preferred_username', user_data.get('nickname', 'unknown'))
        email = user_data.get('email', '')
        groups = user_data.get('groups', [])
        
        role = "user"
        # Cek apakah grup admin yang diset di config ada di list grup user
        if Config.OIDC_ADMIN_GROUP in groups:
            role = "admin"
            
        print(f"[OIDC] Login Success: {username} | Groups: {groups} | Role: {role}")
        
        return {
            "username": username,
            "role": role,
            "email": email,
            "groups": groups
        }

    except Exception as e:
        print(f"[OIDC] Error: {str(e)}")
        return None
