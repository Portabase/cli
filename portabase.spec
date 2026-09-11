# PyInstaller build definition. Declarative, so the workflows do not carry
# build flags and `uv run pyinstaller portabase.spec` reproduces CI locally.
#
# The binary name comes from PORTABASE_BINARY_NAME (default: portabase); the
# release matrix sets it to portabase_<os>_<arch>.
import os

from PyInstaller.utils.hooks import collect_all, collect_data_files

NAME = os.environ.get("PORTABASE_BINARY_NAME", "portabase")

datas = [
    ("pyproject.toml", "."),
    ("templates", "templates"),
]
binaries = []
hiddenimports = []

for package in ("rich", "requests"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

datas += collect_data_files("certifi")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=NAME,
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
