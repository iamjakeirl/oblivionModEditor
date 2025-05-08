jorkXL Oblivion Remastered Mod Manager – Agent Reference

This document is a single-source reference for LLM agents that need to reason about, extend, or refactor the code-base. Anything not covered here can be inferred from the source files themselves.
1. High-level layout

oblivion_mod_manager/
 ├─ main.py                ← CLI/entry; boots GUI
 ├─ mod_manager/           ← backend logic
 │   ├─ install.py         (placeholder)
 │   ├─ pak_manager.py     PAK add/remove/activate/deactivate/reconcile
 │   ├─ registry.py        ESP plugin.txt helpers
 │   ├─ ue4ss_installer.py UE4SS download/uninstall/mod juggling
 │   └─ utils.py           shared helpers & on-disk state
 ├─ ui/                    ← PyQt5 GUI
 │   ├─ main_window.py     giant tabbed window (ESP/PAK/UE4SS/Settings)
 │   ├─ jorkTreeViewQT.py  tree-model (groups, drag, rename…)
 │   ├─ jorkTreeBrowser.py thin QTreeView wrapper w/ search + state
 │   ├─ install_type_dialog.py  steam vs game-pass chooser
 │   └─ row_builders.py    normalize {id,…} rows for all mod types
 └─ data/  (created under %APPDATA%/OblivionModManager)
     ├─ settings.json      user settings (game_path, install_type, …)
     ├─ pak_mods.json      persisted list of managed PAKs
     └─ display_names.json per-mod {display,group} overrides

2. Core data shapes
2.1 Mod row-dict (used by ModTreeModel)
key	type	notes
id	str	Primary key. Format: `"<subfolder>
real	str	Actual filename (e.g. CoolMod.pak).
display	str	User-visible name (falls back to real).
group	str	Hierarchical group path Parent/Child. Empty ⇒ “Ungrouped”.
subfolder	str|None	Subdir inside ~mods or LogicMods etc.
active	bool	Enabled in game (True) vs disabled (False).
pak_info / esp_info / ue4ss_info	dict	Raw backend object (type-specific).
2.2 pak_mods.json

[
  {
    "name": "CoolMod.pak",
    "base_name": "CoolMod",
    "files": ["…/~mods/CoolMod.pak","…/CoolMod.ucas", …],
    "extensions": [".pak",".ucas",".utoc"],
    "subfolder": null,      // or "Some/Sub"
    "installed_date": null,
    "active": true,
    "from_logicmods": false // set only after disable/enable cycles
  }
]

2.3 display_names.json

{
  "LogicMods/Sub|Awesome.pak": { "display": "Awesome++", "group": "Graphics" },
  "|SomeESP.esp"             : { "display": "Better Stuff", "group": "Gameplay/Quests" }
}

3. Principal back-end APIs
Module / func	Purpose	Typical caller
pak_manager.add_pak(game_path, src_pak, subfolder)	Copy .pak + .ucas + .utoc bundle into ~mods/ (or nested subfolder) and register in pak_mods.json.	Archive import in MainWindow._install_extracted_mod
pak_manager.remove_pak(game_path, pak_name)	Hard-delete bundle + registry.	GUI “Delete” context action
pak_manager.activate_pak / deactivate_pak	Move files between ~mods and sibling DisabledMods directory.	Double-click rows
pak_manager.reconcile_pak_list(game_path)	Rescan disk → keep registry in sync (adds stray files, drops missing).	PAK-tab refresh
registry.read_plugins_txt / write_plugins_txt	Read/write plugins.txt; retains comment prefix # for disabled ESPs.	ESP-tab enable/disable
ue4ss_installer.install_ue4ss	Download zip → extract into `…/Binaries/Win64	WinGDK. Also patches mods.txt/mods.json`.
ue4ss_installer.add_ue4ss_mod	Copy detected FolderX into UE4SS/Mods and register.	Archive import

All PAK/ESP/UI operations eventually emit self._load_pak_list() or self.refresh_lists() to refresh the two master tree-views.
4. UI flow cheat-sheet

    Startup (main.py)
    • get_game_path() → optional migration tasks
    • ui.main_window.run() spins up Qt app.

    MainWindow

        Initializes 4 tabs: ESP, PAK, UE4SS, Settings.

        Each tab embeds two ModTreeBrowser views (enabled/disabled).

        File-drop handler auto-extracts archives, classifies ESP/PAK/UE4SS, then calls the relevant back-end functions.

    ModTreeBrowser / ModTreeModel

        Hierarchical tree: group rows (is_group=True) + leaf rows.

        Drag-n-drop re-groups mods by writing display_names.json.

        Keeps expansion state across model resets.

5. Extension points
Goal	Where / How
Support new mod type (e.g. textures)	• Add backend manager texture_manager.py patterned after pak_manager.

                                      • Extend `row_builders.py` with `rows_from_textures`.  
                                      • Add new tab or integrate into PAK tab.                    |

| Add settings entry | • Update utils.load_settings / save_settings helpers.
• Extend UI Settings tab. |
| Bulk migration / one-shot fixes | Implement migration function in utils.* and call it from main_window.__init__ before GUI builds. |
6. ID & grouping conventions

    ID normalization – When looking up display info the code tries three keys:

        normalized (strip DisabledMods/)

        original

        |filename.

    Group paths – Slash-delimited ("Parent/Sub"). Nested groups are allowed; tree builds groups on demand.

7. Disk layout expectations

<GameRoot>/
 └─ OblivionRemastered/
     └─ Content/Paks/
         ├─ ~mods/…            ← user pak dir (customizable)
         ├─ LogicMods/…        ← script-centric paks
 <GameRoot>/…/Paks/DisabledMods/…  ← auto-managed disabled bucket
 <GameRoot>/…/Binaries/Win64|WinGDK/
         ├─ dwmapi.dll
         └─ UE4SS/Mods/…

Disabled UE4SS installs are parked in %APPDATA%/OblivionModManager/data/disabled_ue4ss/.
8. Quick troubleshooting checklist
Symptom	Suspect / fix
Tree view loses expansion	Ensure ModTreeBrowser._wire_expansion_signals() is called after swapping models.
Index mismatch warnings	Usually stale Qt indexes – detach old model: view.setModel(None) before building a fresh proxy.
PAK missing in list	Call reconcile_pak_list(game_path) then refresh; verify .pak isn’t in DEFAULT_PAK_FILES.
UE4SS mods ignored	Confirm ue4ss_installed() returns (True, …) and that mods.txt contains mod_folder : 1.
9. Style & coding rules for agents

    Always mutate display_names.json using set_display_info(_bulk) helpers.

    Never write raw paths; use helpers in utils.py.

    UI code must go through PyQt5; follow dark-theme styles defined in main_window.py.

    New backend modules should not import from UI.

    Unit of state = settings.json + pak_mods.json; keep them consistent.