# mod_manager/obse64_installer.py
# -*- coding: utf-8 -*-
"""Helpers for installing / uninstalling the **OBSE64** (Oblivion Remastered Script Extender).

Steam Only  →  <GAME_ROOT>\\OblivionRemastered\\Binaries\\Win64\\obse64_loader.exe
GamePass/MS Store/EGS are unsupported by OBSE64.

OBSE64 requires manual download from Nexus Mods.
Archive contains obse64_loader.exe, obse64_*.dll files, and src folder (ignored).
"""
from __future__ import annotations

import os, tempfile, zipfile, shutil, subprocess
from pathlib import Path
from typing import Tuple, List, Optional, Callable

from .utils import get_install_type, DATA_DIR

OBSE64_FOLDER = "OBSE"
OBSE64_LOADER = "obse64_loader.exe"
OBSE64_PLUGINS_FOLDER = "plugins"
OBSE64_DISABLED_FOLDER = "disabled"

DEBUG = False

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _get_obse64_target_dir(game_root: str | Path, install_type: str) -> Path:
    """Return where OBSE64 **should** be installed for the given install type.
    Steam: {game_root}/OblivionRemastered/Binaries/Win64/
    GamePass/Others: Not supported
    """
    if install_type != "steam":
        raise ValueError(f"OBSE64 is not supported on {install_type} installations")
    
    game_root = Path(game_root)
    return game_root / "OblivionRemastered" / "Binaries" / "Win64"

def get_obse64_dir(game_root: str | Path) -> Optional[Path]:
    """Get the OBSE64 installation directory if it exists."""
    install_type = get_install_type() or "unknown"
    if install_type != "steam":
        return None
    
    try:
        target_dir = _get_obse64_target_dir(game_root, install_type)
        loader_path = target_dir / OBSE64_LOADER
        if loader_path.exists():
            return target_dir
    except ValueError:
        pass
    return None

def obse64_installed(game_root: str | Path) -> Tuple[bool, str]:
    """Check if OBSE64 is installed and return status.
    Returns (is_installed, version_or_error_message)
    """
    install_type = get_install_type() or "unknown"
    if install_type != "steam":
        return False, "OBSE64 is only supported on Steam installations"
    
    obse_dir = get_obse64_dir(game_root)
    if not obse_dir:
        return False, "Not installed"
    
    loader_path = obse_dir / OBSE64_LOADER
    if not loader_path.exists():
        return False, "Installation incomplete (loader missing)"
    
    # Check for at least one OBSE64 DLL
    dll_files = list(obse_dir.glob("obse64_*.dll"))
    if not dll_files:
        return False, "Installation incomplete (DLLs missing)"
    
    # Try to determine version from DLL name (e.g., obse64_0_411_140.dll)
    version = "installed"
    for dll in dll_files:
        if "_" in dll.stem:
            # Extract version from filename like obse64_0_411_140.dll
            parts = dll.stem.split("_")[1:]  # Skip "obse64"
            if len(parts) >= 3:
                version = ".".join(parts)
                break
    
    return True, version

# ---------------------------------------------------------------------------
# Installation / uninstallation
# ---------------------------------------------------------------------------

