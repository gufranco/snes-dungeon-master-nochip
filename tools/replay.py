"""Feed the cartridge's own recorded traffic to the routines, on the processor.

The model reproduces what the chip returned across a whole recorded run, but the
model is not what ships. The 65816 routines are, and they have to answer every
request the cartridge ever made with the byte its chip answered.

So the recorded stream is compiled into a cartridge that walks it, feeds each
run of writes through the entry points the patched game calls, reads back what
the routines return, and checks it against what the chip returned at that point.
The expected bytes travel in the script and the comparison happens on the
processor, so a run reports counters rather than a transcript and the script may
be as large as the cartridge holds.

Nothing here reconstructs a transaction. An earlier attempt did, and it put a
parser between the cartridge and the check: twelve merges in fifteen hundred
came back differing from the cartridge while agreeing exactly with the model,
which is the signature of a harness feeding something the chip was never fed.
What the trace says, in the order it says it, is what gets fed.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any


def _load_beside(name: str) -> Any:
    """A module that sits next to this one, loaded the way the tools load each other."""
    import importlib.util
    from pathlib import Path

    where = Path(__file__).resolve().parent / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, where)
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


protocol = _load_beside("protocol")

FEED = 0x01
CHECK = 0x02
END = 0x00

KIND_WRITE = 0
KIND_READ = 1

RUN_LIMIT = 0xFFFF

BANK_SIZE = 0x8000
SCRIPT_BANK = 0x02

STATE = 0x0D00
BYTE_COUNT = 4
TRANSACTIONS = 0x0A
COMPARED = 0x0E
WRONG = 0x12
FIRST = 0x16
EXPECTED = 0x1A
RETURNED = 0x1B
DONE = 0x1C

FINISHED = 0xA5


class ScriptTooLong(Exception):
    pass


def runs_from(records: Any) -> Iterator[Any]:
    """Consecutive bytes going the same way, as the cartridge sent them."""
    kind = None
    payload = bytearray()
    for this_kind, byte in records:
        if this_kind != kind:
            if payload:
                yield (kind, bytes(payload))
            kind, payload = this_kind, bytearray()
        payload.append(byte)
    if payload:
        yield (kind, bytes(payload))


def script_for(runs: Any) -> bytes:
    """The byte stream the cartridge walks.

    A run longer than a count can declare is split across several, which changes
    nothing about what reaches the chip: the state machine sees the same bytes
    in the same order either way.
    """
    out = bytearray()
    for kind, payload in runs:
        tag = FEED if kind == KIND_WRITE else CHECK
        at = 0
        while at < len(payload):
            piece = payload[at : at + RUN_LIMIT]
            out.append(tag)
            out += len(piece).to_bytes(2, "little")
            out += piece
            at += len(piece)
    out.append(END)
    return bytes(out)


WORK_RAM_BANK = 0x7E
"""The first bank the cartridge does not reach.

Banks $7E and $7F are work RAM whatever the cartridge holds, so a script laid
into the file past that point is addressed as memory rather than as ROM and the
cursor reads the power on fill instead of the script. A run that walked into it
spent its last comparisons against $55 and then stopped on a byte it took for the
end marker, which is what a script overrunning this looks like from outside.
"""


def capacity(image_bytes: int, bank: int = SCRIPT_BANK) -> int:
    """How much script an image of this size can carry from this bank on."""
    banks = min(image_bytes // BANK_SIZE, WORK_RAM_BANK)
    return max(0, (banks - bank) * BANK_SIZE)


def place_script(image: bytes | bytearray, script: bytes, bank: int = SCRIPT_BANK) -> bytes:
    """The script laid into the image from the given bank onward.

    LoROM exposes the upper half of each bank, and a file offset runs
    continuously, so a script that outgrows one bank simply continues at the
    next offset. The cartridge's cursor makes the same step.
    """
    if len(script) > capacity(len(image), bank):
        raise ScriptTooLong(
            f"the script is {len(script)} bytes and the image carries "
            f"{capacity(len(image), bank)} from bank ${bank:02X}"
        )
    out = bytearray(image)
    at = bank * BANK_SIZE
    out[at : at + len(script)] = script
    return bytes(out)


SYNC = 0x0F
SET_TRANSPARENT = 0x03

MAX_OVERSHOOT = 2048
"""How far a batch may run past the room it was given.

