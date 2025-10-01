# invoiceutil.py
import os
import re
import json
import tempfile
from typing import List, Any, Dict

import pandas as pd
from langchain.prompts import PromptTemplate
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain.chains import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain
from langchain_google_genai import (
    ChatGoogleGenerativeAI,
    GoogleGenerativeAIEmbeddings
)

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

def _ensure_google_key():
    if not os.getenv("GOOGLE_API_KEY"):
        raise EnvironmentError(
            "GOOGLE_API_KEY não encontrado nas variáveis de ambiente (.env)."
        )

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
    model_name: str = "gemini-2.0-flash",
    embedding_model: str = "models/embedding-001",
    retriever_k: int = 6
) -> pd.DataFrame:
    """
    Recebe a lista do st.file_uploader (UploadedFile) e retorna um DataFrame
    com os campos extraídos por arquivo.
    """
    _ensure_google_key()

    if not user_pdf_list:
        return pd.DataFrame(columns=COLUMNS)

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
        convert_system_message_to_human=True,
    )
    embeddings = GoogleGenerativeAIEmbeddings(model=embedding_model)
    prompt = PromptTemplate.from_template(INVOICE_PROMPT_TEMPLATE)

    rows = []

    for uploaded in user_pdf_list:
        pdf_path = _save_uploaded_to_temp(uploaded)

        loader = PyPDFLoader(pdf_path)
        pages = loader.load_and_split()

        vector = FAISS.from_documents(pages, embeddings)
        retriever = vector.as_retriever(search_kwargs={"k": retriever_k})

        document_chain = create_stuff_documents_chain(llm, prompt)
        retrieval_chain = create_retrieval_chain(retriever, document_chain)

        response = retrieval_chain.invoke({"input": ""})
        raw_answer = response.get("answer", "") or response.get("result", "")

        parsed = _robust_json_parse(raw_answer)
        normalized = _postprocess_json_fields(parsed)

        row = {
            "file": uploaded.name,
            **normalized
        }
        rows.append(row)



    df = pd.DataFrame(rows, columns=COLUMNS)
    return df
