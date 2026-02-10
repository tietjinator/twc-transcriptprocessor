# PyInstaller spec for bootstrap app
# This bundles only the bootstrap UI + installer. Runtime is downloaded on first run.

from PyInstaller.utils.hooks import collect_submodules

hidden_imports = collect_submodules("tkinter") + collect_submodules("app")

block_cipher = None


a = Analysis(
    ["../app/entrypoint.py"],
    pathex=[".."],
    binaries=[],
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="Transcript Processor",
    debug=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="Transcript Processor",
)

app = BUNDLE(
    coll,
    name="Transcript Processor.app",
    icon="../assets/AppIcon.icns",
)
