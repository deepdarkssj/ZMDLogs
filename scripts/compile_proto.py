from __future__ import annotations

import subprocess
import sys
from pathlib import Path
import shutil
import re

ROOT_PROTOS = [
    "CS_BATTLE_OP.proto",
    "CS_ENTER_DUNGEON.proto",
    "CS_LEAVE_DUNGEON.proto",
    "CS_MERGE_MSG.proto",
    "EQUIP_DATA.proto",
    "ITEM_INST.proto",
    "SC_OBJECT_ENTER_VIEW.proto",
    "SC_OBJECT_LEAVE_VIEW.proto",
    "SC_SYNC_CHAR_BAG_INFO.proto",
    "SC_SELF_SCENE_INFO.proto",
]


def collect_proto_closure(proto_dir: Path, roots: list[str]) -> list[Path]:
    pending = list(roots)
    seen: set[str] = set()
    ordered: list[Path] = []

    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        path = proto_dir / name
        if not path.exists():
            raise SystemExit(f"missing proto dependency: {path}")
        ordered.append(path)
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            stripped = line.strip()
            if not stripped.startswith('import "'):
                continue
            dependency = stripped.split('"', 2)[1]
            pending.append(dependency)

    return sorted(ordered)


def sanitize_proto_file(source: Path, target: Path) -> None:
    stack: list[dict[str, object]] = []
    output_lines: list[str] = []
    message_field_re = re.compile(r"=\s*(\d+)\s*;")
    for line in source.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith("message ") and stripped.endswith("{"):
            stack.append({"kind": "message", "name": stripped.split()[1], "used": set()})
            output_lines.append(line)
            continue
        if stripped.startswith("enum ") and stripped.endswith("{"):
            stack.append({"kind": "enum", "name": stripped.split()[1]})
            output_lines.append(line)
            continue
        if stripped.startswith("oneof ") and stripped.endswith("{"):
            used = None
            for ctx in reversed(stack):
                if ctx["kind"] == "message":
                    used = ctx["used"]
                    break
            stack.append({"kind": "oneof", "name": stripped.split()[1], "used": used or set()})
            output_lines.append(line)
            continue
        if stack and stripped == "}":
            stack.pop()
            output_lines.append(line)
            continue

        current = stack[-1] if stack else None
        if current and current["kind"] == "enum" and stripped.startswith("None ="):
            indent = line[: len(line) - len(line.lstrip())]
            output_lines.append(f"{indent}{current['name']}_None = {stripped.split('=', 1)[1]}")
            continue

        if current and current["kind"] in {"message", "oneof"}:
            match = message_field_re.search(stripped)
            used = current["used"]
            if match and not stripped.startswith(("reserved ", "option ", "extensions ")):
                field_no = int(match.group(1))
                if field_no in used:
                    candidate = field_no + 1
                    while candidate in used:
                        candidate += 1
                    line = message_field_re.sub(f"= {candidate};", line, count=1)
                    field_no = candidate
                used.add(field_no)

        output_lines.append(line)
    target.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def build_sanitized_proto_dir(root: Path, proto_files: list[Path]) -> Path:
    sanitized_dir = root / ".proto_sanitized"
    if sanitized_dir.exists():
        shutil.rmtree(sanitized_dir)
    sanitized_dir.mkdir(parents=True, exist_ok=True)
    for path in proto_files:
        sanitize_proto_file(path, sanitized_dir / path.name)
    return sanitized_dir


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    proto_dir = root / "proto"
    out_dir = root / "src" / "endfieldlogs" / "proto_generated"

    if not proto_dir.exists():
        raise SystemExit(f"proto directory not found: {proto_dir}")

    out_dir.mkdir(parents=True, exist_ok=True)
    proto_files = collect_proto_closure(proto_dir, ROOT_PROTOS)
    if not proto_files:
        raise SystemExit(f"no proto files found in {proto_dir}")
    sanitized_dir = build_sanitized_proto_dir(root, proto_files)

    for path in proto_files:
        cmd = [
            sys.executable,
            "-m",
            "grpc_tools.protoc",
            f"-I{sanitized_dir}",
            f"--python_out={out_dir}",
            str(sanitized_dir / path.name),
        ]
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            return int(result.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
