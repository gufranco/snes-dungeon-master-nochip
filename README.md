<div align="center">

# Dungeon Master without the DSP-2

**Tooling to build a Dungeon Master ROM with the coprocessor designed out, so it runs from any flash
cartridge that can hold it.**

[![licence](https://img.shields.io/github/license/gufranco/dungeon-master-nochip)](LICENSE)

</div>

---

## What this is

Dungeon Master is the only SNES cartridge that carries a DSP-2. The chip converts the game's Atari ST
bitmap graphics into the console's own tile format, scales them for the dungeon view, composites them
against a transparent colour, and multiplies. Without it the game does not draw.

This project computes ahead of time everything the chip computes from fixed inputs, stores the results
in a larger image, and redirects the code that used to ask the chip so it reads the finished bytes
instead. The three operations that take run-time operands become native 65816. The result is an
ordinary SNES ROM with no coprocessor to emulate.

You supply the retail dump. Nothing here contains game data, and nothing ever will.

## Status

Not buildable yet. The analysis tooling and the scaffolding are in place; the conversion is not. This
section says what runs, and it will say more as more does.

| part | state |
|------|-------|
| dump identification | works |
| 65816 disassembly and interpretation | works, against a per-opcode suite |
| the DSP-2's own behaviour | works, against the chip's reference implementation |
| address arithmetic for the expanded image | works, against a library of real cartridges |
| pinned assembler container | builds |
| the conversion itself | not started |

## The dump

Named as No-Intro names it. Every digest is of the whole file with no copier header. SHA-256 is the
one that decides; the others are there to cross-check against databases that still key on them.

| file | read as | size |
|---|---|---|
| Dungeon Master, USA | `roms/dungeon-master-usa.sfc` | 1,048,576 |

| digest | value |
|---|---|
| SHA-256 | `2dfc2e037679a62a960dab9682bca6d1b2737f603edd336c8b2fdf05db10cc07` |
| SHA-1 | `e65ae62ec9a1c48a3512db66f929c7b0055ae2c3` |
| MD5 | `3d1b171d7486438af2d9ec3d98b155cd` |
| CRC32 | `0DFD9CEB` |

The Japanese and European releases carry the same chip. Neither is declared with digests yet, because
neither has been measured, and a guessed digest is worse than an absent one.

```bash
python3 tools/identify.py
```

It reports what it found, and when a file does not match it says which way it is wrong, prints the
digest it computed, and gives a command for working the digest out yourself on macOS, Linux or
Windows.

## Prerequisites

| Tool | Version | Why |
|:-----|:--------|:----|
| [Python 3](https://www.python.org/) | 3.12 | every analysis and build module |
| [Docker](https://www.docker.com/) | any current | pins the assembler and the emulator |
| Your own cartridge dump | 1,048,576 bytes | placed in `roms/` under the name above |

Nothing is installed from a package index at build time. The build containers pin their toolchains,
run with no network access, and run as a non-root user.

## The hardware this is checked against

```bash
git clone --recurse-submodules https://github.com/gufranco/dungeon-master-nochip.git
```

The models this project measures itself against are not written here. Each is its own repository,
pinned as a submodule at the root of this one under the name of the repository it is, and each is
held to something outside itself rather than to its author's confidence. They sit at the root rather
than under a folder because anybody opening this should see what it is built on without going
looking.

| model | what proves it |
|---|---|
| [65816](https://github.com/gufranco/mos65xx-python) | a per-opcode suite, 5,120,000 cases |
| [DSP-2](https://github.com/gufranco/snes-dsp-python) | the chip's own reference implementation |
| [cartridge map](https://github.com/gufranco/snes-mapper-python) | every header combination in a real cartridge library |
| [ROM image](https://github.com/gufranco/snes-rom-image-python) | the whole of that same library, rewritten and checked |

A model that has never disagreed with something is not a model that is right, it is one that has
never been asked. Three of the four above were wrong the first time they were measured that way, and
every one of those defects sat in the part that looked obviously correct.

They also start dirty. Memory and registers hold arbitrary but reproducible values rather than
zeroes, because real hardware does, and anything here that wants a cleared machine has to ask for
one. That turns a read of something never written from an accident into a question.

## When something is wrong

```bash
python3 doctor.py
```

It looks at this machine and prints what is actually there: the Python, every model this project is
pinned to and its version, whether the coprocessor can run at all, which cartridge dumps are present
and the SHA-256 of each, and how much recorded traffic is here. It then asks every model for its own
report and files what comes back under that model's name, so the whole chain is in one place rather
than one layer of it.

Nothing is inferred and nothing is hidden. A check that fails says what it saw, and a check that
itself throws is reported as what it threw rather than taking the report down with it. Paste all of
it into an issue.

## Repository guide

Analysis modules in Python, each with its tests beside it, and a pinned container per toolchain.

| file | role |
|------|------|
| [`hardware.py`](hardware.py) | puts the pinned hardware models on the import path, and says where the microcode is |
| [`doctor.py`](doctor.py) | what is actually on this machine, the whole chain, printed for a bug report |
| [`mos65xx-python/`](mos65xx-python/) | the 65816, held to a per-opcode suite |
| [`snes-dsp-python/`](snes-dsp-python/) | the DSP-2, running the chip's own microcode |
| [`snes-mapper-python/`](snes-mapper-python/) | the cartridge map, held to a library of real cartridges |
| [`snes-rom-image-python/`](snes-rom-image-python/) | image handling, held to that same library |
| [`build.py`](build.py) | Docker wrapper around a pinned asar |
| [`version.py`](version.py) | the release number, rewritten by [`scripts/set-version.sh`](scripts/set-version.sh) |
| [`artifacts.manifest.json`](artifacts.manifest.json) | every dump this project reads, and what makes each one itself |
| [`tools/identify.py`](tools/identify.py) | checks a dump, and says what is wrong when it is |
| [`asm/`](asm/) | assembly that goes into the ROM, with its own container pinning asar |
| [`emu/`](emu/) | the harness everything is validated against |
| [`ref/`](ref/) | the pinned reference the conversion is checked against |
| [`snes9x/`](snes9x/) | the emulator change the finished image needs, as a patch against a pinned tree |

## Working on this

| What | Command |
|:-----|:--------|
| Every test | `for t in *.test.py tools/*.test.py; do python3 "$t" \|\| break; done` |
| Lint | `ruff check .` |
| Format | `ruff format --check .` |
| Workflows | `actionlint` |
| Shell | `shellcheck --severity=style --shell=bash scripts/*.sh` |

### Conventions

| Convention | Where |
|:-----------|:------|
| Commit messages | [Conventional Commits](https://www.conventionalcommits.org/), which drives the version number |
| Python style | [`pyproject.toml`](pyproject.toml), ruff at line length 100, targeting 3.12 |
| Tests | one `<module>.test.py` beside each module, standard library `unittest` |
| Comments | required in the assembly and only there: entry and exit state, register widths, and where each recovered address came from |
| Builds | in Docker, pinned, no network, non-root. Never on the host |
| Releases | semantic versioning cut by the pipeline. Each image carries its version in the filename |

### Decisions worth knowing

- **No ROM data enters this repository.** Not dumps, not intermediates, not test fixtures. It is why
  parts of the suite skip rather than fail without a dump.
- **The cartridge is the only oracle.** A source and size pair is a request because the retail
  cartridge asks for it. Producing a plausible result for a pair nobody asked for proves nothing,
  since any bitmap scales to something of exactly the size requested.
- **The build depends on nothing outside this repository.** A fresh clone plus a dump is enough, with
  no network and no second checkout.

## Contributing

Measurements first. [CONTRIBUTING.md](CONTRIBUTING.md) has the gates a change is expected to pass,
[SECURITY.md](SECURITY.md) says what belongs in a private report, and the
[Code of Conduct](CODE_OF_CONDUCT.md) applies wherever this project is discussed.

Never attach a cartridge or a microcode image, and never link to somewhere either can be downloaded.
A digest identifies a file without carrying it.

## Citing this

[CITATION.cff](CITATION.cff) is kept in step with the released version by the same script that
stamps the release, so the version it names is the version that shipped.

## Acknowledgements

**FTL Games and Software Heaven**, for the game and for the port.

**The snes9x team**, for the emulator, for `dsp2.cpp` as the reference this conversion is checked
against, and for reviewing the mapper this image relies on.

**neviksti and the Star Ocean chip-free conversion**, which is where the addressing rule for images
too large for the address space comes from.

**The Zeldix community**, where most of the SNES romhacking knowledge this leans on is written down.

## Legal

No ROM data is distributed here. Everything in this repository operates on a file you must already
own, and the patches are derived from analysis of a retail cartridge you supply.

The tooling, the assembly and this document are released under the [MIT licence](LICENSE). That
covers my own work and nothing else. It grants no rights in the game.
