import os
import shutil
import glob
from pathlib import Path
from .utils import get_game_path, load_pak_mods, save_pak_mods, get_custom_mod_dir_name, delete_display_info

# --- Dynamic PAK Directory Discovery ---
# Instead of hardcoding the full path, we search for the correct directory structure
# This allows compatibility with different install types (Steam, Xbox, etc.)
# The manager will find the active PAK mods directory (~mods) and create/manage the disabled directory as a sibling.
# This is robust to different install layouts and future-proofs the mod manager.
TARGET_PAK_SUFFIX = lambda: os.path.join("Content", "Paks", get_custom_mod_dir_name())
DISABLED_FOLDER_NAME = "DisabledMods"
# --------------------------------------

def _find_pak_path_suffix(base_path, target_suffix):
    """
    Recursively search for a directory whose absolute path ends with target_suffix.
    This allows the mod manager to work with different install layouts (Steam, Xbox, etc.).
    Returns the first match found, or None if not found.
    """
    if not os.path.isdir(base_path):
        return None
    for root, dirs, files in os.walk(base_path):
        if root.endswith(target_suffix):
            return root
    return None

# The primary file extension for PAK mods
PAK_EXTENSION = '.pak'

# Common additional extensions that might be used with PAK mods
# Not required, but will be handled if present
RELATED_EXTENSIONS = ['.ucas', '.utoc']

def get_pak_target_dir(game_path):
    """
    Dynamically find the absolute path to the active PAK mods directory (~mods).
    This supports different install types by searching for the correct directory suffix.
    Returns None if not found.
    """
    if not game_path or not os.path.isdir(game_path):
        print(f"Error: Invalid game path: {game_path}")
        return None
    target_dir = _find_pak_path_suffix(game_path, TARGET_PAK_SUFFIX())
    if not target_dir:
        print(f"Error: Could not find active PAK directory ending in '{TARGET_PAK_SUFFIX()}' within {game_path}")
        return None
    return target_dir

def get_disabled_pak_dir(game_path):
    """
    Return the disabled PAK mods directory as a sibling to the Paks directory.
    """
    if not game_path or not os.path.isdir(game_path):
        print(f"Error: Invalid game path: {game_path}")
        return None
    paks_root = get_paks_root_dir(game_path)
    if not paks_root:
        print(f"Error: Could not find Paks root directory in {game_path}")
        return None
    obvdata_root = os.path.dirname(paks_root)
    disabled_dir = os.path.join(obvdata_root, DISABLED_FOLDER_NAME)
    os.makedirs(disabled_dir, exist_ok=True)
    return disabled_dir

DEFAULT_PAK_FILES = {
    "OblivionRemastered-WinGDK.pak",
    "OblivionRemastered-WinGDK.ucas",
    "OblivionRemastered-WinGDK.utoc",
    "global.ucas",
    "global.utoc",
}

def is_default_pak_file(filename):
    return os.path.basename(filename) in DEFAULT_PAK_FILES

def list_managed_paks():
    """
    Get the list of currently managed PAK mods, excluding default game files.
    """
    return [pak for pak in load_pak_mods() if not is_default_pak_file(pak.get("name", ""))]

def get_related_files(directory, base_name):
    """
    Find all files in a directory with the same base name but any extension.
    
    Args:
        directory (str): Directory to search
        base_name (str): Base name of the file without extension
        
    Returns:
        list: List of file paths with the same base name
    """
    related_files = []
    
    # Get all files in the directory
    try:
        all_files = os.listdir(directory)
        for filename in all_files:
            file_base_name = os.path.splitext(filename)[0]
            if file_base_name == base_name:
                file_path = os.path.join(directory, filename)
                if os.path.isfile(file_path):
                    related_files.append(file_path)
    except Exception as e:
        print(f"Error searching for related files: {str(e)}")
    
    return related_files

