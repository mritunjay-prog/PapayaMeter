import requests
import configparser
import os
import json
import socket
import random
from datetime import datetime

try:
    from core.get_jwt_token import get_token
except ImportError:
    from get_jwt_token import get_token

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.properties')

def get_config():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)
    return config

def get_lat_lon():
    """Fetch latitude and longitude from ipapi.co."""
    try:
        response = requests.get('https://ipapi.co/json/', timeout=5)
        if response.status_code == 200:
            data = response.json()
            return float(data.get('latitude')), float(data.get('longitude'))
    except Exception as e:
        print(f"⚠️ Location detection failed: {e}. Using fallback coordinates.")
    
    config = get_config()
    return config.getfloat('location', 'latitude'), config.getfloat('location', 'longitude')

# --- Logic from DeviceProvision1.py ---

def get_asset_profile_id_by_name(url, token, profile_name):
    headers = {'X-Authorization': f'Bearer {token}'}
    r = requests.get(f"{url}/api/assetProfiles", headers=headers, params={"pageSize": 100, "page": 0})
    r.raise_for_status()
    for profile in r.json().get("data", []):
        if profile["name"] == profile_name:
            return profile["id"]["id"]
    return None

def get_device_profile_id_by_name(url, token, profile_name):
    headers = {'X-Authorization': f'Bearer {token}'}
    r = requests.get(f"{url}/api/deviceProfiles", headers=headers, params={"pageSize": 100, "page": 0})
    r.raise_for_status()
    for profile in r.json().get("data", []):
        if profile["name"] == profile_name:
            return profile["id"]["id"]
    return None

def list_all_assets(url, token):
    headers = {'X-Authorization': f'Bearer {token}'}
    r = requests.get(f"{url}/api/tenant/assets", headers=headers, params={"pageSize": 1000, "page": 0})
    r.raise_for_status()
    return r.json().get("data", [])

def find_asset_in_list(assets, name):
    for asset in assets:
        if asset['name'].upper() == name.upper():
            return asset
    return None

def create_asset(url, token, name, profile_id, type_name):
    headers = {'X-Authorization': f'Bearer {token}', "Content-Type": "application/json"}
    payload = {
        "name": name,
        "type": type_name,
        "assetProfileId": {"entityType": "ASSET_PROFILE", "id": profile_id}
    }
    r = requests.post(f"{url}/api/asset", headers=headers, json=payload)
    r.raise_for_status()
    return r.json()

def send_asset_attributes(url, token, asset_id, lat, lon):
    headers = {'X-Authorization': f'Bearer {token}', "Content-Type": "application/json"}
    url_attr = f"{url}/api/plugins/telemetry/ASSET/{asset_id}/attributes/SERVER_SCOPE"
    payload = {"latitude": lat, "longitude": lon}
    requests.post(url_attr, headers=headers, json=payload).raise_for_status()

def check_relation_exists(url, token, from_id, to_id, from_type="ASSET", to_type="ASSET"):
    headers = {'X-Authorization': f'Bearer {token}'}
    params = {"fromId": from_id, "fromType": from_type, "toId": to_id, "toType": to_type, "relationType": "Contains"}
    r = requests.get(f"{url}/api/relation/info", headers=headers, params=params)
    return r.status_code == 200

def create_relation(url, token, from_id, from_type, to_id, to_type):
    headers = {'X-Authorization': f'Bearer {token}', "Content-Type": "application/json"}
    payload = {
        "from": {"id": from_id, "entityType": from_type},
        "to": {"id": to_id, "entityType": to_type},
        "type": "Contains",
        "typeGroup": "COMMON"
    }
    requests.post(f"{url}/api/relation", headers=headers, json=payload).raise_for_status()

def find_device_by_name(url, token, name):
    headers = {'X-Authorization': f'Bearer {token}'}
    r = requests.get(f"{url}/api/tenant/devices", headers=headers, params={"pageSize": 10, "page": 0, "textSearch": name})
    r.raise_for_status()
    for device in r.json().get("data", []):
        if device["name"].lower() == name.lower():
            return device
    return None

def create_device(url, token, name, profile_id):
    headers = {'X-Authorization': f'Bearer {token}', "Content-Type": "application/json"}
    payload = {
        "name": name,
        "type": "default",
        "deviceProfileId": {"entityType": "DEVICE_PROFILE", "id": profile_id}
    }
    r = requests.post(f"{url}/api/device", headers=headers, json=payload)
    r.raise_for_status()
    return r.json()

