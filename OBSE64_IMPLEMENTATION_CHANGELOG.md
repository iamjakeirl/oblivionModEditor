# OBSE64 Implementation Changelog

This document tracks all changes made to implement OBSE64 (Oblivion Remastered Script Extender) support in the mod manager.

## PROJECT CONTEXT FOR FUTURE DEVELOPMENT

### Project Overview
This is **jorkXL's Oblivion Remastered Mod Manager** - a PyQt5-based GUI application for managing mods for the recently released Oblivion Remastered game. The manager supports multiple mod types and modloaders through a tabbed interface.

### Core Architecture
- **Main Entry**: `oblivion_mod_manager/main.py` - launches the GUI
- **UI Core**: `oblivion_mod_manager/ui/main_window.py` - main window with tabbed interface
- **Backend**: `oblivion_mod_manager/mod_manager/` - installer modules and utilities
- **Settings**: Stored in `DATA_DIR` (user data folder), includes game path and mod configurations

### Current Tabs (5 total)
1. **ESP Mods** - Plugin files (.esp/.esm), manages load order via plugins.txt
2. **PAK Mods** - Archive files (.pak), can be activated/deactivated  
3. **MagicLoader** - JSON-based modloader with manual Nexus download
4. **UE4SS** - Script extender with Lua mod support, auto-download
5. **OBSE64** - Script extender with .dll plugin support, manual Nexus download (NEW)

### Key Patterns & Conventions

#### Installer Module Pattern
Each modloader follows this pattern (see `magicloader_installer.py`, `ue4ss_installer.py`, `obse64_installer.py`):
- `{name}_installed()` → (bool, str) - check status
- `install_{name}()` → (bool, str) - install from archive/auto-download  
- `uninstall_{name}()` → bool - move to disabled backup folder
- `reenable_{name}()` → bool - restore from backup
- `get_{name}_dir()` → Path - installation directory
- `list_{name}_mods/plugins()` → (List[enabled], List[disabled])
- `activate/deactivate_{name}_mod()` - toggle individual items

#### UI Integration Pattern
Each tab follows this structure:
1. **Search box** - filters mod lists
2. **Two tree views** - enabled/disabled items with double-click toggle
3. **Status label** - shows installation status and counts
4. **Button row** - Install/Uninstall, Browse/Launch, Refresh
5. **"Show real names" checkbox** - toggles display vs real filenames

#### Row Builders (`ui/row_builders.py`)
Converts backend data to standardized format for `ModTreeBrowser`:
```python
{
    "id": "unique_identifier",
    "real": "actual_filename", 
    "display": "user_friendly_name",
    "group": "grouping_category",
    "subfolder": "optional_subfolder",
    "active": bool,
    "{type}_info": {"name": str, "enabled": bool}
}
```

### Undo/Redo System (`ui/undo_system.py`)

A comprehensive command pattern implementation for reversible mod operations across all tabs.

#### Core Components

**UndoStack** - Central manager with Qt signal integration:
- Maintains action history with configurable size limit (default: 50 actions)
- Emits signals for UI updates (`canUndoChanged`, `undoTextChanged`, etc.)
- Thread-safe execution with proper state management
- Integrated with main window's Edit menu (Ctrl+Z, Ctrl+Y shortcuts)

**UndoAction (ABC)** - Base class for all reversible operations:
```python
class UndoAction(ABC):
    def execute(self) -> bool:  # Perform the action
    def undo(self) -> bool:     # Reverse the action  
    def description(self) -> str # Human-readable description
```

#### Action Types

**ToggleModAction** - Generic mod enable/disable for ESP/UE4SS/OBSE64:
- Uses callback functions for tab-agnostic implementation
- Captures old/new states for bidirectional operations
- Automatically triggers UI refresh after state changes

