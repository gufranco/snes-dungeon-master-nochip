<div align="center">

# Dungeon Master without the DSP-2

**Tooling to build a Dungeon Master ROM with the coprocessor designed out, so it runs from any flash
cartridge that can hold it.**

[![licence](https://img.shields.io/github/license/gufranco/snes-dungeon-master-nochip)](LICENSE)

</div>

---

## What this is

Dungeon Master is the only SNES cartridge that carries a DSP-2. The chip converts the game's Atari ST
bitmap graphics into the console's own tile format, scales them for the dungeon view, composites them
against a transparent colour, and multiplies. Without it the game does not draw.

This project reimplements all six of the chip's commands in 65816 and points the cartridge's own
instructions at them. Every access is redirected in place and every replacement is the same width as
the instruction it replaces, so nothing in the image moves and no address the game computes for
itself changes meaning. The result is an ordinary SNES ROM with no coprocessor to emulate.

Computing the answers ahead of time and storing them was the first plan, and measurement ruled it
out. The part is a renderer rather than an unpacker: what it is asked to convert is the dungeon view
as composed for wherever the player is standing, so there is no fixed set of answers to compute.
Searching the retail dump for the exact bytes the cartridge sends finds every one of the mirror
command's inputs, 1.2% of the merge command's, and 0.3% of the tile command's.

You supply the retail dump. Nothing here contains game data, and nothing ever will.

## Status

It builds and it answers correctly. It costs the processor about four times what the chip path cost,
and draws the dungeon in the same number of frames.

| part | state |
|------|-------|
| dump identification | works |
| 65816 disassembly and interpretation | works, against a per-opcode suite |
| the DSP-2's own behaviour | works, against the chip's reference implementation |
| address arithmetic for the image | works, against a library of real cartridges |
| pinned assembler container | builds |
| the six operations in 65816 | answer every recorded byte, on the processor |
| the finished cartridge | builds from a dump in one command, and boots with no coprocessor |
| speed | 59,874 cycles a frame against 14,385 for the chip path, in a frame of 59,561 |

```bash
python3 cartridge.py roms/dungeon-master-usa.sfc "build/Dungeon Master (USA) (nochip).sfc"
```

It assembles, points every access at the replacement, and rewrites the header so nothing declares a
coprocessor. It refuses to write the file if either check finds anything left: an access still going
to the chip, or a header mirror still declaring one. An image with the routines placed and the
accesses not redirected boots and plays perfectly, because the emulator reads the header, provides a
DSP-2 and serves every request itself.

**Correctness.** Four runs of 30,000 frames each were driven on the emulator with every byte in and
out of the port recorded: three seeded random walks and one steady route. Feeding those streams back
through the routines, on the processor, walks 8,722,303 runs and checks 98,333,301 bytes against what
the recording holds. None are wrong.

That figure is agreement with the recording, and the recording holds what the emulator answered
rather than what the part answered. Those turn out to be the same thing: replaying a whole recording
against the part's own microcode reproduces all 17,241,846 bytes the cartridge returned, none wrong.

What a recording cannot do is say anything about inputs it does not contain, and that is where the
routines were found wrong. Every recorded multiply has a zero first operand, and no recording taken
here holds a scale or a mirror at all. Both defects were found by asking the part directly, and
neither could have been found by replaying traffic. All six commands are now held to the part over
inputs chosen rather than observed.

**Speed.** The chip computed while the program that fed it carried on, so replacing it with code
cannot be free. Weighted by how often the cartridge sends each command, the routines spend 59,874
cycles a frame where the port traffic cost 14,385. That ratio has a floor under it: the retail figure
counts the stores and block moves and not the time the game spent spinning on a status register
waiting for an answer, which nobody here can measure.

What it costs a player is a separate measurement. Driving both cartridges along the same route for
30,000 frames, eight minutes of walking and turning, 29,941 frames are drawn the same. The conversion
reaches the title screen 56 frames later, and after that never falls a frame behind. Timing the
dungeon redraw directly, over 139 of them, both cartridges settle in 26 frames and the conversion was
slower on none: the game paces that redraw itself, and both the chip and the routines finish inside
it. [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) carries both measurements, what each cannot say, and the
two ideas that look obvious and do not work.

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
git clone --recurse-submodules https://github.com/gufranco/snes-dungeon-master-nochip.git
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
| [tile format](https://github.com/gufranco/snes-graphics-python) | the console's own bitplane layout, held to recorded output |
| [driver](https://github.com/gufranco/snes-driver-python) | where in the cartridge's code it reaches the part |

The 65816 model is also the instrument the replacement is measured with. It drives a bus cycle by
cycle, so what a routine costs is the cycles it actually took rather than a sum from a table.

A model is worth what has disagreed with it. Several of those above were wrong the first time they
were measured that way, and every one of those defects sat in the part that looked obviously correct.

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

A check that fails says what it saw, and a check that itself throws is reported as what it threw
rather than taking the report down with it. Paste all of it into an issue.

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
| [`snes-graphics-python/`](snes-graphics-python/) | the tile format the conversion produces |
| [`snes-driver-python/`](snes-driver-python/) | where the cartridge's own code reaches the part |
| [`cartridge.py`](cartridge.py) | a dump in, a cartridge that needs no coprocessor out |
| [`build.py`](build.py) | Docker wrapper around a pinned asar |
| [`patch.py`](patch.py) | redirects every site in place, each replacement the width of what it replaces |
| [`sites.py`](sites.py) | where those sites are, and the filler the stubs go in |
| [`stateblock.py`](stateblock.py) | reads the block's declared layout and refuses two fields that share a byte |
| [`similarity.py`](similarity.py) | every byte the finished cartridge does not share with the dump, and which region owns it |
| [`check.py`](check.py) | every gate in one pass, each pinned to the version the runner installs |
| [`assembled.py`](assembled.py) | the image the measurements read, and whether it predates its sources |
| [`dsptrace.py`](dsptrace.py) | reads a recorded port trace back into transactions |
| [`version.py`](version.py) | the release number, rewritten by [`scripts/set-version.sh`](scripts/set-version.sh) |
| [`artifacts.manifest.json`](artifacts.manifest.json) | every dump this project reads, and what makes each one itself |
| [`tools/identify.py`](tools/identify.py) | checks a dump, and says what is wrong when it is |
| [`tools/cost.py`](tools/cost.py) | what each command costs, on the processor, against what the chip path cost |
| [`tools/replay.py`](tools/replay.py) | the recorded stream fed back through the routines, on the processor |
| [`tools/verify_trace.py`](tools/verify_trace.py) | the recorded stream against the chip's own microcode |
| [`tools/boot.py`](tools/boot.py) | drives the finished cartridge and fails if it still wants a chip |
| [`tools/pace.py`](tools/pace.py) | drives both cartridges on one input and says how far behind the conversion runs |
| [`tools/placement.py`](tools/placement.py) | maps the work RAM the game touches, and fails if it reaches the state block |
| [`conformance/`](conformance/) | the record of what is settled and what is not, with a test holding it to the prose |
| [`asm/`](asm/) | assembly that goes into the ROM, with its own container pinning asar |
| [`emu/`](emu/) | the harness everything is validated against |
| [`ref/`](ref/) | the pinned reference the conversion is checked against |
| [`snes9x/`](snes9x/) | the emulator change the finished image needs, as a patch against a pinned tree |

## Working on this

| What | Command |
|:-----|:--------|
| Everything below, in one pass | `python3 check.py` |
| The same without the container | `python3 check.py --quick` |
| Every test | `for t in *.test.py tools/*.test.py conformance/*.test.py; do python3 "$t" \|\| break; done` |
| Coverage, which fails below 100% | `python3 -m coverage erase && for t in *.test.py tools/*.test.py conformance/*.test.py; do python3 -m coverage run -a "$t"; done && python3 -m coverage report` |
| What is on this machine | `python3 doctor.py` |
| Lint | `ruff check .` |
| Types | `mypy .` |
| Format | `ruff format --check .` |
| Workflows | `actionlint` |
| Shell | `shellcheck --severity=style --shell=bash scripts/*.sh` |
| What each command costs | `python3 tools/cost.py` |
| The recorded traffic through the routines | `python3 tools/replay.py build/trace-s1.bin` |
| That the cartridge runs, and runs without a chip | `python3 tools/boot.py` |
| That the game still leaves the state block's work RAM alone | `python3 tools/placement.py` |
| How far behind the conversion runs | `python3 tools/pace.py roms/<dump>.sfc build/<name>.sfc` |
| That nothing outside a declared region moved | `python3 similarity.py roms/<dump>.sfc build/<name>.sfc` |

The last six need a dump, and each needs something built from it as well: `cost.py` the assembled
image and its symbol table, `replay.py` a recorded trace on top of those, `boot.py` the finished
cartridge, `placement.py` the dump alone, and `pace.py` and `similarity.py` both cartridges at once.
Every one of them reports that it has nothing to run rather than passing.

### Conventions

| Convention | Where |
|:-----------|:------|
| Commit messages | [Conventional Commits](https://www.conventionalcommits.org/), which drives the version number |
| Python style | [`pyproject.toml`](pyproject.toml), ruff at line length 100, targeting 3.12 |
| Tests | one `<module>.test.py` beside each module, standard library `unittest` |
| Coverage | 100% of statements and branches, enforced by [`pyproject.toml`](pyproject.toml). A branch with no test fails the build rather than lowering the number |
| Comments | required in the assembly and only there: entry and exit state, register widths, and where each recovered address came from |
| Builds | in Docker, pinned, no network, non-root. Never on the host |
| Releases | semantic versioning cut by the pipeline. Each image carries its version in the filename |

### Decisions worth knowing

- **No ROM data enters this repository.** Not dumps, not intermediates, not test fixtures. It is why
  parts of the suite skip rather than fail without a dump, and why the checks that need one live in
  `*.retail.test.py` files kept out of the coverage measurement: a machine with the dump runs one set
  of paths and a machine without it runs the other, so no single build can exercise both.
- **The part's own microcode answers for the part.** Nothing here computes a DSP-2 result. What a
  command answers is whatever the program the chip carries answers, and a check that needs that
  program reports it had nothing to run rather than passing without it.
- **The cartridge is the only oracle.** A source and size pair is a request because the retail
  cartridge asks for it. Producing a plausible result for a pair nobody asked for proves nothing,
  since any bitmap scales to something of exactly the size requested.
- **The build depends on nothing outside this repository.** A fresh clone plus a dump is enough, with
  no network and no second checkout.
- **Speed is a number, never an adjective.** Every claim about how fast something is comes from
  [`tools/cost.py`](tools/cost.py), which runs the routine on the processor model against recorded
  traffic and prices it against what the same exchange cost when a chip answered it. Both figures
  print per command, because a single total would hide which one regressed.
- **What is not known is written down.** [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) carries every place
  a claim here is narrower than it looks, with the measurement that would settle it, and
  [`conformance/divergences.json`](conformance/divergences.json) carries the same record in a form a
  program can read. A test holds the two together so an entry cannot be added to one and forgotten in
  the other.

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
