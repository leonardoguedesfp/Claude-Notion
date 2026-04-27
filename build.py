#!/usr/bin/env python3
"""Build script — packages the app into a Windows .exe via PyInstaller."""
from __future__ import annotations

import pathlib
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
ASSETS = ROOT / "notion_rpadv" / "assets"
ICON = ASSETS / "icon.ico"


def generate_icon() -> None:
    """Generate icon.ico from PNG asset using Pillow."""
    try:
        from PIL import Image  # type: ignore[import]
    except ImportError:
        print("Warning: Pillow not installed, skipping icon generation.")
        return

    src = ASSETS / "symbol-navy.png"
    if not src.exists():
        print(f"Warning: {src} not found, skipping icon generation.")
        return

    img = Image.open(src).convert("RGBA")
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    imgs = [img.resize(s, Image.LANCZOS) for s in sizes]

    ICON.parent.mkdir(exist_ok=True, parents=True)
    imgs[0].save(ICON, format="ICO", append_images=imgs[1:], sizes=sizes)
    print(f"Icon written: {ICON}")


def run_pyinstaller() -> None:
    icon_arg = f"--icon={ICON}" if ICON.exists() else "--icon=NONE"

    cmd: list[str] = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--name", "NotionRPADV",
        icon_arg,
        "--add-data", f"{ASSETS}{';' if sys.platform == 'win32' else ':'}notion_rpadv/assets",
        # Hidden imports that PyInstaller may miss
        "--hidden-import", "keyring.backends.Windows",
        "--hidden-import", "keyring.backends.SecretService",
        "--hidden-import", "notion_rpadv.pages.dashboard",
        "--hidden-import", "notion_rpadv.pages.processos",
        "--hidden-import", "notion_rpadv.pages.clientes",
        "--hidden-import", "notion_rpadv.pages.tarefas",
        "--hidden-import", "notion_rpadv.pages.catalogo",
        "--hidden-import", "notion_rpadv.pages.importar",
        "--hidden-import", "notion_rpadv.pages.logs",
        "--hidden-import", "notion_rpadv.pages.configuracoes",
        "--hidden-import", "notion_rpadv.widgets.command_palette",
        "--hidden-import", "notion_rpadv.widgets.shortcuts_modal",
        "--hidden-import", "notion_rpadv.widgets.floating_save",
        "--hidden-import", "notion_rpadv.widgets.toast",
        "--hidden-import", "notion_rpadv.widgets.modal",
        "--hidden-import", "notion_rpadv.widgets.sidebar",
        "--hidden-import", "notion_rpadv.widgets.status_bar",
        "--hidden-import", "notion_rpadv.widgets.chip",
        "--hidden-import", "notion_rpadv.widgets.person_chip",
        "--hidden-import", "notion_rpadv.services.notion_facade",
        "--hidden-import", "notion_rpadv.services.log_service",
        "--hidden-import", "notion_rpadv.services.shortcuts",
        "--hidden-import", "notion_rpadv.cache.db",
        "--hidden-import", "notion_rpadv.cache.sync",
        "--hidden-import", "notion_bulk_edit.schemas",
        "--hidden-import", "notion_bulk_edit.config",
        "--hidden-import", "notion_bulk_edit.validators",
        "--hidden-import", "notion_bulk_edit.encoders",
        "--hidden-import", "notion_bulk_edit.notion_api",
        "--hidden-import", "notion_bulk_edit.gerar_template",
        "--hidden-import", "openpyxl",
        "--collect-data", "notion_rpadv",
        "--collect-data", "notion_bulk_edit",
        # Suppress the console on Windows
        "--noconsole",
        "notion_rpadv/__main__.py",
    ]

    subprocess.run(cmd, check=True, cwd=str(ROOT))


def clean_build_artifacts() -> None:
    """Remove previous build and spec files."""
    for d in (BUILD,):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            print(f"Removed: {d}")

    spec_file = ROOT / "NotionRPADV.spec"
    if spec_file.exists():
        spec_file.unlink()
        print(f"Removed: {spec_file}")


def main() -> None:
    print("=== NotionRPADV Build ===")
    print(f"Root: {ROOT}")

    print("\n[1/3] Generating icon…")
    generate_icon()

    print("\n[2/3] Running PyInstaller…")
    run_pyinstaller()

    exe_name = "NotionRPADV.exe" if sys.platform == "win32" else "NotionRPADV"
    exe_path = DIST / exe_name
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n[3/3] Build complete: {exe_path} ({size_mb:.1f} MB)")
    else:
        print(f"\n[3/3] Build complete. Output in: {DIST}")


if __name__ == "__main__":
    main()
