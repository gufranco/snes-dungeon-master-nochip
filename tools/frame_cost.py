import importlib.util
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import dsptrace  # noqa: E402

TRAMPOLINE_FIRST = 0x0080
TRAMPOLINE_LAST = 0x008F

MIRRORING_BANKS = 0x40

TRACES = tuple(ROOT / "build" / f"trace-s{tour}.bin" for tour in (1, 2, 3))

Prices = dict[str, tuple[float, float]]


@dataclass(frozen=True, slots=True)
class Tally:
    frames: int
    calls: Counter[tuple[str, bool]]
    retail: Counter[str]


def through_mover(record: Any) -> bool:
    pc: int = record.pc
    bank = (pc >> 16) & 0x7F
    return bank < MIRRORING_BANKS and TRAMPOLINE_FIRST <= (pc & 0xFFFF) <= TRAMPOLINE_LAST


class Watched:
    def __init__(self, stream: Iterable[Any]) -> None:
        self.stream = stream
        self.moved = False

    def __iter__(self) -> Iterator[Any]:
        for record in self.stream:
            self.moved = self.moved or through_mover(record)
            yield record

    def take(self) -> bool:
        seen, self.moved = self.moved, False
        return seen


def tally(stream: Iterable[Any], after: int, retail: Callable[..., int]) -> Tally:
    calls: Counter[tuple[str, bool]] = Counter()
    retail_cycles: Counter[str] = Counter()
    watched = Watched(stream)
    span: tuple[int, int] | None = None
    for transaction in dsptrace.transactions(watched):
        dispatched = watched.take()
        if not transaction.complete or transaction.frame < after:
            continue
        span = (transaction.frame if span is None else span[0], transaction.frame)
        calls[(transaction.name, dispatched)] += 1
        retail_cycles[transaction.name] += retail(
            transaction.name, transaction.parameters, transaction.output
        )
    frames = 0 if span is None else span[1] - span[0] + 1
    return Tally(frames, calls, retail_cycles)


def combined(tallies: Iterable[Tally]) -> Tally:
    every = tuple(tallies)
    return Tally(
        sum(one.frames for one in every),
        sum((one.calls for one in every), Counter()),
        sum((one.retail for one in every), Counter()),
    )


def rows(found: Tally, prices: Prices) -> list[tuple[str, int, float, float, float]]:
    out = []
    for name in sorted({name for name, _ in found.calls}):
        direct, dispatched = found.calls[(name, False)], found.calls[(name, True)]
        calls = direct + dispatched
        direct_price, dispatched_price = prices.get(name, (0.0, 0.0))
        ours = (direct * direct_price + dispatched * dispatched_price) / found.frames
        out.append((name, calls, dispatched / calls, ours, found.retail[name] / found.frames))
    return out


def report(found: Tally, prices: Prices) -> list[str]:
    if not found.frames:
        return ["  no complete exchange was recorded after the settled frame"]
    lines = [
        f"  {found.frames:,} frames, every exchange after the boot sequence",
        f"  {'command':<12}{'calls':>12}{'dispatched':>12}{'ours':>9}{'retail':>9}",
    ]
    ours_total, retail_total = 0.0, 0.0
    for name, calls, share, ours, retail in rows(found, prices):
        lines.append(f"  {name:<12}{calls:>12,}{share:>12.0%}{ours:>9,.0f}{retail:>9,.0f}")
        ours_total, retail_total = ours_total + ours, retail_total + retail
    lines.append(f"  {'a frame':<36}{ours_total:>9,.0f}{retail_total:>9,.0f}")
    return lines


def means(joined: dict[str, list[tuple[int, int, int, bool]]]) -> Prices:
    return {
        name: (
            sum(one for one, _, _, _ in entries) / len(entries),
            sum(two for _, two, _, _ in entries) / len(entries),
        )
        for name, entries in joined.items()
    }


def load_cost() -> Any:
    spec = importlib.util.spec_from_file_location("cost", ROOT / "tools" / "cost.py")
    assert spec is not None and spec.loader is not None, "no loader for the cost harness"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def priced(cost: Any, rom_path: Path, trace: Path, wanted: int) -> Prices:
    rom = rom_path.read_bytes()
    names = cost.symbols(rom_path.with_suffix(".sym").read_text())
    return means(
        cost.joined(
            cost.sweep(rom, names, trace, wanted, cost.SAMPLED, dispatched=False),
            cost.sweep(rom, names, trace, wanted, cost.SAMPLED, dispatched=True),
        )
    )


def main(
    argv: list[str],
    say: Callable[[str], None] = print,
    load: Callable[[], Any] = load_cost,
    price: Callable[..., Prices] = priced,
) -> int:
    cost = load()
    rom_path = ROOT / "asm" / "dm-sym.sfc" if len(argv) < 2 else Path(argv[1])
    traces = TRACES if len(argv) < 3 else tuple(Path(one) for one in argv[2:])
    missing = [
        str(one) for one in (rom_path, rom_path.with_suffix(".sym"), *traces) if not one.exists()
    ]
    if missing:
        say(f"  missing: {', '.join(missing)}")
        return 2
    prices = price(cost, rom_path, traces[0], 60)
    found = combined(
        tally(dsptrace.records(one), cost.SETTLED_FRAME, cost.retail_cost) for one in traces
    )
    for line in report(found, prices):
        say(line)
    return 0 if found.frames else 1


if __name__ == "__main__":  # pragma: no cover
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[union-attr]
    raise SystemExit(main(sys.argv))
