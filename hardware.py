"""Put the hardware models this project is checked against on the import path.

The models used to live in this repository as loose modules, each loaded by file
path. They are now separate repositories, pinned here as submodules at the
root, so that the thing this project is measured against is measured itself: the processor against
a per-opcode suite, the coprocessor against the chip's own reference, and the
cartridge map and the image handling against a library of real cartridges.

Two consequences are worth stating, because both change what code here must do.

The models start unclean. Their memory and registers hold arbitrary but
reproducible values rather than zeroes, because hardware does. Anything here that
wants a cleared machine now has to ask for one, and asking is the point: a read
of something never written stops looking deliberate.

And nothing is loaded by file path any more. `load()` returns a model by the name
it is published under, which reads the same way at the top of a module as the
file-path helper it replaces and does not need an import to be moved below a
statement to work.
"""

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

FIRMWARE = ROOT / "firmware"

FIRMWARE_VARIABLE = "UPD7725_FIRMWARE_DIR"

PACKAGES = {
    "mos65xx": "mos65xx-python",
    "snesdsp": "snes-dsp-python",
    "mapper": "snes-mapper-python",
    "romimage": "snes-rom-image-python",
}
"""The package each submodule provides, and the directory it lives in.

The directories sit at the root of this repository under the names of the
repositories they are, rather than under a folder that hides them. Anybody who
opens this project sees what it is built on without going looking, which is the
point: each of those is a project in its own right and is held to its own oracle.
"""


class UnknownPackage(Exception):
    pass


def root_of(package):
    """Where a vendored model lives, by the name it is imported under."""
    directory = PACKAGES.get(package)
    if directory is None:
        raise UnknownPackage(
            f"{package} is not vendored here; this project carries {', '.join(sorted(PACKAGES))}"
        )
    return ROOT / directory


def install(environment=None):
    """Make every vendored model importable, and say where the microcode is.

    The coprocessor model runs the part's own microcode, which belongs to whoever
    made the part and is never carried in any of these repositories. It looks in
    the directories that variable names, then beside itself. Neither reaches a
    project two levels up, so this points it at the one this project keeps, and
    adds to whatever was already named rather than replacing it: somebody who set
    the variable meant it.
    """
    for package in PACKAGES:
        entry = str(root_of(package))
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return name_firmware(environment)


def name_firmware(environment=None):
    """Put this project's firmware directory in front of whatever was named."""
    where = environment if environment is not None else os.environ
    already = [one for one in where.get(FIRMWARE_VARIABLE, "").split(os.pathsep) if one]
    if str(FIRMWARE) in already:
        return where[FIRMWARE_VARIABLE]
    where[FIRMWARE_VARIABLE] = os.pathsep.join([str(FIRMWARE), *already])
    return where[FIRMWARE_VARIABLE]


def load(package):
    """A model, by the name it is published under."""
    root_of(package)
    install()
    return importlib.import_module(package)
