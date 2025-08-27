# PyInstaller spe c file for Remote Zip Explorer
# Uses ico icon for all platforms
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

a = Analysis([
    'main.py',
],
    pathex=[],
    binaries=[],
    datas=[('Remote Zip Explorer.ico', '.')],
    hiddenimports=collect_submodules('remotezip'),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
	pyz,
	a.scripts,
	[],
	exclude_binaries=True,
	name='RemoteZipExplorer',
	debug=False,
	bootloader_ignore_signals=False,
	strip=False,
	upx=True,
	console=False,
	icon='Remote Zip Explorer.ico',
)
coll = COLLECT(
	exe,
	a.binaries,
	a.zipfiles,
	a.datas,
	strip=False,
	upx=True,
	upx_exclude=[],
	name='RemoteZipExplorer'
)



