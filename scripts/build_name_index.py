from __future__ import annotations

import argparse
import json
from pathlib import Path

from endfieldlogs.game_data import build_name_index


def build_parser() -> argparse.ArgumentParser:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Build compact Endfield character name index")
    parser.add_argument("--character-table", type=Path, default=root / "jsondata" / "CharacterTable.json")
    parser.add_argument("--i18n-table", type=Path, default=root / "jsondata" / "I18nTextTable_CN.json")
    parser.add_argument("--output", type=Path, default=root / "jsondata" / "CharacterNameIndex.json")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    name_index = build_name_index(args.character_table.resolve(), args.i18n_table.resolve())
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(name_index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {len(name_index)} names to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
