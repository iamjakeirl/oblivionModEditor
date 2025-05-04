# mod_manager/ue4ss_installer.py
import os, tempfile, zipfile, shutil, requests, glob
from pathlib import Path
from .utils import UE4SS_URL, get_install_type
import json
import re

DEBUG = False

BIN_MAP = {
    "steam":  r"OblivionRemastered\Binaries\Win64",
    "gamepass": r"OblivionRemastered\Binaries\WinGDK",
}

def install_ue4ss(game_root: str, install_type: str, progress_cb=None):
    if install_type not in ("steam", "gamepass"):
        return False, "Unknown install type"

    # Find the correct bin directory
    if install_type == "steam":
        target_dir = _find_bin_dir(game_root, "Win64")
    else:
        target_dir = _find_bin_dir(game_root, "WinGDK")
    if not target_dir:
        return False, "Could not find correct binary directory (Win64/WinGDK) in game folder"

    # Verify the Shipping exe is present before extraction
    found_exe = False
    for f in os.listdir(target_dir):
        if f.startswith("OblivionRemastered-Win") and f.endswith("-Shipping.exe"):
            found_exe = True
            break
    if not found_exe:
        return False, "Shipping exe not found for verification"

    target_dir.mkdir(parents=True, exist_ok=True)

    tmp_zip = Path(tempfile.gettempdir()) / "ue4ss_tmp.zip"
    # download
    with requests.get(UE4SS_URL, stream=True) as r:
        r.raise_for_status()
        with open(tmp_zip, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if progress_cb: progress_cb(chunk)
                f.write(chunk)
    # extract
    with zipfile.ZipFile(tmp_zip) as zf:
        zf.extractall(target_dir)
    tmp_zip.unlink(missing_ok=True)

    # After extraction, update mods.txt to disable certain mods
    mods_txt = target_dir / "UE4SS" / "Mods" / "mods.txt"
    if mods_txt.exists():
        try:
            with open(mods_txt, "r", encoding="utf-8") as f:
                lines = f.readlines()
            with open(mods_txt, "w", encoding="utf-8") as f:
                for line in lines:
                    line_to_match = line.lstrip('\ufeff')
                    if re.match(r"^\s*CheatManagerEnablerMod\s*[:=]", line_to_match):
                        f.write("CheatManagerEnablerMod : 0\n")
                    elif re.match(r"^\s*ConsoleCommandsMod\s*[:=]", line_to_match):
                        f.write("ConsoleCommandsMod : 0\n")
                    elif re.match(r"^\s*ConsoleEnablerMod\s*[:=]", line_to_match):
                        f.write("ConsoleEnablerMod : 0\n")
                    else:
                        f.write(line)
        except Exception as e:
            print(f"[UE4SS] Failed to update mods.txt: {e}")

    # After extraction, update mods.json to the specified state
    mods_json = target_dir / "UE4SS" / "Mods" / "mods.json"
    mods_json_data = [
        {"mod_name": "CheatManagerEnablerMod", "mod_enabled": False},
        {"mod_name": "ConsoleCommandsMod", "mod_enabled": False},
        {"mod_name": "ConsoleEnablerMod", "mod_enabled": False},
        {"mod_name": "SplitScreenMod", "mod_enabled": False},
        {"mod_name": "LineTraceMod", "mod_enabled": False},
        {"mod_name": "BPML_GenericFunctions", "mod_enabled": True},
        {"mod_name": "BPModLoaderMod", "mod_enabled": True},
        {"mod_name": "Keybinds", "mod_enabled": True}
    ]
    try:
        with open(mods_json, "w", encoding="utf-8") as f:
            json.dump(mods_json_data, f, indent=4)
    except Exception as e:
        print(f"[UE4SS] Failed to update mods.json: {e}")

    # verify dwmapi.dll
    if not (target_dir / "dwmapi.dll").exists():
        return False, "dwmapi.dll missing after extraction"
    return True, ""

def _find_bin_dir(base_path, bin_folder):
    """Recursively search for a directory whose absolute path ends with the given bin_folder name and contains the correct Shipping exe."""
    for root, dirs, files in os.walk(base_path):
        if os.path.basename(root).lower() == bin_folder.lower():
            if DEBUG:
                print(f"[UE4SS] Checking for Shipping exe in: {root}")
            # Check for the required Shipping exe
            for f in os.listdir(root):
                if f.startswith("OblivionRemastered-Win") and f.endswith("-Shipping.exe"):
                    if DEBUG:
                        print(f"[UE4SS] Found Shipping exe: {f} in {root}")
                    return Path(root)
    return None

def get_ue4ss_bin_dir(game_root):
    t = get_install_type()
    if t == "steam":
        return _find_bin_dir(game_root, "Win64")
    elif t == "gamepass":
        return _find_bin_dir(game_root, "WinGDK")
    return None

def ue4ss_installed(game_root):
    d = get_ue4ss_bin_dir(game_root)
    if not d: return (False, "")
    dll = d / "dwmapi.dll"
    return (dll.exists(), "unknown")  # placeholder version detection

def uninstall_ue4ss(game_root):
    d = get_ue4ss_bin_dir(game_root)
    if not d: return False
    ok = False
    try:
        # Remove dwmapi.dll and the UE4SS folder in the same directory
        dll_path = d / "dwmapi.dll"
        ue4ss_folder = d / "UE4SS"
        if dll_path.exists():
            dll_path.unlink()
        if ue4ss_folder.exists() and ue4ss_folder.is_dir():
            shutil.rmtree(ue4ss_folder)
        ok = True
    except Exception:
        ok = False
    return ok

# ---------- UE4SS MODS HELPERS ----------
def get_ue4ss_mods_dir(game_root):
    """Return path to .../UE4SS/Mods ; create if missing."""
    bin_dir = get_ue4ss_bin_dir(game_root)
    if not bin_dir:
        return None
    mods_dir = bin_dir / "UE4SS" / "Mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    return mods_dir

def read_ue4ss_mods_txt(game_root):
    """Return (enabled_mods, disabled_mods) from mods.txt as two lists of mod folder names."""
    bin_dir = get_ue4ss_bin_dir(game_root)
    if not bin_dir:
        return [], []
    mods_file = bin_dir / "UE4SS" / "Mods" / "mods.txt"
    enabled, disabled = [], []
    if mods_file.exists():
        for line in mods_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if ":" in line:
                name, val = [x.strip() for x in line.split(":", 1)]
                if val == "1":
                    enabled.append(name)
                else:
                    disabled.append(name)
            else:
                # fallback: treat as enabled
                enabled.append(line)
    return enabled, disabled

def set_ue4ss_mod_enabled(game_root, mod_folder_name, enabled=True):
    """Set the enabled/disabled state of a mod in mods.txt."""
    bin_dir = get_ue4ss_bin_dir(game_root)
    if not bin_dir:
        return False
    mods_file = bin_dir / "UE4SS" / "Mods" / "mods.txt"
    if not mods_file.exists():
        return False
    lines = mods_file.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(mod_folder_name):
            lines[i] = f"{mod_folder_name} : {'1' if enabled else '0'}"
            found = True
            break
    if not found:
        lines.append(f"{mod_folder_name} : {'1' if enabled else '0'}")
    mods_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True

def _update_mods_txt(bin_dir: Path, mod_folder_name: str):
    """Insert mod_folder_name : 1 into mods.txt above the keybind sentinel line."""
    mods_file = bin_dir / "mods.txt"
    sentinel = "; Built-in keybinds, do not move up!"
    lines = []
    if mods_file.exists():
        lines = mods_file.read_text(encoding="utf-8").splitlines()
    # Remove any existing entry for this mod
    lines = [l for l in lines if not l.strip().startswith(mod_folder_name)]
    try:
        idx = lines.index(sentinel)
    except ValueError:
        idx = len(lines)
    lines.insert(idx, f"{mod_folder_name} : 1")
    mods_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

def add_ue4ss_mod(game_root: str, src_mod_dir: Path):
    """
    Copy the entire FolderX into UE4SS/Mods and register it in mods.txt.
    Returns True if installed, False if UE4SS missing.
    """
    bin_dir = get_ue4ss_bin_dir(game_root)
    if not bin_dir:
        return False
    ue4ss_mods_dir = bin_dir / "UE4SS" / "Mods"
    ue4ss_mods_dir.mkdir(parents=True, exist_ok=True)
    dest = ue4ss_mods_dir / src_mod_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src_mod_dir, dest)
    # Remove enabled.txt if present
    enabled_txt = dest / "enabled.txt"
    if enabled_txt.exists():
        enabled_txt.unlink()
    mods_txt_dir = bin_dir / "UE4SS" / "Mods"
    _update_mods_txt(mods_txt_dir, src_mod_dir.name)
    return True 