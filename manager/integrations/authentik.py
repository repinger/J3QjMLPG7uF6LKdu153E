# manager/integrations/authentik.py

import requests
from config import Config

def get_headers():
    return {
        "Authorization": f"Bearer {Config.AUTHENTIK_TOKEN}",
        "Content-Type": "application/json"
    }

# --- GROUPS CRUD ---
def get_groups():
    try:
        res = requests.get(f"{Config.AUTHENTIK_API_URL}/core/groups/", headers=get_headers())
        if res.status_code == 200:
            return [{'pk': g['pk'], 'name': g['name'], 'is_superuser': g.get('is_superuser', False)} for g in res.json().get('results', [])]
    except: pass
    return []

def create_group(name):
    url = f"{Config.AUTHENTIK_API_URL}/core/groups/"
    return requests.post(url, json={"name": name, "is_superuser": False}, headers=get_headers())

def update_group(pk, name):
    url = f"{Config.AUTHENTIK_API_URL}/core/groups/{pk}/"
    return requests.patch(url, json={"name": name}, headers=get_headers())

def delete_group(pk):
    return requests.delete(f"{Config.AUTHENTIK_API_URL}/core/groups/{pk}/", headers=get_headers())

# --- USERS CRUD ---
def get_users(admin_group_pk=None):
    try:
        res = requests.get(f"{Config.AUTHENTIK_API_URL}/core/users/?page_size=100", headers=get_headers())
        if res.status_code == 200:
            all_users = res.json().get('results', [])
            for u in all_users:
                username = u.get('username', '')
                u['is_protected'] = False
                if username == 'akadmin' or username.startswith('ak-outpost-'):
                    u['is_protected'] = True
                    u['role_label'] = 'System'
                elif admin_group_pk and admin_group_pk in u.get('groups', []):
                    u['is_protected'] = True
                    u['role_label'] = 'Admin'
            return all_users
    except Exception as e:
        print(f"[!] Get Users Error: {e}")
    return []

def create_user(username, name, email, group_pk=None):
    url = f"{Config.AUTHENTIK_API_URL}/core/users/"
    payload = {"username": username, "name": name, "email": email, "is_active": True}
    if group_pk: payload["groups"] = [group_pk]
    return requests.post(url, json=payload, headers=get_headers())

def set_password(user_pk, password):
    url = f"{Config.AUTHENTIK_API_URL}/core/users/{user_pk}/set_password/"
    return requests.post(url, json={"password": password}, headers=get_headers())

def update_user(pk, data):
    url = f"{Config.AUTHENTIK_API_URL}/core/users/{pk}/"
    payload = {
        "name": data.get("name"),
        "email": data.get("email"),
        "is_active": data.get("is_active") == "on",
        "groups": data.getlist("groups")
    }
    return requests.patch(url, json=payload, headers=get_headers())

def delete_user(pk):
    return requests.delete(f"{Config.AUTHENTIK_API_URL}/core/users/{pk}/", headers=get_headers())

# --- PROVIDERS ---
def get_oauth_providers():
    providers = []
    url = f"{Config.AUTHENTIK_API_URL}/providers/oauth2/?page_size=100"
    while url:
        try:
            res = requests.get(url, headers=get_headers())
            if res.status_code == 200:
                data = res.json()
                providers.extend(data.get('results', []))
                url = data.get('pagination', {}).get('next')
            else: break
        except: break
    return providers

def update_provider(pk, name, redirect_uris=None):
    url = f"{Config.AUTHENTIK_API_URL}/providers/oauth2/{pk}/"
    payload = {"name": name}
    if redirect_uris is not None:
        payload["redirect_uris"] = [{"url": u.strip(), "matching_mode": "strict"} for u in redirect_uris if u.strip()]
    return requests.patch(url, json=payload, headers=get_headers())

def delete_provider(pk):
    url = f"{Config.AUTHENTIK_API_URL}/providers/oauth2/{pk}/"
    requests.delete(url, headers=get_headers())

def create_provider(name, flow_pk, inv_flow_pk, client_type, redirect_uris, slug, secret, mappings):
    url = f"{Config.AUTHENTIK_API_URL}/providers/oauth2/"
    payload = {
        "name": name,
        "authorization_flow": flow_pk,
        "invalidation_flow": inv_flow_pk,
        "client_type": client_type,
        "redirect_uris": redirect_uris,
        "client_id": slug,
        "client_secret": secret,
        "property_mappings": mappings,
        "sub_mode": "hashed_user_id"
    }
    return requests.post(url, json=payload, headers=get_headers())

# --- APPLICATIONS ---
def get_apps():
    apps = []
    url = f"{Config.AUTHENTIK_API_URL}/core/applications/?page_size=100"
    while url:
        try:
            res = requests.get(url, headers=get_headers())
            if res.status_code == 200:
                data = res.json()
                apps.extend(data.get('results', []))
                url = data.get('pagination', {}).get('next')
            else: break
        except: break
    return apps

def create_application(name, slug, provider_pk, launch_url):
    url = f"{Config.AUTHENTIK_API_URL}/core/applications/"
    payload = {
        "name": name,
        "slug": slug,
        "provider": provider_pk,
        "meta_launch_url": launch_url
    }
    return requests.post(url, json=payload, headers=get_headers())

def update_application(pk, name, launch_url, redirect_uris=None):
    # 1. Cari Slug & Provider ID
    target_slug = None
    provider_pk = None
    all_apps = get_apps()
    for app in all_apps:
        if str(app['pk']) == str(pk):
            target_slug = app['slug']
            provider_pk = app.get('provider')
            break
            
    if not target_slug: return requests.Response() # Fail safe

    # 2. Update App
    url_app = f"{Config.AUTHENTIK_API_URL}/core/applications/{target_slug}/"
    payload_app = {"name": name, "meta_launch_url": launch_url}
    res_app = requests.patch(url_app, json=payload_app, headers=get_headers())
    
    # 3. Update Provider
    if res_app.status_code == 200 and provider_pk:
        update_provider(provider_pk, name, redirect_uris)
        
    return res_app

def delete_application(pk):
    target_slug = None
    provider_pk = None
    all_apps = get_apps() 
    for app in all_apps:
        if str(app['pk']) == str(pk):
            target_slug = app.get('slug')
            provider_pk = app.get('provider')
            break
    
    identifier = target_slug if target_slug else pk
    url_app = f"{Config.AUTHENTIK_API_URL}/core/applications/{identifier}/"
    res_app = requests.delete(url_app, headers=get_headers())
    
    if res_app.status_code == 204 and provider_pk:
        delete_provider(provider_pk)
        
    return res_app

# --- OIDC HELPERS ---
def get_flow_pk(slug):
    try:
        res = requests.get(f"{Config.AUTHENTIK_API_URL}/flows/instances/?slug={slug}", headers=get_headers())
        if res.status_code == 200:
            results = res.json().get('results', [])
            if results: return results[0]['pk']
    except: pass
    return None

def get_property_mappings():
    mappings = []
    try:
        mapping_names = ["Proxy default OAuth Mapping", "OIDC-Scope-Profile", "OIDC-Scope-Email", "OIDC-Scope-OpenID"]
        for m_name in mapping_names:
            m_res = requests.get(f"{Config.AUTHENTIK_API_URL}/core/property-mappings/?name={m_name}", headers=get_headers())
            if m_res.status_code == 200 and m_res.json().get('results'):
                mappings.append(m_res.json()['results'][0]['pk'])
    except: pass
    return mappings
