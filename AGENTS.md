# Working in this repository

Read [`FAMILY.md`](FAMILY.md) first. It is the standard every member is built to
and it is identical in all twenty of them. This file is the part that is only
true here.

## What this project is, in one paragraph

Dungeon Master is the one SNES cartridge carrying a DSP-2, and without that part
the game does not draw. This replaces the part with 65816 code and points the
cartridge's own instructions at it. Every access is redirected in place and every
replacement is the same width as the instruction it replaces, so nothing in the
image moves and no address the game computes for itself changes meaning.

## The part is a renderer, not an unpacker

This is the fact the shape of everything here follows from, and it is the first
thing a reader assumes wrongly.

The DSP-2 has six commands: convert a bitmap to the console's tile format, set a
transparent colour, merge two bitmaps against it, mirror, multiply, and scale.
None of them decompresses anything. What the cartridge asks it to convert is the
dungeon view as composed for where the player is standing, so the set of inputs
is not fixed and cannot be computed ahead of time and stored.

That was measured rather than argued. Searching the retail dump for the exact
bytes the cartridge sends finds every one of the mirror command's inputs, 1.2% of
the merge command's, and 0.3% of the tile command's. Mirror only ever mirrors
fixed assets. The two that matter do not.

A second measurement closes the other half of it. Comparing two recorded runs,
99.3% of tile calls and 99.2% of merge calls use an input the other run had
already seen, so a table of answers would cover almost everything. But no cheap
key exists to find them by: a sixteen byte prefix still fails to tell 154 of
1,767 tile inputs apart, and a sixty four entry cache of recent inputs hits 2.7%,
because the repeats are spread across a whole run rather than clustered.

## Speed is a measured number, not a claim

A chip worked while the program feeding it carried on. Moving that work onto the
processor cannot be free, so every statement about it here is a cycle count.

[`tools/cost.py`](tools/cost.py) runs each command on the 65816 model, which
drives a bus cycle by cycle, feeds it the cartridge's own recorded traffic, checks
every answer against what the chip returned, and prices the exchange against what
it cost when a chip answered it. Both figures print per command. A single total
would hide which one regressed, which is the whole reason for the tool.

Three things follow for anybody changing the assembly:

- **Run the cost tool before and after.** A change that makes an operation
  clearer and slower is a change this project cannot take without saying so.
- **The scaffolding is the cost, not the arithmetic.** A merge computes four
  bytes for about 180 cycles and the whole exchange takes 1,207, or 1,292 when
  it arrives through a dispatcher, which most of the traffic does. The rest is
  standing in for one instruction: saving what the caller had, pointing the data
  bank and the direct page at the state block, and putting it back. There are
  about 120 of those interceptions in a frame.
- **Know the ceiling before optimising.** The routines add 56,419 cycles to a
  frame that holds 59,561, and the two commands that matter are already within a
  few hundred cycles of what this shape can do.
  [`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md) carries the measurements, including
  the two ideas that look obvious and do not work: caching answers, and indexing
  a table by two input bytes at once.

## The six models, and why there are six

Every claim about what a part does is made by a member on the import path, never
here. [`hardware.py`](hardware.py) is the only way any of them is reached.

| model | what it answers for |
|---|---|
| `snes-dsp` | what the DSP-2 returns, by running the part's own microcode |
| `mos65xx` | the processor the replacement runs on, and the instrument it is measured with |
| `snes-mapper` | the cartridge map |
| `snes-rom-image` | the forms the image is stored in |
| `snes-graphics` | the tile format the conversion produces |
| `snes-driver` | where in the cartridge's own code it reaches the part |

The models start dirty. Memory and registers hold arbitrary but reproducible
values rather than zeroes, because hardware does, so anything wanting a cleared
machine has to ask for one.

## What must never enter this repository

No cartridge, no microcode, no patched output, no intermediate derived from any
of them. Not as a fixture, not as a test resource, not in a commit that is later
reverted. Digests identify a file without carrying it, and
[`artifacts.manifest.json`](artifacts.manifest.json) is where they live.

This is why parts of the suite skip rather than fail without a dump, and why the
checks that need one live in `*.retail.test.py` files kept out of the coverage
measurement: a machine with the dump runs one set of paths and a machine without
it runs the other, so no single run can exercise both.

## Gates

Everything below must pass before a change is done. There is no partial credit.

| gate | command |
|---|---|
| tests | `for t in *.test.py tools/*.test.py conformance/*.test.py; do python3 "$t" \|\| break; done` |
| coverage, which fails below 100% | `python3 -m coverage erase && for t in *.test.py tools/*.test.py conformance/*.test.py; do python3 -m coverage run -a "$t"; done && python3 -m coverage report` |
| types | `mypy .` |
| lint | `ruff check .` |
| format | `ruff format --check .` |
| workflows | `actionlint` |
| this machine | `python3 doctor.py` |
| the cartridge | `python3 cartridge.py roms/<dump>.sfc build/<name>.sfc` |

A change to the assembly adds two more: rebuild, then run
[`tools/cost.py`](tools/cost.py) and read both columns, and run
[`tools/boot.py`](tools/boot.py), which drives the finished cartridge and fails
if the header still declares a coprocessor, if anything asked one for something,
if the run stopped early, or if the screen never lit. The last of those is not
padding: the first wrong placement of the state block passed every other check
and booted to black.

## Conventions that are only true here

- **Comments are required in the assembly and only there.** Entry and exit state,
  register widths, and where each recovered address came from. Python carries its
  reasoning in docstrings.
- **The assembler is asar 1.81, pinned in a container.** It has two traps worth
  knowing: `label+0*N` silently assembles to `$FFFFFF` rather than to `label`, and
  a define written as `!NAME = 512  ; a comment` captures the comment, so any
  expression using it fails to resolve. Both cost a debugging session; write the
  offsets out.
- **An eight bit immediate inside a sixteen bit region desynchronises the
  instruction stream** and the symptom is a stack that runs away, not an
  assembler error. Check the width the code is in before adding a `lda.b`.
- **An image with the routines placed is not a converted cartridge.** Assembling
  puts the replacement in the image; nothing calls it until
  [`patch.py`](patch.py) redirects the accesses and the header stops declaring a
  coprocessor. The half-done image boots and plays, because the emulator reads
  that header and provides the chip. What tells you is the emulator's own line:
  `dsp=2` with millions of chip events on a run that should have none. Build
  through [`cartridge.py`](cartridge.py), which does both steps and refuses to
  write the file if either check finds anything left.
- **Placement in work RAM is measured, never guessed.** The state block sits in a
  run of 4,078 bytes that three thirty thousand frame tours never touched, found
  by comparing the whole of work RAM against the previous frame after every
  frame. An earlier instrument watched byte accesses only, missed everything this
  game moves by DMA, and put the block on top of a live table.

## Where the open questions are

[`OPEN-QUESTIONS.md`](OPEN-QUESTIONS.md). Anything not yet settled by measurement
belongs there, with the measurement that would settle it.
