from __future__ import annotations

import json
import math
from typing import Any
from uuid import uuid4

import numpy as np
import psycopg
from psycopg.rows import dict_row

from services.credits import InsufficientCredits, finish, reserve, start_execution, upgrade_daily_credits

from .errors import ChemistryError


def json_value(value: Any) -> Any:
    """Freeze numerical results as strict JSON, rejecting nonfinite predictions."""
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Calculation returned a nonfinite numerical value.")
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"Calculation returned an unsupported value: {type(value).__name__}.")


def dumps(value: Any) -> str:
    return json.dumps(json_value(value), ensure_ascii=False, allow_nan=False)


class ChemistryStore:
    """Persist owned scientific inputs, jobs and their matching credit transitions."""

    def __init__(self, database_url: str):
        self.connection = psycopg.connect(database_url, autocommit=True, row_factory=dict_row, connect_timeout=5)
        try:
            self._initialize()
            with self.connection.transaction():
                upgrade_daily_credits(self.connection)
        except BaseException:
            self.connection.close()
            raise

    def _initialize(self) -> None:
        with self.connection.transaction():
            self.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended('molspec_chemistry.schema', 0))")
            self.connection.execute("CREATE SCHEMA IF NOT EXISTS molspec_chemistry")
            self.connection.execute("SET search_path TO molspec_chemistry")
            self.connection.execute("SET TIME ZONE 'UTC'")
            self.connection.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version integer PRIMARY KEY
                )
            """)
            version = self.connection.execute("SELECT max(version) AS version FROM schema_version").fetchone()["version"]
            if version == 1:
                return
            if version is not None:
                raise RuntimeError(f"Unsupported chemistry schema version: {version}")
            self.connection.execute("""
                CREATE TABLE molecules (
                    id text PRIMARY KEY, owner_id text NOT NULL, payload text NOT NULL
                );
                CREATE TABLE spectra (
                    id text PRIMARY KEY, owner_id text NOT NULL, payload text NOT NULL
                );
                CREATE TABLE jobs (
                    id text PRIMARY KEY, owner_id text NOT NULL,
                    operation text NOT NULL,
                    status text NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
                    inputs text NOT NULL, created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
                    result text, error text,
                    UNIQUE (owner_id, id)
                );
                CREATE INDEX jobs_pending ON jobs(status, created_at, id);
                CREATE INDEX jobs_owner_created ON jobs(owner_id, created_at DESC, id);
                CREATE TABLE job_requests (
                    owner_id text NOT NULL, request_id text NOT NULL, fingerprint text NOT NULL, job_id text NOT NULL,
                    PRIMARY KEY (owner_id, request_id),
                    FOREIGN KEY (owner_id, job_id) REFERENCES jobs(owner_id, id)
                );
                INSERT INTO schema_version(version) VALUES (1);
            """)

    def close(self) -> None:
        self.connection.close()

    def _save_input(self, table: str, owner_id: str, payload: dict) -> dict:
        value = {**payload, "id": uuid4().hex}
        encoded = dumps(value)
        self.connection.execute(
            f"INSERT INTO {table}(id, owner_id, payload) VALUES (%s, %s, %s)",
            (value["id"], owner_id, encoded),
        )
        return json.loads(encoded)

    def _get_input(self, table: str, owner_id: str, identifier: str) -> dict | None:
        row = self.connection.execute(
            f"SELECT payload FROM {table} WHERE owner_id=%s AND id=%s", (owner_id, identifier),
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def save_molecule(self, owner_id: str, payload: dict) -> dict:
        return self._save_input("molecules", owner_id, payload)

    def get_molecule(self, owner_id: str, identifier: str) -> dict | None:
        return self._get_input("molecules", owner_id, identifier)

    def save_spectrum(self, owner_id: str, payload: dict) -> dict:
        return self._save_input("spectra", owner_id, payload)

    def get_spectrum(self, owner_id: str, identifier: str) -> dict | None:
        return self._get_input("spectra", owner_id, identifier)

    def replay_job(self, owner_id: str, request_id: str, fingerprint: str) -> dict | None:
        row = self.connection.execute(
            "SELECT jobs.*, job_requests.fingerprint FROM job_requests "
            "JOIN jobs ON jobs.owner_id=job_requests.owner_id AND jobs.id=job_requests.job_id "
            "WHERE job_requests.request_id=%s AND job_requests.owner_id=%s",
            (request_id, owner_id),
        ).fetchone()
        if row is None:
            return None
        if row.pop("fingerprint") != fingerprint:
            raise ChemistryError("request_id_conflict", "The request ID already belongs to a different calculation.", 409)
        return self._job(row)

    def create_job(self, owner_id: str, operation: str, inputs: dict, *, source: str,
                   request_id: str | None = None, fingerprint: str | None = None,
                   new_molecule: dict | None = None) -> dict:
        identifier = uuid4().hex
        with self.connection.transaction():
            if request_id is not None:
                lock_key = dumps(["molspec_chemistry.request", owner_id, request_id])
                self.connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
                existing = self.replay_job(owner_id, request_id, fingerprint)
                if existing is not None:
                    return existing
            try:
                reserve(self.connection, owner_id, identifier, operation, source)
            except InsufficientCredits as error:
                raise ChemistryError("insufficient_credits", "Not enough credits for this calculation.", 402) from error
            if new_molecule is not None:
                molecule = self.save_molecule(owner_id, new_molecule)
                inputs = {
                    **inputs, "molecule_id": molecule["id"],
                    "molecule": {key: value for key, value in molecule.items() if key != "svg"},
                }
            row = self.connection.execute(
                "INSERT INTO jobs(id, owner_id, operation, status, inputs, created_at, updated_at) "
                "VALUES (%s, %s, %s, 'queued', %s, now(), now()) RETURNING *",
                (identifier, owner_id, operation, dumps(inputs)),
            ).fetchone()
            if request_id is not None:
                self.connection.execute(
                    "INSERT INTO job_requests(owner_id, request_id, fingerprint, job_id) VALUES (%s, %s, %s, %s)",
                    (owner_id, request_id, fingerprint, identifier),
                )
            return self._job(row)

    @staticmethod
    def _job(row: dict) -> dict:
        result = dict(row)
        del result["owner_id"]
        for field in ("inputs", "result", "error"):
            result[field] = json.loads(result[field]) if result[field] is not None else None
        for field in ("created_at", "updated_at"):
            result[field] = result[field].isoformat()
        return result

    def get_job(self, owner_id: str, identifier: str) -> dict | None:
        row = self.connection.execute(
            "SELECT * FROM jobs WHERE owner_id=%s AND id=%s", (owner_id, identifier),
        ).fetchone()
        return self._job(row) if row else None

    def list_jobs(self, owner_id: str) -> list[dict]:
        rows = self.connection.execute(
            "SELECT * FROM jobs WHERE owner_id=%s ORDER BY created_at DESC, id", (owner_id,),
        )
        return [self._job(row) for row in rows]

    def claim_next(self) -> tuple[str, dict] | None:
        row = self.connection.execute("""
            WITH pending AS (
                SELECT id FROM jobs WHERE status='queued' ORDER BY created_at, id
                LIMIT 1 FOR UPDATE SKIP LOCKED
            )
            UPDATE jobs SET status='running', updated_at=now()
            FROM pending WHERE jobs.id=pending.id RETURNING jobs.*
        """).fetchone()
        return (row["owner_id"], self._job(row)) if row else None

    def cancel_job(self, owner_id: str, identifier: str) -> dict:
        with self.connection.transaction():
            row = self.connection.execute(
                "SELECT * FROM jobs WHERE owner_id=%s AND id=%s FOR UPDATE", (owner_id, identifier),
            ).fetchone()
            if row is None:
                raise ChemistryError("not_found", "Calculation was not found.", 404)
            if row["status"] == "running":
                raise ChemistryError("job_running", "Running native model calls cannot be safely interrupted. The calculation remains running.", 409)
            if row["status"] == "queued":
                row = self.connection.execute(
                    "UPDATE jobs SET status='cancelled', updated_at=now() "
                    "WHERE owner_id=%s AND id=%s RETURNING *", (owner_id, identifier),
                ).fetchone()
                finish(self.connection, owner_id, identifier, succeeded=False, duration_ms=None)
            return self._job(row)

    def start_execution(self, owner_id: str, identifier: str) -> None:
        start_execution(self.connection, owner_id, identifier)

    def finish_job(self, owner_id: str, identifier: str, *, result: dict | None = None,
                   error: dict | None = None, spectra: dict[str, dict] | None = None,
                   duration_ms: int | None = None) -> None:
        succeeded = error is None
        with self.connection.transaction():
            row = self.connection.execute(
                "SELECT status FROM jobs WHERE owner_id=%s AND id=%s FOR UPDATE", (owner_id, identifier),
            ).fetchone()
            if row is None or row["status"] != "running":
                return
            if spectra is not None:
                result = dict(result)
                for modality, spectrum in spectra.items():
                    saved = self.save_spectrum(owner_id, spectrum)
                    result[f"{modality}_id"] = saved["id"]
            self.connection.execute(
                "UPDATE jobs SET status=%s, updated_at=now(), result=%s, error=%s WHERE owner_id=%s AND id=%s",
                ("succeeded" if succeeded else "failed", dumps(result) if result is not None else None,
                 dumps(error) if error is not None else None, owner_id, identifier),
            )
            finish(self.connection, owner_id, identifier, succeeded=succeeded, duration_ms=duration_ms,
                   model_unavailable=error is not None and error.get("code") == "model_unavailable")

    def recover_interrupted(self) -> None:
        error = {"code": "interrupted",
                 "message": "Calculation was interrupted by a service restart; submit a new job to retry."}
        with self.connection.transaction():
            rows = self.connection.execute(
                "UPDATE jobs SET status='failed', updated_at=now(), result=NULL, error=%s "
                "WHERE status='running' RETURNING id, owner_id", (dumps(error),),
            ).fetchall()
            for row in rows:
                finish(self.connection, row["owner_id"], row["id"], succeeded=False, duration_ms=None)
