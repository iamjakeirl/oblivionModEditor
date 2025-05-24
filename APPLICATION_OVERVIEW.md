# jorkXL's Oblivion Remastered Mod Manager - Application Overview

## Project Description

A comprehensive mod management application for Oblivion Remastered, supporting multiple mod types and loaders with an intuitive tabbed interface. The application provides drag-and-drop installation, visual mod organization, and complete undo/redo functionality for safe mod management.

## Core Features

### Multi-Tab Mod Management
- **ESP Mods**: Plugin management with load order control, tree/flat view modes, preserve load order toggle, bulk operations
- **PAK Mods**: Archive-based mod activation/deactivation with group organization, LogicMods support
- **MagicLoader**: JSON-based mod management with launcher integration
- **UE4SS**: Lua script mod management with built-in UE4SS installer
- **OBSE64**: Plugin management for Oblivion Script Extender 64-bit
- **Settings**: Configurable mod installation directories

### Advanced User Interface
- **Drag & Drop Installation**: Direct archive import (.zip, .7z, .rar)
- **Search & Filter**: Real-time filtering across all mod types
- **Group Organization**: Custom grouping with display name management
- **Context Menus**: Right-click operations (rename, group, delete)
- **Dark Theme**: Modern, consistent UI styling across all tabs
- **Load Order Preservation**: Toggle to maintain ESP positions when enabling/disabling

### Intelligent Mod Detection
- **Auto-Installation**: Detects ESP, PAK, UE4SS, and OBSE64 content in archives
- **Smart Merging**: Handles ~mods, LogicMods, and shared resource folders
- **Conflict Resolution**: Prompts for overwrites and duplicate handling
- **Multi-Loader Support**: Single archives can contain mods for multiple systems

## Context Menu Architecture

### Dual Context Menu System
The application uses a hybrid context menu architecture with both generic and tab-specific implementations:

#### Generic Context Menu (`ui/jorkTreeBrowser.py`)
- **Location**: Lines 58-60, 245-366
- **Setup**: `self.customContextMenuRequested.connect(self._show_context_menu)`
- **Handles**: Basic operations (rename, group, delete) for all mod types
- **Refresh System**: `_refresh_parent_views()` method (lines 367-375) calls appropriate tab refresh functions

#### Tab-Specific Context Menus (`ui/main_window.py`)
- **PAK Tab**: `_show_pak_view_context_menu()` (lines 1976+) → calls `self._load_pak_list()`
- **ESP Tab**: `_show_esp_context_menu()` (lines 3661+) → calls `self.refresh_lists()` 
- **MagicLoader Tab**: `_show_magic_context_menu()` (lines 4105+) → calls `self._refresh_magic_status()`
- **UE4SS/OBSE64 Tabs**: Use generic context menu only

### Context Menu Signal Connections & Conflict Prevention
Each tab connects context menus in `main_window.py` `__init__()`. **Critical**: Tabs with specific context menus must disconnect the generic one first to prevent conflicts:

```python
# ESP Tab - Proper pattern (lines ~410-418)
self.esp_enabled_view.customContextMenuRequested.disconnect()
self.esp_disabled_view.customContextMenuRequested.disconnect()
self.esp_enabled_view.customContextMenuRequested.connect(
    lambda pos: self._show_esp_context_menu(pos, True))

# MagicLoader Tab - Fixed pattern (lines ~543-548)
self.magic_enabled_view.customContextMenuRequested.disconnect()
self.magic_disabled_view.customContextMenuRequested.disconnect()
self.magic_enabled_view.customContextMenuRequested.connect(
    lambda pos: self._show_magic_context_menu(pos, True))
```

**Key Pattern**: Always call `.disconnect()` before `.connect()` when overriding the generic context menu to prevent dual context menu conflicts.

### Refresh Method Coverage
The generic `_refresh_parent_views()` method supports all tabs:
- `_load_pak_list` (PAK tab)
- `refresh_lists` (ESP tab)
- `_refresh_ue4ss_status` (UE4SS tab)
- `_refresh_magic_status` (MagicLoader tab) - **Added in recent fix**
- `_refresh_obse64_status` (OBSE64 tab) - **Added in recent fix**

## LogicMods System & Recent Fixes

### LogicMods Reactivation Issue (FIXED)

**Problem**: PAK mods containing LogicMods folders were being placed back into the normal mods folder instead of the LogicMods folder when reactivated after deactivation.

**Root Cause**: The `reconcile_pak_list()` function only added new entries and removed missing entries, but didn't update existing entries when their location changed. When LogicMods content was merged during installation, PAK metadata wasn't updated to reflect the new location.

**Solution Applied**:

