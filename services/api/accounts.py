from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
from psycopg.rows import dict_row

from services.credits import daily_allowance, refresh_daily_balance, upgrade_daily_credits

from .config import DEVELOPMENT_IDENTITIES

COOKIE = "molspec_session"
TOKEN_COLUMNS = "id, name, created_at, expires_at, last_used_at, revoked_at"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class Accounts:
    def __init__(self, dsn: str, *, free_credits: int | None = None, session_hours: int = 24):
        self.dsn = dsn
        self.free_credits = daily_allowance() if free_credits is None else free_credits
        self.session_hours = session_hours
        if not 0 <= self.free_credits <= 10**9 or not 0 < session_hours <= 24 * 30:
            raise ValueError("Invalid credit grant or session duration")

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row, connect_timeout=5)

    def initialize(self):
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(109202601)")
            conn.execute("CREATE SCHEMA IF NOT EXISTS molspec_app")
            conn.execute("""CREATE TABLE IF NOT EXISTS molspec_app.account_schema_versions (
                version INTEGER PRIMARY KEY, installed_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
            version = conn.execute("SELECT max(version) AS version FROM molspec_app.account_schema_versions").fetchone()["version"]
            if version == 2:
                return
            if version not in {None, 1}:
                raise RuntimeError(f"Unsupported account schema version: {version}")
            if version is None:
                conn.execute("""
                    CREATE TABLE molspec_app.users (
                        id TEXT PRIMARY KEY, nickname TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    );
                    CREATE TABLE molspec_app.identities (
                        provider TEXT NOT NULL, subject TEXT NOT NULL,
                        user_id TEXT NOT NULL REFERENCES molspec_app.users(id),
                        PRIMARY KEY (provider, subject)
                    );
                    CREATE TABLE molspec_app.sessions (
                        secret_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES molspec_app.users(id),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL
                    );
                    CREATE TABLE molspec_app.access_tokens (
                        id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES molspec_app.users(id),
                        name TEXT NOT NULL, secret_hash TEXT NOT NULL UNIQUE, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        expires_at TIMESTAMPTZ NOT NULL, last_used_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ
                    );
                    CREATE INDEX access_tokens_user ON molspec_app.access_tokens(user_id, created_at DESC);
                    CREATE TABLE molspec_app.credit_balances (
                        user_id TEXT PRIMARY KEY REFERENCES molspec_app.users(id),
                        available BIGINT NOT NULL CHECK (available >= 0), reserved BIGINT NOT NULL CHECK (reserved >= 0)
                    );
                    CREATE TABLE molspec_app.credit_entries (
                        user_id TEXT NOT NULL REFERENCES molspec_app.users(id), task_id TEXT NOT NULL,
                        operation TEXT NOT NULL, source TEXT NOT NULL, amount BIGINT NOT NULL,
                        status TEXT NOT NULL CHECK (status IN ('granted','reserved','settled','released','recorded')),
                        rule_version TEXT NOT NULL, usage JSONB, duration_ms BIGINT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), finished_at TIMESTAMPTZ,
                        PRIMARY KEY (user_id, task_id)
                    );
                    CREATE INDEX credit_entries_user_time ON molspec_app.credit_entries(user_id, created_at DESC, task_id);
                    INSERT INTO molspec_app.account_schema_versions(version) VALUES (1);
                """)
            upgrade_daily_credits(conn)

    def login_mock(self, identity: str):
        return self.login_verified_identity("development-mock", identity, DEVELOPMENT_IDENTITIES[identity])

    def login_verified_identity(self, provider: str, subject: str, nickname: str):
        """Session entry point after a provider has verified its subject."""
        secret = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"{provider}/{subject}",))
            user = conn.execute(
                """SELECT u.id, u.nickname FROM molspec_app.identities i JOIN molspec_app.users u ON i.user_id=u.id
                   WHERE i.provider=%s AND i.subject=%s""", (provider, subject),
            ).fetchone()
            if user is None:
                user = {"id": secrets.token_hex(16), "nickname": nickname}
                conn.execute("INSERT INTO molspec_app.users(id,nickname) VALUES (%s,%s)", (user["id"], nickname))
                conn.execute(
                    "INSERT INTO molspec_app.identities(provider,subject,user_id) VALUES (%s,%s,%s)",
                    (provider, subject, user["id"]),
                )
                conn.execute(
                    "INSERT INTO molspec_app.credit_balances(user_id,available,reserved) VALUES (%s,0,0)",
                    (user["id"],),
                )
            refresh_daily_balance(conn, user["id"], self.free_credits)
            conn.execute(
                "INSERT INTO molspec_app.sessions(secret_hash,user_id,expires_at) VALUES (%s,%s,%s)",
                (digest(secret), user["id"], datetime.now(timezone.utc) + timedelta(hours=self.session_hours)),
            )
        return secret, user

    def session_user(self, secret: str | None):
        if not secret:
            return None
        with self.connect() as conn:
            return conn.execute(
                """SELECT u.id,u.nickname FROM molspec_app.sessions s JOIN molspec_app.users u ON s.user_id=u.id
                   WHERE s.secret_hash=%s AND s.expires_at > now()""", (digest(secret),),
            ).fetchone()

    def logout(self, secret: str | None):
        if secret:
            with self.connect() as conn:
                conn.execute("DELETE FROM molspec_app.sessions WHERE secret_hash=%s", (digest(secret),))

    def tokens(self, user_id: str):
        with self.connect() as conn:
            return conn.execute(
                f"SELECT {TOKEN_COLUMNS} FROM molspec_app.access_tokens WHERE user_id=%s ORDER BY created_at DESC,id",
                (user_id,),
            ).fetchall()

    def create_token(self, user_id: str, name: str, expires_in_days: int):
        secret = "molspec_" + secrets.token_urlsafe(32)
        with self.connect() as conn:
            record = conn.execute(
                f"""INSERT INTO molspec_app.access_tokens(id,user_id,name,secret_hash,expires_at)
                    VALUES (%s,%s,%s,%s,%s) RETURNING {TOKEN_COLUMNS}""",
                (secrets.token_hex(16), user_id, name, digest(secret),
                 datetime.now(timezone.utc) + timedelta(days=expires_in_days)),
            ).fetchone()
        return {"token": secret, "record": record}

    def revoke_token(self, user_id: str, token_id: str):
        with self.connect() as conn:
            return conn.execute(
                """UPDATE molspec_app.access_tokens SET revoked_at=COALESCE(revoked_at, now())
                   WHERE user_id=%s AND id=%s RETURNING id""", (user_id, token_id),
            ).fetchone() is not None

    def token_user(self, secret: str):
        if not secret.startswith("molspec_"):
            return None
        with self.connect() as conn:
            row = conn.execute(
                """UPDATE molspec_app.access_tokens SET last_used_at=now()
                   WHERE secret_hash=%s AND expires_at > now() AND revoked_at IS NULL RETURNING user_id""",
                (digest(secret),),
            ).fetchone()
        return row["user_id"] if row else None

    def balance(self, user_id: str):
        with self.connect() as conn:
            refresh_daily_balance(conn, user_id, self.free_credits)
            return conn.execute(
                "SELECT available,reserved FROM molspec_app.credit_balances WHERE user_id=%s", (user_id,),
            ).fetchone()

    def usage(self, user_id: str):
        with self.connect() as conn:
            refresh_daily_balance(conn, user_id, self.free_credits)
            balance = conn.execute(
                "SELECT available,reserved FROM molspec_app.credit_balances WHERE user_id=%s FOR SHARE", (user_id,),
            ).fetchone()
            entries = conn.execute(
                """SELECT task_id, operation, source,
                          CASE WHEN status='released' THEN 0 ELSE amount END AS amount,
                          status, rule_version, usage, duration_ms, created_at, finished_at
                   FROM molspec_app.credit_entries WHERE user_id=%s
                   ORDER BY created_at DESC,task_id LIMIT 200""", (user_id,),
            ).fetchall()
        return {**balance, "entries": entries}
