from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .install_detect import detect_game_dll_dir
from .logging_utils import configure_logging
from .runtime_paths import bundle_root
from .service import DamageLogService, ServiceConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Endfield damage log service")
    subparsers = parser.add_subparsers(dest="command", required=True)
    gui = subparsers.add_parser("gui", help="Run the PySide6 control panel")
    gui.add_argument("--config", type=Path, default=None)
    gui.add_argument("--debug", action="store_true", help="Write parsed debug messages to local JSON files")
    gui.add_argument("--debug-dir", type=Path, default=None)

    serve = subparsers.add_parser("serve", help="Run the realtime damage log service")
    serve.add_argument("--ws-port", type=int, default=29325)
    serve.add_argument("--log-dir", type=Path, default=Path("logs"))
    serve.add_argument("--log-level", default="INFO")
    serve.add_argument("--game-exe", default="Endfield.exe")
    serve.add_argument("--npcap-device", default="auto")
    serve.add_argument(
        "--dll-dir",
        type=Path,
        default=detect_game_dll_dir() or Path(r"E:\Hypergryph Launcher\games\Endfield Game"),
    )
    serve.add_argument("--no-overlay", action="store_true", help="Run the service without opening the floating overlay window")
    serve.add_argument("--debug", action="store_true", help="Write parsed debug messages to local JSON files")
    serve.add_argument("--debug-dir", type=Path, default=Path("debug"))
    serve.add_argument(
        "--merge-multi-phase-enemy-battles",
        action="store_true",
        help="Merge configured multi-phase boss fights into a single battle until the tracked enemy dies",
    )
    root = bundle_root()
    serve.add_argument("--rsa-key-txt", type=Path, default=root.parent / "rsa_keys.txt")
    serve.add_argument("--name-index", type=Path, default=root / "jsondata" / "CharacterNameIndex.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "gui":
        from .gui_main import run_gui

        return run_gui(
            args.config.resolve() if args.config is not None else None,
            debug_enabled=bool(args.debug),
            debug_dir=args.debug_dir.resolve() if args.debug_dir is not None else None,
        )

    configure_logging(args.log_level)
    config = ServiceConfig(
        ws_port=args.ws_port,
        log_dir=args.log_dir.resolve(),
        log_level=args.log_level,
        game_exe=args.game_exe,
        npcap_device=args.npcap_device,
        dll_dir=args.dll_dir.resolve(),
        debug_enabled=bool(args.debug),
        debug_dir=args.debug_dir.resolve(),
        rsa_key_txt=args.rsa_key_txt.resolve(),
        name_index_path=args.name_index.resolve(),
        merge_multi_phase_enemy_battles=bool(args.merge_multi_phase_enemy_battles),
    )
    if args.no_overlay:
        service = DamageLogService(config)
        asyncio.run(service.run())
    else:
        from .overlay_host import run_with_overlay

        return run_with_overlay(config)
    return 0
