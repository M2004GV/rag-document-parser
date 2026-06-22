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


def test_save_transactions_is_idempotent(storage):
    """Reimportar o mesmo arquivo não deve duplicar transações no histórico."""
    uid = storage.create_user(" frank ".strip(), "x")
    df = pd.DataFrame([
        {"arquivo": "nubank.ofx", "mes_referencia": "03/2026", "data": "10/03/2026",
         "descricao": "MERCADO", "categoria": "Supermercado", "valor": 99.9, "parcela": ""},
        {"arquivo": "nubank.ofx", "mes_referencia": "03/2026", "data": "11/03/2026",
         "descricao": "UBER", "categoria": "Transporte", "valor": 23.5, "parcela": ""},
    ])
    assert storage.save_transactions(uid, df) == 2
    # Segundo e terceiro envios do mesmo lote não inserem nada novo.
    assert storage.save_transactions(uid, df) == 0
    assert storage.save_transactions(uid, df) == 0
    assert len(storage.load_transactions(uid)) == 2


def test_migration_dedupes_legacy_rows(storage):
    """Linhas duplicadas pré-existentes são removidas ao reinicializar o banco."""
    uid = storage.create_user("grace", "x")
    row = (uid, "f.ofx", "03/2026", "10/03/2026", "X", "Outros", 10.0, "")
    # Insere a mesma transação 3x diretamente, simulando uma base poluída.
    with storage._connect() as conn:
        conn.execute("DROP INDEX IF EXISTS idx_tx_natural")
        conn.executemany(
            """INSERT INTO transactions
               (user_id, arquivo, mes_referencia, data, descricao, categoria, valor, parcela)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [row, row, row],
        )
    assert len(storage.load_transactions(uid)) == 3
    storage.init_db()  # dispara a migração de dedup
    assert len(storage.load_transactions(uid)) == 1


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
