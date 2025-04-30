
import os
import json
from pathlib import Path

SETTINGS_PATH = Path(__file__).parent.parent / 'data' / 'settings.json'


def get_game_path():
    """Read the game path from settings.json. Returns None if not set."""
    try:
        with open(SETTINGS_PATH, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        return settings.get('game_path')
    except Exception:
        return None

def get_esp_folder():
    """Return the path to the ESP folder inside the game directory."""
    game_path = get_game_path()
    if not game_path:
        return None
    return os.path.join(game_path, 'Content', 'Dev', 'ObvData', 'Data')

def get_plugins_txt_path():
    """Return the path to plugins.txt inside the ESP folder."""
    esp_folder = get_esp_folder()
    if not esp_folder:
        return None
    return os.path.join(esp_folder, 'Plugins.txt') 