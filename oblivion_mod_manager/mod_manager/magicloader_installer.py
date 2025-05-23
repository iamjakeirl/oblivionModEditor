# mod_manager/magicloader_installer.py
# -*- coding: utf-8 -*-
"""Helpers for installing / uninstalling the **MagicLoader** patcher.

Steam layout  →  <GAME_ROOT>\MagicLoader\MagicLoader.exe
Game Pass     →  <GAME_ROOT>\Content\MagicLoader\MagicLoader.exe

MagicLoader download currently requires manual fetch from Nexus Mods.
If the caller supplies *zip_path* we use that; otherwise we attempt to
fetch the public URL constant (may 404 until Nexus provides one).
"""
from __future__ import annotations

import os, tempfile, zipfile, shutil, subprocess
from pathlib import Path
from typing import Tuple, List, Optional, Callable

from .utils import get_install_type  # NEW – detect steam / gamepass

MAGICLOADER_URL     = "https://github.com/Haphestia/MagicLoader/releases/latest/download/MagicLoader.zip"
MAGICLOADER_FOLDER  = "MagicLoader"
ML_EXE              = "MagicLoader.exe"
ML_CLI              = "mlcli.exe"

DEBUG = True

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _find_ml_dir(game_root: str | Path) -> Optional[Path]:
    """Recursively search *game_root* for a *MagicLoader* dir containing
    either executable; return the **shallowest** match."""
    base = Path(game_root)
    if not base.is_dir():
        return None
    candidates: List[Path] = []
    for root, dirs, _ in os.walk(base):
        for d in dirs:
            if d.lower() == MAGICLOADER_FOLDER.lower():
                p = Path(root) / d
                if (p / ML_EXE).exists() or (p / ML_CLI).exists():
                    candidates.append(p)
    if not candidates:
        return None
    return min(candidates, key=lambda p: len(p.relative_to(base).parts))


def get_magicloader_dir(game_root: str | Path) -> Optional[Path]:
    return _find_ml_dir(game_root)


def magicloader_installed(game_root: str | Path) -> Tuple[bool, str]:
    d = get_magicloader_dir(game_root)
    if not d:
        return False, ""
    exe = d / ML_EXE
    if not exe.exists():
        return False, ""
    # No version check, just return True and empty string
    return True, ""

# ---------------------------------------------------------------------------
# Installation / uninstallation
# ---------------------------------------------------------------------------

def _target_ml_dir(game_root: Path, install_type: str) -> Path:
    """Return where *MagicLoader* **should** live for the given install type."""
    if install_type == "gamepass":
        return game_root / "Content" / MAGICLOADER_FOLDER
    return game_root / MAGICLOADER_FOLDER  # steam / generic


def install_magicloader(game_root: str | Path,
                         zip_path: str | Path | None = None,
                         progress_cb: Optional[Callable[[bytes], None]] = None
                         ) -> Tuple[bool, str]:
    """Install MagicLoader from *zip_path* (or download if None).
    Handles correct Steam vs GamePass target directories.
    """
    game_root = Path(game_root)
    if not game_root.is_dir():
        return False, "Invalid game path"

    # Determine install type
    install_type = get_install_type() or "steam"
    target_dir = _target_ml_dir(game_root, install_type)

    # ---------------- acquire archive ----------------
    if zip_path is None:
        import requests
        tmp_zip = Path(tempfile.gettempdir()) / "magicloader_tmp.zip"
        try:
            with requests.get(MAGICLOADER_URL, stream=True) as r:
                r.raise_for_status()
                with open(tmp_zip, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                        if progress_cb:
                            progress_cb(chunk)
        except Exception as e:
            return False, f"Download failed: {e}"
        zip_path = tmp_zip
    else:
        zip_path = Path(zip_path)
        if not zip_path.is_file():
            return False, "Archive not found"

    # ---------------- extract to temp ----------------
    temp_extract = Path(tempfile.mkdtemp(prefix="ml_inst_"))
    try:
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(temp_extract)
    except Exception as e:
        shutil.rmtree(temp_extract, ignore_errors=True)
        return False, f"Extraction failed: {e}"
    finally:
        if str(zip_path).startswith(tempfile.gettempdir()):
            zip_path.unlink(missing_ok=True)

    # Locate extracted MagicLoader folder (may be root or nested)
    extracted_ml = _find_ml_dir(temp_extract)
    if not extracted_ml:
        shutil.rmtree(temp_extract, ignore_errors=True)
        return False, "MagicLoader folder not found in archive"

    # Clean existing install then move/merge
    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(extracted_ml), str(target_dir))
    except Exception as e:
        shutil.rmtree(temp_extract, ignore_errors=True)
        return False, f"Move failed: {e}"

    shutil.rmtree(temp_extract, ignore_errors=True)
    ok, _ = magicloader_installed(game_root)
    return (ok, "" if ok else "Installed but exe not detected")


def uninstall_magicloader(game_root: str | Path) -> bool:
    from .utils import DATA_DIR
    d = get_magicloader_dir(game_root)
    if not d:
        return False
    disabled_dir = Path(DATA_DIR) / "disabled_magicloader"
    disabled_dir.mkdir(parents=True, exist_ok=True)
    try:
        dest = disabled_dir / MAGICLOADER_FOLDER
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(d), str(dest))
        return True
    except Exception:
        return False


def reenable_magicloader(game_root: str | Path) -> bool:
    from .utils import DATA_DIR
    disabled_dir = Path(DATA_DIR) / "disabled_magicloader" / MAGICLOADER_FOLDER
    if not disabled_dir.exists():
        return False
    install_type = get_install_type() or "steam"
    target = _target_ml_dir(Path(game_root), install_type)
    try:
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(disabled_dir), str(target))
        return True
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Mods helpers (json scripts)
# ---------------------------------------------------------------------------