A break is only taken where the chip is idle, because a break anywhere else
splits a command from its result. When the room runs out mid command the batch
carries on to the next safe point, and the longest command is a merge of 255,
which is 512 bytes fed and 255 read. The caller leaves this much spare.
"""


def stream_batches(runs: Any, room: int, shape: Any = None) -> Any:
    """Batches a fresh cartridge can each start from, with what it carries.

    A batch is a separate run of the cartridge, so anything the part holds is
    lost at the boundary. Two things follow. A break may only happen where the
    part is between commands and owes nothing, or a command's payload lands in
    one batch and its drain in the next, and the routines then return the idle
    byte where the cartridge returned a result. And every batch after the first
    opens with a sync and the transparent colour in force, because that colour
    decides what a merge returns and a batch that starts without it reports
    failures that are the harness's own.

    Where the boundaries are is a question about the shape of the traffic rather
    than about what the part computes, so it is answered by tracking the stream
    rather than by asking a chip. Silicon cannot be asked: its status register
    says the part wants attention and never how much it still owes.
    """
    shape = protocol.Shape() if shape is None else shape
    current: list[Any] = []
    used = 1  # the stop marker every script carries
    prelude = b""

    for kind, payload in runs:
        cost = 3 + len(payload)
        idle = kind == KIND_WRITE and shape.at_boundary
        if used + cost > room and idle and current:
            yield ([(KIND_WRITE, prelude)] if prelude else []) + current
            prelude = bytes([SYNC, SET_TRANSPARENT, shape.transparent or 0x00])
            current = []
            used = 3 + len(prelude) + 1  # the prelude run and the stop marker

        current.append((kind, payload))
        used += cost

        if kind == KIND_WRITE:
            for byte in payload:
                shape.wrote(byte)
        else:
            for _ in payload:
                shape.was_read()

    if current:
        yield ([(KIND_WRITE, prelude)] if prelude else []) + current


def batches_of(runs: Any, room: int) -> list[Any]:
    """Runs grouped so each group's script fits the room, never splitting one."""
    batches: list[Any] = []
    current: list[Any] = []
    used = 0
    for kind, payload in runs:
        cost = 3 + len(payload)
        if used + cost > room and current:
            batches.append(current)
            current, used = [], 0
        current.append((kind, payload))
        used += cost
    if current:
        batches.append(current)
    return batches


IMAGE_BYTES = 0x400000
FRAMES = 4000000
ASSEMBLER = "dungeon-master-nochip/asar:1.81"
EMULATOR = "dungeon-master-nochip/emu:dev"


def _number(dump: bytes, offset: int, width: int) -> int:
    at = STATE + offset
    return int.from_bytes(dump[at : at + width], "little")


def read_counters(dump: bytes) -> Any:
    """What the run reported, read out of the dumped work RAM."""
    return {
        "finished": dump[STATE + DONE] == FINISHED,
        "transactions": _number(dump, TRANSACTIONS, BYTE_COUNT),
        "compared": _number(dump, COMPARED, BYTE_COUNT),
        "wrong": _number(dump, WRONG, BYTE_COUNT),
        "first": _number(dump, FIRST, BYTE_COUNT),
        "expected": dump[STATE + EXPECTED],
        "returned": dump[STATE + RETURNED],
    }


def assemble_command(root: Path, build: Path) -> list[str]:
    """What assembling the replay cartridge shells out to."""
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--entrypoint",
        "sh",
        "-v",
        f"{root / 'asm'}:/src:ro",
        "-v",
        f"{build}:/out",
        ASSEMBLER,
        "-c",
        "cd /src && asar --no-title-check --fix-checksum=on dsp2-replay.asm /out/replay.sfc",
    ]


def _shell_out(args: list[str]) -> Any:
    import subprocess

    return subprocess.run(args, capture_output=True, text=True, check=False)


def assemble(root: Path, build: Path, execute: Any = _shell_out) -> Any:
    """The replay cartridge, assembled by the pinned toolchain."""
    (build / "replay.sfc").write_bytes(bytes(IMAGE_BYTES))
    built = execute(assemble_command(root, build))
    if built.returncode:
        raise SystemExit(built.stderr or built.stdout)
    return (build / "replay.sfc").read_bytes()