def add_pak(game_path, source_pak_path, target_subfolder=None):
    """
    Copy the PAK file and any related files to the game's ~mods directory (inside Paks root) and add it to the managed list.
    """
    ensure_paks_structure(game_path)
    paks_root = get_paks_root_dir(game_path)
    if not paks_root:
        print(f"Error: Could not find Paks root directory in {game_path}")
        return False
    mods_dir = os.path.join(paks_root, get_custom_mod_dir_name())
    # If a subfolder is specified, append it to the ~mods directory
    target_dir = mods_dir
    if target_subfolder:
        target_dir = os.path.join(mods_dir, target_subfolder)
    # Validate source path
    if not source_pak_path or not os.path.isfile(source_pak_path):
        print(f"Error: Invalid source file: {source_pak_path}")
        return False
    # Check the file extension - must be .pak
    file_ext = os.path.splitext(source_pak_path)[1].lower()
    if file_ext != PAK_EXTENSION:
        print(f"Error: Source file must be a .pak file, got: {file_ext}")
        return False
    # Get the base name without extension
    source_base_name = os.path.splitext(os.path.basename(source_pak_path))[0]
    source_dir = os.path.dirname(source_pak_path)
    # Find all related files in the source directory with the same base name
    related_files = get_related_files(source_dir, source_base_name)
    # Make sure the PAK file is included in the related files
    if source_pak_path not in related_files:
        related_files.append(source_pak_path)
    # Check if the PAK file already exists in the target directory
    target_pak_path = os.path.join(target_dir, f"{source_base_name}{PAK_EXTENSION}")
    if os.path.exists(target_pak_path):
        print(f"Error: PAK file already exists at {target_pak_path}")
        return False
    try:
        # Ensure target directory exists
        os.makedirs(target_dir, exist_ok=True)
        # Copy all related files
        copied_files = []
        for source_file in related_files:
            filename = os.path.basename(source_file)
            target_file = os.path.join(target_dir, filename)
            if os.path.exists(target_file):
                print(f"Warning: File already exists, skipping: {target_file}")
                continue
            shutil.copy2(source_file, target_file)
            copied_files.append(target_file)
            print(f"Copied: {filename}")
        pak_mods = load_pak_mods()
        extensions = sorted(set(os.path.splitext(f)[1].lower() for f in copied_files))
        new_pak = {
            "name": f"{source_base_name}{PAK_EXTENSION}",
            "base_name": source_base_name,
            "files": copied_files,
            "extensions": extensions,
            "subfolder": target_subfolder,
            "installed_date": None,
            "active": True
        }
        pak_mods.append(new_pak)
        if save_pak_mods(pak_mods):
            subfolder_info = f" in subfolder '{target_subfolder}'" if target_subfolder else ""
            print(f"Success: Added PAK mod {source_base_name}{subfolder_info} with extensions: {', '.join(extensions)}")
            return True
        else:
            print(f"Error: Failed to update PAK mods list after adding {source_base_name}")
            for file_path in copied_files:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
            return False
    except Exception as e:
        print(f"Error adding PAK mod {source_base_name}: {str(e)}")
        for source_file in related_files:
            filename = os.path.basename(source_file)
            target_file = os.path.join(target_dir, filename)
            if os.path.exists(target_file):
                try:
                    os.remove(target_file)
                except Exception:
                    pass
        return False

def remove_pak(game_path, pak_name):
    """
    Remove a PAK file and all related files from the ~mods directory (inside Paks root) and the managed list.
    """
    ensure_paks_structure(game_path)
    paks_root = get_paks_root_dir(game_path)
    if not paks_root:
        return False
    mods_dir = os.path.join(paks_root, get_custom_mod_dir_name())
    base_name = os.path.splitext(pak_name)[0]
    pak_mods = load_pak_mods()
    pak_entry = None
    pak_index = -1
    for i, entry in enumerate(pak_mods):
        if entry.get("name") == pak_name:
            pak_entry = entry
            pak_index = i
            break
    if pak_index == -1:
        print(f"Error: PAK mod {pak_name} not found in managed list")
        return False
    files_to_remove = []
    if "files" in pak_entry and pak_entry["files"]:
        files_to_remove = pak_entry["files"]
    else:
        subfolder = pak_entry.get("subfolder")
        mod_dir = mods_dir
        if subfolder:
            mod_dir = os.path.join(mods_dir, subfolder)
        files_to_remove = get_related_files(mod_dir, base_name)
    try:
        removed_files = []
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                os.remove(file_path)
                removed_files.append(file_path)
                print(f"Removed file: {os.path.basename(file_path)}")
        if not removed_files:
            print(f"Warning: No files found for PAK mod {pak_name}, removing from list only")
        if pak_entry.get("subfolder"):
            subfolder_path = os.path.join(mods_dir, pak_entry["subfolder"])
            if os.path.exists(subfolder_path) and os.path.isdir(subfolder_path):
                if not os.listdir(subfolder_path):
                    os.rmdir(subfolder_path)
                    print(f"Removed empty subfolder: {pak_entry['subfolder']}")
        pak_mods.pop(pak_index)
        if save_pak_mods(pak_mods):
            print(f"Success: Removed PAK mod {pak_name} from managed list")
            # Remove display info entry
            mod_id = f"{pak_entry.get('subfolder','')}|{pak_entry['name']}"
            delete_display_info(mod_id)
            return True
        else:
            print(f"Error: Failed to update PAK mods list after removing {pak_name}")
            return False
    except Exception as e:
        print(f"Error removing PAK mod {pak_name}: {str(e)}")
        return False

