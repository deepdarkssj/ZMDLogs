from __future__ import annotations

import os
import shutil
from pathlib import Path


def _require_pyinstaller():
    try:
        from PyInstaller.__main__ import run as pyinstaller_run
        from PyInstaller.utils.hooks import collect_data_files, collect_submodules
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "PyInstaller is not installed. Run:\n"
            "  python -m pip --python .\\.venv\\Scripts\\python.exe install pyinstaller"
        ) from exc
    return pyinstaller_run, collect_data_files, collect_submodules


def _add_data_arg(path: Path, target: str) -> str:
    return f"{path}{os.pathsep}{target}"


def main() -> int:
    pyinstaller_run, collect_data_files, collect_submodules = _require_pyinstaller()

    root = Path(__file__).resolve().parents[1]
    dist_dir = root / "build" / "dist"
    work_dir = root / "build" / "pyinstaller"
    spec_dir = root / "build" / "spec"

    for folder in (dist_dir, work_dir, spec_dir):
        folder.mkdir(parents=True, exist_ok=True)

    data_pairs: list[tuple[Path, str]] = [
        (root / "data", "data"),
        (root / "icon", "icon"),
        (root / "icon.png", "."),
        (root / "icon.ico", "."),
        (root / "jsondata" / "ActorImageTable.json", "jsondata"),
        (root / "jsondata" / "CharacterNameIndex.json", "jsondata"),
        (root / "overlay" / "dist", "overlay/dist"),
        (root / "overlay_comboskill" / "dist", "overlay_comboskill/dist"),
        (root / "overlay_buff" / "dist", "overlay_buff/dist"),
        (root / "overlay_uid" / "dist", "overlay_uid/dist"),
        (root / "src" / "endfieldlogs" / "overlay_assets", "endfieldlogs/overlay_assets"),
    ]
    datas: list[str] = [_add_data_arg(path, target) for path, target in data_pairs if path.exists()]
    datas.extend(_add_data_arg(Path(src), dest) for src, dest in collect_data_files("qfluentwidgets"))

    hidden_imports = sorted(
        set(
            collect_submodules("qfluentwidgets")
            + collect_submodules("endfieldlogs.proto_generated")
            + [
                "PySide6.QtCore",
                "PySide6.QtGui",
                "PySide6.QtWidgets",
                "PySide6.QtWebEngineCore",
                "PySide6.QtWebEngineWidgets",
            ]
        )
    )

    name = "EndfieldLogs"
    app_dir = dist_dir / name
    if app_dir.exists():
        shutil.rmtree(app_dir)

    args = [
        str(root / "scripts" / "launch_gui.py"),
        "--name",
        name,
        "--onedir",
        "--windowed",
        "--clean",
        "--noconfirm",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(work_dir),
        "--specpath",
        str(spec_dir),
        "--paths",
        str(root / "src"),
    ]
    icon_path = root / "icon.ico"
    if icon_path.exists():
        args.extend(["--icon", str(icon_path)])
    for data_arg in datas:
        args.extend(["--add-data", data_arg])
    for hidden in hidden_imports:
        args.extend(["--hidden-import", hidden])

    pyinstaller_run(args)
    print(f"built {app_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
