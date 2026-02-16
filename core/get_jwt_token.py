import requests
import configparser
import os

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.properties')

def get_token():
    config = configparser.ConfigParser()
    config.read(CONFIG_PATH)

    url = config.get('thingsboard', 'url').strip('/')
    username = config.get('thingsboard', 'username')
    password = config.get('thingsboard', 'password')
    token = config.get('thingsboard', 'token', fallback='')

    if token:
        # Validate existing token
        headers = {'X-Authorization': f'Bearer {token}'}
        try:
            response = requests.get(f"{url}/api/auth/user", headers=headers)
            if response.status_code == 200:
                return token
        except requests.exceptions.RequestException:
            pass

    # Fetch new token
    login_url = f"{url}/api/auth/login"
    payload = {
        "username": username,
        "password": password
    }
    
    try:
        response = requests.post(login_url, json=payload)
        response.raise_for_status()
        new_token = response.json().get('token')
        
        # Save new token to config
        config.set('thingsboard', 'token', new_token)
        with open(CONFIG_PATH, 'w') as configfile:
            config.write(configfile)
            
        return new_token
    except Exception as e:
        print(f"Error fetching JWT token: {e}")
        return None

if __name__ == "__main__":
    token = get_token()
    if token:
        print(f"Successfully obtained token: {token[:10]}...")
    else:
        print("Failed to obtain token.")
