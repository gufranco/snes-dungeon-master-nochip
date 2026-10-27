import importlib.util
import random
import sys
from collections import namedtuple
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _load_tool(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec is not None and spec.loader is not None, "no loader for that path"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(ROOT))
import hardware  # noqa: E402

hardware.install()

import snesdsp  # noqa: E402

replay = _load_tool("replay")
protocol = _load_tool("protocol")

PART = "dsp2"


def chip(build: Any = None) -> Any:
    return (build or snesdsp.Chip)(PART)


def why_not(model: Any = None) -> Any:
    return (model or snesdsp).why_not()


TILE = 0x01
TRANSPARENT = 0x03
MERGE = 0x05
MIRROR = 0x06
MULTIPLY = 0x09
SCALE = 0x0D
SYNC = 0x0F

COMMANDS = (TILE, TRANSPARENT, MERGE, MIRROR, MULTIPLY, SCALE, SYNC)

UNKNOWN = 0x100

UNRECOGNISED = tuple(value for value in range(256) if value not in COMMANDS)

WEIGHTS = {
    TILE: 12,
    TRANSPARENT: 8,
    MERGE: 40,
    MIRROR: 10,
    MULTIPLY: 10,
    SCALE: 10,
    SYNC: 4,
    UNKNOWN: 4,
}

EDGE_LENGTHS = (1, 2, 3, 4, 15, 16, 17, 127, 128, 254, 255)

Case = namedtuple("Case", "command lengths written expected")


def _length(rng: Any) -> int:
    if rng.random() < 0.4:
        chosen: int = rng.choice(EDGE_LENGTHS)
        return chosen
    drawn: int = rng.randrange(1, 256)
    return drawn


def _lengths_for(command: int, rng: Any) -> tuple[int, ...]:
    if command == UNKNOWN:
        return ()
    if command in (MERGE, MIRROR):
        return (_length(rng),)
    if command == SCALE:
        return (_length(rng), _length(rng))
    return ()


COLOURS = 16

OPENING_COLOUR = 0


def build_cases(seed: int, count: int, only: Any = None, build: Any = chip) -> list[Any]:
    rng = random.Random(seed)
    part = build()
    shape = protocol.Shape()
    chosen_commands = (*COMMANDS, UNKNOWN) if only is None else tuple(only)
    population = [command for command in chosen_commands for _ in range(WEIGHTS[command])]

    cases: list[Any] = []
    for step in range(count + 1):
        chosen = TRANSPARENT if step == 0 else rng.choice(population)
        command = rng.choice(UNRECOGNISED) if chosen == UNKNOWN else chosen
        lengths = _lengths_for(chosen, rng)

        written = bytearray([command, *lengths])
        for byte in written:
            part.write(byte)
            shape.wrote(byte)

        while shape.expecting_input:
            if command == TRANSPARENT:
                byte = OPENING_COLOUR if step == 0 else rng.randrange(COLOURS)
            else:
                byte = rng.randrange(256)
            written.append(byte)
            part.write(byte)
            shape.wrote(byte)

        pending: int = shape.produced
        wanted: int = pending
        if pending and rng.random() < 0.25:
            wanted = rng.randrange(0, pending)
        collected = bytearray()
        for _ in range(wanted):
            collected.append(hardware.answer(part))
            shape.was_read()
        cases.append(Case(command, lengths, bytes(written), bytes(collected)))
    return cases


def runs_for(cases: Any) -> list[Any]:
    runs: list[Any] = []
    for case in cases:
        runs.append((replay.KIND_WRITE, case.written))
        if case.expected:
            runs.append((replay.KIND_READ, case.expected))
    return runs


NAMES = {
    TILE: "tile",
    TRANSPARENT: "transparent",
    MERGE: "merge",
    MIRROR: "mirror",
    MULTIPLY: "multiply",
    SCALE: "scale",
    SYNC: "sync",
}

BYTE_FOR = {name: command for command, name in NAMES.items()}

CALIBRATION_TRACE = ROOT / "build" / "trace-s1.bin"

WITNESS = "mirror"

Reading = namedtuple("Reading", "answered kept_up")


def answered(part: Any, transaction: Any) -> bool:
    for byte in (
        bytes([transaction.command]) + bytes(transaction.lengths) + bytes(transaction.parameters)
    ):
        part.write(byte)
    given = bytes(hardware.answer(part) for _ in range(len(transaction.output)))
    return given == bytes(transaction.output)


def sample(transactions: Any, wanted: Any = None) -> Any:
    wanted = tuple(NAMES.values()) if wanted is None else tuple(wanted)
    found: dict[str, Any] = {}
    colour = None
    for transaction in transactions:
        if not transaction.complete:
            continue
        if transaction.name == NAMES[TRANSPARENT] and colour is None:
            colour = transaction
        if transaction.name in wanted and transaction.name not in found:
            found[transaction.name] = transaction
        if len(found) == len(wanted) and colour is not None:
            break
    return colour, found


