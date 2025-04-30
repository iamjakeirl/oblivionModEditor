# Handles mod registry logic 
import os
from .utils import get_esp_folder, get_plugins_txt_path

def list_esp_files():
    """List all .esp files in the ESP folder."""
    esp_folder = get_esp_folder()
    if not esp_folder or not os.path.isdir(esp_folder):
        return []
    return [f for f in os.listdir(esp_folder) if f.lower().endswith('.esp')]

def read_plugins_txt():
    """Read plugins.txt and return a list of plugin names (one per line, stripped)."""
    plugins_path = get_plugins_txt_path()
    if not plugins_path or not os.path.isfile(plugins_path):
        return []
    with open(plugins_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def write_plugins_txt(plugin_list):
    """Write the given list of plugin names to plugins.txt, one per line."""
    plugins_path = get_plugins_txt_path()
    if not plugins_path:
        return False
    with open(plugins_path, 'w', encoding='utf-8') as f:
        for plugin in plugin_list:
            f.write(f"{plugin}\n")
    return True 