def run_command(build: Path) -> list[str]:
    """What running one batch through the emulator shells out to."""
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "-e",
        "DMDUMP=replay-wram.bin",
        "-e",
        f"DMSTOP={STATE + DONE:X}:{FINISHED:X}",
        "-v",
        f"{build}:/work",
        EMULATOR,
        "replay.sfc",
        str(FRAMES),
    ]


def run_batch(build: Path, skeleton: Any, batch: Any, execute: Any = _shell_out) -> Any:
    """One batch walked by the cartridge, and the counters it left behind."""
    script = script_for(batch)
    (build / "replay.sfc").write_bytes(place_script(skeleton, script))
    execute(run_command(build))
    return script, read_counters((build / "replay-wram.bin").read_bytes())


def walk(
    build: Path,
    skeleton: Any,
    batches: Any,
    run_batch: Any,
    say: Callable[[str], None],
    clock: Any,
) -> Any:
    """Every batch through the cartridge, or nothing when one does not finish."""
    walked = compared = wrong = 0
    failures: list[Any] = []
    for number, batch in enumerate(batches):
        started = clock()
        script, found = run_batch(build, skeleton, batch)
        say(
            f"    batch {number:3d}: {len(script):8d} bytes of script, "
            f"{found['compared']:9d} checked, {found['wrong']:6d} wrong, "
            f"{clock() - started:5.1f}s"
        )
        if not found["finished"]:
            say(f"  batch {number} did not finish, {found['compared']} checked")
            return None
        walked += found["transactions"]
        compared += found["compared"]
        wrong += found["wrong"]
        if found["wrong"]:
            failures.append((number, found))
    return walked, compared, wrong, failures


def summary_lines(
    written: int, returned: int, walked: Any, compared: int, wrong: int, failures: Any
) -> list[str]:
    """What a run found, in the order somebody reading it wants it."""
    lines = [
        "",
        f"  written {written}, the chip returned {returned}",
        f"  runs walked   {walked}",
        f"  bytes checked {compared}",
        f"  bytes wrong   {wrong}",
    ]
    lines.extend(
        f"    batch {number}: first at byte {found['first']}, "
        f"cartridge ${found['expected']:02X}, routines ${found['returned']:02X}"
        for number, found in failures[:5]
    )
    return lines


def main(
    argv: list[str],
    assemble: Any = assemble,
    run_batch: Any = run_batch,
    records: Any = None,
    say: Callable[[str], None] = print,
    clock: Any = None,
) -> int:
    """A recorded trace fed to the routines on the processor, and what disagreed."""
    import time
    from pathlib import Path

    clock = time.time if clock is None else clock

    if not argv:
        say("usage: replay.py <trace.bin> [record limit]")
        return 2

    root = Path(__file__).resolve().parent.parent
    build = root / "build"
    trace = Path(argv[0])
    limit = int(argv[1]) if len(argv) > 1 else 0

    if not trace.exists():
        say(f"  no trace at {trace}; the builder records their own")
        return 0

    read_records = load_dsptrace(root).records if records is None else records
    skeleton = assemble(root, build)
    say(f"  cartridge built, {len(skeleton)} bytes")

    stream = ((record.kind, record.byte) for record in read_records(str(trace)))
    if limit:
        stream = (item for index, item in enumerate(stream) if index < limit)

    room = capacity(IMAGE_BYTES) - MAX_OVERSHOOT
    written = returned = 0

    def counted(source: Any) -> Any:
        nonlocal written, returned
        for kind, payload in source:
            if kind == KIND_WRITE:
                written += len(payload)
            else:
                returned += len(payload)
            yield (kind, payload)

    batches = stream_batches(counted(runs_from(stream)), room)
    found = walk(build, skeleton, batches, run_batch, say, clock)
    if found is None:
        return 1

    walked, compared, wrong, failures = found
    for line in summary_lines(written, returned, walked, compared, wrong, failures):
        say(line)
    return 0 if wrong == 0 else 1


def load_dsptrace(root: Path) -> Any:
    import importlib.util

    spec = importlib.util.spec_from_file_location("dsptrace", root / "dsptrace.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    import sys

    raise SystemExit(main(sys.argv[1:]))
