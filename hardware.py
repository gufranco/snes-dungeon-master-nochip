"""Put the hardware models this project is checked against on the import path.

The models used to live in this repository as loose modules, each loaded by file
path. They are now separate repositories, pinned here as submodules, so that the
thing this project is measured against is measured itself: the processor against
a per-opcode suite, the coprocessor against the chip's own reference, the
cartridge map against a library of real cartridges.

Two consequences are worth stating, because both change what code here must do.

The models start unclean. Their memory and registers hold arbitrary but
reproducible values rather than zeroes, because hardware does. Anything here that
wants a cleared machine now has to ask for one, and asking is the point: a read
of something never written stops looking deliberate.

And nothing is loaded by file path any more. The packages are ordinary imports
once `install()` has run, which is the one thing this module does.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EMULATORS = ROOT / "emulators"

PACKAGES = {
    "mos65xx": "mos65xx",
    "dsp2": "snes-dsp2",
    "mapper": "snes-mapper",
}
"""The package each submodule provides, and the directory it lives in."""


class UnknownPackage(Exception):
    pass


def root_of(package):
    """Where a vendored model lives, by the name it is imported under."""
    directory = PACKAGES.get(package)
    if directory is None:
        raise UnknownPackage(
            f"{package} is not vendored here; this project carries {', '.join(sorted(PACKAGES))}"
        )
    return EMULATORS / directory


def install():
    """Make every vendored model importable, without stacking the path."""
    for package in PACKAGES:
        entry = str(root_of(package))
        if entry not in sys.path:
            sys.path.insert(0, entry)
