# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# LEGALDONG-UI-1: 공식 법정동 Snapshot을 EXE 내부(sys._MEIPASS)에 번들한다 -
# src/pc/legal_dong_loader.default_snapshot_path()가 frozen 환경에서
# _MEIPASS/data/legal_dong_snapshot.json을 찾는다.
datas += [('data/legal_dong_snapshot.json', 'data')]

# EXE-PACKAGE-1: data/regions_kr_sample.json도 frozen 환경에 번들해야 한다 -
# src/ui.py의 REGIONS_SAMPLE_PATH가 이 파일을 못 찾으면
# _ensure_subdivision_data_loaded()(앱 시작 시 auto_subdivide_var 값과
# 무관하게 항상 호출됨)가 FileNotFoundError를 그대로 전파해 앱이 시작도
# 되기 전에 크래시한다.
datas += [('data/regions_kr_sample.json', 'data')]


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='NaverPlaceSalesDBCollector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
