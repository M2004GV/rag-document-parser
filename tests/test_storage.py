import importlib

import pandas as pd
import pytest


@pytest.fixture()
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_DB_PATH", str(tmp_path / "test.db"))
    import storage as storage_module
    importlib.reload(storage_module)
    storage_module.init_db()
    return storage_module


def test_create_and_verify_user(storage):
    uid = storage.create_user("alice", "senha123")
    assert storage.verify_user("alice", "senha123") == uid
    assert storage.verify_user("alice", "errada") is None


def test_duplicate_user_raises(storage):
    storage.create_user("bob", "x")
    with pytest.raises(ValueError):
        storage.create_user("bob", "y")


def test_save_and_load_transactions(storage):
    uid = storage.create_user("carol", "x")
    df = pd.DataFrame([
        {"arquivo": "f", "mes_referencia": "01/2026", "data": "05/01/2026",
         "descricao": "IFOOD", "categoria": "Alimentação", "valor": 45.9, "parcela": ""},
    ])
    assert storage.save_transactions(uid, df) == 1
    loaded = storage.load_transactions(uid)
    assert len(loaded) == 1
    assert loaded.iloc[0]["descricao"] == "IFOOD"


def test_transactions_scoped_per_user(storage):
    u1 = storage.create_user("u1", "x")
    u2 = storage.create_user("u2", "x")
    df = pd.DataFrame([{"arquivo": "f", "mes_referencia": "01/2026", "data": "",
                        "descricao": "X", "categoria": "Outros", "valor": 1.0, "parcela": ""}])
    storage.save_transactions(u1, df)
    assert len(storage.load_transactions(u1)) == 1
    assert storage.load_transactions(u2).empty


def test_cache_roundtrip(storage):
    storage.cache_set("hash1", "expense", {"transacoes": [1, 2]})
    assert storage.cache_get("hash1", "expense") == {"transacoes": [1, 2]}
    assert storage.cache_get("missing", "expense") is None


def test_budgets(storage):
    uid = storage.create_user("dora", "x")
    storage.set_budget(uid, "Alimentação", 500.0)
    assert storage.get_budgets(uid) == {"Alimentação": 500.0}
    storage.set_budget(uid, "Alimentação", 0)  # remove
    assert storage.get_budgets(uid) == {}


def test_category_rules(storage):
    uid = storage.create_user("edu", "x")
    storage.add_category_rule(uid, "ifood", "Alimentação")
    rules = storage.get_category_rules(uid)
    assert len(rules) == 1
    storage.delete_category_rule(rules[0]["id"])
    assert storage.get_category_rules(uid) == []