def deactivate_pak(game_path, pak_info):
    """
    Move a PAK mod from the active directory to the disabled directory.
    
    Args:
        game_path (str): The game installation path
        pak_info (dict): PAK mod information dictionary
        
    Returns:
        bool: True if successful, False otherwise
    """
    paks_root = get_paks_root_dir(game_path)
    if not paks_root:
        return False
    disabled_dir = get_disabled_pak_dir(game_path)
    if not disabled_dir:
        return False
        
    # Handle regular mods vs LogicMods differently
    subfolder = pak_info.get("subfolder")
    if subfolder and subfolder.startswith("LogicMods"):
        # This is a LogicMods pak file
        if subfolder == "LogicMods":
            # It's directly in LogicMods folder
            source_dir = os.path.join(paks_root, "LogicMods")
            target_dir = disabled_dir  # Move to root of disabled dir
        else:
            # It's in a subfolder of LogicMods
            # Extract the part after "LogicMods/"
            subpath = subfolder[len("LogicMods")+1:]  # +1 for the path separator
            source_dir = os.path.join(paks_root, "LogicMods", subpath)
            target_dir = os.path.join(disabled_dir, subpath)
            os.makedirs(target_dir, exist_ok=True)
    else:
        # Regular mod in ~mods directory
        source_dir = get_pak_target_dir(game_path)
        if not source_dir:
            return False
            
        if subfolder:
            source_dir = os.path.join(source_dir, subfolder)
            target_dir = os.path.join(disabled_dir, subfolder)
            os.makedirs(target_dir, exist_ok=True)
        else:
            target_dir = disabled_dir
    
    # Get all files to move
    files_to_move = []
    if "files" in pak_info and pak_info["files"]:
        files_to_move = pak_info["files"]
    else:
        # Fall back to searching
        files_to_move = get_related_files(source_dir, pak_info["base_name"])
    
    # Keep track of moved files and their new locations
    moved_files = []
    try:
        for source_file in files_to_move:
            if os.path.exists(source_file):
                # Get the file name
                file_name = os.path.basename(source_file)
                target_file = os.path.join(target_dir, file_name)
                
                # Move the file
                shutil.move(source_file, target_file)
                moved_files.append((source_file, target_file))
                print(f"Moved {file_name} to disabled folder")
        
        # Update the PAK mod entry in the list
        pak_mods = load_pak_mods()
        for pak in pak_mods:
            if (pak.get("name") == pak_info.get("name") and 
                pak.get("subfolder") == pak_info.get("subfolder")):
                # Update the files list with new paths
                pak["files"] = [target for _, target in moved_files]
                # Mark as disabled
                pak["active"] = False
                
                # Remember if this was from LogicMods to restore correctly later
                if subfolder and subfolder.startswith("LogicMods"):
                    pak["from_logicmods"] = True
                
                break
        
        # Save the updated list
        if save_pak_mods(pak_mods):
            # Clean up empty folders
            if pak_info.get("subfolder"):
                # Check if source subfolder is empty
                if os.path.exists(source_dir) and not os.listdir(source_dir):
                    os.rmdir(source_dir)
                    print(f"Removed empty subfolder: {subfolder}")
            
            print(f"PAK mod {pak_info['name']} successfully deactivated")
            return True
        else:
            # Undo the file moves if saving the list failed
            for source, target in moved_files:
                source_dir = os.path.dirname(source)
                os.makedirs(source_dir, exist_ok=True)
                shutil.move(target, source)
            print(f"Failed to save PAK mod list, changes reverted")
            return False
            
    except Exception as e:
        print(f"Error deactivating PAK mod: {str(e)}")
        # Attempt to undo any moves that succeeded
        for source, target in moved_files:
            try:
                source_dir = os.path.dirname(source)
                os.makedirs(source_dir, exist_ok=True)
                shutil.move(target, source)
            except Exception:
                pass
        return False

