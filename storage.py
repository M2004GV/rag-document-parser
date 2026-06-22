# storage.py
"""Persistência local em SQLite.

Concentra todo o acesso a banco da aplicação:
- usuários e autenticação simples (item 14)
- histórico de transações por usuário (item 2)
- cache de extração por hash do PDF (item 10)
- orçamentos por categoria (item 7)
- regras de categorização customizadas (item 6)

O banco fica em ``./data/app.db`` por padrão (configurável via ``APP_DB_PATH``).
"""
import os
import sqlite3
import json
import hashlib
import secrets
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

import pandas as pd

DB_PATH = os.environ.get("APP_DB_PATH", os.path.join("data", "app.db"))

GUEST_USERNAME = "guest"

TRANSACTION_COLUMNS = [
    "arquivo",
    "mes_referencia",
    "data",
    "descricao",
    "categoria",
    "valor",
    "parcela",
]


# ---------------------------------------------------------------------------
# Conexão / schema
# ---------------------------------------------------------------------------

@contextmanager
def _connect():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Cria as tabelas se ainda não existirem e garante o usuário convidado."""
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt          TEXT NOT NULL,
                created_at    TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS transactions (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id        INTEGER NOT NULL,
                arquivo        TEXT,
                mes_referencia TEXT,
                data           TEXT,
                descricao      TEXT,
                categoria      TEXT,
                valor          REAL,
                parcela        TEXT,
                created_at     TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS pdf_cache (
                file_hash   TEXT NOT NULL,
                kind        TEXT NOT NULL,
                payload     TEXT NOT NULL,
                created_at  TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (file_hash, kind)
            );

            CREATE TABLE IF NOT EXISTS budgets (
                user_id   INTEGER NOT NULL,
                categoria TEXT NOT NULL,
                limite    REAL NOT NULL,
                PRIMARY KEY (user_id, categoria)
            );

            CREATE TABLE IF NOT EXISTS category_rules (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                pattern   TEXT NOT NULL,
                categoria TEXT NOT NULL
            );
            """
        )
    # Garante idempotência das transações: limpa duplicatas herdadas e cria o
    # índice único que impede novas inserções repetidas (ver save_transactions).
    _migrate_dedupe_transactions()
    # Usuário convidado sempre disponível (senha aleatória, não usada para login).
    if get_user_id(GUEST_USERNAME) is None:
        create_user(GUEST_USERNAME, secrets.token_hex(16))


# Chave natural que identifica uma transação repetida (mesmo arquivo reimportado).
_TX_NATURAL_KEY = (
    "user_id", "arquivo", "mes_referencia", "data", "descricao", "valor", "parcela"
)


def _migrate_dedupe_transactions() -> None:
    """Remove transações duplicadas pré-existentes e cria o índice único.

    Bancos criados antes da correção podem conter a mesma transação várias
    vezes (reimportação do mesmo arquivo). Mantemos a linha de menor ``id`` de
    cada grupo e só então criamos o índice único — caso contrário a criação
    falharia sobre dados já duplicados.
    """
    key = ", ".join(_TX_NATURAL_KEY)
    with _connect() as conn:
        conn.execute(
            f"""DELETE FROM transactions
                WHERE id NOT IN (
                    SELECT MIN(id) FROM transactions GROUP BY {key}
                )"""
        )
        conn.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_natural ON transactions ({key})"
        )


# ---------------------------------------------------------------------------
# Autenticação (item 14)
# ---------------------------------------------------------------------------

def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), 200_000
    ).hex()


def create_user(username: str, password: str) -> int:
    """Cria um usuário. Levanta ValueError se o nome já existir."""
    username = username.strip().lower()
    if not username or not password:
        raise ValueError("Usuário e senha são obrigatórios.")
    salt = secrets.token_hex(16)
    pwd_hash = _hash_password(password, salt)
    try:
        with _connect() as conn:
            cur = conn.execute(
                "INSERT INTO users (username, password_hash, salt) VALUES (?, ?, ?)",
                (username, pwd_hash, salt),
            )
            return cur.lastrowid
    except sqlite3.IntegrityError as e:
        raise ValueError(f"O usuário '{username}' já existe.") from e


