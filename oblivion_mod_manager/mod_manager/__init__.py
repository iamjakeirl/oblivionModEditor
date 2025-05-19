# Re‑export helpers so external scripts can do `from mod_manager import magicloader_installed`
from .magicloader_installer import (
    magicloader_installed,
    install_magicloader,
    uninstall_magicloader,
    reenable_magicloader,
) 