def activate_pak(game_path, pak_info):
    """
    Move a PAK mod from the disabled directory to the active directory.
    
    Args:
        game_path (str): The game installation path
        pak_info (dict): PAK mod information dictionary
        
    Returns:
        bool: True if successful, False otherwise
    """
    paks_root = get_paks_root_dir(game_path)
    if not paks_root:
        return False
    disabled_dir = get_disabled_pak_dir(game_path)
    if not disabled_dir:
        return False
        
    # Handle regular mods vs LogicMods differently
    subfolder = pak_info.get("subfolder")
    if subfolder and subfolder.startswith("DisabledMods"):
        # This is a disabled mod that was originally from LogicMods or regular folder
        if subfolder == "DisabledMods":
            # It's directly in DisabledMods folder, move back to LogicMods
            source_dir = disabled_dir
            # Determine if it was originally from LogicMods based on metadata
            if pak_info.get("from_logicmods", False):
                target_dir = os.path.join(paks_root, "LogicMods")
                # Update subfolder in pak_info
                pak_info["subfolder"] = "LogicMods"
            else:
                target_dir = get_pak_target_dir(game_path)
                # Reset subfolder in pak_info
                pak_info["subfolder"] = None
        else:
            # It's in a subfolder of DisabledMods
            # Extract the part after "DisabledMods/"
            subpath = subfolder[len("DisabledMods")+1:]
            source_dir = os.path.join(disabled_dir, subpath)
            
            # Determine if it was originally from LogicMods based on metadata
            if pak_info.get("from_logicmods", False) or subpath.startswith("LogicMods"):
                # If it was from LogicMods or the subpath still indicates LogicMods
                if subpath.startswith("LogicMods"):
                    # The subpath already contains LogicMods prefix
                    logicmods_subpath = subpath[len("LogicMods")+1:]  # +1 for separator
                    target_dir = os.path.join(paks_root, "LogicMods", logicmods_subpath)
                    pak_info["subfolder"] = subpath  # Keep the full path
                else:
                    target_dir = os.path.join(paks_root, "LogicMods", subpath)
                    pak_info["subfolder"] = f"LogicMods/{subpath}"
            else:
                target_dir = os.path.join(get_pak_target_dir(game_path), subpath)
                pak_info["subfolder"] = subpath
            
            os.makedirs(target_dir, exist_ok=True)
    else:
        # Normal case - it's a regular subfolder or no subfolder
        target_dir = get_pak_target_dir(game_path)
        if not target_dir:
            return False
            
        if subfolder:
            source_dir = os.path.join(disabled_dir, subfolder)
            target_dir = os.path.join(target_dir, subfolder)
            os.makedirs(target_dir, exist_ok=True)
        else:
            source_dir = disabled_dir
    
    # Get all files to move
    files_to_move = []
    if "files" in pak_info and pak_info["files"]:
        files_to_move = pak_info["files"]
    else:
        # Fall back to searching
        files_to_move = get_related_files(source_dir, pak_info["base_name"])
    
    # Keep track of moved files and their new locations
    moved_files = []
    try:
        for source_file in files_to_move:
            if os.path.exists(source_file):
                # Get the file name
                file_name = os.path.basename(source_file)
                target_file = os.path.join(target_dir, file_name)
                
                # Move the file
                shutil.move(source_file, target_file)
                moved_files.append((source_file, target_file))
                print(f"Moved {file_name} to active folder")
        
        # Update the PAK mod entry in the list
        pak_mods = load_pak_mods()
        for pak in pak_mods:
            if (pak.get("name") == pak_info.get("name") and 
                pak.get("subfolder") == pak_info.get("subfolder")):
                # Update the files list with new paths
                pak["files"] = [target for _, target in moved_files]
                # Mark as active
                pak["active"] = True
                break
        
        # Save the updated list
        if save_pak_mods(pak_mods):
            # Clean up empty folders
            if pak_info.get("subfolder"):
                # Check if disabled subfolder is empty
                disabled_subfolder = os.path.join(disabled_dir, pak_info["subfolder"])
                if os.path.exists(disabled_subfolder) and not os.listdir(disabled_subfolder):
                    os.rmdir(disabled_subfolder)
                    print(f"Removed empty disabled subfolder: {pak_info['subfolder']}")
            
            print(f"PAK mod {pak_info['name']} successfully activated")
            return True
        else:
            # Undo the file moves if saving the list failed
            for source, target in moved_files:
                source_dir = os.path.dirname(source)
                os.makedirs(source_dir, exist_ok=True)
                shutil.move(target, source)
            print(f"Failed to save PAK mod list, changes reverted")
            return False
            
    except Exception as e:
        print(f"Error activating PAK mod: {str(e)}")
        # Attempt to undo any moves that succeeded
        for source, target in moved_files:
            try:
                source_dir = os.path.dirname(source)
                os.makedirs(source_dir, exist_ok=True)
                shutil.move(target, source)
            except Exception:
                pass
        return False

