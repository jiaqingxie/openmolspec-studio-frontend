"""Daily credit operations shared by the application and chemistry transactions."""
from __future__ import annotations

import os

from psycopg.types.json import Jsonb

CREDIT_DAY = "(now() AT TIME ZONE 'Asia/Shanghai')::date"


class InsufficientCredits(Exception):
    pass


def daily_allowance() -> int:
    return int(os.getenv("OPENMOLSPEC_FREE_CREDITS", "20"))


def rule_version() -> str:
    return os.getenv("OPENMOLSPEC_CREDIT_RULE_VERSION", "v2")


def upgrade_daily_credits(conn):
    # Either service can start first during a deployment. Chemistry recovery needs
    # this schema even when the application has not started yet.
    conn.execute("SELECT pg_advisory_xact_lock(109202601)")
    if conn.execute(
        "SELECT to_regclass('molspec_app.account_schema_versions') IS NOT NULL AS ready"
    ).fetchone()["ready"]:
        version = conn.execute(
            "SELECT max(version) AS version FROM molspec_app.account_schema_versions"
        ).fetchone()["version"]
        if version == 1:
            conn.execute("""
                ALTER TABLE molspec_app.credit_balances ADD COLUMN credit_day DATE;
                ALTER TABLE molspec_app.credit_entries ADD COLUMN credit_day DATE,
                    ADD COLUMN execution_started BOOLEAN NOT NULL DEFAULT FALSE;
                INSERT INTO molspec_app.account_schema_versions(version) VALUES (2);
            """)


def refresh_daily_balance(conn, owner_id: str, allowance: int):
    # The balance row serializes refreshes and reservations for one account.
    refreshed = conn.execute(
        f"""UPDATE molspec_app.credit_balances
            SET available=%s, reserved=0, credit_day={CREDIT_DAY}
            WHERE user_id=%s AND (credit_day IS NULL OR credit_day < {CREDIT_DAY})
            RETURNING credit_day""",
        (allowance, owner_id),
    ).fetchone()
    if refreshed is not None:
        day = refreshed["credit_day"]
        conn.execute(
            """INSERT INTO molspec_app.credit_entries
                   (user_id, task_id, operation, source, amount, status, rule_version, credit_day)
               VALUES (%s, %s, 'daily_credit_grant', 'system', %s, 'granted', %s, %s)""",
            (owner_id, f"daily_grant:{day}", allowance, rule_version(), day),
        )


def reserve(conn, owner_id: str, job_id: str, operation: str, source: str):
    refresh_daily_balance(conn, owner_id, daily_allowance())
    row = conn.execute(
        """UPDATE molspec_app.credit_balances SET available=available-1, reserved=reserved+1
           WHERE user_id=%s AND available >= 1 RETURNING credit_day""",
        (owner_id,),
    ).fetchone()
    if row is None:
        raise InsufficientCredits
    conn.execute(
        """INSERT INTO molspec_app.credit_entries
               (user_id, task_id, operation, source, amount, status, rule_version, credit_day)
           VALUES (%s, %s, %s, %s, -1, 'reserved', %s, %s)""",
        (owner_id, job_id, operation, source, rule_version(), row["credit_day"]),
    )


def start_execution(conn, owner_id: str, job_id: str):
    conn.execute(
        """UPDATE molspec_app.credit_entries SET execution_started=true
           WHERE user_id=%s AND task_id=%s AND status='reserved'""",
        (owner_id, job_id),
    )


def finish(conn, owner_id: str, job_id: str, *, succeeded: bool, duration_ms: int | None,
           model_unavailable: bool = False):
    row = conn.execute(
        """UPDATE molspec_app.credit_entries
           SET status=CASE WHEN %s OR (execution_started AND NOT %s) THEN 'settled' ELSE 'released' END,
               duration_ms=%s, finished_at=now()
           WHERE user_id=%s AND task_id=%s AND status='reserved'
           RETURNING amount, status, credit_day""",
        (succeeded, model_unavailable, duration_ms, owner_id, job_id),
    ).fetchone()
    if row is not None:
        amount = -row["amount"]
        conn.execute(
            """UPDATE molspec_app.credit_balances SET reserved=reserved-%s, available=available+%s
               WHERE user_id=%s AND credit_day IS NOT DISTINCT FROM %s""",
            (amount, amount if row["status"] == "released" else 0, owner_id, row["credit_day"]),
        )


def record_model_usage(conn, owner_id: str, run_id: str, usage: dict):
    conn.execute(
        """INSERT INTO molspec_app.credit_entries(user_id, task_id, operation, source, amount, status, rule_version, usage)
           VALUES (%s, %s, 'agent_reply', 'web', 0, 'recorded', %s, %s)
           ON CONFLICT (user_id, task_id) DO UPDATE SET usage=excluded.usage""",
        (owner_id, run_id, rule_version(), Jsonb(usage)),
    )
