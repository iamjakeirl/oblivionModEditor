"""
Undo/Redo system for tree operations in the Oblivion Mod Manager.
Focuses on reversible actions within the tree views (enable/disable, rename, group, delete, reorder).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
import json
import shutil
from pathlib import Path
from PyQt5.QtCore import QObject, pyqtSignal


class UndoAction(ABC):
    """Base class for all undoable actions."""
    
    def __init__(self, description: str):
        self.description = description
        
    @abstractmethod
    def execute(self) -> bool:
        """Execute the action. Return True if successful."""
        pass
        
    @abstractmethod
    def undo(self) -> bool:
        """Undo the action. Return True if successful."""
        pass
        
    def __str__(self):
        return self.description


class UndoStack(QObject):
    """Manages the undo/redo stack for tree operations."""
    
    # Signals for UI updates
    canUndoChanged = pyqtSignal(bool)
    canRedoChanged = pyqtSignal(bool)
    undoTextChanged = pyqtSignal(str)
    redoTextChanged = pyqtSignal(str)
    
    def __init__(self, max_actions: int = 50):
        super().__init__()
        self.max_actions = max_actions
        self.actions: List[UndoAction] = []
        self.current_index = -1  # Index of last executed action
        
    def push(self, action: UndoAction) -> bool:
        """Execute and add an action to the stack."""
        print(f'[UNDO-STACK] push called with action: {action.description}')
        # Execute the action first
        if not action.execute():
            print(f'[UNDO-STACK] action.execute() failed for: {action.description}')
            return False
            
        print(f'[UNDO-STACK] action.execute() succeeded for: {action.description}')
        
        # Remove any actions after current index (redo stack)
        if self.current_index < len(self.actions) - 1:
            removed_count = len(self.actions) - self.current_index - 1
            self.actions = self.actions[:self.current_index + 1]
            print(f'[UNDO-STACK] Removed {removed_count} redo actions')
            
        # Add new action
        self.actions.append(action)
        self.current_index += 1
        
        # Limit stack size
        if len(self.actions) > self.max_actions:
            self.actions.pop(0)
            self.current_index -= 1
            print(f'[UNDO-STACK] Trimmed stack to {self.max_actions} actions')
            
        print(f'[UNDO-STACK] Stack now has {len(self.actions)} actions, current_index: {self.current_index}')
        self._emit_signals()
        return True
        
    def undo(self) -> bool:
        """Undo the last action."""
        print(f'[UNDO-STACK] undo() called - can_undo: {self.can_undo()}')
        if not self.can_undo():
            print(f'[UNDO-STACK] Cannot undo - no actions available')
            return False
            
        action = self.actions[self.current_index]
        print(f'[UNDO-STACK] Attempting to undo: {action.description}')
        if action.undo():
            print(f'[UNDO-STACK] Successfully undid: {action.description}')
            self.current_index -= 1
            self._emit_signals()
            return True
        else:
            print(f'[UNDO-STACK] Failed to undo: {action.description}')
        return False
        
    def redo(self) -> bool:
        """Redo the next action."""
        print(f'[UNDO-STACK] redo() called - can_redo: {self.can_redo()}')
        if not self.can_redo():
            print(f'[UNDO-STACK] Cannot redo - no actions available')
            return False
            
        action = self.actions[self.current_index + 1]
        print(f'[UNDO-STACK] Attempting to redo: {action.description}')
        if action.execute():
            print(f'[UNDO-STACK] Successfully redid: {action.description}')
            self.current_index += 1
            self._emit_signals()
            return True
        else:
            print(f'[UNDO-STACK] Failed to redo: {action.description}')
        return False
        
    def can_undo(self) -> bool:
        """Check if undo is possible."""
        return self.current_index >= 0
        
    def can_redo(self) -> bool:
        """Check if redo is possible."""
        return self.current_index < len(self.actions) - 1
        
    def undo_text(self) -> str:
        """Get description of action that would be undone."""
        if self.can_undo():
            return f"Undo {self.actions[self.current_index].description}"
        return "Undo"
        
    def redo_text(self) -> str:
        """Get description of action that would be redone."""
        if self.can_redo():
            return f"Redo {self.actions[self.current_index + 1].description}"
        return "Redo"
        
    def clear(self):
        """Clear the entire undo stack."""
        self.actions.clear()
        self.current_index = -1
        self._emit_signals()
        
    def _emit_signals(self):
        """Emit all relevant signals for UI updates."""
        self.canUndoChanged.emit(self.can_undo())
        self.canRedoChanged.emit(self.can_redo())
        self.undoTextChanged.emit(self.undo_text())
        self.redoTextChanged.emit(self.redo_text())


class StateSnapshot:
    """Captures state that can be restored later."""
    
    def __init__(self):
        self.data: Dict[str, Any] = {}
        
    def capture_file(self, file_path: Path, key: str = None):
        """Capture the current state of a file."""
        if key is None:
            key = str(file_path)
            
        if file_path.exists():
            try:
                if file_path.suffix == '.json':
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.data[key] = json.load(f)
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.data[key] = f.read()
            except Exception:
                self.data[key] = None
        else:
            self.data[key] = None
            
    def capture_directory_state(self, directory: Path, key: str):
        """Capture which files exist in a directory."""
        if directory.exists():
            self.data[key] = [f.name for f in directory.iterdir() if f.is_file()]
        else:
            self.data[key] = []
            
    def restore_file(self, file_path: Path, key: str = None) -> bool:
        """Restore a file to its captured state."""
        if key is None:
            key = str(file_path)
            
        if key not in self.data:
            return False
            
        try:
            if self.data[key] is None:
                # File didn't exist, remove it
                if file_path.exists():
                    file_path.unlink()
            else:
                # Restore file content
                file_path.parent.mkdir(parents=True, exist_ok=True)
                if file_path.suffix == '.json':
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(self.data[key], f, indent=2)
                else:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(self.data[key])
            return True
        except Exception:
            return False
            
    def get(self, key: str, default=None):
        """Get captured data by key."""
        return self.data.get(key, default)
        
    def set(self, key: str, value: Any):
        """Set captured data."""
        self.data[key] = value


# Action types for tree operations
class ToggleModAction(UndoAction):
    """Action for enabling/disabling mods."""
    
    def __init__(self, mod_id: str, tab_type: str, old_state: bool, new_state: bool, 
                 toggle_callback, refresh_callback):
        action_type = "Enable" if new_state else "Disable"
        super().__init__(f"{action_type} {mod_id}")
        self.mod_id = mod_id
        self.tab_type = tab_type
        self.old_state = old_state
        self.new_state = new_state
        self.toggle_callback = toggle_callback
        self.refresh_callback = refresh_callback
        
    def execute(self) -> bool:
        """Toggle to new state."""
        try:
            self.toggle_callback(self.mod_id, self.new_state)
            self.refresh_callback()
            return True
        except Exception:
            return False
            
    def undo(self) -> bool:
        """Toggle back to old state."""
        try:
            self.toggle_callback(self.mod_id, self.old_state)
            self.refresh_callback()
            return True
        except Exception:
            return False


class RenameAction(UndoAction):
    """Action for renaming mods or groups."""
    
    def __init__(self, target_id: str, old_name: str, new_name: str, 
                 rename_callback, refresh_callback):
        super().__init__(f"Rename '{old_name}' to '{new_name}'")
        self.target_id = target_id
        self.old_name = old_name
        self.new_name = new_name
        self.rename_callback = rename_callback
        self.refresh_callback = refresh_callback
        
    def execute(self) -> bool:
        """Apply new name."""
        try:
            self.rename_callback(self.target_id, self.new_name)
            self.refresh_callback()
            return True
        except Exception:
            return False
            
    def undo(self) -> bool:
        """Restore old name."""
        try:
            self.rename_callback(self.target_id, self.old_name)
            self.refresh_callback()
            return True
        except Exception:
            return False


class GroupChangeAction(UndoAction):
    """Action for moving mods between groups."""
    
    def __init__(self, mod_id: str, old_group: str, new_group: str, 
                 group_callback, refresh_callback):
        super().__init__(f"Move '{mod_id}' from '{old_group}' to '{new_group}'")
        self.mod_id = mod_id
        self.old_group = old_group
        self.new_group = new_group
        self.group_callback = group_callback
        self.refresh_callback = refresh_callback
        
    def execute(self) -> bool:
        """Move to new group."""
        try:
            self.group_callback(self.mod_id, self.new_group)
            self.refresh_callback()
            return True
        except Exception:
            return False
            
    def undo(self) -> bool:
        """Move back to old group."""
        try:
            self.group_callback(self.mod_id, self.old_group)
            self.refresh_callback()
            return True
        except Exception:
            return False


class PakToggleAction(UndoAction):
    """Special action for PAK toggles that looks up fresh pak_info at execution time."""
    
    def __init__(self, pak_id: str, old_state: bool, new_state: bool, 
                 game_path: str, refresh_callback):
        action_type = "Enable" if new_state else "Disable"
        super().__init__(f"{action_type} {pak_id}")
        self.pak_id = pak_id
        self.old_state = old_state
        self.new_state = new_state
        self.game_path = game_path
        self.refresh_callback = refresh_callback
        
    def _find_pak_info(self) -> tuple:
        """Find current pak_info by pak_id. Returns (pak_info, found)."""
        from mod_manager.pak_manager import list_managed_paks
        all_paks = list_managed_paks()
        
        # Extract the base name from the original pak_id (remove any subfolder prefix)
        original_name = self.pak_id.split('|')[-1]  # Get the actual filename part
        print(f'[PAK-ACTION] _find_pak_info: looking for base name "{original_name}" from pak_id "{self.pak_id}"')
        
        # First try exact match (for cases where pak_id hasn't changed)
        for pak in all_paks:
            pak_subfolder = pak.get('subfolder', '') or ''
            reconstructed_id = f"{pak_subfolder}|{pak['name']}"
            if reconstructed_id == self.pak_id:
                print(f'[PAK-ACTION] _find_pak_info: found exact match with pak_id "{reconstructed_id}"')
                return pak, True
        
        # If exact match fails, try to find by base name regardless of folder
        for pak in all_paks:
            if pak['name'] == original_name:
                pak_subfolder = pak.get('subfolder', '') or ''
                reconstructed_id = f"{pak_subfolder}|{pak['name']}"
                print(f'[PAK-ACTION] _find_pak_info: found base name match with pak_id "{reconstructed_id}"')
                return pak, True
        
        print(f'[PAK-ACTION] _find_pak_info: no match found for base name "{original_name}"')
        return None, False
        
    def execute(self) -> bool:
        """Toggle to new state."""
        print(f'[PAK-ACTION] execute() called: pak_id={self.pak_id}, new_state={self.new_state}')
        pak_info, found = self._find_pak_info()
        if not found:
            print(f'[PAK-ACTION] execute() failed: pak_info not found for {self.pak_id}')
            return False
            
        print(f'[PAK-ACTION] execute() found pak_info: {pak_info}')
        try:
            from mod_manager.pak_manager import activate_pak, deactivate_pak
            if self.new_state:
                print(f'[PAK-ACTION] execute() calling activate_pak')
                activate_pak(self.game_path, pak_info)
            else:
                print(f'[PAK-ACTION] execute() calling deactivate_pak')
                deactivate_pak(self.game_path, pak_info)
            print(f'[PAK-ACTION] execute() pak operation succeeded, calling refresh')
            self.refresh_callback()
            print(f'[PAK-ACTION] execute() completed successfully')
            return True
        except Exception as e:
            print(f'[PAK-ACTION] execute() failed with exception: {e}')
            return False
            
    def undo(self) -> bool:
        """Toggle back to old state."""
        print(f'[PAK-ACTION] undo() called: pak_id={self.pak_id}, old_state={self.old_state}')
        pak_info, found = self._find_pak_info()
        if not found:
            print(f'[PAK-ACTION] undo() failed: pak_info not found for {self.pak_id}')
            return False
            
        print(f'[PAK-ACTION] undo() found pak_info: {pak_info}')
        try:
            from mod_manager.pak_manager import activate_pak, deactivate_pak
            if self.old_state:
                print(f'[PAK-ACTION] undo() calling activate_pak')
                activate_pak(self.game_path, pak_info)
            else:
                print(f'[PAK-ACTION] undo() calling deactivate_pak')
                deactivate_pak(self.game_path, pak_info)
            print(f'[PAK-ACTION] undo() pak operation succeeded, calling refresh')
            self.refresh_callback()
            print(f'[PAK-ACTION] undo() completed successfully')
            return True
        except Exception as e:
            print(f'[PAK-ACTION] undo() failed with exception: {e}')
            return False


class FileOperationAction(UndoAction):
    """Action for file-based operations (delete, move)."""
    
    def __init__(self, description: str, state_snapshot: StateSnapshot, 
                 restore_callback, refresh_callback):
        super().__init__(description)
        self.state_snapshot = state_snapshot
        self.restore_callback = restore_callback
        self.refresh_callback = refresh_callback
        self.executed = False
        
    def execute(self) -> bool:
        """File operation was already done, just mark as executed."""
        self.executed = True
        return True
        
    def undo(self) -> bool:
        """Restore from snapshot."""
        if not self.executed:
            return False
        try:
            self.restore_callback(self.state_snapshot)
            self.refresh_callback()
            return True
        except Exception:
            return False


class LoadOrderAction(UndoAction):
    """Action for ESP load order changes via drag-and-drop."""
    
    def __init__(self, old_order: list, new_order: list, 
                 set_order_callback, refresh_callback):
        # Create a concise description of the change
        if len(old_order) != len(new_order):
            super().__init__(f"Load Order Change ({len(old_order)} → {len(new_order)} mods)")
        else:
            # Find what moved
            moved_items = []
            for i, (old_item, new_item) in enumerate(zip(old_order, new_order)):
                if old_item != new_item:
                    moved_items.append(new_item)
            
            if moved_items:
                if len(moved_items) == 1:
                    super().__init__(f"Move '{moved_items[0]}'")
                else:
                    super().__init__(f"Reorder {len(moved_items)} mods")
            else:
                super().__init__("Load Order Change")
        
        self.old_order = old_order.copy()
        self.new_order = new_order.copy()
        self.set_order_callback = set_order_callback
        self.refresh_callback = refresh_callback
        self.executed = False
        
    def execute(self) -> bool:
        """Apply new load order."""
        try:
            self.set_order_callback(self.new_order)
            self.refresh_callback()
            self.executed = True
            return True
        except Exception as e:
            print(f"LoadOrderAction.execute() failed: {e}")
            return False
            
    def undo(self) -> bool:
        """Restore old load order."""
        if not self.executed:
            return False
        try:
            self.set_order_callback(self.old_order)
            self.refresh_callback()
            return True
        except Exception as e:
            print(f"LoadOrderAction.undo() failed: {e}")
            return False


class BulkToggleAction(UndoAction):
    """Undo action for bulk enabling/disabling multiple mods at once."""
    
    def __init__(self, changes: list, tab_type: str, toggle_callback, refresh_callback):
        """
        Initialize bulk toggle action.
        
        Args:
            changes: List of (mod_id, old_state, new_state) tuples
            tab_type: Type of tab (ESP, PAK, etc.)
            toggle_callback: Function to call for individual toggles
            refresh_callback: Function to refresh the UI
        """
        self.changes = changes
        self.tab_type = tab_type
        self.toggle_callback = toggle_callback
        self.refresh_callback = refresh_callback
        
        # Create description based on the changes
        enable_count = sum(1 for _, _, new_state in changes if new_state)
        disable_count = len(changes) - enable_count
        
        if enable_count > 0 and disable_count > 0:
            self.description = f"Bulk Toggle {len(changes)} {tab_type} mods"
        elif enable_count > 0:
            self.description = f"Bulk Enable {enable_count} {tab_type} mods"
        else:
            self.description = f"Bulk Disable {disable_count} {tab_type} mods"
    
    def execute(self) -> bool:
        """Execute the bulk toggle by applying all changes."""
        try:
            for mod_id, old_state, new_state in self.changes:
                self.toggle_callback(mod_id, new_state)
            self.refresh_callback()
            self.executed = True
            return True
        except Exception as e:
            print(f"BulkToggleAction.execute() failed: {e}")
            return False
    
    def undo(self) -> bool:
        """Undo the bulk toggle by reverting all changes."""
        if not hasattr(self, 'executed') or not self.executed:
            return False
        try:
            for mod_id, old_state, new_state in self.changes:
                self.toggle_callback(mod_id, old_state)
            self.refresh_callback()
            self.executed = False
            return True
        except Exception as e:
            print(f"BulkToggleAction.undo() failed: {e}")
            return False


class MagicLoaderBulkToggleAction(UndoAction):
    """Special bulk action for MagicLoader that batches JSON file operations and calls CLI once."""
    
    def __init__(self, changes: list, game_path: str, refresh_callback):
        """
        Initialize MagicLoader bulk toggle action.
        
        Args:
            changes: List of (mod_name, old_state, new_state) tuples
            game_path: Path to the game directory
            refresh_callback: Function to refresh the UI
        """
        self.changes = changes
        self.game_path = game_path
        self.refresh_callback = refresh_callback
        
        # Create description based on the changes
        enable_count = sum(1 for _, _, new_state in changes if new_state)
        disable_count = len(changes) - enable_count
        
        if enable_count > 0 and disable_count > 0:
            self.description = f"Bulk Toggle {len(changes)} MagicLoader mods"
        elif enable_count > 0:
            self.description = f"Bulk Enable {enable_count} MagicLoader mods"
        else:
            self.description = f"Bulk Disable {disable_count} MagicLoader mods"
    
    def execute(self) -> bool:
        """Execute the bulk toggle using batched operations."""
        try:
            from mod_manager.magicloader_installer import (
                bulk_activate_ml_mods, bulk_deactivate_ml_mods, reload_ml_config
            )
            
            # Separate changes into activate and deactivate lists
            mods_to_activate = [mod_name for mod_name, old_state, new_state in self.changes if new_state]
            mods_to_deactivate = [mod_name for mod_name, old_state, new_state in self.changes if not new_state]
            
            total_successful = 0
            total_failed = 0
            
            # Batch activate mods (no CLI calls)
            if mods_to_activate:
                successful, failed = bulk_activate_ml_mods(self.game_path, mods_to_activate)
                total_successful += successful
                total_failed += failed
                print(f"[MagicLoader] Bulk activated {successful}/{len(mods_to_activate)} mods")
            
            # Batch deactivate mods (no CLI calls)
            if mods_to_deactivate:
                successful, failed = bulk_deactivate_ml_mods(self.game_path, mods_to_deactivate)
                total_successful += successful
                total_failed += failed
                print(f"[MagicLoader] Bulk deactivated {successful}/{len(mods_to_deactivate)} mods")
            
            # Now call CLI once to reload configuration
            if total_successful > 0:
                cli_success, cli_output = reload_ml_config(self.game_path)
                if not cli_success:
                    print(f"[MagicLoader] CLI reload failed: {cli_output}")
                else:
                    print(f"[MagicLoader] CLI reload successful: {cli_output}")
            
            # Refresh UI
            self.refresh_callback()
            
            # Mark as executed if any operations succeeded
            if total_successful > 0:
                self.executed = True
                return True
            else:
                print(f"[MagicLoader] All bulk operations failed ({total_failed} failures)")
                return False
                
        except Exception as e:
            print(f"MagicLoaderBulkToggleAction.execute() failed: {e}")
            return False
    
    def undo(self) -> bool:
        """Undo the bulk toggle by reverting all changes."""
        if not hasattr(self, 'executed') or not self.executed:
            return False
            
        try:
            from mod_manager.magicloader_installer import (
                bulk_activate_ml_mods, bulk_deactivate_ml_mods, reload_ml_config
            )
            
            # Reverse the changes - swap old_state and new_state
            mods_to_activate = [mod_name for mod_name, old_state, new_state in self.changes if old_state]
            mods_to_deactivate = [mod_name for mod_name, old_state, new_state in self.changes if not old_state]
            
            total_successful = 0
            total_failed = 0
            
            # Batch activate mods (revert to old enabled state)
            if mods_to_activate:
                successful, failed = bulk_activate_ml_mods(self.game_path, mods_to_activate)
                total_successful += successful
                total_failed += failed
                print(f"[MagicLoader] Undo: Bulk activated {successful}/{len(mods_to_activate)} mods")
            
            # Batch deactivate mods (revert to old disabled state)
            if mods_to_deactivate:
                successful, failed = bulk_deactivate_ml_mods(self.game_path, mods_to_deactivate)
                total_successful += successful
                total_failed += failed
                print(f"[MagicLoader] Undo: Bulk deactivated {successful}/{len(mods_to_deactivate)} mods")
            
            # Now call CLI once to reload configuration
            if total_successful > 0:
                cli_success, cli_output = reload_ml_config(self.game_path)
                if not cli_success:
                    print(f"[MagicLoader] Undo: CLI reload failed: {cli_output}")
                else:
                    print(f"[MagicLoader] Undo: CLI reload successful: {cli_output}")
            
            # Refresh UI
            self.refresh_callback()
            self.executed = False
            
            return total_successful > 0
            
        except Exception as e:
            print(f"MagicLoaderBulkToggleAction.undo() failed: {e}")
            return False 