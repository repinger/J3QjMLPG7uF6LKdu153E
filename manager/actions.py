# manager/actions.py

import uuid
from integrations import authentik, stalwart

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

def create_oidc_app_action(name, redirect_uris_str, launch_url, client_type, flow_mode='implicit'):
    slug = name.lower().replace(" ", "-")
    
    if not redirect_uris_str: redirect_uris_str = ""
    raw_uris = [ensure_url(u) for u in redirect_uris_str.replace('\r\n', ',').replace('\n', ',').split(',') if u.strip()]
    redirect_uris_payload = [{"url": uri, "matching_mode": "strict"} for uri in raw_uris]

    if flow_mode == 'explicit':
        auth_flow_slug = "default-provider-authorization-explicit-consent"
    else:
        auth_flow_slug = "default-provider-authorization-implicit-consent"
        
    final_auth_flow = authentik.get_flow_pk(auth_flow_slug)
    inv_flow = authentik.get_flow_pk("default-provider-invalidation-flow")
    
    if not final_auth_flow: return False, f"Error: Flow '{auth_flow_slug}' not found."
    if not inv_flow: return False, "Error: Default Invalidation Flow not found."

    mappings = authentik.get_property_mappings()
    secret = str(uuid.uuid4())[:40]
    
    prov_res = authentik.create_provider(name, final_auth_flow, inv_flow, client_type, redirect_uris_payload, slug, secret, mappings)
    
    if prov_res.status_code == 403: return False, "Permission Denied: Need 'authentik Admins'."
    if prov_res.status_code != 201: return False, f"Provider Error: {prov_res.text}"
        
    provider_pk = prov_res.json()['pk']

    final_launch_url = ensure_url(launch_url)
    if not final_launch_url and raw_uris:
        final_launch_url = raw_uris[0]
        
    app_res = authentik.create_application(name, slug, provider_pk, final_launch_url)
    
    if app_res.status_code != 201:
        authentik.delete_provider(provider_pk)
        return False, f"App Error: {app_res.text}"
    
    return True, "Application created successfully."
