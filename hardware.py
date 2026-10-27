import importlib
import os
import sys
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent

FIRMWARE = ROOT / "firmware"

FIRMWARE_VARIABLE = "UPD7725_FIRMWARE_DIR"

POLL_LIMIT = 1_000_000

PACKAGES = {
    "mos65xx": "mos65xx-python",
    "snesdsp": "snes-dsp-python",
    "mapper": "snes-mapper-python",
    "romimage": "snes-rom-image-python",
}


class UnknownPackage(Exception):
    pass


class PartNeverAsked(Exception):
    pass


def root_of(package: str) -> Path:
    directory = PACKAGES.get(package)
    if directory is None:
        raise UnknownPackage(
            f"{package} is not vendored here; this project carries {', '.join(sorted(PACKAGES))}"
        )
    return ROOT / directory


def install(environment: MutableMapping[str, str] | None = None) -> str:
    for package in PACKAGES:
        entry = str(root_of(package))
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return name_firmware(environment)


def name_firmware(environment: MutableMapping[str, str] | None = None) -> str:
    where = environment if environment is not None else os.environ
    already = [one for one in where.get(FIRMWARE_VARIABLE, "").split(os.pathsep) if one]
    if str(FIRMWARE) in already:
        return where[FIRMWARE_VARIABLE]
    where[FIRMWARE_VARIABLE] = os.pathsep.join([str(FIRMWARE), *already])
    return where[FIRMWARE_VARIABLE]


def load(package: str) -> Any:
    root_of(package)
    install()
    return importlib.import_module(package)


def answer(part: Any, limit: int = POLL_LIMIT) -> int:
    for _ in range(limit):
        if part.asking:
            return int(part.read())
        part.step()
    raise PartNeverAsked(f"the part did not raise its request in {limit} steps")
