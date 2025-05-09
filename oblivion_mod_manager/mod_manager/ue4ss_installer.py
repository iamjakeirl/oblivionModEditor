# mod_manager/ue4ss_installer.py
import os, tempfile, zipfile, shutil, requests, glob
from pathlib import Path
from .utils import UE4SS_URL, get_install_type
import json
import re

DEBUG = False

# Reserved UE4SS mod-folder names that should never appear in the manager
# nor be listed in mods.txt
RESERVED_MODS = {"shared"}

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

def read_ue4ss_mods_txt(game_root: str, *, normalize: bool = True):
    """Return (enabled_mods, disabled_mods) after *optionally* normalising legacy enabled.txt mods.

    Normalisation rules:
        • Any folder inside UE4SS/Mods that is NOT referenced in mods.txt is treated as:
              – enabled if an `enabled.txt` file exists inside it
              – disabled otherwise
        • A corresponding entry is then written to mods.txt (and enabled.txt removed) so
          future reads rely solely on mods.txt.
    """
    bin_dir = get_ue4ss_bin_dir(game_root)
    if not bin_dir:
        return [], []

    mods_root = bin_dir / "UE4SS" / "Mods"
    mods_file = mods_root / "mods.txt"

    enabled: list[str] = []
    disabled: list[str] = []

    # Parse existing mods.txt (if any)
    if mods_file.exists():
        for line in mods_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if ":" in line:
                name, val = [x.strip() for x in line.split(":", 1)]
            else:
                name, val = line, "1"  # default enabled if no colon

            # Skip reserved system folders (e.g. shared)
            if name.lower() in RESERVED_MODS:
                continue

            if val == "1":
                enabled.append(name)
            else:
                disabled.append(name)

    # --- Legacy enabled.txt scan -------------------------------------------------
    if normalize:
        from pathlib import Path

        listed = set(enabled) | set(disabled)

        if mods_root.exists():
            for child in mods_root.iterdir():
                if not child.is_dir():
                    continue
                mod_name = child.name

                if mod_name in listed:
                    continue  # already accounted for

                enabled_flag = (child / "enabled.txt").exists()

                # Record state
                if enabled_flag:
                    enabled.append(mod_name)
                else:
                    disabled.append(mod_name)

                # Normalise: add to mods.txt and rename enabled.txt → managed.txt
                _update_mods_txt(mods_root, mod_name, enabled=enabled_flag)

                # Rename legacy flag file so we don't create/delete it again
                if (child / "enabled.txt").exists():
                    try:
                        (child / "enabled.txt").replace(child / "managed.txt")
                    except Exception:
                        (child / "enabled.txt").unlink(missing_ok=True)

    # ---------------------------------------------------------------------------

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

def _update_mods_txt(bin_dir: Path, mod_folder_name: str, *, enabled: bool = True):
    """Ensure mods.txt contains a line `mod_folder_name : 1|0` above sentinel (or at end).

    If the entry already exists it is replaced. `enabled` controls the value written.
    """
    # Never write entries for reserved folders (e.g. shared)
    if mod_folder_name.lower() in RESERVED_MODS:
        return

    mods_file = bin_dir / "mods.txt"
    sentinel = "; Built-in keybinds, do not move up!"

    # Ensure the file exists so we can read/patch it
    if not mods_file.exists():
        mods_file.write_text(f"{sentinel}\n", encoding="utf-8")

    lines = mods_file.read_text(encoding="utf-8").splitlines()

    # Strip any previous occurrence of this mod
    lines = [l for l in lines if not l.strip().startswith(f"{mod_folder_name} :")]

    # Guarantee sentinel line exists
    if sentinel not in lines:
        lines.append(sentinel)

    # Insert just above sentinel so UE4SS retains order assumptions
    try:
        idx = lines.index(sentinel)
    except ValueError:
        idx = len(lines)

    lines.insert(idx, f"{mod_folder_name} : {'1' if enabled else '0'}")

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
    mod_name_lower = src_mod_dir.name.lower()

    # -------- SPECIAL-CASE: shared system folder --------
    if mod_name_lower in RESERVED_MODS:
        _merge_tree(src_mod_dir, ue4ss_mods_dir / src_mod_dir.name)
        return True  # merged successfully, no mods.txt entry

    dest = ue4ss_mods_dir / src_mod_dir.name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src_mod_dir, dest)
    # If the mod ships an enabled.txt flag, rename it so future scripts know it's been managed
    enabled_txt = dest / "enabled.txt"
    if enabled_txt.exists():
        try:
            enabled_txt.replace(dest / "managed.txt")
        except Exception:
            enabled_txt.unlink(missing_ok=True)
    mods_txt_dir = bin_dir / "UE4SS" / "Mods"
    _update_mods_txt(mods_txt_dir, src_mod_dir.name, enabled=True)
    return True

