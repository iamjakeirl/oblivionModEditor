import os
import json
import sys
from pathlib import Path
import filecmp
import shutil

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

def load_settings():  # helper – central read
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_settings(data: dict):  # helper – central write
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

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

def open_folder_in_explorer(path):
    """
    Open the given folder in Windows Explorer (Windows only).
    """
    if not os.path.isdir(path):
        return False
    try:
        os.startfile(path)
        return True
    except Exception as e:
        print(f"Error opening folder in Explorer: {e}")
        return False

# UE4SS support
UE4SS_URL = "https://github.com/UE4SS-RE/RE-UE4SS/releases/download/experimental-latest/UE4SS_v3.0.1-394-g437a8ff.zip"
UE4SS_VERSION = "v3.0.1-394-g437a8ff"

def get_install_type():
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("install_type")
    except Exception:
        return None

def set_install_type(t):
    data = {}
    if SETTINGS_PATH.exists():
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            if content:
                data = json.loads(content)
    data["install_type"] = t
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def guess_install_type(game_root: str) -> str:
    p = game_root.lower()
    if r"\steam\steamapps\common" in p:
        return "steam"
    if r"\xboxgames" in p:
        return "gamepass"
    return "unknown"

def ensure_custom_mod_dir_name_default():
    s = load_settings()
    if "custom_mod_dir_name" not in s:
        s["custom_mod_dir_name"] = "~mods"
        save_settings(s)

def get_custom_mod_dir_name():
    ensure_custom_mod_dir_name_default()
    s = load_settings()
    return s.get("custom_mod_dir_name", "~mods")

def set_custom_mod_dir_name(name: str):
    if not name or name.lower() == "logicmods":
        raise ValueError("Invalid custom mod folder name")
    s = load_settings()
    s["custom_mod_dir_name"] = name
    save_settings(s)

def migrate_disabled_mods_if_needed(game_path):
    """
    If the migration flag is not set, move mods from the old disabled folder (inside Paks) to the new sibling DisabledMods folder,
    then set the flag in settings.json. Should be called at app startup.
    """
    s = load_settings()
    if s.get("disabled_mods_migrated", False):
        return
    from mod_manager.pak_manager import get_paks_root_dir, DISABLED_FOLDER_NAME
    import shutil
    paks_root = get_paks_root_dir(game_path)
    if not paks_root:
        return
    old_disabled = os.path.join(paks_root, "disabled")
    obvdata_root = os.path.dirname(paks_root)
    new_disabled = os.path.join(obvdata_root, DISABLED_FOLDER_NAME)
    if os.path.isdir(old_disabled):
        # Move all files and folders from old_disabled to new_disabled
        for item in os.listdir(old_disabled):
            src = os.path.join(old_disabled, item)
            dst = os.path.join(new_disabled, item)
            try:
                if os.path.isdir(src):
                    shutil.move(src, dst)
                else:
                    shutil.move(src, dst)
            except Exception as e:
                print(f"Error migrating disabled mod {item}: {e}")
        # Remove old folder
        try:
            os.rmdir(old_disabled)
        except Exception:
            pass
    s["disabled_mods_migrated"] = True
    save_settings(s)

# --- In‑memory cache to avoid repeated disk reads --------------------------
_DISPLAY_CACHE = None

def _display_cache():
    """Return (and lazily populate) the in‑memory display‑info dict."""
    global _DISPLAY_CACHE
    if _DISPLAY_CACHE is None:
        _DISPLAY_CACHE = _load_display()   # existing helper reads from disk
    return _DISPLAY_CACHE
# ---------------------------------------------------------------------------

# --- Display Registry Helpers ---
DISPLAY_FILE = DATA_DIR / 'display_names.json'

def _load_display():
    try:
        return json.load(DISPLAY_FILE.open('r', encoding='utf-8'))
    except Exception:
        return {}

def _save_display(data: dict):
    DISPLAY_FILE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(data, DISPLAY_FILE.open('w', encoding='utf-8'), indent=2)
    global _DISPLAY_CACHE          # <‑‑ add this line
    _DISPLAY_CACHE = data          # keep cache in sync

def get_display_info(mod_id: str):
    """Return cached display info dict for a given mod id."""
    return _display_cache().get(mod_id, {})

def set_display_info(mod_id: str, *, display: str = None, group: str = None):
    data = _display_cache()
    entry = data.get(mod_id, {})
    if display is not None:
        entry["display"] = display
    if group is not None:
        entry["group"] = group
    data[mod_id] = entry
    _save_display(data)            # writes to disk
    # cache already updated in‑place

def delete_display_info(mod_id: str):
    data = _display_cache()
    if mod_id in data:
        del data[mod_id]
        _save_display(data)        # writes and keeps cache consistent

def _merge_tree(src_dir: str, dest_dir: str):
    """
    Recursively copy src_dir into dest_dir.
    • Directories are created as needed.
    • If a file with the same name already exists at the destination and is
      byte‑identical, it is skipped; otherwise it is overwritten.
    """
    for root, _, files in os.walk(src_dir):
        rel = os.path.relpath(root, src_dir)
        target_root = dest_dir if rel == "." else os.path.join(dest_dir, rel)
        os.makedirs(target_root, exist_ok=True)
        for fname in files:
            src = os.path.join(root, fname)
            dst = os.path.join(target_root, fname)
            try:
                # skip identical file
                if os.path.exists(dst) and filecmp.cmp(src, dst, shallow=False):
                    continue
                shutil.copy2(src, dst)
            except Exception:
                # best‑effort copy; ignore single‑file failures
                pass 

def set_display_info_bulk(changes: list[tuple[str,str]]):
    """
    changes = [(mod_id, new_group_str), ...] – display unchanged
    """
    data = _display_cache()
    for mid, grp in changes:
        entry = data.get(mid, {})
        entry["group"] = grp
        data[mid] = entry
    _save_display(data) 

# ------------------------------------------------------------------
# ONE‑TIME DISPLAY‑KEY MIGRATION (old "None|" prefix → empty prefix)
# ------------------------------------------------------------------
def migrate_display_keys_if_needed():
    """
    Run once: rewrite display_names.json keys that start with 'None|'
    to the modern '|<filename>' form, then set a flag in settings.
    """
    s = load_settings()
    if s.get("display_keys_migrated_v2", False):
        return

    data      = _display_cache()          # current dict
    modified  = False
    for old_key in list(data.keys()):
        if old_key.startswith("None|"):
            new_key = "|" + old_key.split("|", 1)[1]
            if new_key not in data:       # avoid overwrite
                data[new_key] = data.pop(old_key)
            else:
                # conflict → prefer newer key, just drop old
                data.pop(old_key)
            modified = True

    if modified:
        _save_display(data)

    s["display_keys_migrated_v2"] = True
    save_settings(s) 