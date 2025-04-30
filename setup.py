from cx_Freeze import setup, Executable
import os
import shutil

# Build options
build_exe_options = {
    "packages": ["PyQt5", "py7zr", "rarfile", "pyunpack", "easyprocess"],
    "include_files": [],  # Add data files or folders if needed
    "excludes": ["PyQt5.QtQml", "PyQt5.QtQuick"],  # Exclude QML modules to avoid QmlImportsPath error
    # We'll move all files to 'libs' after build
}

# Main executable
exe = Executable(
    script="oblivion_mod_manager/main.py",
    base="Win32GUI",  # Use "Console" if you want a console window
    target_name="OblivionModManager.exe"
)

setup(
    name="OblivionModManager",
    version="1.0",
    description="jorkXL's Oblivion Remastered Mod Manager",
    options={"build_exe": build_exe_options},
    executables=[exe]
)

# --- Post-build step: Move all dependencies to 'libs' subfolder ---
def move_dependencies_to_libs(build_dir, exe_name):
    libs_dir = os.path.join(build_dir, "libs")
    os.makedirs(libs_dir, exist_ok=True)
    for item in os.listdir(build_dir):
        item_path = os.path.join(build_dir, item)
        # Skip the main exe and the libs folder itself
        if item == exe_name or item == "libs":
            continue
        # Move files and folders to libs
        shutil.move(item_path, os.path.join(libs_dir, item))

if __name__ == "__main__":
    # Only run post-build if the build folder exists
    build_dir = os.path.join("build", "exe.win-amd64-3.12")  # Adjust Python version as needed
    exe_name = "OblivionModManager.exe"
    if os.path.exists(build_dir):
        move_dependencies_to_libs(build_dir, exe_name) 