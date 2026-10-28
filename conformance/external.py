from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zlib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

MANIFEST = ROOT / "artifacts.manifest.json"

FOLDER = ROOT / "external"

SECTION = "external"

USAGE = "usage: external.py [--describe FILE ...]"

CHUNK = 1 << 20

IGNORED = frozenset({".DS_Store"})

VERIFIED = "verified"

MISSING = "missing"

WRONG = "wrong"

UNMODIFIED = "use an unmodified copy"

CHECKOUT = "checkout"


def kept(path: Path | str | None = None) -> dict[str, dict[str, Any]]:
    with Path(path or MANIFEST).open() as handle:
        held: dict[str, dict[str, Any]] = json.load(handle)[SECTION]
    return held


def identity(path: Path) -> dict[str, Any]:
    size = 0
    crc = 0
    hashes = {name: hashlib.new(name) for name in ("md5", "sha1", "sha256")}
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            size += len(chunk)
            crc = zlib.crc32(chunk, crc)
            for one in hashes.values():
                one.update(chunk)
    found: dict[str, Any] = {"size": size, "crc32": f"{crc:08x}"}
    found.update({name: one.hexdigest() for name, one in hashes.items()})
    return found


def diagnosis(
    artifact: Mapping[str, Any], entry: Mapping[str, Any], found: Mapping[str, Any]
) -> str:
    seen = f"{entry['path']} is {found['size']} bytes with SHA-256 {found['sha256']}"
    for bad in artifact.get("known_bad", []):
        if bad.get("sha256") == found["sha256"]:
            return f"{seen}, a known bad copy: {bad['reason']}"
    if found["size"] == entry["size"]:
        return f"{seen}: the right size with other bytes, so altered or patched; {UNMODIFIED}"
    expected = f"{entry['common_filename']} is {entry['size']} bytes"
    return f"{seen}, where {expected}; it is another file"


def head(where: Path) -> str:
    done = subprocess.run(
        ["git", "-C", str(where), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout.strip() if done.returncode == 0 else "no commit"


def examine_checkout(name: str, artifact: Mapping[str, Any], folder: Path) -> tuple[str, str]:
    where = folder / artifact["path"]
    again = f"fetch it with {artifact['fetchedBy']}"
    if not where.is_dir():
        return MISSING, f"{name}: {artifact['path']} is not in {folder.name}/; {again}"
    found = head(where)
    if found != artifact["commit"]:
        pinned = artifact["commit"]
        return WRONG, f"{name}: {artifact['path']} is at {found}, pinned at {pinned}; {again}"
    return VERIFIED, f"{name}: {artifact['path']} at {found[:12]}"


def examine(name: str, artifact: Mapping[str, Any], folder: Path) -> tuple[str, str]:
    if artifact.get("kind") == CHECKOUT:
        return examine_checkout(name, artifact, folder)
    present = [entry for entry in artifact["accepted"] if (folder / entry["path"]).is_file()]
    if not present:
        wanted = ", ".join(entry["path"] for entry in artifact["accepted"])
        return MISSING, f"{name}: none of {wanted} is in {folder.name}/"
    seen = []
    for entry in present:
        found = identity(folder / entry["path"])
        if found["sha256"] == entry["sha256"]:
            return VERIFIED, f"{name}: {entry['path']}, {entry['label']}"
        seen.append(diagnosis(artifact, entry, found))
    return WRONG, f"{name}: " + "; ".join(seen)


def unlisted(held: Mapping[str, Mapping[str, Any]], folder: Path) -> list[str]:
    files = [one for one in held.values() if one.get("kind") != CHECKOUT]
    named = {entry["path"] for artifact in files for entry in artifact["accepted"]}
    trees = tuple(f"{one['path']}/" for one in held.values() if one.get("kind") == CHECKOUT)
    if not folder.is_dir():
        return []
    return sorted(
        rel
        for path in folder.rglob("*")
        if path.is_file()
        and path.name not in IGNORED
        and (rel := path.relative_to(folder).as_posix()) not in named
        and not rel.startswith(trees)
    )


def say(line: str) -> None:
    sys.stdout.write(line + "\n")


def described(path: Path, folder: Path) -> dict[str, Any]:
    inside = path.is_relative_to(folder)
    where = path.relative_to(folder) if inside else path
    return {"path": where.as_posix(), "common_filename": path.name, **identity(path)}


def describe(paths: Sequence[str], folder: Path) -> int:
    refused = 0
    for given in paths:
        path = Path(given).resolve()
        if not path.is_file():
            say(f"REFUSED {given} is not a file")
            refused += 1
            continue
        say(json.dumps(described(path, folder.resolve()), indent=2))
    return 1 if refused else 0


def report(held: Mapping[str, Mapping[str, Any]], folder: Path) -> int:
    counts = {VERIFIED: 0, MISSING: 0, WRONG: 0}
    failed = False
    for name, artifact in held.items():
        state, line = examine(name, artifact, folder)
        counts[state] += 1
        say(f"{'ok' if state == VERIFIED else state.upper()} {line}")
        failed = failed or state == WRONG or (state == MISSING and bool(artifact.get("required")))
    extra = unlisted(held, folder)
    for rel in extra:
        say(f"UNLISTED {rel} is in {folder.name}/ and in no manifest entry")
    say(
        f"{counts[VERIFIED]} of {len(held)} verified, {counts[MISSING]} missing, "
        f"{counts[WRONG]} wrong, {len(extra)} unlisted"
    )
    return 1 if failed else 0


def main(
    argv: Sequence[str],
    where: Path | str | None = None,
    manifest: Path | str | None = None,
) -> int:
    folder = Path(where or FOLDER)
    if argv and argv[0] == "--describe":
        if len(argv) == 1:
            raise SystemExit(USAGE)
        return describe(argv[1:], folder)
    if argv:
        raise SystemExit(USAGE)
    return report(kept(manifest), folder)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
