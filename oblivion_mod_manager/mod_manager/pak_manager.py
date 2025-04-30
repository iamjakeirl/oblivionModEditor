import os
import shutil
import glob
from pathlib import Path
from .utils import get_game_path, load_pak_mods, save_pak_mods

# --- !! IMPORTANT !! ---
# Verify this relative path based on Oblivion Remastered's structure
# According to user info, PAK mods are stored in:
# The Elder Scrolls IV- Oblivion Remastered\Content\OblivionRemastered\Content\Paks\~mods
PAK_SUBDIR = "Content/OblivionRemastered/Content/Paks/~mods"
DISABLED_PAK_SUBDIR = "Content/OblivionRemastered/Content/Paks/disabled"
# ---

# The primary file extension for PAK mods
PAK_EXTENSION = '.pak'

# Common additional extensions that might be used with PAK mods
# Not required, but will be handled if present
RELATED_EXTENSIONS = ['.ucas', '.utoc']

def get_pak_target_dir(game_path):
    """
    Get the absolute path to the PAK mods directory.
    
    Args:
        game_path (str): The game installation path
        
    Returns:
        str or None: Absolute path to the PAK directory or None if invalid
    """
    if not game_path or not os.path.isdir(game_path):
        print(f"Error: Invalid game path: {game_path}")
        return None
        
    target_dir = os.path.join(game_path, PAK_SUBDIR)
    return target_dir

def get_disabled_pak_dir(game_path):
    """
    Get the absolute path to the disabled PAK mods directory.
    
    Args:
        game_path (str): The game installation path
        
    Returns:
        str or None: Absolute path to the disabled PAK directory or None if invalid
    """
    if not game_path or not os.path.isdir(game_path):
        print(f"Error: Invalid game path: {game_path}")
        return None
        
    disabled_dir = os.path.join(game_path, DISABLED_PAK_SUBDIR)
    # Make sure the directory exists
    os.makedirs(disabled_dir, exist_ok=True)
    return disabled_dir

