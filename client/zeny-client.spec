from pathlib import Path

client_directory = Path(SPECPATH)
project_root = client_directory.parent
source_root = project_root / "src"
icon_path = source_root / "zeny_project_handler_client" / "assets" / "zeny_project_handler.ico"
asset_directory = source_root / "zeny_project_handler_client" / "assets"
asset_target = "zeny_project_handler_client/assets"

analysis = Analysis(
    [str(source_root / "zeny_project_handler_client" / "__main__.py")],
    pathex=[str(source_root)],
    binaries=[],
    datas=[
        (str(asset_directory / "zeny_project_handler.ico"), asset_target),
        (str(asset_directory / "zeny_project_handler.png"), asset_target),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "alembic",
        "fitz",
        "pymupdf",
        "sqlite3",
        "sqlalchemy",
        "zeny_project_handler",
        "zeny_project_handler_api_spec",
        "zeny_project_handler_server",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ZenyProjectHandler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(icon_path),
)
bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ZenyProjectHandler",
)