def get_device_credentials(url, token, device_id):
    headers = {'X-Authorization': f'Bearer {token}'}
    r = requests.get(f"{url}/api/device/{device_id}/credentials", headers=headers)
    r.raise_for_status()
    return r.json()["credentialsId"]

def provision():
    print("🚀 Starting Device Provisioning (Advanced Logic)...")
    
    token = get_token()
    if not token:
        print("❌ Authentication failed!")
        return None

    config = get_config()
    url = config.get('thingsboard', 'url').strip('/')
    
    # 1. Assets Configuration
    country_name = config.get('assets', 'country_name').upper()
    state_name = config.get('assets', 'state_name')
    serial_number = config.get('assets', 'serial_number')
    device_name = config.get('assets', 'device_name')
    
    # 2. Profiles
    cp_name = config.get('profiles', 'country_profile_name')
    sp_name = config.get('profiles', 'state_profile_name')
    dp_name = config.get('profiles', 'device_profile_name')

    cp_id = get_asset_profile_id_by_name(url, token, cp_name)
    sp_id = get_asset_profile_id_by_name(url, token, sp_name)
    dp_id = get_device_profile_id_by_name(url, token, dp_name)

    if not cp_id:
        print(f"❌ Country profile '{cp_name}' not found on ThingsBoard!")
    if not sp_id:
        print(f"❌ State profile '{sp_name}' not found on ThingsBoard!")
    if not dp_id:
        print(f"❌ Device profile '{dp_name}' not found on ThingsBoard!")

    if not all([cp_id, sp_id, dp_id]):
        return None

    # 3. Geolocation (ipapi for lat/long only)
    lat, lon = get_lat_lon()
    print(f"📍 Detected Coordinates: {lat}, {lon}")

    # 4. Asset Hierarchy logic from DeviceProvision1.py
    print(f"🏢 Verifying Asset Hierarchy: {country_name} -> {state_name}...")
    assets = list_all_assets(url, token)
    
    # Country
    country_asset = find_asset_in_list(assets, country_name)
    if not country_asset:
        print(f"➕ Creating Country Asset: {country_name}")
        country_asset = create_asset(url, token, country_name, cp_id, cp_name)
        send_asset_attributes(url, token, country_asset['id']['id'], lat, lon)
    
    # State
    state_asset = find_asset_in_list(assets, state_name)
    if not state_asset:
        print(f"➕ Creating State Asset: {state_name}")
        state_asset = create_asset(url, token, state_name, sp_id, sp_name)
        send_asset_attributes(url, token, state_asset['id']['id'], lat, lon)

    # Link Country -> State
    if not check_relation_exists(url, token, country_asset['id']['id'], state_asset['id']['id']):
        print(f"🔗 Linking {country_name} -> {state_name}")
        create_relation(url, token, country_asset['id']['id'], "ASSET", state_asset['id']['id'], "ASSET")

    # 5. Device Registration
    print(f"🛰️ Registering Device: {device_name}...")
    device = find_device_by_name(url, token, device_name)
    if not device:
        print(f"➕ Creating Device: {device_name}")
        device = create_device(url, token, device_name, dp_id)
    
    # Link State -> Device
    if not check_relation_exists(url, token, state_asset['id']['id'], device['id']['id'], to_type="DEVICE"):
        print(f"🔗 Linking {state_name} -> {device_name}")
        create_relation(url, token, state_asset['id']['id'], "ASSET", device['id']['id'], "DEVICE")

    # 6. Credentials
    device_access_token = get_device_credentials(url, token, device['id']['id'])
    print(f"🔑 Obtained Device Access Token: {device_access_token}")

    # 7. Initial Handshake
    heartbeat = {
        "serial": serial_number,
        "latitude": lat,
        "longitude": lon,
        "system_info": f"Host: {socket.gethostname()}, OS: {os.name}"
    }
    
    # Send via HTTP for initial handshake
    requests.post(f"{url}/api/v1/{device_access_token}/telemetry", json=heartbeat).raise_for_status()
    
    print("✅ Provisioning Complete!")
    return device_access_token

if __name__ == "__main__":
    provision()
