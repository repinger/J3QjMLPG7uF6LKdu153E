# manager/actions.py

from integrations import authentik, stalwart
from config import Config
from utils import generate_authentik_key
import re

def ensure_url(url):
    if not url: return ""
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        return f"https://{url}"
    return url

def create_full_user_action(username, name, email, password, group_pk=None):
    # 1. Create User di Authentik
    auth_res = authentik.create_user(username, name, email, group_pk)
    
    if auth_res.status_code not in [200, 201]:
        return False, auth_res, None
        
    user_pk = auth_res.json().get('pk')
    
    # 2. Set Password di Authentik
    if user_pk: 
        pass_res = authentik.set_password(user_pk, password)
        
        # [FIX] Authentik bisa return 204 (No Content) jika sukses.
        # Jadi kita harus anggap 200 DAN 204 sebagai sukses.
        if pass_res.status_code not in [200, 204]:
            # ROLLBACK: Hapus user jika password gagal (misal complexity error)
            authentik.delete_user(user_pk)
            return False, pass_res, None
    else:
        # Safety fallback
        return False, auth_res, None
    
    # 3. Create Mailbox di Stalwart
    stal_res = stalwart.create_mailbox(username, name, password, email)
    
    return True, auth_res, stal_res

def create_oidc_app_action(name, redirect_uris_raw, launch_url, client_type='confidential', flow_mode='implicit'):
    # 1. Generate Slug
    slug = re.sub(r'[^a-z0-9]', ' ', name.lower())
    slug = re.sub(r'\s+', ' ', slug).strip().replace(' ', '-')
    if not slug: slug = generate_authentik_key(8)
    
    # 2. Prepare Redirect URIs
    redirect_uris = []
    if redirect_uris_raw:
        raw_list = re.split(r'[\n,]', redirect_uris_raw)
        for uri in raw_list:
            u = uri.strip()
            if u:
                redirect_uris.append({"url": u, "matching_mode": "strict"})

    # 3. Get Dependencies
    flow_slug = 'default-provider-authorization-implicit-consent' if flow_mode == 'implicit' else 'default-provider-authorization-explicit-consent'
    
    auth_flow_pk = authentik.get_flow_pk(flow_slug)
    if not auth_flow_pk:
        auth_flow_pk = authentik.get_flow_pk('default-provider-authorization-explicit-consent')
        
    inv_flow_pk = authentik.get_flow_pk('default-provider-invalidation-flow')
    property_mappings = authentik.get_property_mappings()

    if not auth_flow_pk:
        return False, "Error: Default Authorization Flow not found in Authentik."

    # 4. Generate Credentials
    new_client_id = generate_authentik_key(40)
    new_client_secret = generate_authentik_key(128)

    # 5. Create Provider
    prov_res = authentik.create_provider(
        name=name,
        flow_pk=auth_flow_pk,
        inv_flow_pk=inv_flow_pk,
        client_type=client_type,
        redirect_uris=redirect_uris,
        client_id=new_client_id,
        client_secret=new_client_secret,
        mappings=property_mappings
    )

    if prov_res.status_code != 201:
        return False, f"Provider Creation Failed: {prov_res.text}"
    
    provider_pk = prov_res.json()['pk']

    # 6. Create Application
    app_res = authentik.create_application(name, slug, provider_pk, launch_url)
    
    if app_res.status_code == 201:
        return True, "Application created successfully."
    else:
        # Rollback
        authentik.delete_provider(provider_pk)
        return False, f"App Creation Failed: {app_res.text}"
