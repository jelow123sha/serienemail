# Serienmail.spec
block_cipher = None

a = Analysis(
    ['Serienmail.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'PyQt5.QtCore.Qt',
        'PyQt5.QtGui.QIcon',
        'PyQt5.QtWidgets.QApplication',
        'PyQt5.QtWidgets.QMainWindow',
        'PyQt5.QtWidgets.QTableWidget',
        'PyQt5.QtWidgets.QComboBox',
        'PyQt5.QtWidgets.QFileDialog',
        'PyQt5.QtWidgets.QMenu',
        'PyQt5.QtWidgets.QCheckBox',
        'email.mime.multipart',
        'email.mime.text',
        'email.mime.base',
        'email.encoders',
        'mimetypes'
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='Serienmail',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon=None
)