def calibrate(colour: Any, witness: Any, subjects: Any, build: Any = chip) -> dict[str, Any]:
    verdicts: dict[str, Any] = {}
    for name, transaction in subjects.items():
        part = build()
        if colour is not None:
            answered(part, colour)
        answered(part, witness)
        verdicts[name] = Reading(answered(part, transaction), answered(part, witness))
    return verdicts


def trusted(readings: Any) -> tuple[int, ...]:
    sound = {name for name, one in readings.items() if one.answered and one.kept_up}
    found = [BYTE_FOR[name] for name in sound if name in BYTE_FOR]
    if NAMES[SYNC] in sound:
        found.append(UNKNOWN)
    return tuple(sorted(found))


def oracle(
    trace: Any = None,
    build: Any = chip,
    transactions: Any = None,
) -> dict[str, Any] | None:
    if transactions is None:
        trace = CALIBRATION_TRACE if trace is None else Path(trace)
        if not trace.exists():
            return None
        import dsptrace

        transactions = dsptrace.transactions(dsptrace.records(trace))

    colour, found = sample(transactions)
    if WITNESS not in found:
        return None
    return calibrate(colour, found[WITNESS], found, build)


def walk(
    build: Any,
    skeleton: Any,
    batches: Any,
    run_batch: Any,
    say: Callable[[str], None],
    clock: Any,
) -> Any:
    walked = compared = wrong = 0
    failures: list[Any] = []
    for number, batch in enumerate(batches):
        started = clock()
        script, found = run_batch(build, skeleton, batch)
        if not found["finished"]:
            say(f"  batch {number} did not finish, {found['compared']} checked")
            return None
        walked += found["transactions"]
        compared += found["compared"]
        wrong += found["wrong"]
        if found["wrong"]:
            failures.append((number, found))
        say(
            f"    batch {number:3d}: {len(script):8d} bytes of script, "
            f"{found['compared']:9d} checked, {found['wrong']:6d} wrong, "
            f"{clock() - started:5.1f}s"
        )
    return walked, compared, wrong, failures


def summary_lines(cases: Any, walked: Any, compared: int, wrong: int, failures: Any) -> list[str]:
    per_command: dict[int, int] = {}
    for case in cases:
        per_command[case.command] = per_command.get(case.command, 0) + 1

    names = dict(NAMES)
    for command in sorted(per_command):
        names.setdefault(command, f"unknown ${command:02X}")

    lines = ["", "  cases by command:"]
    lines.extend(f"    {names[command]:12s} {per_command.get(command, 0)}" for command in COMMANDS)
    strange = sum(count for command, count in per_command.items() if command not in COMMANDS)
    lines.append(f"    {'unrecognised':12s} {strange}")
    lines.append("")
    lines.append(f"  runs walked   {walked}")
    lines.append(f"  bytes checked {compared}")
    lines.append(f"  bytes wrong   {wrong}")
    lines.extend(
        f"    batch {number}: first at byte {found['first']}, "
        f"part ${found['expected']:02X}, routines ${found['returned']:02X}"
        for number, found in failures[:5]
    )
    return lines


def main(
    argv: list[str],
    refuses: Any = why_not,
    assemble: Any = replay.assemble,
    run_batch: Any = replay.run_batch,
    generate: Any = build_cases,
    say: Callable[[str], None] = print,
    clock: Any = None,
    checked: Any = None,
) -> int:
    import time

    clock = time.time if clock is None else clock
    checked = oracle if checked is None else checked

    seed = int(argv[0]) if argv else 1
    count = int(argv[1]) if len(argv) > 1 else 20000
    only = [int(name, 0) for name in argv[2:]] or None

    reason = refuses()
    if reason:
        say(f"  nothing to build: {reason}")
        return 2

    readings = checked()
    if readings is None:
        say("  the oracle is unchecked: no recording here to measure it against, and")
        say("  a run against an unmeasured oracle reports its faults as the routines'")
        return 2

    for name, one in sorted(readings.items()):
        if one.answered and one.kept_up:
            continue
        fault = (
            "answers what the cartridge did not"
            if not one.answered
            else "answers correctly and leaves the next exchange unanswerable"
        )
        say(f"  {name} is left out: against this recording the model {fault}")

    allowed = trusted(readings)
    wanted = [one for one in (only or allowed) if one in allowed]
    if not wanted:
        say("  nothing left to generate, so there is nothing this run could report")
        return 2

    build = ROOT / "build"
    skeleton = assemble(ROOT, build)
    say(f"  cartridge built, {len(skeleton)} bytes")

    cases = generate(seed, count, wanted)
    runs = runs_for(cases)
    expected = sum(len(case.expected) for case in cases)
    say(f"  seed {seed}, {len(cases)} cases, {expected} bytes the part gave back")

    room = replay.capacity(replay.IMAGE_BYTES) - replay.MAX_OVERSHOOT
    found = walk(build, skeleton, replay.batches_of(runs, room), run_batch, say, clock)
    if found is None:
        return 1

    walked, compared, wrong, failures = found
    for line in summary_lines(cases, walked, compared, wrong, failures):
        say(line)
    return 0 if wrong == 0 else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    raise SystemExit(main(sys.argv[1:]))