1. **Enhanced Installation Process** (`ui/main_window.py`):
   - Added `reconcile_pak_list()` call after LogicMods merge operations
   - Automatically updates PAK metadata to reflect correct LogicMods location

2. **Completely Rewrote `reconcile_pak_list()`** (`mod_manager/pak_manager.py`):
   - **Before**: Only added missing/removed non-existent entries
   - **After**: Updates existing entries when their subfolder location changes
   - Uses name-based lookups instead of complex tuple comparisons
   - Preserves metadata like `from_logicmods` flag

3. **Enhanced Deactivation/Reactivation Logic**:
   - Improved detection: `"LogicMods" in subfolder` (not just `startswith`)
   - Added fallback logic to check `from_logicmods` flag
   - Automatically corrects subfolder metadata during reactivation

**Impact**: 
- ✅ LogicMods PAKs now correctly reactivate to LogicMods folder
- ✅ Works for any PAK location changes, not just LogicMods
- ✅ Self-healing metadata correction system
- ✅ Handles complex LogicMods subdirectory structures

### LogicMods Group Preservation Issue (FIXED)

**Problem**: When LogicMods PAKs were deactivated, they showed as "Ungrouped" even if they previously had a group when enabled. The group name would only return when reactivated.

**Root Cause**: The group lookup fallback regex `^(DisabledMods[\\/]+)` only matched "DisabledMods/" but not "DisabledMods" (without trailing slash). When LogicMods PAKs were deactivated to the root disabled directory, their mod ID became "DisabledMods|ModName.pak", which didn't match the regex.

**Solution Applied** (`ui/jorkTreeViewQT.py`):

1. **Fixed Regex Pattern**:
   - **Before**: `^(DisabledMods[\\/]+)` - only matched with trailing slash/backslash
   - **After**: `^DisabledMods(?:[\\/]+|$)` - matches with or without trailing separators

2. **Enhanced Fallback Logic**:
   - **Step 1**: Try direct lookup (`DisabledMods|ModName.pak`)
   - **Step 2**: Try normalized lookup (strip "DisabledMods" → `|ModName.pak`)
   - **Step 3**: **NEW** - If normalized to empty subfolder, try LogicMods (`LogicMods|ModName.pak`)
   - **Step 4**: Fallback to name-only lookup (`|ModName.pak`)

**Impact**:
- ✅ LogicMods groups now preserved when deactivated
- ✅ Backwards compatible with existing group lookups
- ✅ Handles both root disabled mods and subfolder disabled mods
- ✅ Automatically finds correct group info regardless of disable method

## Mod Update Workflow Limitations (DISCOVERED)

### Current Update Behavior

**ESP Mods**:
- ❌ **Load order NOT preserved** - updated ESPs move to end of plugins.txt
- ✅ Display names and groups preserved (stored separately from plugins.txt)

**PAK Mods**:
- ❌ **Installation fails** if PAK with same name exists (no overwrite prompt)
- ❌ Must manually delete old PAK first, **losing all metadata** (groups, display names)

**Recommended Update Workflow**:
- **ESP**: Note position → Update → Manually drag back to original position
- **PAK**: Note metadata → Delete old → Install new → Re-assign metadata

## Recent Bug Fixes

### MagicLoader Double Context Menu Issue (Fixed - Current Session)

**Problem**: In the MagicLoader tab, when entering a display name or group name and pressing Enter, the operation would work but immediately open another context menu. Users had to click OK/Cancel to dismiss this second menu.

**Root Cause**: MagicLoader views had both the generic context menu (from `ModTreeBrowser`) AND the specific context menu connected simultaneously. Unlike ESP tab, MagicLoader wasn't disconnecting the generic context menu before connecting its specific one.

**Solution Applied**:
- **File**: `ui/main_window.py` (lines ~543-548)
- **Change**: Added `disconnect()` calls before `connect()` calls for MagicLoader context menus
- **Pattern**: Made MagicLoader follow the same pattern as ESP tab to prevent dual context menu conflicts

```python
# Added these disconnect calls before the existing connect calls
self.magic_enabled_view.customContextMenuRequested.disconnect()
self.magic_disabled_view.customContextMenuRequested.disconnect()
```

**Impact**: 
- ✅ Eliminates double context menu in MagicLoader tab
- ✅ Makes MagicLoader consistent with ESP tab behavior
- ✅ Provides clean user experience for display name and group operations

### MagicLoader Group Update Issue (Fixed - Previous Session)

**Problem**: When using the context menu to group a MagicLoader mod, the group name didn't update in the table view until the mod was activated/deactivated.

**Root Cause**: The `_refresh_parent_views()` method in `ui/jorkTreeBrowser.py` (line 369) was missing `_refresh_magic_status` from its refresh function list, causing the MagicLoader tab views not to update immediately after group changes.

