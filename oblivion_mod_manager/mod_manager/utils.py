import os
import json
import sys
from pathlib import Path

# For Windows standard application data location
def get_app_data_dir():
    """Return the standard directory for application data storage."""
    app_name = "OblivionModManager"
    
    # On Windows, use AppData/Roaming
    if os.name == 'nt':
        app_data = os.environ.get('APPDATA')
        if app_data:
            return Path(app_data) / app_name
    
    # Fallback to user home directory if standard locations not available
    return Path.home() / f".{app_name.lower()}"

# Ensure the data directory exists
DATA_DIR = get_app_data_dir() / 'data'
os.makedirs(DATA_DIR, exist_ok=True)

SETTINGS_PATH = DATA_DIR / 'settings.json'
PAK_MODS_FILE = DATA_DIR / 'pak_mods.json'


def get_game_path():
    """Read the game path from settings.json. Returns None if not set."""
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        return settings.get('game_path')
    except Exception:
        return None

def get_esp_folder():
    """Auto-detect the ESP folder by searching for */ObvData/Data under the game directory."""
    game_path = get_game_path()
    if not game_path:
        return None
    for root, dirs, files in os.walk(game_path):
        if root.lower().endswith(os.path.join('obvdata', 'data').lower()):
            return root
    return None

def get_plugins_txt_path():
    """Return the path to plugins.txt inside the ESP folder."""
    esp_folder = get_esp_folder()
    if not esp_folder:
        return None
    return os.path.join(esp_folder, 'Plugins.txt')

def load_pak_mods():
    """Load PAK mods information from the JSON file.
    
    Returns:
        list: A list of PAK mod data dictionaries. Returns an empty list if file doesn't exist
              or if there's an error reading/parsing the file.
    """
    try:
        if not os.path.exists(PAK_MODS_FILE):
            return []
            
        with open(PAK_MODS_FILE, 'r', encoding='utf-8') as f:
            pak_mods_data = json.load(f)
            
        return pak_mods_data
    except IOError as e:
        print(f"Error reading PAK mods file: {e}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing PAK mods JSON: {e}")
        return []

def save_pak_mods(pak_mods_data):
    """Save PAK mods information to the JSON file.
    
    Args:
        pak_mods_data (list): A list of PAK mod data dictionaries to save.
        
    Returns:
        bool: True if successful, False otherwise.
    """
    try:
        with open(PAK_MODS_FILE, 'w', encoding='utf-8') as f:
            json.dump(pak_mods_data, f, indent=2)
        return True
    except IOError as e:
        print(f"Error writing PAK mods file: {e}")
        return False 