def get_ml_mods_dir(game_root: str | Path) -> Optional[Path]:
    """
    Return the MagicLoader JSON mod directory for the current install type.
    Steam:   OblivionRemastered\OblivionRemastered\Content\Dev\ObvData\Data\MagicLoader
    GamePass: The Elder Scrolls IV- Oblivion Remastered\Content\OblivionRemastered\Content\Dev\ObvData\Data\MagicLoader
    """
    from .utils import get_install_type
    game_root = Path(game_root)
    install_type = get_install_type() or "steam"
    if install_type == "gamepass":
        mods_dir = game_root / "Content" / "OblivionRemastered" / "Content" / "Dev" / "ObvData" / "Data" / "MagicLoader"
    else:
        mods_dir = game_root / "OblivionRemastered" / "Content" / "Dev" / "ObvData" / "Data" / "MagicLoader"
    mods_dir.mkdir(parents=True, exist_ok=True)
    return mods_dir

# New: Disabled MagicLoader JSONs sibling directory

def get_disabled_ml_mods_dir(game_root: str | Path) -> Optional[Path]:
    """
    Return the DisabledMagicLoader JSON mod directory for the current install type.
    Sibling to the main MagicLoader JSON folder.
    """
    from .utils import get_install_type
    game_root = Path(game_root)
    install_type = get_install_type() or "steam"
    if install_type == "gamepass":
        disabled_dir = game_root / "Content" / "OblivionRemastered" / "Content" / "Dev" / "ObvData" / "Data" / "DisabledMagicLoader"
    else:
        disabled_dir = game_root / "OblivionRemastered" / "Content" / "Dev" / "ObvData" / "Data" / "DisabledMagicLoader"
    disabled_dir.mkdir(parents=True, exist_ok=True)
    return disabled_dir


def list_ml_json_mods(game_root: str | Path) -> Tuple[List[str], List[str]]:
    """
    Return (enabled, disabled) JSONs as two lists.
    """
    enabled_dir = get_ml_mods_dir(game_root)
    disabled_dir = get_disabled_ml_mods_dir(game_root)
    enabled = [p.name for p in enabled_dir.glob("*.json")] if enabled_dir else []
    disabled = [p.name for p in disabled_dir.glob("*.json")] if disabled_dir else []
    return enabled, disabled


def _call_ml_cli(game_root: str | Path, command: str = "reload") -> Tuple[bool, str]:
    """Call MagicLoader CLI tool to reload configuration."""
    ml_dir = get_magicloader_dir(game_root)
    if not ml_dir:
        return False, "MagicLoader not found"
    
    cli_exe = ml_dir / ML_CLI
    if not cli_exe.exists():
        return False, f"mlcli.exe not found at {cli_exe}"
    
    try:
        result = subprocess.run(
            [str(cli_exe), command],
            cwd=str(ml_dir),
            capture_output=True,
            text=True,
            timeout=30
        )
        if DEBUG:
            print(f"[MagicLoader CLI] Command: {command}")
            print(f"[MagicLoader CLI] Return code: {result.returncode}")
            print(f"[MagicLoader CLI] Output: {result.stdout}")
            if result.stderr:
                print(f"[MagicLoader CLI] Error: {result.stderr}")
        
        output = result.stdout.strip() if result.stdout else ""
        error = result.stderr.strip() if result.stderr else ""
        combined = f"{output}\n{error}".strip() if error else output
        
        return result.returncode == 0, combined
    except subprocess.TimeoutExpired:
        return False, "CLI command timed out"
    except Exception as e:
        return False, f"CLI execution failed: {e}"


def deactivate_ml_mod(game_root: str | Path, json_name: str) -> bool:
    enabled_dir = get_ml_mods_dir(game_root)
    disabled_dir = get_disabled_ml_mods_dir(game_root)
    if not enabled_dir or not disabled_dir:
        return False
    src = enabled_dir / json_name
    if not src.exists():
        return False
    try:
        dest = disabled_dir / json_name
        if dest.exists():
            dest.unlink()
        shutil.move(str(src), str(dest))
        
        # Call CLI to reload MagicLoader configuration
        success, output = _call_ml_cli(game_root, "reload")
        if DEBUG or not success:
            print(f"[MagicLoader] Deactivated {json_name}")
            if output:
                print(f"[MagicLoader CLI Output] {output}")
        
        return True
    except Exception as e:
        if DEBUG:
            print(f"[MagicLoader] Failed to deactivate {json_name}: {e}")
        return False


def activate_ml_mod(game_root: str | Path, json_name: str) -> bool:
    enabled_dir = get_ml_mods_dir(game_root)
    disabled_dir = get_disabled_ml_mods_dir(game_root)
    if not enabled_dir or not disabled_dir:
        return False
    src = disabled_dir / json_name
    if not src.exists():
        return False
    try:
        dest = enabled_dir / json_name
        if dest.exists():
            dest.unlink()
        shutil.move(str(src), str(dest))
        
        # Call CLI to reload MagicLoader configuration
        success, output = _call_ml_cli(game_root, "reload")
        if DEBUG or not success:
            print(f"[MagicLoader] Activated {json_name}")
            if output:
                print(f"[MagicLoader CLI Output] {output}")
        
        return True
    except Exception as e:
        if DEBUG:
            print(f"[MagicLoader] Failed to activate {json_name}: {e}")
        return False