**PakToggleAction** - Specialized PAK handling with dynamic lookup:
- **Key Innovation**: Looks up fresh `pak_info` at execution time
- **Problem Solved**: PAK IDs change when mods move between enabled/disabled folders
- **Implementation**: Uses base filename matching when exact pak_id fails
- **Robustness**: Handles subfolder changes during mod state transitions

**RenameAction** - File/group renaming operations:
- Captures old/new names for proper reversal
- Integrates with context menu rename functionality

**GroupChangeAction** - Mod organization operations:
- Handles moves between custom groups
- Maintains group hierarchy consistency

**FileOperationAction** - Complex file system operations:
- Uses StateSnapshot system for complete state restoration
- Handles mod deletion, folder moves, etc.

#### Integration Patterns

**Main Window Integration**:
```python
# Initialize undo system
self.undo_stack = UndoStack()
self.undo_stack.canUndoChanged.connect(self.undo_action.setEnabled)
self.undo_stack.undoTextChanged.connect(self.undo_action.setText)

# Create undo-enabled wrapper methods
def _toggle_pak_with_undo(self, pak_id: str, new_state: bool):
    action = PakToggleAction(pak_id, old_state, new_state, self.game_path, self._load_pak_list)
    self.undo_stack.push(action)
```

**Tree View Integration**:
- Double-click handlers automatically create undo actions
- Context menu operations wrapped in undo-enabled methods
- All state changes flow through undo system for consistency

#### Technical Considerations

**Model Refresh Coordination**:
- All undo actions include refresh callbacks to update UI
- Prevents stale data in tree views after undo/redo operations
- Handles proxy model updates and expansion state restoration

**Memory Management**:
- Action history automatically trimmed at configurable limit
- StateSnapshot system efficiently captures file states
- Weak references prevent circular dependencies

**Error Handling**:
- Graceful fallbacks when undo operations fail
- Debug logging for troubleshooting action failures
- Silent failures don't corrupt undo stack state

**Cross-Tab Consistency**:
- Actions designed to work across different mod types
- Callback-based design enables tab-agnostic implementation
- Centralized refresh coordination prevents UI desynchronization

#### Usage Guidelines

1. **Always use undo wrappers** for user-initiated mod operations
2. **Include refresh callbacks** in all custom actions
3. **Test undo/redo cycles** when implementing new operations
4. **Handle dynamic ID changes** for mods that move between folders
5. **Capture sufficient state** for complete operation reversal

The undo system significantly improves user experience by making mod management operations reversible and providing confidence for experimental configurations.

### Installation Types & Restrictions
- **Steam**: Full support for all modloaders
- **GamePass/MS Store**: Limited support (no OBSE64, UE4SS restrictions)
- Detection via `get_install_type()` in utils.py

### File Structure & Locations
```
Game Root/
├── OblivionRemastered/
│   ├── Binaries/Win64/           # OBSE64, UE4SS location
│   └── Content/Paks/             # PAK mods location
├── Data/                         # ESP mods location  
└── MagicLoader/                  # MagicLoader location (Steam)
    └── Mods/                     # JSON mods

User Data (DATA_DIR)/
├── disabled_*/ folders           # Backup locations for uninstalled modloaders
├── pak_manager_db.json          # PAK mod registry
└── settings.json                # Game path, custom settings
```

### Key Dependencies
- **PyQt5** - GUI framework
- **pyunpack** - Archive extraction (.zip/.7z/.rar)
- **py7zr, rarfile, zipfile** - Archive handling
- **requests** - HTTP downloads (for auto-installing modloaders)
- **pathlib** - Modern path handling

### Drag & Drop System
Archives dropped on window are:
1. **Detected** by file extension (.zip, .7z, .rar)
2. **Extracted** to temp directory
3. **Analyzed** for content type:
   - OBSE64: Contains `obse64_loader.exe` or `obse64_*.dll` → direct install
   - MagicLoader: Contains `MagicLoader.exe` → abort with error
   - UE4SS: Contains `.lua` files in `scripts/` folders → install as UE4SS mods
   - Regular: Contains `.esp` or `.pak` files → install as ESP/PAK mods

