from concurrent.futures import ThreadPoolExecutor

import pytest

from services.api.accounts import Accounts
from services.api.store import Conflict, Store


def test_store_requires_verified_user_scope():
    assert callable(Store.initialize)
    store = Store("postgresql://unused")
    with pytest.raises(RuntimeError, match="owner"):
        store.list_conversations()


def test_postgres_run_is_ordered_and_serializes_idempotent_submissions(postgres_dsn, account_owner):
    store = Store(postgres_dsn)
    store.initialize()
    with store.as_user(account_owner):
        conversation_id = store.create_conversation()["id"]

    def submit():
        with store.as_user(account_owner):
            return store.begin_run(conversation_id, "检查乙醇", [], {}, request_id="retry")

    with ThreadPoolExecutor(max_workers=2) as workers:
        first, second = workers.map(lambda _: submit(), range(2))
    run_id = first[0]["id"]
    assert second[0]["id"] == run_id
    assert sum(user is not None for _, user, _ in (first, second)) == 1

    with store.as_user(account_owner):
        with pytest.raises(Conflict):
            store.begin_run(conversation_id, "另一个请求", [], {})
        store.add_event(run_id, "delta", {"content": "乙醇"})
        store.finish_run(run_id, "乙醇", [], [], usage={"input_tokens": 5})
        store.finish_run(run_id, "重复完成", [], [])

    restarted = Store(postgres_dsn)
    restarted.initialize()
    with restarted.as_user(account_owner):
        conversation = restarted.get_conversation(conversation_id)
        assert [message["content"] for message in conversation["messages"]] == ["检查乙醇", "乙醇"]
        assert conversation["active_run_id"] is None
        assert restarted.get_run(run_id)["usage"] == {"input_tokens": 5}
        events = restarted.events(run_id)
        assert [event["type"] for event in events] == ["run", "delta", "done"]
        assert restarted.events(run_id, after=events[0]["id"]) == events[1:]

    with Accounts(postgres_dsn).connect() as db:
        usage = db.execute("""
            SELECT amount, status, usage FROM molspec_app.credit_entries WHERE user_id=%s AND task_id=%s
        """, (account_owner, run_id)).fetchall()
    assert usage == [{"amount": 0, "status": "recorded", "usage": {"input_tokens": 5}}]


def test_store_enforces_owner_on_direct_and_derived_access(postgres_dsn, account_owner, second_account_owner):
    store = Store(postgres_dsn)
    store.initialize()
    with store.as_user(account_owner):
        conversation = store.create_conversation()
        attachment = store.save_attachment({"kind": "document"})
        run, _, _ = store.begin_run(conversation["id"], "分析", [attachment], {}, request_id="shared")
        store.save_checkpoint(run["id"], {"state": "ready"})

    with store.as_user(second_account_owner):
        assert store.list_conversations() == []
        other = store.create_conversation()
        for operation in (
            lambda: store.get_conversation(conversation["id"]),
            lambda: store.delete_conversation(conversation["id"]),
            lambda: store.get_run(run["id"]),
            lambda: store.events(run["id"]),
            lambda: store.add_event(run["id"], "delta", {"content": "changed"}),
            lambda: store.checkpoint(run["id"]),
            lambda: store.save_checkpoint(run["id"], None),
            lambda: store.finish_run(run["id"], "changed", [], []),
            lambda: store.fail_run(run["id"], "invalid", "changed"),
            lambda: store.transcripts(conversation["id"]),
            lambda: store.get_attachments([attachment["id"]]),
            lambda: store.begin_run(conversation["id"], "分析", [], {}, request_id="shared"),
            lambda: store.begin_run(other["id"], "分析", [attachment], {}),
        ):
            with pytest.raises(KeyError):
                operation()
        other_run, _, _ = store.begin_run(other["id"], "分析", [], {}, request_id="shared")
        assert other_run["id"] != run["id"]

    assert store.recover_interrupted() == [(account_owner, run, {"state": "ready"})]
    with store.as_user(second_account_owner):
        assert store.get_run(other_run["id"])["status"] == "failed"
