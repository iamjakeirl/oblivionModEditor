# Undo/Redo System Documentation

## Overview

The Oblivion Mod Manager now includes a comprehensive undo/redo system that allows you to reverse and reapply tree operations across all mod types. This feature helps prevent accidental changes and makes experimentation safer.

## What Can Be Undone

The undo system currently supports the following tree operations:

### ✅ Supported Operations
- **Enable/Disable Mods**: Toggle mods on/off across all tabs (ESP, PAK, UE4SS, MagicLoader, OBSE64)
- **Rename Mods**: Change display names via context menu
- **Group Changes**: Move mods between groups, create/rename groups
- **Single-Mod Operations**: All individual mod toggles support undo

### ❌ Not Currently Supported
- **Bulk Operations**: Multi-selection group operations (coming in future updates)
- **Modloader Installation**: Installing/uninstalling modloaders themselves
- **File System Operations**: Direct file deletions, archive installations
- **Load Order Changes**: ESP drag-and-drop reordering (planned for future)

## How to Use

### Keyboard Shortcuts
- **Ctrl+Z**: Undo last action
- **Ctrl+Y**: Redo last undone action

### Menu Access
1. Click **Edit** in the menu bar
2. Select **Undo** or **Redo**
3. Menu items show what action will be undone/redone

### Visual Feedback
- Menu items are disabled when no undo/redo is available
- Status bar shows confirmation when actions are undone/redone
- Action descriptions are descriptive (e.g., "Undo Enable MyMod.pak")

## Technical Details

### Architecture
The undo system uses the **Command Pattern** with these core components:

- **UndoStack**: Manages the history of actions (max 50 actions)
- **UndoAction**: Base class for all reversible operations
- **Action Types**: Specialized classes for toggles, renames, and grouping

### Action Types

#### ToggleModAction
```python
# Handles enable/disable operations
action = ToggleModAction(mod_id, tab_type, old_state, new_state, toggle_callback, refresh_callback)
```

#### RenameAction
```python
# Handles display name changes
action = RenameAction(target_id, old_name, new_name, rename_callback, refresh_callback)
```

#### GroupChangeAction
```python
# Handles group modifications
action = GroupChangeAction(mod_id, old_group, new_group, group_callback, refresh_callback)
```

### Integration Points

The system integrates with existing functionality through wrapper methods:

- `_toggle_pak_with_undo(pak_id, enable)`
- `_toggle_esp_with_undo(esp_name, enable)`
- `_toggle_ue4ss_with_undo(mod_name, enable)`
- `_toggle_magic_with_undo(mod_name, enable)`
- `_toggle_obse64_with_undo(plugin_name, enable)`
- `_rename_with_undo(mod_id, old_name, new_name, refresh_callback)`
- `_change_group_with_undo(mod_id, old_group, new_group, refresh_callback)`

## Examples

### Basic Usage

1. **Enable a mod**: Double-click a disabled mod
   - Action recorded: "Enable MyMod.pak"
   - Press Ctrl+Z to undo
   - Press Ctrl+Y to redo

2. **Rename a mod**: Right-click → "Rename Display Name"
   - Action recorded: "Rename 'MyMod.pak' to 'My Custom Mod'"
   - Undo restores original name

3. **Change group**: Right-click → "Set Group"
   - Action recorded: "Move 'MyMod.pak' from 'Graphics' to 'Gameplay'"
   - Undo moves back to original group

### Multiple Actions

```
1. Enable ModA.pak
2. Rename ModB.pak to "Better ModB"
3. Move ModC.pak to "UI" group
4. Disable ModD.pak

Now you can:
- Ctrl+Z → Undo "Disable ModD.pak"
- Ctrl+Z → Undo "Move ModC.pak to UI group"
- Ctrl+Z → Undo "Rename ModB.pak"
- Ctrl+Z → Undo "Enable ModA.pak"

Then Ctrl+Y to redo any of these actions
```

## Error Handling

The system includes robust error handling:

- **Failed Actions**: Actions that fail to execute are not added to the undo stack
- **Failed Undo**: If an undo operation fails, the stack remains consistent
- **State Validation**: Current state is checked before creating actions to prevent unnecessary operations

## Performance Considerations

- **Memory Usage**: Stack limited to 50 actions to prevent excessive memory use
- **Fast Operations**: State snapshots are lightweight (no full file copies)
- **UI Responsiveness**: All operations are synchronous but fast

## Future Enhancements

### Planned Features
1. **Bulk Operation Support**: Undo for multi-selection operations
2. **Load Order Undo**: Support for ESP drag-and-drop reordering
3. **Compound Actions**: Group related actions together (e.g., "Install Mod Package")
4. **Persistent History**: Optional saving of undo history between sessions
5. **Visual History**: Timeline view of all actions taken

### Advanced Features (Under Consideration)
1. **Branching History**: Support for multiple undo branches
2. **Action Filtering**: Hide/show specific action types
3. **Macro Recording**: Record and replay action sequences
4. **Cross-Tab Operations**: Support for actions affecting multiple tabs

## Troubleshooting

### Common Issues

**Q: Undo/Redo menu items are grayed out**
A: This is normal when there are no actions to undo/redo. Perform a tree operation first.

**Q: Some operations can't be undone**
A: Bulk operations and modloader installations are not yet supported. Check the "Not Currently Supported" section above.

**Q: Undo doesn't restore the exact previous state**
A: This might happen if external changes occurred (e.g., files modified outside the application). Restart the application if needed.

### Debug Information

If you encounter issues:
1. Check the status bar for error messages
2. Look for console output when running from terminal
3. Verify that the mod files haven't been modified externally

## Code Integration Guide

### For Developers

To add undo support to a new operation:

1. **Create Action Wrapper**:
```python
def _my_operation_with_undo(self, item_id: str, new_value):
    # Get current state
    current_value = get_current_state(item_id)
    
    # Create action
    def callback(id, value):
        apply_operation(id, value)
        
    action = MyCustomAction(item_id, current_value, new_value, callback, self.refresh)
    self._execute_with_undo(action)
```

2. **Update Existing Methods**:
```python
def existing_operation(self, item_id):
    # Old direct call:
    # apply_operation(item_id, new_value)
    
    # New with undo:
    self._my_operation_with_undo(item_id, new_value)
```

3. **Test Integration**:
```python
# Verify action is recorded
assert self.undo_stack.can_undo()

# Test undo
self.undo_stack.undo()
assert get_current_state(item_id) == original_value
```

## Conclusion

The undo/redo system provides a safety net for mod management operations while maintaining the application's existing workflow. It's designed to be unobtrusive yet powerful, giving users confidence to experiment with their mod configurations.

For questions or issues, please refer to the main application documentation or create an issue in the project repository. 