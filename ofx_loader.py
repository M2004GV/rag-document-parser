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


def parse_ofx(uploaded, rules=None) -> pd.DataFrame:
    """Converte um arquivo OFX (UploadedFile do Streamlit ou path) em DataFrame."""
    data = uploaded.getbuffer() if hasattr(uploaded, "getbuffer") else open(uploaded, "rb").read()
    name = getattr(uploaded, "name", "extrato.ofx")
    raw = bytes(data)

    if ofx_available():
        rows = _parse_with_ofxparse(raw, name, rules)
    else:
        rows = _parse_with_regex(raw.decode("latin-1", errors="ignore"), name, rules)

    if not rows:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    return pd.DataFrame(rows, columns=TRANSACTION_COLUMNS)


def _parse_with_ofxparse(raw: bytes, name: str, rules) -> List[dict]:
    import io
    from ofxparse import OfxParser

    ofx = OfxParser.parse(io.BytesIO(raw))
    rows: List[dict] = []
    for account in ofx.accounts:
        for t in account.statement.transactions:
            valor = -float(t.amount)  # OFX: débito negativo -> gasto positivo
            descricao = (t.payee or t.memo or "").strip()
            dt = t.date
            rows.append(_row(name, dt.strftime("%d/%m/%Y") if dt else "",
                             f"{dt.month:02d}/{dt.year}" if dt else "",
                             descricao, valor, rules))
    return rows


def _parse_with_regex(text: str, name: str, rules) -> List[dict]:
    rows: List[dict] = []
    for block in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", text, flags=re.DOTALL | re.IGNORECASE):
        amount = _tag(block, "TRNAMT")
        dtposted = _tag(block, "DTPOSTED")
        memo = _tag(block, "MEMO") or _tag(block, "NAME")
        try:
            valor = -float(amount)
        except (TypeError, ValueError):
            continue
        data, mes_ref = "", ""
        if dtposted and len(dtposted) >= 8:
            yyyy, mm, dd = dtposted[0:4], dtposted[4:6], dtposted[6:8]
            data, mes_ref = f"{dd}/{mm}/{yyyy}", f"{mm}/{yyyy}"
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
