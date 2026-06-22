# analytics.py
"""Análises derivadas das transações.

- status de orçamento por categoria (item 7)
- comparação mês a mês com variação % (item 8)
- previsão de gasto do mês corrente (item 13)
"""
import calendar
from datetime import date
from typing import Dict

import numpy as np
import pandas as pd


def budget_status(df: pd.DataFrame, budgets: Dict[str, float]) -> pd.DataFrame:
    """Compara o gasto por categoria com o teto definido.

    Retorna DataFrame: categoria, gasto, limite, percentual, estourou.
    Considera apenas categorias com orçamento definido.
    """
    cols = ["categoria", "gasto", "limite", "percentual", "estourou"]
    if not budgets:
        return pd.DataFrame(columns=cols)

    positives = df[df["valor"] > 0] if not df.empty else df
    gastos = (
        positives.groupby("categoria")["valor"].sum()
        if not positives.empty
        else pd.Series(dtype=float)
    )

    rows = []
    for categoria, limite in budgets.items():
        gasto = float(gastos.get(categoria, 0.0))
        pct = round(gasto / limite * 100, 1) if limite else 0.0
        rows.append(
            {
                "categoria": categoria,
                "gasto": round(gasto, 2),
                "limite": round(float(limite), 2),
                "percentual": pct,
                "estourou": gasto > limite,
            }
        )
    return pd.DataFrame(rows, columns=cols).sort_values(
        "percentual", ascending=False
    ).reset_index(drop=True)


def month_over_month(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela categoria x mês com a variação % do último mês vs o anterior.

    Retorna um DataFrame pivot (categorias nas linhas, meses nas colunas) mais
    uma coluna ``variacao_%`` comparando os dois meses mais recentes.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    positives = df[df["valor"] > 0]
    if positives.empty or positives["mes_referencia"].nunique() < 1:
        return pd.DataFrame()

    pivot = positives.pivot_table(
        index="categoria",
        columns="mes_referencia",
        values="valor",
        aggfunc="sum",
        fill_value=0.0,
    )
    # Ordena meses cronologicamente (mm/yyyy).
    meses = sorted(pivot.columns, key=_month_key)
    pivot = pivot[meses].round(2)

    if len(meses) >= 2:
        anterior, atual = meses[-2], meses[-1]
        # np.nan (não pd.NA) mantém a coluna float para que .round() funcione.
        prev = pivot[anterior].replace(0, np.nan)
        pivot["variacao_%"] = (
            (pivot[atual] - pivot[anterior]) / prev * 100
        ).round(1)
    else:
        pivot["variacao_%"] = np.nan

    return pivot.reset_index()


def forecast_current_month(df: pd.DataFrame, today: date | None = None) -> dict:
    """Projeta o gasto total do mês corrente.

    Combina duas estimativas quando possível:
    - run-rate: gasto-até-agora no mês escalado para o mês inteiro
    - média histórica dos meses anteriores

    Retorna dict com gasto_atual, projecao, media_historica e dias_restantes.
    """
    today = today or date.today()
    mes_corrente = f"{today.month:02d}/{today.year}"
    dias_no_mes = calendar.monthrange(today.year, today.month)[1]
    dias_restantes = dias_no_mes - today.day

    empty = {
        "mes": mes_corrente,
        "gasto_atual": 0.0,
        "projecao": 0.0,
        "media_historica": 0.0,
        "dias_restantes": dias_restantes,
    }
    if df is None or df.empty:
        return empty

    positives = df[df["valor"] > 0]
    if positives.empty:
        return empty

    por_mes = positives.groupby("mes_referencia")["valor"].sum()

    gasto_atual = float(por_mes.get(mes_corrente, 0.0))
    historicos = por_mes.drop(labels=[mes_corrente], errors="ignore")
    media_historica = float(historicos.mean()) if not historicos.empty else 0.0

    if gasto_atual > 0 and today.day > 0:
        run_rate = gasto_atual / today.day * dias_no_mes
        if media_historica > 0:
            projecao = (run_rate + media_historica) / 2
        else:
            projecao = run_rate
    else:
        projecao = media_historica

    return {
        "mes": mes_corrente,
        "gasto_atual": round(gasto_atual, 2),
        "projecao": round(projecao, 2),
        "media_historica": round(media_historica, 2),
        "dias_restantes": dias_restantes,
    }


def _month_key(mes: str):
    """Chave de ordenação para 'mm/yyyy' (entradas inválidas vão para o fim)."""
    try:
        mm, yyyy = str(mes).split("/")
        return (int(yyyy), int(mm))
    except (ValueError, AttributeError):
        return (9999, 99)
