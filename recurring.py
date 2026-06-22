# recurring.py
"""Detecção de gastos recorrentes / assinaturas (item 4).

Agrupa transações por estabelecimento normalizado e sinaliza aquelas que se
repetem em múltiplos meses (ou múltiplas vezes com valor estável) como
prováveis assinaturas.
"""
from typing import List

import pandas as pd

from categories import normalize_merchant


def detect_recurring(df: pd.DataFrame, min_ocorrencias: int = 2) -> pd.DataFrame:
    """Identifica gastos recorrentes.

    Considera recorrente o estabelecimento que aparece em ``min_ocorrencias`` ou
    mais meses distintos, ou que se repete em ``min_ocorrencias`` lançamentos com
    valor praticamente igual (variação <= 5%).

    Retorna DataFrame com: descricao, categoria, ocorrencias, meses,
    valor_medio, total e is_assinatura.
    """
    cols = ["descricao", "categoria", "ocorrencias", "meses",
            "valor_medio", "total", "is_assinatura"]
    if df is None or df.empty or "descricao" not in df.columns:
        return pd.DataFrame(columns=cols)

    work = df[df["valor"] > 0].copy()
    if work.empty:
        return pd.DataFrame(columns=cols)

    work["_merchant"] = work["descricao"].map(normalize_merchant)
    work = work[work["_merchant"] != ""]
    if work.empty:
        return pd.DataFrame(columns=cols)

    groups: List[dict] = []
    for merchant, g in work.groupby("_merchant"):
        ocorrencias = len(g)
        meses = g["mes_referencia"].nunique()
        valor_medio = float(g["valor"].mean())
        total = float(g["valor"].sum())
        # Valor estável: desvio relativo pequeno entre os lançamentos.
        spread = (g["valor"].max() - g["valor"].min()) / valor_medio if valor_medio else 1.0
        is_recorrente = meses >= min_ocorrencias
        is_valor_estavel = ocorrencias >= min_ocorrencias and spread <= 0.05
        if not (is_recorrente or is_valor_estavel):
            continue
        groups.append(
            {
                "descricao": g["descricao"].mode().iloc[0] if not g["descricao"].mode().empty
                             else g["descricao"].iloc[0],
                "categoria": g["categoria"].mode().iloc[0] if not g["categoria"].mode().empty
                             else g["categoria"].iloc[0],
                "ocorrencias": ocorrencias,
                "meses": meses,
                "valor_medio": round(valor_medio, 2),
                "total": round(total, 2),
                # Assinatura: recorrente em vários meses E valor estável.
                "is_assinatura": bool(is_recorrente and is_valor_estavel),
            }
        )

    if not groups:
        return pd.DataFrame(columns=cols)

    result = pd.DataFrame(groups, columns=cols)
    return result.sort_values(
        ["is_assinatura", "total"], ascending=[False, False]
    ).reset_index(drop=True)
