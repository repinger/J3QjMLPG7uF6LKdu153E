# manager/actions.py

from integrations import authentik
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
    auth_res = authentik.create_user(username, name, email, group_pk)
    if auth_res.status_code not in [200, 201]:
        return False, auth_res, None
    user_pk = auth_res.json().get('pk')
    if user_pk: authentik.set_password(user_pk, password)
    stal_res = stalwart.create_mailbox(username, name, password, email)
    return True, auth_res, stal_res

def create_oidc_app_action(name, redirect_uris_raw, launch_url, client_type='confidential', flow_mode='implicit'):
    # 1. Generate Slug (URL friendly name)
    slug = name.lower().strip().replace(' ', '-').replace('/', '-')
    slug = re.sub(r'[^a-z0-9\-]', '', slug)
    
    # 2. Prepare Redirect URIs
    redirect_uris = []
    if redirect_uris_raw:
        # Split by newline or comma, and strip whitespace
        raw_list = re.split(r'[\n,]', redirect_uris_raw)
        for uri in raw_list:
            u = uri.strip()
            if u:
                redirect_uris.append({"url": u, "matching_mode": "strict"})

    # 3. Get Dependencies (Flows & Mappings)
    # Gunakan flow default atau flow spesifik
    flow_slug = 'default-provider-authorization-implicit-consent' if flow_mode == 'implicit' else 'default-provider-authorization-explicit-consent'
    
    auth_flow_pk = authentik.get_flow_pk(flow_slug)
    # Fallback jika flow implicit tidak ketemu, pakai default explicit
    if not auth_flow_pk:
        auth_flow_pk = authentik.get_flow_pk('default-provider-authorization-explicit-consent')
        
    inv_flow_pk = authentik.get_flow_pk('default-provider-invalidation-flow')
    property_mappings = authentik.get_property_mappings()

    if not auth_flow_pk:
        return False, "Error: Default Authorization Flow not found in Authentik."

    # 4. [BARU] GENERATE CREDENTIALS SEPERTI AUTHENTIK
    # Authentik standard: Client ID (40 chars), Secret (128 chars)
    new_client_id = generate_authentik_key(40)
    new_client_secret = generate_authentik_key(128)

    # 5. Create Provider
    # Perhatikan kita mengirim new_client_id, bukan slug
    prov_res = authentik.create_provider(
        name=name,
        flow_pk=auth_flow_pk,
        inv_flow_pk=inv_flow_pk,
        client_type=client_type,
        redirect_uris=redirect_uris,
        client_id=new_client_id,      # Parameter baru
        client_secret=new_client_secret, # Parameter baru
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
        # Rollback (hapus provider jika app gagal)
        authentik.delete_provider(provider_pk)
        return False, f"App Creation Failed: {app_res.text}"
