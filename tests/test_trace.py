import os
from pathlib import Path

from python_claw_agent.observability.trace import Span, export_trace_to_file, prune_old_traces


def test_prune_old_traces_keeps_newest(tmp_path: Path) -> None:
    folder = tmp_path / "traces"
    folder.mkdir()
    for i in range(25):
        path = folder / f"trace_s_{i:03d}.json"
        path.write_text("{}", encoding="utf-8")
        os.utime(path, (i + 1_700_000_000, i + 1_700_000_000))
    deleted = prune_old_traces(folder, keep=20)
    assert deleted == 5
    remaining = sorted(p.name for p in folder.glob("trace_*.json"))
    assert len(remaining) == 20
    assert "trace_s_000.json" not in remaining
    assert "trace_s_024.json" in remaining


def test_export_trace_prunes(tmp_path: Path) -> None:
    for _ in range(22):
        span = Span(name="root")
        span.end()
        export_trace_to_file(span, str(tmp_path), "s", keep=20)
    traces = list((tmp_path / ".claw" / "traces").glob("trace_*.json"))
    assert len(traces) == 20