**Solution Applied**: 
- **File**: `ui/jorkTreeBrowser.py`
- **Line**: 369 
- **Change**: Updated refresh method list to include all tab refresh functions

## Undo/Redo System Architecture

### Core Components

#### UndoStack Class
- **Action Management**: Centralized stack for all undoable operations
- **State Tracking**: Maintains current position and operation history
- **Signal Integration**: Qt-compatible signals for UI state updates
- **Memory Management**: Automatic cleanup of old actions

#### Action Types
- **ToggleModAction**: Enable/disable operations across all mod types
- **RenameAction**: Display name changes with duplicate validation
- **GroupChangeAction**: Group assignment modifications
- **LoadOrderAction**: ESP load order modifications (NEW)
- **PakToggleAction**: PAK-specific activation with dynamic pak_info lookup
- **FileOperationAction**: File system operations with state snapshots

#### Integration Points
- **Menu System**: Edit menu with Ctrl+Z/Ctrl+Y shortcuts
- **Action Feedback**: Dynamic menu text showing operation descriptions
- **Cross-Tab Support**: Consistent undo behavior across all mod types
- **State Validation**: Ensures actions remain valid after model changes

### Recent Undo System Enhancements

#### Load Order Undo/Redo (Previous Update)
- **Drag & Drop Tracking**: Captures order before and after drag operations
- **Revert Operation Support**: "Revert to Default Load Order" now undoable
- **Smart State Detection**: Only creates undo actions when order actually changes
- **Flat List Integration**: Works with both tree and load-order flat view modes

#### Enhanced Widget Integration
- **PluginsListWidget**: Added pre-drag order capture and undo callback support
- **Load Order Restoration**: Dedicated method to restore order from saved state
- **Seamless Integration**: Undo works transparently with existing UI operations

## OBSE64 Implementation

### Installation System
- **Archive Detection**: Automatically identifies OBSE64 components in imports
- **Steam Validation**: Restricts installation to Steam versions only
- **Progress Tracking**: Visual feedback during installation process
- **Backup Management**: Preserve/restore capability for safe testing

### Plugin Management
- **Enable/Disable**: Move plugins between active and disabled folders
- **Tree Organization**: Consistent UI with other mod types
- **Undo Integration**: Full undo/redo support for all plugin operations
- **Context Operations**: Rename, group, and delete plugin files

### ESP Load Order Management
- **Preserve Load Order Toggle**: User-configurable option for ESP enable/disable behavior
  - **When ON** (default): ESPs are commented/uncommented in-place, maintaining their position
  - **When OFF**: ESPs are removed and re-added at the end (legacy behavior)
- **New ESP Handling**: ESPs not in plugins.txt are always added at the end regardless of toggle
- **Default ESP Protection**: Default/stock ESPs cannot be disabled regardless of toggle state
- **Setting Persistence**: Toggle state is saved in user settings and remembered between sessions
- **Bulk Operations**: Multi-selection enable/disable with full undo support
  - **Context Menu**: Right-click selected ESPs for bulk enable/disable options
  - **Group Operations**: Right-click group headers to enable/disable entire groups
  - **Keyboard Shortcuts**: Ctrl+E to enable, Ctrl+D to disable selected ESPs
  - **Mixed State Handling**: Intelligently handles selections with different current states
  - **Undo Support**: All bulk operations are undoable as single actions

### Launcher Integration
- **Direct Launch**: "Launch OBSE64" button for convenient game startup
- **Installation Validation**: Ensures OBSE64 is properly installed before launch
- **Error Handling**: Clear feedback for launch failures and missing components

## Technical Architecture

### Model-View Integration
- **ModTreeModel**: Custom tree model supporting grouping and real/display names
- **ModFilterProxy**: Advanced filtering with search highlighting
- **Dynamic Refresh**: Efficient model updates without losing UI state
- **Memory Management**: Proper cleanup of old models and proxies

### State Management
- **Settings Persistence**: JSON-based configuration storage
- **Display Cache**: O(1) lookup for mod display information
- **Bulk Operations**: Efficient group operations with single refresh
- **Migration Support**: Automatic upgrading of legacy data formats

### File System Operations
- **Archive Extraction**: Multi-format support with fallback strategies
- **Directory Merging**: Smart handling of overlapping mod structures
- **Path Validation**: Cross-platform path handling and validation
- **Atomic Operations**: Rollback capability for failed installations

## User Experience Improvements