### Tree View System (`ModTreeBrowser`)
- **Grouping**: Mods can be grouped by category in tree structure
- **Search**: Real-time filtering across all columns
- **Context Menus**: Right-click for rename, group, delete operations
- **Double-click**: Toggle enabled/disabled state
- **Styling**: Consistent dark theme across all tabs

### Status & Feedback System
```python
self.show_status(message, timeout_ms, type)
# Types: "info", "success", "warning", "error"
```

### Manual Download Workflow (OBSE64, MagicLoader)
1. User clicks "Browse Archive" button
2. Install type validation (Steam-only for OBSE64)
3. File dialog for archive selection
4. Progress dialog during installation
5. Archive extraction and file filtering
6. Installation to correct directories
7. Status feedback and UI refresh

### Important Technical Notes
- **Model Refreshing**: Always call `._load_pak_list()` or `._refresh_{tab}_status()` after changes
- **Proxy Models**: Tree views use filter proxies, always `mapToSource()` for real indexes
- **Settings Persistence**: All changes auto-saved to JSON files
- **Error Handling**: Graceful fallbacks, user-friendly error messages
- **Cross-Platform**: Windows-focused but path handling is cross-platform ready

### Testing Checklist Template
For any new modloader integration:
- [ ] Install type detection and restrictions
- [ ] Archive detection and extraction  
- [ ] File placement in correct directories
- [ ] Plugin/mod directory creation
- [ ] Enable/disable functionality
- [ ] Drag-and-drop installation
- [ ] Browse button installation
- [ ] Uninstall/re-enable workflow
- [ ] Error handling and user feedback
- [ ] Integration with refresh/folder systems
- [ ] Launch functionality (if applicable)
- [ ] Context menu operations
- [ ] Tree view display and grouping

### Code Style & Conventions
- **Import Style**: Grouped imports (stdlib, PyQt5, local modules)
- **Error Handling**: Try/except with user-friendly messages
- **Path Handling**: Use `pathlib.Path` for new code
- **Constants**: ALL_CAPS for configuration values
- **Debug**: `DEBUG = False` flag in installer modules
- **Documentation**: Docstrings for public functions

This codebase is well-structured and follows consistent patterns throughout. New modloader integrations should follow the established installer module + UI integration pattern for consistency.

---

## Implementation Plan
- **Target**: Add OBSE64 tab with manual installation support (browse/drag-and-drop)
- **Restriction**: Steam installations only
- **Installation**: Manual archive installation (no automatic download)
- **Plugin Management**: Enable/disable .dll plugins in OBSE/plugins/ directory

## Changes Made

### Phase 1: Core Installer Module

#### Created: `mod_manager/obse64_installer.py`
- **Status**: ✅ Completed
- **Description**: Core installer module following MagicLoader/UE4SS patterns
- **Key Functions**:
  - `obse64_installed()` - Check installation status and extract version from DLL filename
  - `install_obse64()` - Manual archive installation with Steam-only restriction
  - `uninstall_obse64()` - Move to disabled folder in DATA_DIR
  - `reenable_obse64()` - Restore from disabled folder
  - `get_obse64_dir()` - Get installation directory (Binaries/Win64)
  - `get_obse_plugins_dir()` - Get plugins directory with auto-creation
  - `list_obse_plugins()` - List enabled/disabled plugins (.dll files)
  - `activate_obse_plugin()`, `deactivate_obse_plugin()` - Plugin state management
  - `launch_obse64()` - Launch via obse64_loader.exe
- **Features**:
  - Steam-only restriction with proper error messaging
  - Support for .zip, .7z, .rar archives via pyunpack
  - Automatic OBSE folder structure creation
  - Version detection from DLL filename (e.g., obse64_0_411_140.dll → 0.411.140)
  - Archive file filtering (only obse64_loader.exe and obse64_*.dll)
  - Progress callback support for UI updates

