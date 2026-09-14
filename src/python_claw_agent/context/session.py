from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock
import json
import re

from python_claw_agent.context.compact import Compactor
from python_claw_agent.schema import ROLE_USER, Message, ToolCall, Usage


SESSION_WARN_BYTES = 256 * 1024


def is_user_task(msg: Message) -> bool:
    return msg.role == ROLE_USER and not msg.tool_call_id


def select_working_memory(
    history: list[Message],
    tail_limit: int = 48,
    max_user_tasks: int = 6,
) -> list[Message]:
    """Keep recent user tasks plus the turns after them. Never start on a bare tool result."""
    if not history:
        return []
    if tail_limit <= 0:
        tail_limit = 48
    if max_user_tasks <= 0:
        max_user_tasks = 6
    task_idxs = [i for i, msg in enumerate(history) if is_user_task(msg)]
    if task_idxs:
        start = task_idxs[-max_user_tasks] if len(task_idxs) > max_user_tasks else task_idxs[0]
    else:
        start = max(0, len(history) - tail_limit)
    res = list(history[start:])
    if res and not is_user_task(res[0]):
        for i in range(start - 1, -1, -1):
            if is_user_task(history[i]):
                res = [history[i], *res]
                break
        else:
            while res and res[0].role == ROLE_USER and res[0].tool_call_id:
                res = res[1:]
    return res


def session_file(work_dir: str | Path, session_id: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", session_id).strip("._")[:80]
    if not safe:
        safe = "session"
    return Path(work_dir).resolve() / ".claw" / "sessions" / f"{safe}.json"


def _message_to_dict(msg: Message) -> dict:
    data: dict = {
        "role": msg.role,
        "content": msg.content,
        "tool_call_id": msg.tool_call_id,
        "tool_calls": [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in msg.tool_calls
        ],
    }
    if msg.usage is not None:
        data["usage"] = {
            "prompt_tokens": msg.usage.prompt_tokens,
            "completion_tokens": msg.usage.completion_tokens,
        }
    return data


def _message_from_dict(data: dict) -> Message:
    usage = None
    raw_usage = data.get("usage")
    if isinstance(raw_usage, dict):
        usage = Usage(
            prompt_tokens=int(raw_usage.get("prompt_tokens") or 0),
            completion_tokens=int(raw_usage.get("completion_tokens") or 0),
        )
    tool_calls = [
        ToolCall(
            id=str(tc.get("id", "")),
            name=str(tc.get("name", "")),
            arguments=str(tc.get("arguments") or "{}"),
        )
        for tc in data.get("tool_calls") or []
        if isinstance(tc, dict)
    ]
    return Message(
        role=str(data.get("role", ROLE_USER)),
        content=str(data.get("content") or ""),
        tool_calls=tool_calls,
        tool_call_id=str(data.get("tool_call_id") or ""),
        usage=usage,
    )


@dataclass
class Session:
    id: str
    work_dir: str
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost: float = 0.0
    history: list[Message] = field(default_factory=list)
    persist: bool = False
    _lock: Lock = field(default_factory=Lock, repr=False)

    def append(self, *msgs: Message) -> None:
        with self._lock:
            self.history.extend(msgs)
            self.updated_at = datetime.now()
        self._maybe_save()

    def clear_history(self) -> None:
        with self._lock:
            self.history.clear()
            self.updated_at = datetime.now()
        self._maybe_save()

    def compact_history(self, retain_last_msgs: int = 12) -> tuple[int, int]:
        """Fold early tool/assistant blobs in place and rewrite disk. Keeps user tasks."""
        compactor = Compactor(max_chars=0, retain_last_msgs=retain_last_msgs)
        with self._lock:
            before = compactor.estimate_length(self.history)
            self.history = compactor.compact(self.history, force=True)
            after = compactor.estimate_length(self.history)
            self.updated_at = datetime.now()
        self._maybe_save()
        return before, after

    def disk_size_bytes(self) -> int:
        path = session_file(self.work_dir, self.id)
        try:
            return path.stat().st_size if path.is_file() else 0
        except OSError:
            return 0

    def get_working_memory(self, tail_limit: int = 48, max_user_tasks: int = 6) -> list[Message]:
        with self._lock:
            history = list(self.history)
        return select_working_memory(history, tail_limit=tail_limit, max_user_tasks=max_user_tasks)

    def record_usage(self, prompt: int, completion: int, cost: float) -> None:
        with self._lock:
            self.total_prompt_tokens += prompt
            self.total_completion_tokens += completion
            self.total_cost += cost
        self._maybe_save()

    def _maybe_save(self) -> None:
        if self.persist:
            self.save()

    def save(self) -> Path:
        path = session_file(self.work_dir, self.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            payload = {
                "id": self.id,
                "work_dir": str(Path(self.work_dir).resolve()),
                "created_at": self.created_at.isoformat(),
                "updated_at": self.updated_at.isoformat(),
                "total_prompt_tokens": self.total_prompt_tokens,
                "total_completion_tokens": self.total_completion_tokens,
                "total_cost": self.total_cost,
                "history": [_message_to_dict(m) for m in self.history],
            }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    @classmethod
    def load(cls, work_dir: str, session_id: str) -> Session | None:
        path = session_file(work_dir, session_id)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        history = [_message_from_dict(item) for item in data.get("history") or [] if isinstance(item, dict)]
        sess = cls(
            id=str(data.get("id") or session_id),
            work_dir=str(Path(work_dir).resolve()),
            created_at=_parse_dt(data.get("created_at")),
            updated_at=_parse_dt(data.get("updated_at")),
            total_prompt_tokens=int(data.get("total_prompt_tokens") or 0),
            total_completion_tokens=int(data.get("total_completion_tokens") or 0),
            total_cost=float(data.get("total_cost") or 0.0),
            history=history,
            persist=True,
        )
        return sess


def _parse_dt(value: object) -> datetime:
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now()


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = Lock()

    def _key(self, session_id: str, work_dir: str) -> str:
        return f"{Path(work_dir).resolve()}::{session_id}"

    def get_or_create(self, session_id: str, work_dir: str) -> Session:
        key = self._key(session_id, work_dir)
        with self._lock:
            cached = self._sessions.get(key)
            if cached is not None:
                return cached
            loaded = Session.load(work_dir, session_id)
            if loaded is not None:
                self._sessions[key] = loaded
                return loaded
            sess = Session(
                id=session_id,
                work_dir=str(Path(work_dir).resolve()),
                persist=True,
            )
            self._sessions[key] = sess
            return sess

    def clear_cache(self) -> None:
        with self._lock:
            self._sessions.clear()


global_session_mgr = SessionManager()
