# Oblivion Remastered Mod Manager – Python-Only Plan

## 1. Technology & Architecture
- **Language:** Python 3.x only (no Electron, Node, or JS)
- **GUI Framework:** PyQt5, PySide6, or Tkinter (PyQt5/PySide6 recommended for modern look and drag-and-drop support)
- **Single Process:** All logic (UI, file handling, mod management) runs in one Python process
- **Distribution:** Use PyInstaller or cx_Freeze to bundle the app into a standalone executable for Windows

## 2. Directory Structure
- `main.py` – Entry point, launches the GUI
- `mod_manager/` – Core logic (mod install, toggle, registry, etc.)
- `ui/` – GUI code (can be in main.py for simplicity)
- `data/` – Stores mod registry (JSON/SQLite), settings, temp files

## 3. Core Features & Steps

### A. Drag-and-Drop Mod Import
- **UI:** Main window with a visible drag-and-drop area ("Drop your .zip, .7z, or .rar mod here")
- **Validation:** Accept only .zip, .7z, or .rar files. Show error for others
- **Feedback:** Show progress bar or spinner during install

### B. Archive Extraction & Mod Detection
- **Extraction:** Use `zipfile` for .zip, `py7zr` for .7z, and `rarfile`/`pyunpack` for .rar (all pure Python)
- **Temp Folder:** Extract to a temp directory inside `data/temp/`
- **Detection:** Scan for `.esp` and `.pak` files (case-insensitive). Note any other files (e.g., .bsa, .ini)

### C. Install Files to Game Directories
- **Game Path:** Let user set the Oblivion Remastered install path (store in settings)
- **.pak:** Copy to `Content\Paks\~mods\` (create if missing)
- **.esp:** Copy to `Content\Dev\ObvData\Data\`
- **Other files:** Copy as needed (e.g., .bsa, .ini, loose assets)

### D. Update Plugins.txt
- **Location:** `Content\Dev\ObvData\Data\Plugins.txt`
- **Add .esp:** Append new .esp names (avoid duplicates)
- **Format:** One plugin per line, plain text

### E. Mod Registry
- **Storage:** Use a JSON file (e.g., `data/mods.json`) to track installed mods:
    ```json
    [
      {
        "modName": "MyMod",
        "espFiles": ["MyMod.esp"],
        "pakFiles": ["pakchunk99-MyMod.pak"],
        "active": true
      }
    ]
    ```
- **Purpose:** Track which mods are installed, their files, and active/inactive state

### F. Mod Activation/Deactivation
- **UI:** List installed mods with toggle (checkbox or button)
- **Deactivate .esp:** Remove from Plugins.txt
- **Deactivate .pak:** Move to `Content\Paks\~mods\disabled\`
- **Activate:** Reverse the above
- **Sync registry and UI after each action**

### G. Mod List & Load Order
- **UI:** Show all installed mods, their status, and file types (icons or text)
- **Load Order:** Allow user to move .esp mods up/down in the list
- **On change:** Rewrite Plugins.txt to match new order (keep official files at top)

### H. Settings & About
- **Settings:** Let user set/change game path
- **About:** List open-source components and licenses

### I. Error Handling & Backups
- **Backups:** Before changing Plugins.txt or overwriting files, make a backup
- **Errors:** Show clear error messages in the UI

### J. Packaging
- **Bundle:** Use PyInstaller/cx_Freeze to create a Windows .exe (include Python, dependencies)
- **No external dependencies:** All libraries must be open-source and included in the bundle

## 4. Optional Enhancements
- **Portable Mode:** Allow running from a USB stick (store data in app folder)
- **Basic Accessibility:** Keyboard navigation, color contrast
- **Future File Types:** Make file detection logic easy to update

## 5. Example Minimal Directory Layout
```
oblivion_mod_manager/
│
├── main.py
├── mod_manager/
│   ├── __init__.py
│   ├── install.py
│   ├── registry.py
│   └── utils.py
├── ui/
│   └── main_window.py
├── data/
│   ├── mods.json
│   └── settings.json
├── requirements.txt
└── README.md
```

## 6. Recommended Libraries
- PyQt5 or PySide6 (GUI)
- zipfile (standard library, for .zip)
- py7zr (for .7z)
- rarfile, patool, pyunpack (for .rar)
- shutil, os, pathlib (file operations)
- json (mod registry)
- PyInstaller (for packaging)

## 7. Core User Flow
1. User launches app, sets game path if not already set
2. User drags a mod archive onto the window
3. App extracts, detects, and installs files
4. App updates Plugins.txt and registry
5. User sees mod in list, can toggle on/off or reorder
6. All changes reflected in game files and Plugins.txt

---

This approach keeps your app simple, Pythonic, and easy to maintain, while still delivering all the essential features for mod management.