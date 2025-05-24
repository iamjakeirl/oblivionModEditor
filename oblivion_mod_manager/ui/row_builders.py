"""
Reusable helpers that convert backend objects into the generic
{ id, real, subfolder, … , pak_info } row format expected by ModTreeModel.
Later we'll add ESP + UE4SS builders.
"""
def rows_from_paks(pak_mods, display_cache, normalize_cb):
    rows = []
    import re
    by_filename = {cid.split('|')[-1]: info for cid, info in display_cache.items()}
    for pak in pak_mods:
        subfolder = pak.get('subfolder', '') or ''
        # Normalize subfolder: strip DisabledMods[\/] prefix if present
        norm_subfolder = normalize_cb(subfolder)
        norm_mod_id = f"{norm_subfolder}|{pak['name']}"
        orig_mod_id = f"{subfolder}|{pak['name']}"
        # Try normalized mod_id, then original, then by filename
        disp_info = display_cache.get(norm_mod_id) or display_cache.get(orig_mod_id) or by_filename.get(pak["name"], {})
        rows.append({
            "id":        orig_mod_id,
            "real":      pak["name"],
            "display":   disp_info.get("display", pak["name"]),
            "group":     disp_info.get("group", ""),
            "subfolder": pak.get("subfolder"),
            "active":    pak.get("active", True),
            "pak_info":  pak,
        })
    return rows

def rows_from_esps(enabled, disabled):
    # return list[dict] mimicking rows_from_paks; group == "" for now
    # id format: f"|{esp_name}"
    from mod_manager.utils import get_display_info
    
    rows = []
    for esp in enabled:
        display_info = get_display_info(esp)
        rows.append({
            "id": f"|{esp}",
            "real": esp,
            "display": display_info.get("display", esp),
            "group": display_info.get("group", ""),
            "subfolder": None,
            "active": True,
            "esp_info": {"name": esp, "enabled": True},
        })
    for esp in disabled:
        display_info = get_display_info(esp)
        rows.append({
            "id": f"|{esp}",
            "real": esp,
            "display": display_info.get("display", esp),
            "group": display_info.get("group", ""),
            "subfolder": None,
            "active": False,
            "esp_info": {"name": esp, "enabled": False},
        })
    return rows

def rows_from_ue4ss(enabled, disabled):
    rows = []
    for mod in enabled:
        rows.append({
            "id": f"|{mod}",
            "real": mod,
            "display": mod,
            "group": "",
            "subfolder": None,
            "active": True,
            "ue4ss_info": {"name": mod, "enabled": True},
        })
    for mod in disabled:
        rows.append({
            "id": f"|{mod}",
            "real": mod,
            "display": mod,
            "group": "",
            "subfolder": None,
            "active": False,
            "ue4ss_info": {"name": mod, "enabled": False},
        })
    return rows

# ---------------------------------------------------------------------------
# MagicLoader JSON rows
# ---------------------------------------------------------------------------
def rows_from_magic(enabled, disabled):
    # Similar to rows_from_esps - support display names and groups
    # id format: f"|{mod_name}"
    from mod_manager.utils import get_display_info
    
    rows = []
    for mod in enabled:
        display_info = get_display_info(f"|{mod}")
        rows.append({
            "id": f"|{mod}",
            "real": mod,
            "display": display_info.get("display", mod),
            "group": display_info.get("group", ""),
            "subfolder": None,
            "active": True,
            "magic_info": {"name": mod, "enabled": True},
        })
    for mod in disabled:
        display_info = get_display_info(f"|{mod}")
        rows.append({
            "id": f"|{mod}",
            "real": mod,
            "display": display_info.get("display", mod),
            "group": display_info.get("group", ""),
            "subfolder": None,
            "active": False,
            "magic_info": {"name": mod, "enabled": False},
        })
    return rows

# ---------------------------------------------------------------------------
# OBSE64 Plugin rows
# ---------------------------------------------------------------------------
def rows_from_obse64_plugins(enabled, disabled):
    """Convert OBSE64 plugin lists to row format for ModTreeBrowser.
    enabled/disabled are lists of .dll plugin filenames.
    """
    rows = []
    for plugin in enabled:
        rows.append({
            "id": f"|{plugin}",
            "real": plugin,
            "display": plugin,
            "group": "",
            "subfolder": None,
            "active": True,
            "obse64_info": {"name": plugin, "enabled": True},
        })
    for plugin in disabled:
        rows.append({
            "id": f"|{plugin}",
            "real": plugin,
            "display": plugin,
            "group": "",
            "subfolder": None,
            "active": False,
            "obse64_info": {"name": plugin, "enabled": False},
        })
    return rows 