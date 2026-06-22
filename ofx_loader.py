# ofx_loader.py
"""Importação de extratos OFX / Open Finance (item 12).

Arquivos OFX (.ofx) são exportados pela maioria dos bancos e já trazem as
transações estruturadas — não precisam de LLM. Convertemos diretamente para o
mesmo schema de transações usado no resto da aplicação.

Usa a biblioteca ``ofxparse`` se disponível; caso contrário, faz um parsing
mínimo via regex das tags SGML do OFX.
"""
import re
from typing import List

import pandas as pd

from categories import categorize
from storage import TRANSACTION_COLUMNS


def ofx_available() -> bool:
    try:
        import ofxparse  # noqa: F401
        return True
    except ImportError:
        return False


def _categorize(descricao: str, rules=None) -> str:
    return categorize(descricao, rules) or "Outros"


def _month_from_filename(name: str) -> str:
    """Extrai o mês de referência do nome do arquivo (ex.: Nubank_2026-03-01.ofx).

    Em extratos/faturas, as datas das transações se espalham por vários meses
    (uma fatura de março contém compras de fevereiro), então o mês correto do
    extrato é o do nome do arquivo, não o de cada transação. Aceita os formatos
    americanos ``yyyy-mm-dd``, ``yyyy_mm_dd``, ``yyyymmdd`` ou ``yyyy-mm``.
    Retorna ``"mm/yyyy"`` ou ``""`` se nenhuma data for encontrada.
    """
    if not name:
        return ""
    m = re.search(r"(20\d{2})[-_.]?(0[1-9]|1[0-2])(?:[-_.]?\d{2})?", name)
    if m:
        return f"{m.group(2)}/{m.group(1)}"
    return ""


def parse_ofx(uploaded, rules=None) -> pd.DataFrame:
    """Converte um arquivo OFX (UploadedFile do Streamlit ou path) em DataFrame."""
    data = uploaded.getbuffer() if hasattr(uploaded, "getbuffer") else open(uploaded, "rb").read()
    name = getattr(uploaded, "name", "extrato.ofx")
    raw = bytes(data)

    # Mês do extrato vem do nome do arquivo (quando disponível); ver docstring.
    file_month = _month_from_filename(name)

    if ofx_available():
        rows = _parse_with_ofxparse(raw, name, file_month, rules)
    else:
        rows = _parse_with_regex(raw.decode("latin-1", errors="ignore"), name, file_month, rules)

    if not rows:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    return pd.DataFrame(rows, columns=TRANSACTION_COLUMNS)


def _parse_with_ofxparse(raw: bytes, name: str, file_month: str, rules) -> List[dict]:
    import io
    from ofxparse import OfxParser

    ofx = OfxParser.parse(io.BytesIO(raw))
    rows: List[dict] = []
    for account in ofx.accounts:
        for t in account.statement.transactions:
            valor = -float(t.amount)  # OFX: débito negativo -> gasto positivo
            descricao = (t.payee or t.memo or "").strip()
            dt = t.date
            data = dt.strftime("%d/%m/%Y") if dt else ""
            mes_ref = file_month or (f"{dt.month:02d}/{dt.year}" if dt else "")
            rows.append(_row(name, data, mes_ref, descricao, valor, rules))
    return rows


def _parse_with_regex(text: str, name: str, file_month: str, rules) -> List[dict]:
    rows: List[dict] = []
    for block in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, flags=re.DOTALL | re.IGNORECASE):
        amount = _tag(block, "TRNAMT")
        dtposted = _tag(block, "DTPOSTED")
        memo = _tag(block, "MEMO") or _tag(block, "NAME")
        try:
            valor = -float(amount)
        except (TypeError, ValueError):
            continue
        data, mes_ref = "", file_month
        if dtposted and len(dtposted) >= 8:
            yyyy, mm, dd = dtposted[0:4], dtposted[4:6], dtposted[6:8]
            data = f"{dd}/{mm}/{yyyy}"
            mes_ref = file_month or f"{mm}/{yyyy}"
        rows.append(_row(name, data, mes_ref, (memo or "").strip(), valor, rules))
    return rows


def _row(arquivo, data, mes_ref, descricao, valor, rules) -> dict:
    return {
        "arquivo": arquivo,
        "mes_referencia": mes_ref,
        "data": data,
        "descricao": descricao,
        "categoria": _categorize(descricao, rules),
        "valor": round(valor, 2),
        "parcela": "",
    }


def _tag(block: str, tag: str):
    m = re.search(rf"<{tag}>([^<\r\n]*)", block, flags=re.IGNORECASE)
    return m.group(1).strip() if m else None
