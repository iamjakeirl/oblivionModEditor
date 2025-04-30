# Oblivion Remastered Mod Manager

A portable, Python-based mod manager for Oblivion Remastered.

## Features
- Drag-and-drop mod import (.zip, .7z, .rar)
- Mod installation, activation, deactivation
- Mod registry and load order management
- Portable: can run from a USB stick

## Packaging
To create a portable Windows executable:
1. Install requirements: `pip install -r requirements.txt`
2. Use PyInstaller:
   ```
   pyinstaller --onefile --add-data "data;data" main.py
   ```
3. The resulting `.exe` can be run from any location.

See `the_plan.md` for full design details. 