def install_obse64(game_root: str | Path, 
                   zip_path: str | Path,
                   progress_cb: Optional[Callable[[str], None]] = None) -> Tuple[bool, str]:
    """Install OBSE64 from manually provided archive.
    Steam installations only.
    """
    game_root = Path(game_root)
    if not game_root.is_dir():
        return False, "Invalid game path"

    # Check install type
    install_type = get_install_type() or "unknown"
    if install_type != "steam":
        return False, "OBSE64 is only supported on Steam installations"

    # Validate archive exists
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        return False, f"Archive not found: {zip_path}"

    try:
        target_dir = _get_obse64_target_dir(game_root, install_type)
    except ValueError as e:
        return False, str(e)

    # Extract to temp directory first
    temp_extract = Path(tempfile.mkdtemp(prefix="obse64_install_"))
    
    try:
        if progress_cb:
            progress_cb("Extracting archive...")
        
        # Extract archive
        if zip_path.suffix.lower() == '.zip':
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(temp_extract)
        elif zip_path.suffix.lower() == '.7z':
            # Try py7zr first (faster and more reliable for most 7z files)
            try:
                import py7zr
                with py7zr.SevenZipFile(zip_path, mode='r') as z:
                    z.extractall(temp_extract)
            except Exception as e:
                # If py7zr fails (e.g., unsupported compression like bcj2), suggest manual extraction
                return False, f"Unsupported 7z compression format ({str(e)}). Please extract the archive manually and drag the loose files onto the main window."
        elif zip_path.suffix.lower() == '.rar':
            # RAR files are not supported - suggest manual extraction
            return False, "RAR archives are not supported. Please extract the archive manually and drag the loose files onto the main window."
        else:
            return False, f"Unsupported archive format: {zip_path.suffix}"

        if progress_cb:
            progress_cb("Locating OBSE64 files...")

        # Find OBSE64 files in extracted content
        obse_files = []
        
        # Look for obse64_loader.exe and obse64_*.dll files
        for root, dirs, files in os.walk(temp_extract):
            for file in files:
                if file == OBSE64_LOADER or file.startswith("obse64_") and file.endswith(".dll"):
                    obse_files.append(Path(root) / file)
        
        if not obse_files:
            return False, "No OBSE64 files found in archive (obse64_loader.exe or obse64_*.dll)"

        # Check for required loader
        has_loader = any(f.name == OBSE64_LOADER for f in obse_files)
        if not has_loader:
            return False, "Archive missing required obse64_loader.exe"

        if progress_cb:
            progress_cb("Installing files...")

        # Create target directory if needed
        target_dir.mkdir(parents=True, exist_ok=True)

        # Copy OBSE64 files to target directory
        installed_files = []
        for file_path in obse_files:
            dest_path = target_dir / file_path.name
            try:
                shutil.copy2(file_path, dest_path)
                installed_files.append(dest_path)
                if DEBUG:
                    print(f"Installed: {file_path.name} -> {dest_path}")
            except Exception as e:
                # Cleanup on failure
                for installed in installed_files:
                    installed.unlink(missing_ok=True)
                return False, f"Failed to install {file_path.name}: {e}"

        # Create OBSE plugins directory structure
        obse_dir = target_dir / OBSE64_FOLDER
        plugins_dir = obse_dir / OBSE64_PLUGINS_FOLDER
        disabled_dir = plugins_dir / OBSE64_DISABLED_FOLDER
        
        plugins_dir.mkdir(parents=True, exist_ok=True)
        disabled_dir.mkdir(parents=True, exist_ok=True)

        if progress_cb:
            progress_cb("Installation complete")

        # Verify installation
        is_installed, status = obse64_installed(game_root)
        if is_installed:
            return True, f"OBSE64 installed successfully (version {status})"
        else:
            return False, f"Installation verification failed: {status}"

    except Exception as e:
        return False, f"Installation failed: {e}"
    
    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_extract, ignore_errors=True)

def uninstall_obse64(game_root: str | Path) -> bool:
    """Uninstall OBSE64 by moving files to disabled directory."""
    obse_dir = get_obse64_dir(game_root)
    if not obse_dir:
        return False

    # Create disabled backup directory
    disabled_dir = Path(DATA_DIR) / "disabled_obse64"
    disabled_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Move OBSE64 files to disabled directory
        obse_files = [obse_dir / OBSE64_LOADER]
        obse_files.extend(obse_dir.glob("obse64_*.dll"))
        
        for file_path in obse_files:
            if file_path.exists():
                dest_path = disabled_dir / file_path.name
                if dest_path.exists():
                    dest_path.unlink()  # Remove existing backup
                shutil.move(str(file_path), str(dest_path))

        # Also backup OBSE folder if it exists
        obse_folder = obse_dir / OBSE64_FOLDER
        if obse_folder.exists():
            dest_obse = disabled_dir / OBSE64_FOLDER
            if dest_obse.exists():
                shutil.rmtree(dest_obse)
            shutil.move(str(obse_folder), str(dest_obse))

        return True
    except Exception as e:
        if DEBUG:
            print(f"Uninstall error: {e}")
        return False

