# categories.py
"""Categorias e regras de categorização local (item 6).

Permite que o usuário defina regras simples (substring -> categoria) que são
aplicadas ANTES de cair na categoria devolvida pela LLM. Isso dá controle
determinístico e reduz erros de classificação do modelo.
"""
import re
from typing import List, Dict, Optional

import pandas as pd

# Categorias padrão (antes em expenseutil.py).
DEFAULT_CATEGORIES = [
    "Alimentação",
    "Transporte",
    "Compras",
    "Lazer",
    "Saúde",
    "Educação",
    "Serviços",
    "Moradia",
    "Viagem",
    "Streaming",
    "Supermercado",
    "Outros",
]

# Regras embutidas de fallback — estabelecimentos muito comuns no Brasil.
BUILTIN_RULES: List[Dict[str, str]] = [
    {"pattern": "ifood", "categoria": "Alimentação"},
    {"pattern": "uber eats", "categoria": "Alimentação"},
    {"pattern": "rappi", "categoria": "Alimentação"},
    {"pattern": "uber", "categoria": "Transporte"},
    {"pattern": "99app", "categoria": "Transporte"},
    {"pattern": "99 ", "categoria": "Transporte"},
    {"pattern": "posto", "categoria": "Transporte"},
    {"pattern": "netflix", "categoria": "Streaming"},
    {"pattern": "spotify", "categoria": "Streaming"},
    {"pattern": "disney", "categoria": "Streaming"},
    {"pattern": "amazon prime", "categoria": "Streaming"},
    {"pattern": "hbo", "categoria": "Streaming"},
    {"pattern": "youtube premium", "categoria": "Streaming"},
    {"pattern": "carrefour", "categoria": "Supermercado"},
    {"pattern": "pao de acucar", "categoria": "Supermercado"},
    {"pattern": "assai", "categoria": "Supermercado"},
    {"pattern": "drogaria", "categoria": "Saúde"},
    {"pattern": "farmacia", "categoria": "Saúde"},
    {"pattern": "drogasil", "categoria": "Saúde"},
]


def categorize(descricao: str, rules: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
    """Aplica as regras (usuário + embutidas) a uma descrição.

    Retorna a categoria da primeira regra que casar, ou ``None`` se nenhuma casar
    (cabe ao chamador manter a categoria da LLM nesse caso).
    """
    if not descricao:
        return None
    text = descricao.lower()
    all_rules = list(rules or []) + BUILTIN_RULES
    for rule in all_rules:
        pattern = str(rule.get("pattern", "")).lower().strip()
        if pattern and pattern in text:
            return rule.get("categoria")
    return None


def apply_rules(df: pd.DataFrame, rules: Optional[List[Dict[str, str]]] = None) -> pd.DataFrame:
    """Reaplica as regras de categorização ao DataFrame (cópia)."""
    if df is None or df.empty or "descricao" not in df.columns:
        return df
    out = df.copy()

    def _cat(row):
        match = categorize(str(row["descricao"]), rules)
        return match if match else row.get("categoria", "Outros")

    out["categoria"] = out.apply(_cat, axis=1)
    return out


def available_categories(extra: Optional[List[str]] = None) -> List[str]:
    """Lista de categorias padrão mais quaisquer extras informadas pelo usuário."""
    cats = list(DEFAULT_CATEGORIES)
    for c in extra or []:
        if c and c not in cats:
            cats.insert(-1, c)  # mantém "Outros" por último
    return cats


def normalize_merchant(descricao: str) -> str:
    """Normaliza a descrição de um estabelecimento para agrupamento.

    Remove dígitos, parcelas, datas, pontuação e espaços extras, deixando só o
    "miolo" do nome — usado por recurring.py e por agrupamentos.
    """
    if not descricao:
        return ""
    text = descricao.lower()
    text = re.sub(r"\b\d{1,2}/\d{1,2}\b", " ", text)        # parcela 2/12
    text = re.sub(r"\d{2}/\d{2}(?:/\d{2,4})?", " ", text)    # datas
    text = re.sub(r"[*#]+\d+", " ", text)                    # *1234
    text = re.sub(r"[^a-zà-ú\s]", " ", text)                 # tira números/pontuação
    text = re.sub(r"\s+", " ", text).strip()
    return text