def verify_user(username: str, password: str) -> Optional[int]:
    """Retorna o id do usuário se as credenciais conferem, senão None."""
    username = username.strip().lower()
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, password_hash, salt FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if row is None:
        return None
    if secrets.compare_digest(row["password_hash"], _hash_password(password, row["salt"])):
        return row["id"]
    return None


def get_user_id(username: str) -> Optional[int]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username.strip().lower(),)
        ).fetchone()
    return row["id"] if row else None


def guest_user_id() -> int:
    uid = get_user_id(GUEST_USERNAME)
    if uid is None:
        uid = create_user(GUEST_USERNAME, secrets.token_hex(16))
    return uid


# ---------------------------------------------------------------------------
# Transações (item 2)
# ---------------------------------------------------------------------------

def save_transactions(user_id: int, df: pd.DataFrame) -> int:
    """Acrescenta as transações novas ao histórico do usuário.

    A inserção é idempotente: reimportar o mesmo arquivo (mesma transação na
    chave natural) é ignorado em vez de duplicado. Retorna a quantidade de
    transações efetivamente inseridas (novas), não o total enviado.
    """
    if df is None or df.empty:
        return 0
    rows = [
        (
            user_id,
            r.get("arquivo", ""),
            r.get("mes_referencia", ""),
            r.get("data", ""),
            r.get("descricao", ""),
            r.get("categoria", "Outros"),
            float(r.get("valor", 0) or 0),
            r.get("parcela", ""),
        )
        for r in df.to_dict("records")
    ]
    with _connect() as conn:
        before = conn.total_changes
        conn.executemany(
            """INSERT OR IGNORE INTO transactions
               (user_id, arquivo, mes_referencia, data, descricao, categoria, valor, parcela)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            rows,
        )
        return conn.total_changes - before


def load_transactions(user_id: int) -> pd.DataFrame:
    """Carrega todo o histórico de transações do usuário."""
    with _connect() as conn:
        rows = conn.execute(
            f"""SELECT {", ".join(TRANSACTION_COLUMNS)}
                FROM transactions WHERE user_id = ? ORDER BY id""",
            (user_id,),
        ).fetchall()
    if not rows:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    return pd.DataFrame([dict(r) for r in rows], columns=TRANSACTION_COLUMNS)


def clear_transactions(user_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))


# ---------------------------------------------------------------------------
# Cache de extração por hash do PDF (item 10)
# ---------------------------------------------------------------------------

def file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cache_get(fhash: str, kind: str) -> Optional[Any]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT payload FROM pdf_cache WHERE file_hash = ? AND kind = ?",
            (fhash, kind),
        ).fetchone()
    if row is None:
        return None
    try:
        return json.loads(row["payload"])
    except json.JSONDecodeError:
        return None


def cache_set(fhash: str, kind: str, payload: Any) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO pdf_cache (file_hash, kind, payload) VALUES (?, ?, ?)",
            (fhash, kind, json.dumps(payload, ensure_ascii=False)),
        )


# ---------------------------------------------------------------------------
# Orçamentos por categoria (item 7)
# ---------------------------------------------------------------------------

def set_budget(user_id: int, categoria: str, limite: float) -> None:
    with _connect() as conn:
        if limite and limite > 0:
            conn.execute(
                "INSERT OR REPLACE INTO budgets (user_id, categoria, limite) VALUES (?, ?, ?)",
                (user_id, categoria, float(limite)),
            )
        else:
            conn.execute(
                "DELETE FROM budgets WHERE user_id = ? AND categoria = ?",
                (user_id, categoria),
            )


def get_budgets(user_id: int) -> Dict[str, float]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT categoria, limite FROM budgets WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {r["categoria"]: r["limite"] for r in rows}


# ---------------------------------------------------------------------------
# Regras de categorização customizadas (item 6)
# ---------------------------------------------------------------------------

def add_category_rule(user_id: int, pattern: str, categoria: str) -> None:
    pattern = (pattern or "").strip()
    if not pattern or not categoria:
        return
    with _connect() as conn:
        conn.execute(
            "INSERT INTO category_rules (user_id, pattern, categoria) VALUES (?, ?, ?)",
            (user_id, pattern, categoria),
        )


def get_category_rules(user_id: int) -> List[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, pattern, categoria FROM category_rules WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_category_rule(rule_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM category_rules WHERE id = ?", (rule_id,))