def ensure_ue4ss_configs(game_root):
    """
    Ensure UE4SS mods.txt and mods.json are patched/configured for OBMM.
    Returns True if work was done, False if already configured or UE4SS not installed.
    """
    if not ue4ss_installed(game_root)[0]:
        return False
    bin_dir = get_ue4ss_bin_dir(game_root)
    if not bin_dir:
        return False
    mods_dir = bin_dir / "UE4SS" / "Mods"
    mods_dir.mkdir(parents=True, exist_ok=True)
    sentinel = mods_dir / ".obmm_configured"
    if sentinel.exists():
        return False
    mods_txt = mods_dir / "mods.txt"
    mods_json = mods_dir / "mods.json"
    _patch_mods_txt(mods_txt)
    _patch_mods_json(mods_json)
    sentinel.touch()
    return True

def _patch_mods_txt(mods_txt_path):
    """
    Patch mods.txt to ensure each DEFAULT_DISABLED_MOD has a line "{name} : 0" unless already present, preserving order, appending new lines just above the sentinel.
    """
    DEFAULT_DISABLED_MODS = [
        "CheatManagerEnablerMod",
        "ConsoleCommandsMod",
        "ConsoleEnablerMod",
        "SplitScreenMod",
        "LineTraceMod"
    ]
    sentinel = "; Built-in keybinds, do not move up!"
    if mods_txt_path.exists():
        lines = mods_txt_path.read_text(encoding="utf-8").splitlines()
    else:
        lines = []
    # Track which mods are already present (with : 0 or : 1)
    present_mods = set()
    for line in lines:
        for name in DEFAULT_DISABLED_MODS:
            if line.strip().startswith(f"{name} :"):
                present_mods.add(name)
    # Prepare new lines for missing mods
    new_lines = [f"{name} : 0" for name in DEFAULT_DISABLED_MODS if name not in present_mods]
    # Find sentinel index, add if missing
    try:
        idx = lines.index(sentinel)
    except ValueError:
        lines.append(sentinel)
        idx = len(lines) - 1
    # Insert new lines just above sentinel
    lines = lines[:idx] + new_lines + lines[idx:]
    mods_txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

def _patch_mods_json(mods_json_path):
    """
    Patch mods.json to ensure each DEFAULT_DISABLED_MOD has an entry {mod_name: ..., mod_enabled: False} unless already present.
    """
    DEFAULT_DISABLED_MODS = [
        "CheatManagerEnablerMod",
        "ConsoleCommandsMod",
        "ConsoleEnablerMod",
        "SplitScreenMod",
        "LineTraceMod"
    ]
    if mods_json_path.exists():
        try:
            data = json.load(open(mods_json_path, "r", encoding="utf-8"))
        except Exception:
            data = []
    else:
        data = []
    # Only add missing mods
    existing_names = {entry.get("mod_name") for entry in data if isinstance(entry, dict)}
    for name in DEFAULT_DISABLED_MODS:
        if name not in existing_names:
            data.append({"mod_name": name, "mod_enabled": False})
    with open(mods_json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# ---------------- internal helpers --------------------

def _merge_tree(src: Path, dest: Path):
    """Recursively merge *src* directory into *dest* (overwriting duplicates)."""
    if not src.exists():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        d = dest / item.name
        if item.is_dir():
            _merge_tree(item, d)
        else:
            try:
                if d.exists():
                    d.unlink()
                shutil.copy2(item, d)
            except Exception:
                pass 