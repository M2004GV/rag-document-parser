# invoiceutil.py
import os
import re
import json
import tempfile
import time
from typing import List, Any, Dict, Optional

import pandas as pd
from langchain_core.prompts import PromptTemplate
from langchain_ollama import ChatOllama
from langchain_core.output_parsers import StrOutputParser

import storage
from ocr import load_pdf_text_with_ocr_fallback

DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL")


def _make_llm(model_name: str, temperature: float) -> ChatOllama:
    kwargs = {"model": model_name, "temperature": temperature}
    if OLLAMA_BASE_URL:
        kwargs["base_url"] = OLLAMA_BASE_URL
    return ChatOllama(**kwargs)

INVOICE_PROMPT_TEMPLATE = """
Você é um extrator de dados de faturas. Extraia APENAS os campos pedidos do conteúdo abaixo.
Se um campo não existir de forma inequívoca, devolva string vazia para ele.

Campos a extrair (JSON com estas chaves exatas):
- Invoice no.
- Description
- Quantity
- Date
- Unit price
- Amount
- Total
- Email
- Phone number
- Address

Regras:
- Saída deve ser UM JSON único, sem texto extra.
- Remova símbolos de moeda (R$, $, etc.) e separadores de milhar; mantenha ponto decimal.
- Datas no formato dd/mm/yyyy quando possível.
- "Description" deve ser o texto principal de descrição do item/serviço (se houver múltiplas, concatene de forma curta).
- Números: use apenas dígitos e ponto decimal (ex.: 1234.56).
- E-mail deve seguir padrão válido; telefone apenas dígitos (com DDI/DDDs se houver).
- Endereço em linha única.

Conteúdo (pode estar com OCR bagunçado):
{context}
"""

COLUMNS = [
    "file",
    "Invoice no.",
    "Description",
    "Quantity",
    "Date",
    "Unit price",
    "Amount",
    "Total",
    "Email",
    "Phone number",
    "Address",
]


def _invoke_with_retry(chain, input_data, max_retries: int = 2):
    """Retry simples para o Ollama local (ex.: servidor ainda subindo)."""
    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return chain.invoke(input_data)
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(2)
    raise RuntimeError(
        "Falha ao chamar o modelo local via Ollama. Verifique se o serviço está "
        f"ativo (`ollama serve`) e o modelo baixado. Detalhe: {last_err}"
    ) from last_err


def _truncate_text(text: str, max_chars: int = 8_000) -> str:
    return text[:max_chars]


def _strip_currency_symbols(s: str) -> str:
    if not isinstance(s, str):
        return s
    s = s.replace('\u00A0', ' ') 
    s = re.sub(r'[R$\€\£\¥]', '', s) 
    s = re.sub(r'\s{2,}', ' ', s).strip()
    s = re.sub(r'[^0-9.\-]', '', s)
    return s

def _postprocess_json_fields(d: Dict[str, Any]) -> Dict[str, Any]:
    keys = ["Invoice no.", "Description", "Quantity", "Date", "Unit price",
            "Amount", "Total", "Email", "Phone number", "Address"]
    out = {k: "" for k in keys}
    if not isinstance(d, dict):
        return out

    aliases = {k.lower(): k for k in keys}
    for k, v in d.items():
        std_key = aliases.get(str(k).lower().strip())
        if not std_key:
            continue
        val = "" if v is None else str(v).strip()
        if std_key in {"Unit price", "Amount", "Total"}:
            val = _strip_currency_symbols(val)
        elif std_key == "Phone number":
            val = re.sub(r'[^0-9]', '', val)
        out[std_key] = val
    return out

def _robust_json_parse(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    candidate = text.strip()
    m = re.search(r'\{.*\}', candidate, flags=re.DOTALL)
    if m:
        candidate = m.group(0)
    if "'" in candidate and '"' not in candidate:
        candidate = candidate.replace("'", '"')
    candidate = re.sub(r',\s*([}\]])', r'\1', candidate) 
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pairs = re.findall(r'"([^"]+)"\s*:\s*"([^"]*)"', candidate)
        return {k: v for k, v in pairs}

def _save_uploaded_to_temp(uploaded_file) -> str:
    """
    Streamlit UploadedFile -> salva em arquivo temporário e retorna o caminho.
    """
    suffix = os.path.splitext(uploaded_file.name)[1] or ".pdf"
    tmpdir = tempfile.mkdtemp(prefix="invoices_")
    path = os.path.join(tmpdir, os.path.basename(uploaded_file.name))
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path

def create_docs(
    user_pdf_list: List[Any],
    model_name: str = DEFAULT_MODEL,
    use_cache: bool = True,
) -> pd.DataFrame:
    """
    Recebe a lista do st.file_uploader (UploadedFile) e retorna um DataFrame
    com os campos extraídos por arquivo.

    - OCR fallback para notas escaneadas (item 9).
    - Cache por hash do PDF para não reprocessar o mesmo arquivo (item 10).
    """
    if not user_pdf_list:
        return pd.DataFrame(columns=COLUMNS)

    llm = _make_llm(model_name, 0)
    prompt = PromptTemplate.from_template(INVOICE_PROMPT_TEMPLATE)
    chain = prompt | llm | StrOutputParser()

    rows = []

    for uploaded in user_pdf_list:
        fhash = storage.file_hash(bytes(uploaded.getbuffer()))
        normalized = storage.cache_get(fhash, "invoice") if use_cache else None

        if normalized is None:
            pdf_path = _save_uploaded_to_temp(uploaded)
            full_text = _truncate_text(load_pdf_text_with_ocr_fallback(pdf_path))
            raw_answer = _invoke_with_retry(chain, {"context": full_text})
            parsed = _robust_json_parse(raw_answer)
            normalized = _postprocess_json_fields(parsed)
            if use_cache and any(normalized.values()):
                storage.cache_set(fhash, "invoice", normalized)

        rows.append({"file": uploaded.name, **normalized})

    df = pd.DataFrame(rows, columns=COLUMNS)
    return df