#### Modified: `mod_manager/utils.py`
- **Status**: ⏳ Pending
- **Description**: Add OBSE64 constants and helper functions if needed

### Phase 2: Plugin Display Support

#### Modified: `ui/row_builders.py`
- **Status**: ✅ Completed
- **Description**: Add OBSE64 plugin display support
- **Changes**:
  - Added `rows_from_obse64_plugins()` function
  - Follows existing display patterns for ModTreeBrowser
  - Returns rows with `obse64_info` structure

### Phase 3: UI Integration

#### Modified: `ui/main_window.py`
- **Status**: ✅ Completed
- **Description**: Add OBSE64 tab following existing patterns
- **Changes**:
  - Added OBSE64 tab creation with plugin lists (enabled/disabled)
  - Added OBSE64 refresh functionality (`_refresh_obse64_status()`)
  - Added complete button suite: Install/Uninstall/Re-enable, Browse Archive, Launch OBSE64, Refresh
  - Added plugin toggle functionality (`_toggle_obse64_plugin()`)
  - Added plugin removal functionality (`_remove_obse64_plugin()`)
  - Added manual archive installation workflow (`_browse_obse64_archive()`, `_install_obse64_archive()`)
  - Added uninstall/re-enable functionality (`_uninstall_obse64()`, `_reenable_obse64()`)
  - Added launch functionality (`_launch_obse64()`)
  - Added button state management (`_update_obse64_btns()`)
  - Integrated into refresh cycles and initialization
  - Added to folder opening functionality (index 4 = OBSE64 tab)

### Phase 4: Drag-and-Drop Integration

#### Modified: `ui/main_window.py` (dropEvent/dragEnterEvent)
- **Status**: ✅ Completed
- **Description**: Extend existing drag-and-drop to detect OBSE64 archives
- **Changes**:
  - Added OBSE64 archive detection in `_process_dropped_archives()`
  - Routes OBSE64 archives (containing obse64_loader.exe or obse64_*.dll) to direct installer
  - Maintains existing mod installation logic for regular archives
  - Archives detected as OBSE64 bypass regular mod installation workflow

## Technical Details

### Installation Directory
- **Target**: `{game_root}/OblivionRemastered/Binaries/Win64/`
- **Files**: `obse64_loader.exe`, `obse64_*.dll`
- **Plugins**: `OBSE/plugins/` (auto-created)

### Archive Structure Handling
- Extract: `obse64_loader.exe`, `obse64_*.dll` files
- Ignore: `src/` folder, `.txt` files

### Steam-Only Restriction
- Check `get_install_type() == "steam"`
- Show error for GamePass/other installations

### Tab Integration
- OBSE64 tab is index 4 in the notebook
- Integrated into `open_current_tab_folder()` method
- Proper refresh cycle integration
- Consistent UI styling with other tabs

## Testing Checklist
- [ ] Steam installation detection
- [ ] Archive file detection and extraction
- [ ] File placement in correct directories
- [ ] Plugin directory creation
- [ ] Plugin enable/disable functionality
- [ ] Drag-and-drop installation
- [ ] Browse button installation
- [ ] Error handling and user feedback
- [ ] Integration with existing refresh/folder systems
- [ ] Launch functionality (obse64_loader.exe)

## Implementation Complete
All phases have been implemented successfully:
1. ✅ Core installer module with full functionality
2. ✅ Plugin display support integrated into row builders  
3. ✅ Complete UI integration with tab, buttons, and all functionality
4. ✅ Drag-and-drop archive detection and routing

## Notes
- OBSE64 only available from Nexus (manual download required)
- Plugin system uses .dll files, simpler than JSON-based systems
- Launch integration should use obse64_loader.exe instead of normal game executable
- Implementation follows existing patterns from UE4SS and MagicLoader tabs for consistency 