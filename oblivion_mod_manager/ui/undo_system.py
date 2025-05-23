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