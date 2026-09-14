from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from threading import Lock, local
import time
from typing import Any


@dataclass
class Span:
    name: str
    start_time: datetime = field(default_factory=datetime.now)
    end_time: datetime | None = None
    duration_ms: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list[Span] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def end(self) -> None:
        self.end_time = datetime.now()
        self.duration_ms = int((self.end_time - self.start_time).total_seconds() * 1000)

    def add_attribute(self, key: str, value: Any) -> None:
        with self._lock:
            self.attributes[key] = value

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms,
            "attributes": self.attributes,
            "children": [c.to_dict() for c in self.children],
        }


_tls = local()
_stack_lock = Lock()


def _stack() -> list[Span]:
    stack = getattr(_tls, "stack", None)
    if stack is None:
        stack = []
        _tls.stack = stack
    return stack


def start_span(name: str, parent: Span | None = None) -> tuple[Span | None, Span]:
    span = Span(name=name)
    attached_parent = parent
    stack = _stack()
    if attached_parent is None and stack:
        attached_parent = stack[-1]
    if attached_parent is not None:
        with attached_parent._lock:
            attached_parent.children.append(span)
    stack.append(span)
    return attached_parent, span


def pop_span(span: Span) -> None:
    stack = _stack()
    if stack and stack[-1] is span:
        stack.pop()
    elif span in stack:
        stack.remove(span)


def export_trace_to_file(root_span: Span, work_dir: str, session_id: str, keep: int = 20) -> Path:
    trace_dir = Path(work_dir) / ".claw" / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    ns = time.time_ns()
    filename = trace_dir / f"trace_{session_id}_{ns}.json"
    while filename.exists():
        ns += 1
        filename = trace_dir / f"trace_{session_id}_{ns}.json"
    filename.write_text(json.dumps(root_span.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    prune_old_traces(trace_dir, keep=keep)
    return filename


def prune_old_traces(trace_dir: str | Path, keep: int = 20) -> int:
    """Delete oldest trace_*.json files so at most `keep` remain. Returns deleted count."""
    folder = Path(trace_dir)
    if not folder.is_dir() or keep < 0:
        return 0
    files = [p for p in folder.glob("trace_*.json") if p.is_file()]
    files.sort(key=lambda p: (p.stat().st_mtime, p.name))
    extra = files[:-keep] if keep else files
    deleted = 0
    for path in extra:
        try:
            path.unlink()
            deleted += 1
        except OSError:
            continue
    return deleted