def scan_for_installed_paks(game_path):
    """
    Scan the Paks root for installed PAK mods (recursively in all subfolders except LogicMods and disabled), excluding default game files.
    """
    ensure_paks_structure(game_path)
    paks_root = get_paks_root_dir(game_path)
    if not paks_root or not os.path.isdir(paks_root):
        return []
    found_paks = []
    # Walk all subfolders in custom mods dir except disabled
    mods_dir = os.path.join(paks_root, get_custom_mod_dir_name())
    if os.path.isdir(mods_dir):
        for root, dirs, files in os.walk(mods_dir):
            # Skip disabled
            rel = os.path.relpath(root, mods_dir)
            parts = rel.split(os.sep)
            if DISABLED_FOLDER_NAME in parts:
                continue
            pak_files = [f for f in files if f.lower().endswith(PAK_EXTENSION) and not is_default_pak_file(f)]
            subfolder = None if rel == "." else rel
            for pak_file in pak_files:
                base_name = os.path.splitext(pak_file)[0]
                related_files = get_related_files(root, base_name)
                # Exclude if any related file is a default file
                if any(is_default_pak_file(f) for f in related_files):
                    continue
                pak_path = os.path.join(root, pak_file)
                if pak_path not in related_files:
                    related_files.append(pak_path)
                extensions = sorted(set(os.path.splitext(f)[1].lower() for f in related_files))
                found_paks.append({
                    "name": pak_file,
                    "base_name": base_name,
                    "files": related_files,
                    "extensions": extensions,
                    "subfolder": subfolder,
                    "active": True
                })
                
    # Also scan LogicMods directory
    logicmods_dir = os.path.join(paks_root, "LogicMods")
    if os.path.isdir(logicmods_dir):
        for root, dirs, files in os.walk(logicmods_dir):
            rel = os.path.relpath(root, logicmods_dir)
            pak_files = [f for f in files if f.lower().endswith(PAK_EXTENSION) and not is_default_pak_file(f)]
            subfolder = "LogicMods" if rel == "." else os.path.join("LogicMods", rel)
            for pak_file in pak_files:
                base_name = os.path.splitext(pak_file)[0]
                related_files = get_related_files(root, base_name)
                if any(is_default_pak_file(f) for f in related_files):
                    continue
                pak_path = os.path.join(root, pak_file)
                if pak_path not in related_files:
                    related_files.append(pak_path)
                extensions = sorted(set(os.path.splitext(f)[1].lower() for f in related_files))
                found_paks.append({
                    "name": pak_file,
                    "base_name": base_name,
                    "files": related_files,
                    "extensions": extensions,
                    "subfolder": subfolder,
                    "active": True
                })
                
    # Scan disabled mods as before, but use relative to disabled_dir
    disabled_dir = get_disabled_pak_dir(game_path)
    if disabled_dir:
        for root, dirs, files in os.walk(disabled_dir):
            rel = os.path.relpath(root, disabled_dir)
            pak_files = [f for f in files if f.lower().endswith(PAK_EXTENSION) and not is_default_pak_file(f)]
            subfolder = "DisabledMods" if rel == "." else os.path.join("DisabledMods", rel)
            for pak_file in pak_files:
                base_name = os.path.splitext(pak_file)[0]
                related_files = get_related_files(root, base_name)
                if any(is_default_pak_file(f) for f in related_files):
                    continue
                pak_path = os.path.join(root, pak_file)
                if pak_path not in related_files:
                    related_files.append(pak_path)
                extensions = sorted(set(os.path.splitext(f)[1].lower() for f in related_files))
                found_paks.append({
                    "name": pak_file,
                    "base_name": base_name,
                    "files": related_files,
                    "extensions": extensions,
                    "subfolder": subfolder,
                    "active": False
                })
    return found_paks