def reenable_obse64(game_root: str | Path) -> bool:
    """Re-enable OBSE64 by restoring from disabled directory."""
    install_type = get_install_type() or "unknown"
    if install_type != "steam":
        return False

    disabled_dir = Path(DATA_DIR) / "disabled_obse64"
    if not disabled_dir.exists():
        return False

    try:
        target_dir = _get_obse64_target_dir(game_root, install_type)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Restore OBSE64 files
        for file_path in disabled_dir.glob("obse64_*"):
            if file_path.is_file():
                dest_path = target_dir / file_path.name
                if dest_path.exists():
                    dest_path.unlink()
                shutil.move(str(file_path), str(dest_path))

        # Restore OBSE folder
        disabled_obse = disabled_dir / OBSE64_FOLDER
        if disabled_obse.exists():
            target_obse = target_dir / OBSE64_FOLDER
            if target_obse.exists():
                shutil.rmtree(target_obse)
            shutil.move(str(disabled_obse), str(target_obse))

        # Cleanup disabled directory if empty
        try:
            disabled_dir.rmdir()
        except OSError:
            pass  # Directory not empty, that's fine

        return True
    except Exception as e:
        if DEBUG:
            print(f"Re-enable error: {e}")
        return False

# ---------------------------------------------------------------------------
# Plugin management
# ---------------------------------------------------------------------------

def get_obse_plugins_dir(game_root: str | Path) -> Optional[Path]:
    """Get the OBSE plugins directory if OBSE64 is installed."""
    obse_dir = get_obse64_dir(game_root)
    if not obse_dir:
        return None
    
    plugins_dir = obse_dir / OBSE64_FOLDER / OBSE64_PLUGINS_FOLDER
    plugins_dir.mkdir(parents=True, exist_ok=True)
    return plugins_dir

def list_obse_plugins(game_root: str | Path) -> Tuple[List[str], List[str]]:
    """List enabled and disabled OBSE plugins.
    Returns (enabled_plugins, disabled_plugins)
    """
    plugins_dir = get_obse_plugins_dir(game_root)
    if not plugins_dir:
        return [], []

    enabled = []
    disabled = []

    # Enabled plugins (in plugins/ directory)
    for plugin in plugins_dir.glob("*.dll"):
        if plugin.is_file():
            enabled.append(plugin.name)

    # Disabled plugins (in plugins/disabled/ directory)
    disabled_dir = plugins_dir / OBSE64_DISABLED_FOLDER
    if disabled_dir.exists():
        for plugin in disabled_dir.glob("*.dll"):
            if plugin.is_file():
                disabled.append(plugin.name)

    return sorted(enabled), sorted(disabled)

def activate_obse_plugin(game_root: str | Path, plugin_name: str) -> bool:
    """Move plugin from disabled to enabled directory."""
    plugins_dir = get_obse_plugins_dir(game_root)
    if not plugins_dir:
        return False

    disabled_dir = plugins_dir / OBSE64_DISABLED_FOLDER
    src_path = disabled_dir / plugin_name
    dest_path = plugins_dir / plugin_name

    if not src_path.exists():
        return False

    try:
        if dest_path.exists():
            dest_path.unlink()  # Remove existing
        shutil.move(str(src_path), str(dest_path))
        return True
    except Exception as e:
        if DEBUG:
            print(f"Plugin activation error: {e}")
        return False

def deactivate_obse_plugin(game_root: str | Path, plugin_name: str) -> bool:
    """Move plugin from enabled to disabled directory."""
    plugins_dir = get_obse_plugins_dir(game_root)
    if not plugins_dir:
        return False

    disabled_dir = plugins_dir / OBSE64_DISABLED_FOLDER
    disabled_dir.mkdir(exist_ok=True)
    
    src_path = plugins_dir / plugin_name
    dest_path = disabled_dir / plugin_name

    if not src_path.exists():
        return False

    try:
        if dest_path.exists():
            dest_path.unlink()  # Remove existing
        shutil.move(str(src_path), str(dest_path))
        return True
    except Exception as e:
        if DEBUG:
            print(f"Plugin deactivation error: {e}")
        return False

# ---------------------------------------------------------------------------
# Launch helper
# ---------------------------------------------------------------------------

def launch_obse64(game_root: str | Path) -> bool:
    """Launch the game via OBSE64 loader."""
    obse_dir = get_obse64_dir(game_root)
    if not obse_dir:
        return False

    loader_path = obse_dir / OBSE64_LOADER
    if not loader_path.exists():
        return False

    try:
        subprocess.Popen([str(loader_path)], cwd=str(obse_dir))
        return True
    except Exception as e:
        if DEBUG:
            print(f"Launch error: {e}")
        return False 