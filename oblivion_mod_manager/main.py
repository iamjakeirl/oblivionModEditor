# Entry point for jorkXL's Oblivion Remastered Mod Manager
# This file will launch the main GUI

def main():
    from mod_manager.utils import get_game_path, migrate_disabled_mods_if_needed
    game_path = get_game_path()
    if game_path:
        migrate_disabled_mods_if_needed(game_path)
    from ui.main_window import run
    run()

if __name__ == "__main__":
    main() 