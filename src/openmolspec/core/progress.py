"""Progress reporting that stays readable in terminals and log files.

Interactive runs use ``tqdm``.  When stdout/stderr is redirected through tools
such as ``tee``, progress is emitted as periodic newline-delimited status
records instead of carriage-return based bars.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Iterable, Iterator, Optional, TextIO, TypeVar

from tqdm import tqdm


T = TypeVar("T")
_PREFIX = "[OpenMolSpec]"


def progress_mode(stream: Optional[TextIO] = None) -> str:
    """Return ``bar``, ``log`` or ``off`` for the current process.

    ``OPENSPEC_PROGRESS`` can force one of those modes.  The default ``auto``
    uses a bar only when the output stream is an interactive terminal.
    """

    requested = os.environ.get("OPENSPEC_PROGRESS", "auto").strip().lower()
    aliases = {"always": "bar", "tty": "bar", "none": "off", "quiet": "off"}
    requested = aliases.get(requested, requested)
    if requested in {"bar", "log", "off"}:
        return requested
    target = stream or sys.stderr
    return "bar" if target.isatty() else "log"


def status(message: str, *, stream: Optional[TextIO] = None) -> None:
    """Write one flush-safe, grep-friendly status line."""

    print(f"{_PREFIX} {message}", file=stream or sys.stderr, flush=True)


def _duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def track(
    iterable: Iterable[T],
    *,
    total: Optional[int] = None,
    desc: str,
    unit: str = "item",
    leave: bool = True,
    log_interval_seconds: float = 60.0,
    stream: Optional[TextIO] = None,
) -> Iterator[T]:
    """Iterate with a terminal bar or clean periodic log records."""

    target = stream or sys.stderr
    mode = progress_mode(target)
    if total is None:
        try:
            total = len(iterable)  # type: ignore[arg-type]
        except TypeError:
            total = None

    if mode == "bar":
        yield from tqdm(
            iterable,
            total=total,
            desc=desc,
            unit=unit,
            leave=leave,
            dynamic_ncols=True,
            mininterval=1.0,
            file=target,
        )
        return
    if mode == "off":
        yield from iterable
        return

    total_text = f"{total:,} {unit}" if total is not None else unit
    status(f"{desc}: started ({total_text})", stream=target)
    started = time.monotonic()
    last_report = started
    count = 0
    for count, item in enumerate(iterable, start=1):
        yield item
        now = time.monotonic()
        if now - last_report < log_interval_seconds:
            continue
        elapsed = max(now - started, 1e-9)
        rate = count / elapsed
        if total:
            fraction = count / total
            eta = (total - count) / rate if rate else 0.0
            detail = (
                f"{count:,}/{total:,} ({fraction:.1%}) | "
                f"{rate:,.1f} {unit}/s | ETA {_duration(eta)}"
            )
        else:
            detail = f"{count:,} {unit} | {rate:,.1f} {unit}/s"
        status(f"{desc}: {detail}", stream=target)
        last_report = now

    elapsed = time.monotonic() - started
    status(
        f"{desc}: completed ({count:,} {unit}, {_duration(elapsed)})",
        stream=target,
    )