def list_managed_paks():
    """
    Get the list of currently managed PAK mods.
    
    Returns:
        list: List of PAK mod entries
    """
    return load_pak_mods()

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
    Copy the PAK file and any related files to the game's PAK mods directory and add it to the managed list.
    
    Args:
        game_path (str): The game installation path
        source_pak_path (str): Path to the source PAK file
        target_subfolder (str, optional): Subfolder within ~mods to place the PAK in
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Get target directory
    target_dir = get_pak_target_dir(game_path)
    if not target_dir:
        return False
        
    # If a subfolder is specified, append it to the target directory
    if target_subfolder:
        target_dir = os.path.join(target_dir, target_subfolder)
        
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
            # Get just the filename part
            filename = os.path.basename(source_file)
            target_file = os.path.join(target_dir, filename)
            
            # Skip if target already exists (shouldn't happen, but just in case)
            if os.path.exists(target_file):
                print(f"Warning: File already exists, skipping: {target_file}")
                continue
                
            # Copy the file
            shutil.copy2(source_file, target_file)
            copied_files.append(target_file)
            print(f"Copied: {filename}")
        
        # Update the managed PAKs list
        pak_mods = load_pak_mods()
        
        # Get the file extensions for display
        extensions = sorted(set(os.path.splitext(f)[1].lower() for f in copied_files))
        
        # Create a new entry
        new_pak = {
            "name": f"{source_base_name}{PAK_EXTENSION}",  # Use .pak as the main identifier
            "base_name": source_base_name,
            "files": copied_files,
            "extensions": extensions,
            "subfolder": target_subfolder,  # Store the subfolder information
            "installed_date": None,  # Could add datetime.now().isoformat() if desired
            "active": True
        }
        
        pak_mods.append(new_pak)
        
        # Save the updated list
        if save_pak_mods(pak_mods):
            subfolder_info = f" in subfolder '{target_subfolder}'" if target_subfolder else ""
            print(f"Success: Added PAK mod {source_base_name}{subfolder_info} with extensions: {', '.join(extensions)}")
            return True
        else:
            print(f"Error: Failed to update PAK mods list after adding {source_base_name}")
            # Clean up copied files if list update fails
            for file_path in copied_files:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
            return False
            
    except Exception as e:
        print(f"Error adding PAK mod {source_base_name}: {str(e)}")
        # Clean up any copied files
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
    Remove a PAK file and all related files from the game's PAK mods directory and the managed list.
    
    Args:
        game_path (str): The game installation path
        pak_name (str): Name of the PAK file (with .pak extension)
        
    Returns:
        bool: True if successful, False otherwise
    """
    # Get target directory
    target_dir = get_pak_target_dir(game_path)
    if not target_dir:
        return False
    
    # Extract the base name without extension
    base_name = os.path.splitext(pak_name)[0]
    
    # Load current PAK mods list
    pak_mods = load_pak_mods()
    
    # Find the entry for the PAK
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
    
    # Find all related files to remove
    files_to_remove = []
    if "files" in pak_entry and pak_entry["files"]:
        # Use the files list if available
        files_to_remove = pak_entry["files"]
    else:
        # Check if the mod is in a subfolder
        subfolder = pak_entry.get("subfolder")
        mod_dir = target_dir
        if subfolder:
            mod_dir = os.path.join(target_dir, subfolder)
            
        # Fall back to searching for files with the base name
        files_to_remove = get_related_files(mod_dir, base_name)
    
    try:
        # Remove all related files
        removed_files = []
        for file_path in files_to_remove:
            if os.path.exists(file_path):
                os.remove(file_path)
                removed_files.append(file_path)
                print(f"Removed file: {os.path.basename(file_path)}")
        
        # If no files were found, print a warning
        if not removed_files:
            print(f"Warning: No files found for PAK mod {pak_name}, removing from list only")
        
        # Check if we need to remove an empty subfolder
        if pak_entry.get("subfolder"):
            subfolder_path = os.path.join(target_dir, pak_entry["subfolder"])
            if os.path.exists(subfolder_path) and os.path.isdir(subfolder_path):
                # Check if the directory is empty
                if not os.listdir(subfolder_path):
                    os.rmdir(subfolder_path)
                    print(f"Removed empty subfolder: {pak_entry['subfolder']}")
        
        # Remove the entry from the list
        pak_mods.pop(pak_index)
        
        # Save the updated list
        if save_pak_mods(pak_mods):
            print(f"Success: Removed PAK mod {pak_name} from managed list")
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
    # Get the source and target directories
    source_dir = get_pak_target_dir(game_path)
    if not source_dir:
        return False
        
    disabled_dir = get_disabled_pak_dir(game_path)
    if not disabled_dir:
        return False
    
    # Get the subfolder path if any
    if pak_info.get("subfolder"):
        source_dir = os.path.join(source_dir, pak_info["subfolder"])
        # Create matching subfolder in disabled directory
        disabled_subfolder = os.path.join(disabled_dir, pak_info["subfolder"])
        os.makedirs(disabled_subfolder, exist_ok=True)
        target_dir = disabled_subfolder
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
                break
        
        # Save the updated list
        if save_pak_mods(pak_mods):
            # Clean up empty folders
            if pak_info.get("subfolder"):
                # Check if source subfolder is empty
                if os.path.exists(source_dir) and not os.listdir(source_dir):
                    os.rmdir(source_dir)
                    print(f"Removed empty subfolder: {pak_info['subfolder']}")
            
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
    # Get the source and target directories
    disabled_dir = get_disabled_pak_dir(game_path)
    if not disabled_dir:
        return False
        
    target_dir = get_pak_target_dir(game_path)
    if not target_dir:
        return False
    
    # Get the subfolder path if any
    if pak_info.get("subfolder"):
        disabled_subfolder = os.path.join(disabled_dir, pak_info["subfolder"])
        source_dir = disabled_subfolder
        # Create matching subfolder in active directory
        target_subfolder = os.path.join(target_dir, pak_info["subfolder"])
        os.makedirs(target_subfolder, exist_ok=True)
        target_dir = target_subfolder
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
    Scan the PAK directory for installed PAK mods that might not be in our list.
    Uses .pak files as the source of truth.
    Includes checking in subdirectories.
    Includes both active and disabled mods.
    
    Args:
        game_path (str): The game installation path
        
    Returns:
        list: List of dictionaries with information about found PAK mods
    """
    found_paks = []
    
    # Scan active mods first
    target_dir = get_pak_target_dir(game_path)
    if target_dir and os.path.isdir(target_dir):
        # Walk through all subdirectories in the target directory
        for root, dirs, files in os.walk(target_dir):
            # Get PAK files in the current directory
            pak_files = [f for f in files if f.lower().endswith(PAK_EXTENSION)]
            
            # Calculate the subfolder if we're not in the root target directory
            subfolder = None
            if root != target_dir:
                rel_path = os.path.relpath(root, target_dir)
                subfolder = rel_path
            
            # Process each PAK file
            for pak_file in pak_files:
                # Get base name
                base_name = os.path.splitext(pak_file)[0]
                
                # Find all related files in the same directory
                related_files = get_related_files(root, base_name)
                
                # Make sure the PAK file is included
                pak_path = os.path.join(root, pak_file)
                if pak_path not in related_files:
                    related_files.append(pak_path)
                
                # Get the file extensions for display
                extensions = sorted(set(os.path.splitext(f)[1].lower() for f in related_files))
                
                # Add entry to the list
                found_paks.append({
                    "name": pak_file,
                    "base_name": base_name,
                    "files": related_files,
                    "extensions": extensions,
                    "subfolder": subfolder,
                    "active": True
                })
    
    # Scan disabled mods
    disabled_dir = get_disabled_pak_dir(game_path)
    if disabled_dir and os.path.isdir(disabled_dir):
        # Walk through all subdirectories in the disabled directory
        for root, dirs, files in os.walk(disabled_dir):
            # Get PAK files in the current directory
            pak_files = [f for f in files if f.lower().endswith(PAK_EXTENSION)]
            
            # Calculate the subfolder if we're not in the root disabled directory
            subfolder = None
            if root != disabled_dir:
                rel_path = os.path.relpath(root, disabled_dir)
                subfolder = rel_path
            
            # Process each PAK file
            for pak_file in pak_files:
                # Get base name
                base_name = os.path.splitext(pak_file)[0]
                
                # Find all related files in the same directory
                related_files = get_related_files(root, base_name)
                
                # Make sure the PAK file is included
                pak_path = os.path.join(root, pak_file)
                if pak_path not in related_files:
                    related_files.append(pak_path)
                
                # Get the file extensions for display
                extensions = sorted(set(os.path.splitext(f)[1].lower() for f in related_files))
                
                # Add entry to the list
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