def reconcile_pak_list(game_path):
    """
    Reconcile the managed PAK list with what's actually installed.
    Adds missing entries and removes entries for non-existent files.
    Uses .pak files as the source of truth.
    
    Args:
        game_path (str): The game installation path
        
    Returns:
        bool: True if changes were made, False otherwise
    """
    # Scan for installed PAKs (including in subfolders and disabled folder)
    installed_paks = scan_for_installed_paks(game_path)
    
    # Load the current PAK mods list
    managed_paks = load_pak_mods()
    
    # One-time fix for already-stored "tMods" duplicates
    custom = get_custom_mod_dir_name()
    for pak in managed_paks:
        if pak.get("subfolder") == custom:
            pak["subfolder"] = None
    
    # Create identifier tuples for comparison (name + subfolder + active status)
    installed_ids = {(pak["name"], pak.get("subfolder"), pak.get("active", True)) for pak in installed_paks}
    managed_ids = {(pak["name"], pak.get("subfolder"), pak.get("active", True)) for pak in managed_paks}
    
    # Find PAKs to add (installed but not managed)
    paks_to_add = installed_ids - managed_ids
    
    # Find PAKs to remove (managed but not installed)
    paks_to_remove = managed_ids - installed_ids
    
    # Make changes if needed
    changes_made = False
    
    # Add missing PAKs
    for pak_id in paks_to_add:
        pak_name, subfolder, active = pak_id
        for pak in installed_paks:
            if (pak["name"] == pak_name and 
                pak.get("subfolder") == subfolder and 
                pak.get("active", True) == active):
                managed_paks.append(pak)
                changes_made = True
                subfolder_info = f" in subfolder '{subfolder}'" if subfolder else ""
                active_status = "active" if active else "disabled"
                print(f"Added existing {active_status} PAK mod to list: {pak_name}{subfolder_info}")
                break
    
    # Remove entries for non-existent PAKs
    for i in range(len(managed_paks) - 1, -1, -1):
        pak_id = (
            managed_paks[i]["name"], 
            managed_paks[i].get("subfolder"), 
            managed_paks[i].get("active", True)
        )
        if pak_id in paks_to_remove:
            subfolder_info = f" in subfolder '{managed_paks[i].get('subfolder')}'" if managed_paks[i].get("subfolder") else ""
            active_status = "active" if managed_paks[i].get("active", True) else "disabled"
            print(f"Removed non-existent {active_status} PAK mod from list: {managed_paks[i]['name']}{subfolder_info}")
            managed_paks.pop(i)
            changes_made = True
    
    # Save changes if any were made
    if changes_made:
        save_pak_mods(managed_paks)
        print("Updated PAK mods list to match installed files")
    
    return changes_made

def create_subfolder(game_path, subfolder_name):
    """
    Create a subfolder in the PAK mods directory.
    
    Args:
        game_path (str): The game installation path
        subfolder_name (str): Name of the subfolder to create
        
    Returns:
        str or None: Path to the created subfolder, or None if failed
    """
    target_dir = get_pak_target_dir(game_path)
    if not target_dir:
        return None
        
    # Create the full path to the subfolder
    subfolder_path = os.path.join(target_dir, subfolder_name)
    
    try:
        # Create the directory if it doesn't exist
        os.makedirs(subfolder_path, exist_ok=True)
        return subfolder_path
    except Exception as e:
        print(f"Error creating subfolder {subfolder_name}: {str(e)}")
        return None

def get_paks_root_dir(game_path):
    """
    Search for a directory named 'Paks' under the game path and return its absolute path.
    Returns None if not found.
    """
    if not game_path or not os.path.isdir(game_path):
        return None
    for root, dirs, files in os.walk(game_path):
        for d in dirs:
            if d.lower() == "paks":
                return os.path.join(root, d)
    return None

def ensure_paks_structure(game_path):
    """
    Ensure that both ~mods and LogicMods exist in the Paks root directory.
    Returns the Paks root directory, or None if not found.
    """
    paks_root = get_paks_root_dir(game_path)
    if not paks_root:
        return None
    mods_dir = os.path.join(paks_root, get_custom_mod_dir_name())
    logicmods_dir = os.path.join(paks_root, "LogicMods")
    obvdata_root = os.path.dirname(paks_root)
    disabled_dir = os.path.join(obvdata_root, DISABLED_FOLDER_NAME)
    os.makedirs(mods_dir, exist_ok=True)
    os.makedirs(logicmods_dir, exist_ok=True)
    os.makedirs(disabled_dir, exist_ok=True)
    return paks_root 