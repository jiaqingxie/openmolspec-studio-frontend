from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from services.credits import record_model_usage


class Conflict(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def identifier() -> str:
    return uuid.uuid4().hex


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store:
    """PostgreSQL application data accessed in a verified user's scope."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._owner: ContextVar[str | None] = ContextVar("app_store_owner", default=None)

    @contextmanager
    def as_user(self, user_id: str):
        if not user_id:
            raise ValueError("Store requires a verified owner")
        token = self._owner.set(user_id)
        try:
            yield
        finally:
            self._owner.reset(token)

    def _owner_id(self) -> str:
        owner = self._owner.get()
        if owner is None:
            raise RuntimeError("Store requires a verified owner scope")
        return owner

    @contextmanager
    def _db(self):
        with psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5) as db:
            db.execute("SET LOCAL search_path TO pg_catalog, molspec_app")
            yield db

    def initialize(self):
        with self._db() as db:
            db.execute("SELECT pg_advisory_xact_lock(hashtext('molspec_app.store.schema'))")
            db.execute("""
                CREATE TABLE IF NOT EXISTS molspec_app.store_schema_versions (
                    version INTEGER PRIMARY KEY, installed_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
            """)
            if db.execute("SELECT 1 FROM molspec_app.store_schema_versions WHERE version=1").fetchone():
                return
            db.execute("""
                CREATE TABLE molspec_app.conversations (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES molspec_app.users(id),
                    title TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE (id, owner_id)
                );
                CREATE INDEX conversation_owner_updated ON molspec_app.conversations(owner_id, updated_at DESC, id DESC);
                CREATE TABLE molspec_app.messages (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES molspec_app.conversations(id) ON DELETE CASCADE,
                    position BIGINT GENERATED ALWAYS AS IDENTITY,
                    role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL,
                    attachments TEXT NOT NULL DEFAULT '[]', tool_calls TEXT NOT NULL DEFAULT '[]',
                    context TEXT NOT NULL DEFAULT '{}',
                    UNIQUE (conversation_id, id), UNIQUE (conversation_id, position)
                );
                CREATE TABLE molspec_app.runs (
                    id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL, owner_id TEXT NOT NULL,
                    assistant_message_id TEXT NOT NULL, status TEXT NOT NULL, context TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, job_ids TEXT NOT NULL DEFAULT '[]',
                    FOREIGN KEY (conversation_id, owner_id) REFERENCES molspec_app.conversations(id, owner_id) ON DELETE CASCADE,
                    FOREIGN KEY (conversation_id, assistant_message_id)
                        REFERENCES molspec_app.messages(conversation_id, id) ON DELETE CASCADE,
                    UNIQUE (conversation_id, id)
                );
                CREATE UNIQUE INDEX one_active_run ON molspec_app.runs(conversation_id) WHERE status='running';
                CREATE TABLE molspec_app.events (
                    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    run_id TEXT NOT NULL REFERENCES molspec_app.runs(id) ON DELETE CASCADE,
                    type TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE INDEX event_run ON molspec_app.events(run_id, id);
                CREATE TABLE molspec_app.attachments (
                    id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES molspec_app.users(id), data TEXT NOT NULL
                );
                CREATE TABLE molspec_app.agent_state (
                    run_id TEXT PRIMARY KEY REFERENCES molspec_app.runs(id) ON DELETE CASCADE,
                    checkpoint TEXT, transcript TEXT, usage TEXT
                );
                CREATE TABLE molspec_app.message_requests (
                    conversation_id TEXT NOT NULL,
                    request_id TEXT NOT NULL, payload TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    PRIMARY KEY (conversation_id, request_id),
                    FOREIGN KEY (conversation_id, run_id) REFERENCES molspec_app.runs(conversation_id, id) ON DELETE CASCADE
                );
                INSERT INTO molspec_app.store_schema_versions (version) VALUES (1)
            """)

    @staticmethod
    def _conversation(db, conversation_id: str, owner_id: str, *, lock: bool = False):
        query = "SELECT id, title, created_at, updated_at FROM conversations WHERE id=%s AND owner_id=%s"
        row = db.execute(query + (" FOR UPDATE" if lock else ""), (conversation_id, owner_id)).fetchone()
        if row is None:
            raise KeyError(conversation_id)
        return row

    @staticmethod
    def _run(db, run_id: str, owner_id: str, *, lock: bool = False):
        query = "SELECT * FROM runs WHERE id=%s AND owner_id=%s"
        row = db.execute(query + (" FOR UPDATE" if lock else ""), (run_id, owner_id)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return row

    def create_conversation(self, title: str = "新对话") -> dict:
        owner_id = self._owner_id()
        timestamp = now()
        value = {"id": identifier(), "title": title or "新对话", "created_at": timestamp, "updated_at": timestamp}
        with self._db() as db:
            db.execute("""
                INSERT INTO conversations (id, owner_id, title, created_at, updated_at)
                VALUES (%(id)s, %(owner_id)s, %(title)s, %(created_at)s, %(updated_at)s)
            """, {**value, "owner_id": owner_id})
        return value

    def list_conversations(self) -> list[dict]:
        owner_id = self._owner_id()
        with self._db() as db:
            return db.execute("""
                SELECT id, title, created_at, updated_at FROM conversations WHERE owner_id=%s
                ORDER BY updated_at DESC, id DESC
            """, (owner_id,)).fetchall()

    @staticmethod
    def message(row) -> dict:
        value = dict(row)
        value.pop("conversation_id", None)
        value.pop("position", None)
        value["attachments"] = json.loads(value["attachments"])
        value["tool_calls"] = json.loads(value["tool_calls"])
        value["context"] = json.loads(value["context"])
        return value

    def get_conversation(self, conversation_id: str) -> dict:
        owner_id = self._owner_id()
        with self._db() as db:
            value = self._conversation(db, conversation_id, owner_id)
            value["messages"] = [self.message(row) for row in db.execute(
                "SELECT * FROM messages WHERE conversation_id=%s ORDER BY position", (conversation_id,),
            )]
            active = db.execute(
                "SELECT id FROM runs WHERE conversation_id=%s AND status='running'", (conversation_id,),
            ).fetchone()
            value["active_run_id"] = active["id"] if active else None
            return value

    def require_conversation(self, conversation_id: str):
        owner_id = self._owner_id()
        with self._db() as db:
            self._conversation(db, conversation_id, owner_id)

    def delete_conversation(self, conversation_id: str):
        owner_id = self._owner_id()
        with self._db() as db:
            self._conversation(db, conversation_id, owner_id, lock=True)
            if db.execute("SELECT id FROM runs WHERE conversation_id=%s AND status='running'", (conversation_id,)).fetchone():
                raise Conflict("请先停止当前分析，再删除对话。")
            db.execute("DELETE FROM conversations WHERE id=%s", (conversation_id,))

    def save_attachment(self, value: dict, *, attachment_id: str | None = None) -> dict:
        owner_id = self._owner_id()
        value = {**value, "id": attachment_id if attachment_id is not None else identifier()}
        with self._db() as db:
            db.execute("INSERT INTO attachments (id, owner_id, data) VALUES (%s, %s, %s)",
                       (value["id"], owner_id, encode(value)))
        return value

    @staticmethod
    def _attachments(db, ids: list[str], owner_id: str) -> list[dict]:
        output = []
        for attachment_id in dict.fromkeys(ids):
            row = db.execute("SELECT data FROM attachments WHERE id=%s AND owner_id=%s",
                             (attachment_id, owner_id)).fetchone()
            if row is None:
                raise KeyError(attachment_id)
            output.append(json.loads(row["data"]))
        return output

    def get_attachments(self, ids: list[str]) -> list[dict]:
        owner_id = self._owner_id()
        with self._db() as db:
            return self._attachments(db, ids, owner_id)

    def begin_run(self, conversation_id: str, content: str, attachments: list, context: dict,
                  *, request_id: str | None = None, mode: str = "quick"):
        owner_id = self._owner_id()
        attachment_ids = [item["id"] for item in attachments]
        payload = json.dumps([content, attachment_ids, context, mode],
                             ensure_ascii=False, sort_keys=True, allow_nan=False)
        run_id, user_message_id, assistant_id = identifier(), identifier(), identifier()
        with self._db() as db:
            row = self._conversation(db, conversation_id, owner_id, lock=True)
            if request_id:
                previous = db.execute(
                    "SELECT payload, run_id FROM message_requests WHERE conversation_id=%s AND request_id=%s",
                    (conversation_id, request_id),
                ).fetchone()
                if previous:
                    if previous["payload"] != payload:
                        raise Conflict("此请求编号已用于不同的消息。")
                    return self._get_run(db, previous["run_id"], owner_id), None, None
            if db.execute("SELECT id FROM runs WHERE conversation_id=%s AND status='running'", (conversation_id,)).fetchone():
                raise Conflict("这个对话已有分析任务正在运行。")
            attachments = self._attachments(db, attachment_ids, owner_id)
            timestamp = now()
            messages = [
                (user_message_id, "user", content, "completed", attachments, context),
                (assistant_id, "assistant", "", "running", [], {}),
            ]
            saved = []
            for message_id, role, text, status, references, message_context in messages:
                saved.append(self.message(db.execute("""
                    INSERT INTO messages (id, conversation_id, role, content, created_at, status, attachments, context)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING *
                """, (message_id, conversation_id, role, text, timestamp, status,
                      encode(references), encode(message_context))).fetchone()))
            user, assistant = saved
            db.execute("""
                INSERT INTO runs (id, conversation_id, owner_id, assistant_message_id, status, context, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'running', %s, %s, %s)
            """, (run_id, conversation_id, owner_id, assistant_id, encode(context), timestamp, timestamp))
            title = " ".join(content.split())[:36] if row["title"] == "新对话" else row["title"]
            db.execute("UPDATE conversations SET title=%s, updated_at=%s WHERE id=%s", (title, timestamp, conversation_id))
            if request_id:
                db.execute("""
                    INSERT INTO message_requests (conversation_id, request_id, payload, run_id) VALUES (%s, %s, %s, %s)
                """, (conversation_id, request_id, payload, run_id))
            db.execute("INSERT INTO events (run_id, type, data) VALUES (%s, %s, %s)", (
                run_id, "run", encode({"id": run_id, "user_message": user, "assistant_message_id": assistant_id}),
            ))
            return self._get_run(db, run_id, owner_id), user, assistant

    @staticmethod
    def _get_run(db, run_id: str, owner_id: str) -> dict:
        row = db.execute("""
            SELECT runs.*, agent_state.usage FROM runs LEFT JOIN agent_state ON agent_state.run_id=runs.id
            WHERE runs.id=%s AND runs.owner_id=%s
        """, (run_id, owner_id)).fetchone()
        if row is None:
            raise KeyError(run_id)
        row.pop("owner_id")
        for field in ("context", "job_ids", "usage"):
            if row[field] is not None:
                row[field] = json.loads(row[field])
        return row

    def get_run(self, run_id: str) -> dict:
        owner_id = self._owner_id()
        with self._db() as db:
            return self._get_run(db, run_id, owner_id)

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        owner_id = self._owner_id()
        with self._db() as db:
            self._run(db, run_id, owner_id)
            return [{"id": row["id"], "type": row["type"], "data": json.loads(row["data"])} for row in db.execute(
                "SELECT id, type, data FROM events WHERE run_id=%s AND id>%s ORDER BY id", (run_id, after),
            )]

    def add_event(self, run_id: str, kind: str, data: dict):
        owner_id = self._owner_id()
        with self._db() as db:
            run = self._run(db, run_id, owner_id, lock=True)
            if run["status"] != "running":
                return
            db.execute("INSERT INTO events (run_id, type, data) VALUES (%s, %s, %s)", (run_id, kind, encode(data)))
            if kind == "delta":
                db.execute("UPDATE messages SET content=content||%s WHERE id=%s", (data["content"], run["assistant_message_id"]))
            elif kind in {"tool_start", "tool_end"}:
                row = db.execute("SELECT tool_calls FROM messages WHERE id=%s", (run["assistant_message_id"],)).fetchone()
                calls = json.loads(row["tool_calls"])
                record = next((call for call in calls if call["id"] == data["id"]), None)
                if record is None:
                    record = {"id": data["id"], "name": data["name"]}
                    calls.append(record)
                record.update(data)
                record["status"] = "completed" if kind == "tool_end" else "running"
                db.execute("UPDATE messages SET tool_calls=%s WHERE id=%s", (encode(calls), run["assistant_message_id"]))

    def save_checkpoint(self, run_id: str, value: dict | None):
        owner_id = self._owner_id()
        with self._db() as db:
            run = self._run(db, run_id, owner_id, lock=True)
            if run["status"] != "running":
                return
            db.execute("""
                INSERT INTO agent_state (run_id, checkpoint) VALUES (%s, %s)
                ON CONFLICT (run_id) DO UPDATE SET checkpoint=excluded.checkpoint
            """, (run_id, encode(value) if value is not None else None))

    def checkpoint(self, run_id: str):
        owner_id = self._owner_id()
        with self._db() as db:
            self._run(db, run_id, owner_id)
            row = db.execute("SELECT checkpoint FROM agent_state WHERE run_id=%s", (run_id,)).fetchone()
        return json.loads(row["checkpoint"]) if row and row["checkpoint"] else None

    def transcripts(self, conversation_id: str):
        owner_id = self._owner_id()
        with self._db() as db:
            self._conversation(db, conversation_id, owner_id)
            rows = db.execute("""
                SELECT runs.assistant_message_id, agent_state.transcript
                FROM agent_state JOIN runs ON runs.id=agent_state.run_id
                WHERE runs.conversation_id=%s AND agent_state.transcript IS NOT NULL
            """, (conversation_id,))
            return {row["assistant_message_id"]: json.loads(row["transcript"]) for row in rows}

    def record_usage(self, run_id: str, usage: dict):
        owner_id = self._owner_id()
        with self._db() as db:
            self._run(db, run_id, owner_id)
            record_model_usage(db, owner_id, run_id, usage)

    def finish_run(self, run_id: str, content: str, tool_calls: list, job_ids: list, *, transcript=None, usage=None):
        owner_id = self._owner_id()
        with self._db() as db:
            run = self._run(db, run_id, owner_id, lock=True)
            if run["status"] != "running":
                return
            timestamp = now()
            db.execute("UPDATE runs SET status='completed', updated_at=%s, job_ids=%s WHERE id=%s",
                       (timestamp, encode(job_ids), run_id))
            message = self.message(db.execute("""
                UPDATE messages SET content=%s, status='completed', tool_calls=%s WHERE id=%s RETURNING *
            """, (content, encode(tool_calls), run["assistant_message_id"])).fetchone())
            db.execute("INSERT INTO events (run_id, type, data) VALUES (%s, %s, %s)", (run_id, "done", encode({
                "message": message, "job_ids": job_ids, "usage": usage,
            })))
            db.execute("UPDATE conversations SET updated_at=%s WHERE id=%s", (timestamp, run["conversation_id"]))
            db.execute("""
                INSERT INTO agent_state (run_id, checkpoint, transcript, usage) VALUES (%s, NULL, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET checkpoint=NULL, transcript=excluded.transcript, usage=excluded.usage
            """, (run_id, encode(transcript) if transcript is not None else None,
                  encode(usage) if usage is not None else None))
            if usage is not None:
                record_model_usage(db, owner_id, run_id, usage)

    def fail_run(self, run_id: str, code: str, message: str):
        owner_id = self._owner_id()
        with self._db() as db:
            run = self._run(db, run_id, owner_id, lock=True)
            if run["status"] != "running":
                return
            db.execute("UPDATE runs SET status='failed', updated_at=%s WHERE id=%s", (now(), run_id))
            db.execute("""
                UPDATE messages SET status='failed', content=CASE WHEN content='' THEN %s ELSE content END WHERE id=%s
            """, (message, run["assistant_message_id"]))
            db.execute("INSERT INTO events (run_id, type, data) VALUES (%s, %s, %s)",
                       (run_id, "error", encode({"code": code, "message": message})))

    def recover_interrupted(self):
        with self._db() as db:
            runs = db.execute("SELECT id, owner_id FROM runs WHERE status='running' ORDER BY created_at, id").fetchall()
        resumable = []
        for row in runs:
            run_id, owner_id = row["id"], row["owner_id"]
            with self.as_user(owner_id):
                checkpoint = self.checkpoint(run_id)
                if checkpoint:
                    resumable.append((owner_id, self.get_run(run_id), checkpoint))
                else:
                    self.fail_run(run_id, "run_interrupted", "服务已重启，上次分析已中断。可以重新提交分析。")
        return resumable
