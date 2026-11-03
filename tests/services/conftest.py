import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from services.api.accounts import Accounts


@pytest.fixture
def postgres_dsn():
    admin_dsn = os.getenv("OPENMOLSPEC_TEST_DATABASE_URL")
    if not admin_dsn:
        pytest.skip("Set OPENMOLSPEC_TEST_DATABASE_URL for isolated PostgreSQL integration tests")
    database = f"molspec_test_{uuid4().hex}"
    params = conninfo_to_dict(admin_dsn)
    params["dbname"] = database
    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        name = sql.Identifier(database)
        admin.execute(sql.SQL("CREATE DATABASE {}").format(name))
        try:
            yield make_conninfo(**params)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(name))


@pytest.fixture
def account_owner(postgres_dsn):
    accounts = Accounts(postgres_dsn)
    accounts.initialize()
    return accounts.login_mock("researcher")[1]["id"]


@pytest.fixture
def second_account_owner(postgres_dsn):
    accounts = Accounts(postgres_dsn)
    accounts.initialize()
    return accounts.login_mock("analyst")[1]["id"]
