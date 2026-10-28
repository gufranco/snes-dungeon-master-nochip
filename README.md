# Dungeon Master without the DSP-2

Builds a Dungeon Master cartridge image whose DSP-2 coprocessor is replaced by 65816 routines, held byte for byte to the part's own microcode and to the retail cartridge's recorded port traffic.

English | [日本語](README.ja.md) | [简体中文](README.zh-Hans.md) | [繁體中文（香港）](README.zh-HK.md)

[![CI](https://github.com/gufranco/snes-dungeon-master-nochip/actions/workflows/ci.yml/badge.svg)](https://github.com/gufranco/snes-dungeon-master-nochip/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/gufranco/snes-dungeon-master-nochip)](https://github.com/gufranco/snes-dungeon-master-nochip/releases)
[![License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**17,241,846** returned bytes of a recording with no scale reproduced by the part's microcode, **0** wrong, **6** of 6 commands held to the part on chosen inputs, **924** tests, **100%** statement and branch coverage, standard library only

```python
import patch
import sites

image = bytearray(0x10000)
image[0x0100:0x0104] = sites.STA_PORT
image[0x0200:0x0204] = sites.STA_PORT
image[0x0300:0x0304] = sites.LDA_PORT
image[0x0400:0x0404] = sites.LDA_STATUS
image[0x0500:0x0503] = sites.MVN_TO_PORT

symbols = patch.resolve(
    patch.read_symbols(
        """
        00:ff00 b00_first
        00:ff10 b00_feed
        00:ff20 b00_drain
        04:ff00 b04_0080
        04:ff04 b04_0084
        04:ff08 b04_0088
        04:ff0c b04_008C
        20:8000 dsp_write
        20:8040 dsp_read
        """
    )
)

finished = patch.apply(image, symbols)
for site in sites.find(image):
    width = patch.WIDTHS[site.kind]
    before = image[site.offset : site.offset + width].hex(" ")
    after = finished[site.offset : site.offset + width].hex(" ")
    print(f"{site.kind:<6} ${site.bank:02X}:{site.address:04X}  {before}  ->  {after}")
print(patch.residue(image))
print(patch.residue(finished), len(finished) == len(image))
```

```
write  $00:8100  8f 00 80 3f  ->  22 00 ff 00
write  $00:8200  8f 00 80 3f  ->  22 00 80 20
read   $00:8300  af 00 80 3f  ->  22 40 80 20
status $00:8400  af 00 c0 3f  ->  a9 00 ea ea
feed   $00:8500  54 3f 7e  ->  20 10 ff
{'write': 2, 'read': 1, 'status': 1, 'feed': 1}
{} True
```

The example plants five of the cartridge's port accesses in a 64 KB image and redirects them against a symbol table in the form the assembler writes. Each replacement is as wide as the instruction it replaces, so nothing in the image moves. A long store to `$3F:8000` becomes a `jsl` to `dsp_write`, except the first one, which calls the boot entry `b00_first`. A long load becomes a `jsl` to `dsp_read`, a status poll becomes `lda #$00` and two `nop`, and a block move into the port becomes a `jsr` to the feed stub in bank `$00`. `patch.residue` counts what still reaches the chip: five accesses before, none after, and the image keeps its length.

## Install

| Requirement | Version | Needed for |
|:--|:--|:--|
| Python | 3.12 or newer | Every module and command |
| git | Any | Fetching the six pinned models as submodules |
| Docker | Any current | Assembling, and every command that drives the emulator |
| A Dungeon Master dump you own | 1,048,576 bytes, digest under [The dump](#the-dump) | Building the cartridge |
| DSP-2 microcode you own | The image `snes-dsp-python` accepts | The commands that ask the part for an answer |

```bash
git clone --recurse-submodules https://github.com/gufranco/snes-dungeon-master-nochip.git
cd snes-dungeon-master-nochip
python3 doctor.py
```

Nothing is installed from a package index. A source archive from the download-zip link carries no submodules and cannot run. In a clone made without `--recurse-submodules`, run `git submodule update --init --recursive`.

The dump goes in `external/roms/dungeon-master-usa.sfc`. The microcode goes in `external/firmware/`, or in a directory named by `UPD7725_FIRMWARE_DIR`. Git ignores both directories, and nothing here downloads either file.

The doctor prints the machine, the Python, the version of each model, whether the part's microcode runs, the SHA-256 of each dump it finds, how many of the three recorded traces sit in `build/`, and each model's own report under that model's name. A check that throws is reported as what it threw. It exits 1 when any check fails. On a fresh checkout it ends with this line:

```
  4 of 75 checks did not pass
```

The four are the missing dump, the missing microcode as this project and as `snes-dsp-python` each report it, and the empty `snes-mapper-python/cartridges` directory. Paste the whole output into any bug report.

Releases follow [Semantic Versioning](https://semver.org/) and are cut by semantic-release from the commit subjects. Every release is tagged and listed on the [releases page](https://github.com/gufranco/snes-dungeon-master-nochip/releases). A release publishes no image: the cartridge is built from your dump on your machine.

## The interface

Every command is a file run from the repository root with `python3`. Exit 0 is success. Exit 2 means the command was called wrongly or had nothing to work from, and the line it prints says which.

### Building the cartridge

| Command | Arguments | Exit codes |
|:--|:--|:--|
| `cartridge.py <dump> <output>` | The retail dump, and where to write the finished cartridge | 0 written. 1 an access still reaches the chip or a header mirror still declares a coprocessor, and nothing is written. 2 usage, or no file at `<dump>`. Any other code is the assembler's |
| `build.py <patch.asm> <dump> <output-name>` | An assembly file, the dump, and a file name for the result | 0 assembled. 1 the toolchain image did not build. 2 usage. Any other code is asar's |
| `build.py --image` | None | The exit code of `docker build` |
| [`assembled.py`](assembled.py) | None | 0 when `asm/dm-sym.sfc` and its symbols are newer than every `asm/*.asm`, or once they have been rebuilt. 2 no dump at `external/roms/dungeon-master-usa.sfc` |
| `similarity.py <dump> <cartridge>` | The retail dump and a finished cartridge | 0 every changed byte sits in a declared region. 1 at least one does not. 2 usage, or `asm/dm-sym.sfc` is missing or older than its sources |

```bash
python3 cartridge.py external/roms/dungeon-master-usa.sfc "build/Dungeon Master (USA) (nochip).sfc"
```

[`cartridge.py`](cartridge.py) copies the dump to `asm/<output-name>`, assembles [`asm/nochip.asm`](asm/nochip.asm) over it in the pinned asar 1.81 container with no network, reads the symbol table asar writes beside it, redirects every port access in place, and rewrites the header so it declares no coprocessor. It then counts what is left: an access still going to the chip, or a header mirror still declaring one. Either one stops it before the file is written. An image with the routines placed and the accesses not redirected boots and plays, because the emulator reads the header and supplies a DSP-2, so the count is the only thing that tells the two apart.

[`build.py`](build.py) rebuilds the `snes-dungeon-master-nochip/asar:1.81` image on every run and refuses to stage the result over the dump it was given. [`assembled.py`](assembled.py) keeps the measurement image `asm/dm-sym.sfc` current for the commands that read it.

[`similarity.py`](similarity.py) lists every byte the cartridge does not share with the dump and files each one under the region that claims it: the routines, the bank `$00` stubs, the bank `$04` stubs, the redirected sites, or the header fields the rewrite touches. It prints up to 8 bytes that no region claims, with their offset, address and both values.

### Checking a dump

| Command | Arguments | Exit codes |
|:--|:--|:--|
| `tools/identify.py [file name...]` | Optional file names from [`artifacts.manifest.json`](artifacts.manifest.json), all of them by default | 0 at least one dump present and correct and none wrong. 1 a dump has the wrong size, the wrong content or another entry's digest, or no dump is usable. 2 no manifest entry has that name |

```bash
python3 tools/identify.py
```

On a fresh checkout it prints:

```
  dungeon-master-usa.sfc: missing  [Dungeon Master, USA]
      external/roms/dungeon-master-usa.sfc is not there
      macOS and Linux: shasum -a 256 external/roms/dungeon-master-usa.sfc
      Linux, coreutils: sha256sum external/roms/dungeon-master-usa.sfc
      Windows PowerShell: Get-FileHash -Algorithm SHA256 external\roms\dungeon-master-usa.sfc
  dungeon-master-jp.sfc: no digest published  [Dungeon Master, Japan]
      no dump measured yet
  dungeon-master-eur.sfc: no digest published  [Dungeon Master, UK and Europe]
      no dump measured yet

  0 of 3 declared dumps present and correct
```

The second line carries the absolute path on your machine. A 512 byte copier header is stripped before any digest is taken. A file that does not match gets its size, CRC32 and SHA-256 printed, a reason, and the commands that compute the digest on macOS, Linux and Windows.

### Asking the part

These hold the routines to what the DSP-2's own microcode returns, run by `snes-dsp-python`. The routines run on the console's processor inside snes9x, driven by a script cartridge built from [`asm/dsp2-replay.asm`](asm/dsp2-replay.asm), so every command here except `verify_trace.py` needs Docker and the emulator image.

| Command | Arguments | Exit codes |
|:--|:--|:--|
| `tools/verify_trace.py [limit] [trace...]` | A byte limit per trace, and traces, `build/trace-s1.bin` to `trace-s3.bin` by default | 0 the part reproduced every returned byte, or no trace was found. 1 it did not. 2 no microcode |
| `tools/fuzz.py [seed] [count] [command...]` | Seed 1, 20,000 generated exchanges, and command bytes such as `0x05` to restrict them | 0 none wrong. 1 a byte wrong or a batch unfinished. 2 no microcode, no recording to calibrate against, or no command left to generate |
| `tools/replay.py <trace> [limit]` | A recorded trace, and a record limit | 0 none wrong, or no file at `<trace>`. 1 a byte wrong or a batch did not run. 2 usage |
| `tools/verify_merge.py [per-length]` | 3 merges per length, every length from 1 to 80, colours drawn from 16 | 0 none wrong. 1 a byte wrong, the written rule no longer matches the part, or no microcode |
| `tools/verify_multiply.py [extra]` | 17 corner pairs plus 120 seeded pairs | 0 none wrong. 1 a byte wrong, the written rule no longer matches the part, or no microcode |
| `tools/verify_commands.py [each]` | 2 per shape: tile, mirror at every length from 1 to 80, and both scale shapes the cartridge sends | 0 none wrong. 1 a byte wrong, or no microcode |
| `tools/verify_cpu.py [seed] [count]` | Seed 0, 400 single-instruction cases | 0 the `mos65xx` 65816 and snes9x agree on A, X, Y and P for every case. 1 they do not, or the cartridge did not finish |

`verify_trace.py` writes every recorded exchange into the part and compares what it reads back with what the cartridge read. `replay.py` sends the same recording through the routines on the console's processor instead, in batches that fit a 4 MB script cartridge, and prints a line per batch. `fuzz.py` first checks each command against a recording: a command whose model answer disagrees with the cartridge, or leaves the next exchange unanswerable, is left out and named. `verify_cpu.py` checks the processor model that prices the routines against the emulator that runs them.

### Measuring cost, play and placement

| Command | Arguments | Exit codes |
|:--|:--|:--|
| `tools/cost.py [image] [symbols] [trace] [samples]` | `asm/dm-sym.sfc`, the `.sym` beside it, `build/trace-s1.bin`, 60 exchanges per command | 0 every sampled answer matched the part's own. 1 one did not. 2 the image or its symbols are missing, the symbols are older, or the part has no microcode to run |
| `tools/frame_cost.py [image] [trace ...]` | `asm/dm-sym.sfc` and `build/trace-s1.bin` to `trace-s3.bin` | 0 priced. 1 no complete exchange after frame 600. 2 the image, its symbols or a trace is missing |
| `tools/pace.py <dump> <cartridge> [frames]` | Both cartridges, 4,000 frames | 0 the comparison ran. 1 the emulator failed. 2 usage, or a file is missing |
| `tools/boot.py [cartridge] [frames]` | `build/Dungeon Master (USA) (nochip).sfc`, 8,000 frames | 0 no coprocessor declared, no chip request, every frame delivered, the screen lit. 1 any of those failed. 2 no cartridge |
| `tools/placement.py [dump] [frames] [seed]` | `external/roms/dungeon-master-usa.sfc`, 19,000 frames, the steady route unless a seed is given | 0 the game never touched the state block's work RAM. 1 it did, or the run left no map. 2 no dump |
| `tools/tour.py [--frames N] [--seed S] [--steady] [--out PATH]` | 24,000 frames, seed 0, printed to standard output | 0 written. 2 usage |

`cost.py` runs each command on the `mos65xx` 65816 model, which counts every bus cycle, feeds it recorded traffic from frame 600 on, checks each answer against what the part's own microcode returns for the same traffic, and prices the same exchange as the retail path paid for it: 5 cycles per long store and 7 per byte moved. It prints one row per command with the call count, the cycles direct, the cycles through a block-move dispatcher, the retail cycles, the ratio, and how many answers were right. The status-register polling the retail path spent waiting is counted for neither side. `frame_cost.py` counts every complete exchange from frame 600 on in each trace, tells a call that came through one of the four block movers in work RAM from one that came straight from a cartridge site, prices this side at `cost.py`'s mean for that command and path and the retail path exactly, and prints a row per command and the cost of a frame on both sides.

`pace.py` drives both cartridges on the steady route, digests every finished frame, and reports how many frames the conversion drew the same, how many it drew late, the worst lag and the median, then the lag curve in 8 points. `boot.py` fails on any of four things: the header still declares a coprocessor, a chip was asked for something, the run stopped early, or the screen never lit. `placement.py` reads the state block's address range out of [`asm/dsp2-state.asm`](asm/dsp2-state.asm) and reports the longest run of work RAM the game never touched. `tour.py` writes the input scripts these drive: a seeded random walk, or the steady route of up, up, up, left, up, up, up, right.

The emulator image is built once, from the repository root:

```bash
docker build --tag snes-dungeon-master-nochip/emu:dev emu
```

The three traces in `build/` are recorded from it, with a copy of the dump at `build/dungeon-master-usa.sfc`. Each is a seeded 30,000 frame tour and runs to about 1.7 GB:

```bash
for seed in 1 2 3; do
  python3 tools/tour.py --frames 30000 --seed "$seed" --out "build/tour-s$seed.script"
  docker run --rm --network=none --env "DMTRACE=trace-s$seed.bin" \
    --env "DMSCRIPT=tour-s$seed.script" --volume "$PWD/build:/work" \
    snes-dungeon-master-nochip/emu:dev dungeon-master-usa.sfc 30000
done
```

### Running every gate

| Command | Arguments | Exit codes |
|:--|:--|:--|
| `check.py [--quick]` | `--quick` skips every gate that needs the assembled image | 0 every gate passed. 1 at least one failed, named with its last 6 lines. 2 usage |
| [`doctor.py`](doctor.py) | None | 0 every check passed. 1 at least one did not |

[`check.py`](check.py) assembles the measurement image first when it is missing or stale, then runs lint, format, types, the tests under coverage, the JSON and YAML format, the workflows and the shell script, each at the version the pipeline pins. With the image it also runs [`tools/cost.py`](tools/cost.py), the three `*.retail.test.py` checks, and the three `verify_*.py` commands. It runs every gate rather than stopping at the first failure.

### Modules

| Call | Returns |
|:--|:--|
| `sites.find(image, kinds=None)` | Every port access as a `Site(kind, offset, address, bank)`, sorted by offset. `kind` is `write`, `read`, `status`, `feed` or `drain` |
| `sites.census(found)` | A count per kind |
| `sites.verify(found, region="USA")` | The census, or `UnexpectedImage` when it differs from `EXPECTED[region]` |
| `sites.find_trampoline_calls(image, bank=0x04)` | Every `jsr` in bank `$04` to the four block movers at `$0080`, `$0084`, `$0088` and `$008C` |
| `sites.verify_trampoline_calls(calls)` | The count per mover, or `UnexpectedImage` when it differs from `EXPECTED_TRAMPOLINE_CALLS` |
| `sites.address_of(offset)`, `sites.offset_of(bank, address)` | The LoROM bank and address of a file offset, and back |
| `patch.read_symbols(text)` | `{name: (bank, address)}` from an asar symbol file |
| `patch.resolve(symbols)` | The nine entries `REQUIRED` names, or `MissingSymbol` listing the absent ones |
| `patch.apply(image, symbols, boot_write_offset=None)` | The redirected image as `bytes`, same length. The first store is the boot write unless an offset is given |
| `patch.residue(image)` | `{kind: count}` of accesses still reaching the chip, empty when none |
| `patch.regions(image)` | Every offset a redirect rewrites, sites and mover calls together |
| `cartridge.finish(image, symbols_text)` | The image redirected and its header rewritten to declare no coprocessor |
| `cartridge.unfinished(image)` | One line per thing still going to the chip, empty when finished |
| `stateblock.fields(text)` | `{name: (offset, width)}` for every `!S_` field below `$100` in the state block's assembly |
| `stateblock.overlaps(declared)` | Every pair of fields sharing a byte, as `(name, other, first shared offset)` |
| `dsptrace.records(path)` | Each 28-byte record of a recorded trace as a `Record`. A short tail raises `TruncatedTrace` |
| `dsptrace.transactions(records)` | Records grouped into one `Transaction` per command, with `command`, `name`, `lengths`, `parameters`, `output`, `source` and `complete` |
| `dsptrace.summarise(transactions)`, `dsptrace.report(summary)` | Counts per command, per issuing site and per source bank, and their printed form |
| `protocol.Shape()` | Tracks how many bytes a command still wants and how many it owes, from the bytes alone. `wrote(byte)`, `was_read()`, `expecting_input`, `produced`, `at_boundary` |
| `hardware.install()`, `hardware.load(package)` | Puts `mos65xx`, `snesdsp`, `mapper` and `romimage` on the import path and names `external/firmware/` in `UPD7725_FIRMWARE_DIR`. `load` imports one of them |
| `version.stamped(name, release=None)` | The file name a release gives an image |

`dsptrace` and `protocol` count bytes and never compute an answer: every value comes from the recording or from the part.

```python
import hardware
import patch
import sites

print(sites.EXPECTED["USA"])
print({f"${mover:04X}": calls for mover, calls in sites.EXPECTED_TRAMPOLINE_CALLS.items()})
bank, address = sites.address_of(0x012345)
print(f"${bank:02X}:{address:04X}", hex(sites.offset_of(0x82, 0xA345)))

try:
    sites.verify([], "Japan")
except sites.UnexpectedImage as refusal:
    print(refusal)

try:
    patch.resolve({"dsp_write": (0x20, 0x8000)})
except patch.MissingSymbol as refusal:
    print(refusal)

try:
    hardware.root_of("snesgfx")
except hardware.UnknownPackage as refusal:
    print(refusal)
```

```
{'write': 51, 'read': 4, 'status': 5, 'feed': 16, 'drain': 2}
{'$0080': 2, '$0084': 5, '$0088': 4, '$008C': 1}
$02:A345 0x12345
no measured site counts for region Japan; measured regions are ['USA']
the assembled image declares no b00_first, b00_feed, b00_drain, b04_0080, b04_0084, b04_0088, b04_008C, dsp_read
snesgfx is not vendored here; this project carries mapper, mos65xx, romimage, snesdsp
```

The retail USA image holds 78 port accesses and 12 calls to the four block movers. A dump whose counts differ is refused rather than patched.

```python
import stateblock

declared = stateblock.fields(stateblock.SOURCE.read_text())
widest = max(declared.items(), key=lambda one: one[1][1])
print(len(declared), "fields, widest", widest)
print(stateblock.overlaps(declared))
print(stateblock.overlaps({"!S_A": (0x10, 2), "!S_B": (0x11, 1)}))
```

```
25 fields, widest ('!S_SCRATCH', (40, 200))
[]
[('!S_A', '!S_B', 17)]
```

Each field in the state block states its width in its comment, and the assembler cannot see two names for one byte. The 25 fields in [`asm/dsp2-state.asm`](asm/dsp2-state.asm) share none. The last line shows a two-byte field at `$10` and a field at `$11` reported at offset 17.

```python
import tempfile
from pathlib import Path

import dsptrace

exchange = [(0, 0x09), (0, 0x03), (0, 0x00), (0, 0x04), (0, 0x00)]
exchange += [(1, 0x0C), (1, 0x00), (1, 0x00), (1, 0x00)]

with tempfile.TemporaryDirectory() as folder:
    trace = Path(folder) / "trace.bin"
    trace.write_bytes(
        b"".join(
            dsptrace.RECORD.pack(700, 0x04A123, 0, 0, kind, byte, bytes(8), 0x7E, 0x30, bytes(4))
            for kind, byte in exchange
        )
    )
    found = list(dsptrace.transactions(dsptrace.records(trace)))

print(found)
print(found[0].parameters.hex(" "), found[0].output.hex(" "), found[0].complete)
print(dsptrace.report(dsptrace.summarise(found)))
```

```
[<multiply frame=700 pc=$04A123 in=4 out=4>]
03 00 04 00 0c 00 00 00 True
  transactions 1, incomplete 0
    $09 multiply              1
  issuing sites 1
    $04A123           1
  source banks, by command
  distinct source addresses 0
  distinct length tuples 0
```

Nine records make one multiply: the command byte, four operand bytes written, four answer bytes read. The harness in [`emu/`](emu/) writes the trace, one 28-byte record per port access.

```python
from tools import protocol, tour

shape = protocol.Shape()
for byte in (0x05, 0x02, 0x11, 0x22, 0x33, 0x44):
    shape.wrote(byte)
print(shape, shape.produced)

route = tour.steady(3400).splitlines()
print(len(route), route[-4:])
```

```
<Shape between commands, 2 owed> 2
162 ['3260 up', '3266', '3308 up', '3314']
```

A merge of length 2 takes four payload bytes and owes two. A route line is a frame number and the buttons held from it, and a line with no button releases them. The first 3,000 frames press start every 40 frames to get through the title.

### Errors

| Error | Raised when |
|:--|:--|
| `sites.UnexpectedImage` | The access or mover counts differ from the measured USA image, or the region has no measurement |
| `patch.MissingSymbol` | The symbol table lacks a name in `patch.REQUIRED` |
| `patch.UnknownSite` | A site has a kind the rewrite does not cover |
| `hardware.UnknownPackage` | A model name is not one of the four `hardware.PACKAGES` |
| `similarity.NoRegion` | The assembly or the symbol table does not declare a region, a region ends before it starts, or the two images differ in length |
| `dsptrace.TruncatedTrace` | A trace ends inside a record |
| `dsptrace.UnknownLength` | A length byte arrives for a command that takes none |
| `replay.ScriptTooLong` | A replay script exceeds the room left in the script cartridge |
| `replay.EmulatorFailed` | The emulator exits non-zero or writes no work RAM dump within 5 seconds |
| `cost.Ran` | A routine touches an address the cost harness does not model, or does not return within 4,000,000 steps |

## What the chip did

Dungeon Master is the only SNES cartridge that carries a DSP-2. The part has six commands: convert an Atari ST bitmap to the console's tile format, set a transparent colour, merge two bitmaps against it, mirror, multiply, and scale. Without it the game does not draw.

What the cartridge asks it to convert is the dungeon view as composed for where the player stands, so there is no fixed set of answers to compute ahead of time and store. Searching the retail dump for the exact bytes the cartridge sends finds every one of the mirror command's inputs, 1.2% of the merge command's, and 0.3% of the tile command's. The six commands are therefore reimplemented in 65816, and the cartridge's own instructions are pointed at them.

## Status

| Part | State |
|:--|:--|
| Dump identification | Refuses a dump that is not the measured USA one |
| The six commands in 65816 | Answer every recorded byte, on the processor |
| The finished cartridge | Builds from a dump in one command, and boots with no coprocessor |
| Speed | 68,616 cycles a frame against 15,009 for the chip path, in a frame of 59,561 |

Weighted by how often the cartridge sends each command, the routines spend 68,616 cycles a frame where the port traffic cost 15,009. The retail figure leaves out the time the game spent polling a status register for an answer, which nothing here can measure, so the ratio is an upper bound. The 59,561 cycle frame is what the processor has.

Driving both cartridges along the steady route for 30,000 frames, eight minutes of walking and turning, 29,941 frames are drawn the same. The conversion reaches the title screen 56 frames later and after that never falls a frame behind. Timed directly over 139 dungeon redraws, both cartridges settle in 26 frames and the conversion was slower on none. [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) carries both measurements and what each cannot say.

## The dump

Named as No-Intro names it. Every digest is of the whole file with no copier header. SHA-256 decides; the others cross-check against databases that key on them.

| File | Read as | Size |
|:--|:--|:--|
| Dungeon Master, USA | `external/roms/dungeon-master-usa.sfc` | 1,048,576 |

| Digest | Value |
|:--|:--|
| SHA-256 | `2dfc2e037679a62a960dab9682bca6d1b2737f603edd336c8b2fdf05db10cc07` |
| SHA-1 | `e65ae62ec9a1c48a3512db66f929c7b0055ae2c3` |
| MD5 | `3d1b171d7486438af2d9ec3d98b155cd` |
| CRC32 | `0DFD9CEB` |

The Japanese and European releases carry the same chip. [`artifacts.manifest.json`](artifacts.manifest.json) lists both with no digest, and the build refuses them until one is measured.

## The models underneath

Every claim about what a part does is made by another member of the family, pinned as a submodule at the root of this repository under its own name.

| Model | Used here for | Held to |
|:--|:--|:--|
| [`mos65xx-python`](https://github.com/gufranco/mos65xx-python) | Running and pricing the routines in [`tools/cost.py`](tools/cost.py), and [`tools/verify_cpu.py`](tools/verify_cpu.py) | The 65816 per-opcode suite, 5,120,000 cases |
| [`snes-dsp-python`](https://github.com/gufranco/snes-dsp-python) | Every expected answer, by running the part's own microcode | The microcode itself |
| [`snes-rom-image-python`](https://github.com/gufranco/snes-rom-image-python) | Digests, copier headers and the header rewrite | A library of real cartridges |
| [`snes-mapper-python`](https://github.com/gufranco/snes-mapper-python) | Put on the import path by [`hardware.py`](hardware.py) | Every header combination in that library |
| [`snes-graphics-python`](https://github.com/gufranco/snes-graphics-python) | Pinned, imported by no module here | The console's bitplane layout |
| [`snes-driver-python`](https://github.com/gufranco/snes-driver-python) | Pinned, imported by no module here | Where cartridge code reaches its coprocessor |

The models start dirty: memory and registers hold reproducible scrambled values rather than zeroes, so a read of something never written shows up as a wrong answer.

## Repository guide

| Path | Holds |
|:--|:--|
| [`asm/`](asm/) | The 65816 routines, the state block, the stubs, the replay and self-test cartridges, and the asar 1.81 container |
| [`emu/`](emu/) | The snes9x harness every emulator run goes through, as a container pinned to one snes9x commit |
| [`snes9x/`](snes9x/) | The mapping change the finished image needs, as a patch against that commit |
| [`tools/`](tools/) | The commands under [Asking the part](#asking-the-part) and [Measuring cost, play and placement](#measuring-cost-play-and-placement) |
| [`conformance/divergences.json`](conformance/divergences.json) | Every open question in a form a program reads, held to [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) by a test |
| `*.retail.test.py` | Checks that need the dump, kept out of the coverage gate, reported as skipped without it |

## Is it right

Correctness is checked three ways, and each says something the others cannot.

Four runs of 30,000 frames were recorded on the emulator with every byte in and out of the port: three seeded random walks and the steady route. [`tools/replay.py`](tools/replay.py) feeds those streams through the routines on the console's processor and checked 98,333,301 bytes, walking 8,722,303 runs, with none wrong before the scale routine was corrected to the part. The walks hold what snes9x answered for each scale, which the part does not give, so the first 2,014,446 bytes of the first walk now give 598 wrong.

That recording holds what the emulator answered, and the emulator computes the part's results in C. [`tools/verify_trace.py`](tools/verify_trace.py) replays a recording against the part's own microcode. Over `build/trace-t1.bin`, which holds no scale, it reproduces all 17,241,846 bytes the cartridge returned, none wrong. Over the three walks it disagrees on 10,416, 1,050 and 17,302 exchanges, against 10,422, 1,068 and 17,777 scales: snes9x divides the scale step by `(out << 1) + 1` where the microcode divides by `(out << 1) + 2`. Tallied by command over the first 12,000,000 bytes of the first walk, every disagreement is a scale. So the emulator and the part agree on every recorded command but the scale.

A recording says nothing about inputs it does not contain: every recorded multiply has a zero first operand, and the steady route holds no mirror and no scale. So all six commands are also held to the part over chosen inputs, through [`tools/verify_merge.py`](tools/verify_merge.py), [`tools/verify_multiply.py`](tools/verify_multiply.py) and [`tools/verify_commands.py`](tools/verify_commands.py). Two defects in the routines were found that way, and replaying traffic could have found neither.

What stays open, with the measurement that would settle each, is in [OPEN-QUESTIONS.md](OPEN-QUESTIONS.md) and [`conformance/divergences.json`](conformance/divergences.json).

## Working on it

| Need | Where |
|:--|:--|
| Every gate and the order to run them | [CONTRIBUTING.md](CONTRIBUTING.md) |
| The same material for a coding agent | [AGENTS.md](AGENTS.md) |
| The standard this repository shares with the rest of the family | [FAMILY.md](FAMILY.md) |
| Bug reports | [GitHub Issues](https://github.com/gufranco/snes-dungeon-master-nochip/issues) |
| Security reports | [SECURITY.md](SECURITY.md) |

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
uvx --python 3.12 mypy==1.14.1 .
python3 -m coverage erase
for module in *.test.py tools/*.test.py conformance/*.test.py; do python3 -m coverage run -a "$module"; done
python3 -m coverage report
```

Each module has a `<module>.test.py` beside it, and each runs on its own. Coverage is a hard gate at 100% of statements and branches, met on a machine holding neither the dump nor the microcode. `python3 check.py` runs every gate in one pass.

Never attach a cartridge or a microcode image to an issue, and never link to somewhere either can be downloaded. A digest identifies a file without carrying it.

## References

- snes9x, `dsp2.cpp` at commit `2971061cf07fdc6fc7d18883edf4e648eb16a6d2`, https://github.com/snes9xgit/snes9x, the emulator every run and recording goes through.
- asar 1.81, https://github.com/RPGHacker/asar, the assembler, pinned in [`asm/Dockerfile`](asm/Dockerfile).
- neviksti's Star Ocean chip-free conversion, the source of the addressing rule for images too large for the address space.
- The Zeldix community, where much of the SNES romhacking knowledge this relies on is written down.
- FTL Games and Software Heaven made the game and the port.

## Citing this

[CITATION.cff](CITATION.cff) is updated with each release by the script that stamps [`version.py`](version.py).

## License

MIT. See [LICENSE](LICENSE). The license covers the tooling, the assembly and this document. It grants no rights in the game, and no ROM data is distributed here.