### Recent UI Enhancements
- **Search Bar Positioning**: Fixed ESP tab search bar to stay at top (Previous)
- **Load Order Visualization**: Clear indicators for enabled/disabled state
- **Consistent Styling**: Unified tree view appearance across all tabs
- **Status Feedback**: Colored status messages with auto-clear timers
- **Preserve Load Order Toggle**: New option to maintain ESP positions when enabling/disabling
- **LogicMods Reliability**: Fixed reactivation and group preservation issues (LATEST)

### Quality of Life Features
- **Open Folder Button**: Direct access to mod directories from each tab
- **Auto-Refresh**: Intelligent UI updates after external changes
- **Conflict Prevention**: Duplicate name validation and overwrite prompts
- **Batch Operations**: Multi-select support for group operations and bulk ESP enable/disable
- **Load Order Preservation**: When enabled, ESPs maintain their position when toggled
- **Smart Context Menus**: Adaptive right-click menus with relevant bulk options
- **Keyboard Shortcuts**: Quick access to common operations (Ctrl+E, Ctrl+D, Ctrl+Z/Y for undo/redo)
- **Status Feedback**: Clear success/error messages for all operations

## Installation Types & Compatibility

### Supported Platforms
- **Steam**: Full feature support including OBSE64
- **Game Pass**: All features except OBSE64 (platform limitation)
- **Auto-Detection**: Installation type detection with manual override

### Mod Format Support
- **Archives**: .zip, .7z, .rar with automatic extraction
- **Direct Import**: Folder drag-and-drop for manual installations
- **Mixed Content**: Single archives containing multiple mod types
- **Legacy Support**: Handles existing mod installations and configurations

## Future Roadmap

### Planned Features
- **Enhanced Update Workflow**: Proper "update mod" feature that preserves metadata
- **Modpack Support**: Import/export of complete mod configurations
- **Nexus Integration**: Direct downloading with API integration
- **Load Order Presets**: Save/load ESP arrangements with missing mod handling
- **FOMOD Support**: Graphical installer for complex mod packages
- **Conflict Detection**: Visual indicators for mod conflicts and dependencies

### Technical Improvements
- **Performance Optimization**: Faster scanning and loading for large mod collections
- **Enhanced Validation**: Better mod compatibility checking
- **Cloud Sync**: Optional cloud backup of mod configurations
- **Plugin System**: Extensible architecture for community additions

## Development Notes

### Code Organization
- **Modular Design**: Separate modules for each mod type and major feature
- **Clean Separation**: UI, business logic, and file operations properly separated
- **Consistent Patterns**: Standardized approaches across all mod management systems
- **Error Handling**: Comprehensive error recovery and user feedback

### Testing Considerations
- **Undo System**: Extensive testing of complex operation sequences
- **Cross-Platform**: Validation on different Windows versions and installations
- **Large Collections**: Performance testing with hundreds of mods
- **Edge Cases**: Handling of corrupted files, permission issues, and unusual mod structures
- **Context Menu Conflicts**: Testing both generic and tab-specific context menu scenarios
- **LogicMods Integration**: Testing complex LogicMods scenarios and edge cases

### Architecture Insights for Future Development
- **Context Menu Design**: Consider consolidating to single system vs. current hybrid approach
- **Refresh Pattern**: All tabs should implement consistent `_refresh_[tab]_status()` naming
- **Signal Management**: Careful attention to signal connections in tree view components
- **Generic vs. Specific**: Balance between reusable generic components and tab-specific functionality
- **Metadata Preservation**: Consider implementing proper update workflows that preserve all metadata

## Recent Changes Summary

### Context Menu Architecture Fix (Current Session)
1. **Fixed MagicLoader Double Context Menu**: Added proper disconnect/connect pattern to prevent dual context menu conflicts
2. **Standardized Context Menu Handling**: Made MagicLoader consistent with ESP tab implementation
3. **Enhanced Documentation**: Updated context menu architecture documentation with conflict prevention patterns
4. **Improved User Experience**: Eliminated confusing double context menu behavior in MagicLoader tab

### LogicMods System Overhaul (Previous Session)
1. **Fixed LogicMods Reactivation**: Complete rewrite of `reconcile_pak_list()` to update existing entries
2. **Fixed Group Preservation**: Enhanced regex pattern and fallback logic for disabled mods
3. **Enhanced Installation Flow**: Added automatic metadata correction after LogicMods merge
4. **Improved Error Handling**: Better detection and correction of metadata inconsistencies
5. **Discovered Update Limitations**: Documented current mod update workflow limitations

### Earlier Major Updates
- Complete OBSE64 support implementation
- Comprehensive undo/redo system across all mod types
- Multi-loader archive detection and installation
- Advanced tree view organization with grouping
- Modern dark theme UI overhaul
- MagicLoader group update refresh fix

This application represents a mature, full-featured mod management solution with robust LogicMods support and continuing development focused on user experience and advanced workflow support. 