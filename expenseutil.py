# expenseutil.py
import os
import re
import json
import tempfile
from typing import List, Any, Dict

import pandas as pd
from langchain_core.prompts import PromptTemplate
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

EXPENSE_EXTRACTION_PROMPT = """
Você é um especialista em análise de faturas de cartão de crédito brasileiras.
Extraia TODAS as transações/lançamentos do conteúdo abaixo.

Para cada transação, extraia:
- data: data da transação no formato dd/mm/yyyy
- descricao: nome do estabelecimento ou descrição completa
- categoria: categorize como UMA das opções:
  Alimentação, Transporte, Compras, Lazer, Saúde, Educação,
  Serviços, Moradia, Viagem, Streaming, Supermercado, Outros
- valor: valor em reais como número decimal positivo (sem símbolo R$;
  se for estorno/crédito, use valor negativo)
- parcela: informação de parcela se houver (ex: "2/12") ou string vazia

Retorne SOMENTE um JSON válido com esta estrutura exata:
{{
  "mes_referencia": "mm/yyyy",
  "total_fatura": 0.0,
  "transacoes": [
    {{"data": "dd/mm/yyyy", "descricao": "...", "categoria": "...", "valor": 0.0, "parcela": ""}}
  ]
}}

Regras importantes:
- Extraia TODAS as transações visíveis no conteúdo
- Valores: use ponto como separador decimal (ex: 123.45), não vírgula
- Remova "R$", separadores de milhar e espaços dos valores
- Categorize com base no nome do estabelecimento
  (ex: "iFood" → Alimentação, "Uber" → Transporte, "Netflix" → Streaming)
- NÃO inclua nenhum texto fora do JSON
- Se não houver parcela, "parcela" deve ser ""

Conteúdo da fatura:
{context}
"""

ANALYSIS_PROMPT = """
Você é um consultor financeiro pessoal especializado em análise de gastos de cartão de crédito.

Com base nos dados de gastos abaixo, forneça uma análise detalhada e recomendações práticas.

Dados dos gastos:
{spending_data}

Forneça a análise com as seguintes seções:

## Resumo Geral
Uma visão geral dos gastos totais e principais padrões identificados.

## Pontos de Atenção
Categorias ou hábitos que merecem atenção, com valores específicos.

## Top 3 Recomendações
Sugestões práticas e específicas para reduzir gastos, baseadas nos dados reais.

## Metas para o Próximo Mês
Metas realistas e mensuráveis com base nos dados fornecidos.

## O que Está Funcionando Bem
Aspectos positivos dos gastos do usuário.

Seja específico, use os valores reais dos dados e escreva em português brasileiro.
"""

CHAT_PROMPT = """
Você é um assistente financeiro pessoal amigável e direto.

Dados de gastos do usuário:
{spending_data}

Pergunta: {question}

Responda de forma clara, objetiva e útil, usando os dados reais fornecidos.
Escreva em português brasileiro.
"""

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

TRANSACTION_COLUMNS = [
    "arquivo",
    "mes_referencia",
    "data",
    "descricao",
    "categoria",
    "valor",
    "parcela",
]

CATEGORIAS = [
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

# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------

def _ensure_google_key():
    if not os.getenv("GOOGLE_API_KEY"):
        raise EnvironmentError(
            "GOOGLE_API_KEY não encontrado nas variáveis de ambiente (.env)."
        )


def _save_uploaded_to_temp(uploaded_file) -> str:
    suffix = os.path.splitext(uploaded_file.name)[1] or ".pdf"
    tmpdir = tempfile.mkdtemp(prefix="expenses_")
    path = os.path.join(tmpdir, os.path.basename(uploaded_file.name))
    with open(path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return path


def _robust_json_parse(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    candidate = text.strip()
    m = re.search(r"\{.*\}", candidate, flags=re.DOTALL)
    if m:
        candidate = m.group(0)
    if "'" in candidate and '"' not in candidate:
        candidate = candidate.replace("'", '"')
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return {}


def _parse_value(v) -> float:
    """Converte vários formatos de valor para float."""
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return 0.0
    v = v.replace("R$", "").replace("\u00A0", " ").strip()
    v = re.sub(r"[^\d.,\-]", "", v)
    # Formato brasileiro: 1.234,56
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return 0.0


def _spending_summary_text(df: pd.DataFrame) -> str:
    """Monta texto de resumo de gastos para prompts de IA."""
    positives = df[df["valor"] > 0]
    cat_summary = get_category_summary(df)
    monthly_summary = get_monthly_summary(df)
    top_merchants = get_top_merchants(df, 8)

    return (
        f"Total geral: R$ {positives['valor'].sum():.2f}\n"
        f"Número de transações: {len(positives)}\n\n"
        f"Resumo por Categoria:\n{cat_summary.to_string(index=False)}\n\n"
        f"Resumo Mensal:\n{monthly_summary.to_string(index=False)}\n\n"
        f"Top Estabelecimentos:\n{top_merchants.to_string(index=False)}"
    )


# ---------------------------------------------------------------------------
# Funções públicas de extração
# ---------------------------------------------------------------------------

def extract_transactions(
    user_pdf_list: List[Any],
    model_name: str = "gemini-2.0-flash",
) -> pd.DataFrame:
    """
    Extrai todas as transações de faturas de cartão de crédito em PDF.
    Retorna DataFrame com uma linha por transação.
    """
    _ensure_google_key()

    if not user_pdf_list:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)

    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
        convert_system_message_to_human=True,
    )
    prompt = PromptTemplate.from_template(EXPENSE_EXTRACTION_PROMPT)
    chain = prompt | llm | StrOutputParser()

    all_rows = []

    for uploaded in user_pdf_list:
        pdf_path = _save_uploaded_to_temp(uploaded)
        loader = PyPDFLoader(pdf_path)
        pages = loader.load_and_split()

        full_text = "\n\n".join(p.page_content for p in pages)
        raw_answer = chain.invoke({"context": full_text})

        parsed = _robust_json_parse(raw_answer)
        mes_ref = parsed.get("mes_referencia", "")
        transacoes = parsed.get("transacoes", [])

        if isinstance(transacoes, list):
            for t in transacoes:
                if not isinstance(t, dict):
                    continue
                all_rows.append(
                    {
                        "arquivo": uploaded.name,
                        "mes_referencia": mes_ref,
                        "data": t.get("data", ""),
                        "descricao": t.get("descricao", ""),
                        "categoria": t.get("categoria", "Outros"),
                        "valor": _parse_value(t.get("valor", 0)),
                        "parcela": t.get("parcela", ""),
                    }
                )

    if not all_rows:
        return pd.DataFrame(columns=TRANSACTION_COLUMNS)
    return pd.DataFrame(all_rows, columns=TRANSACTION_COLUMNS)


# ---------------------------------------------------------------------------
# Funções públicas de análise
# ---------------------------------------------------------------------------

def get_category_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Resumo de gastos por categoria (apenas valores positivos)."""
    if df.empty:
        return pd.DataFrame(columns=["categoria", "total", "percentual", "transacoes"])

    positives = df[df["valor"] > 0]
    if positives.empty:
        return pd.DataFrame(columns=["categoria", "total", "percentual", "transacoes"])

    summary = (
        positives.groupby("categoria")
        .agg(total=("valor", "sum"), transacoes=("valor", "count"))
        .reset_index()
    )
    total_geral = summary["total"].sum()
    summary["percentual"] = (summary["total"] / total_geral * 100).round(1)
    summary["total"] = summary["total"].round(2)
    return summary.sort_values("total", ascending=False).reset_index(drop=True)


def get_monthly_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Resumo de gastos por mês de referência."""
    if df.empty:
        return pd.DataFrame(columns=["mes_referencia", "total", "transacoes"])

    positives = df[df["valor"] > 0]
    if positives.empty:
        return pd.DataFrame(columns=["mes_referencia", "total", "transacoes"])

    monthly = (
        positives.groupby("mes_referencia")
        .agg(total=("valor", "sum"), transacoes=("valor", "count"))
        .reset_index()
    )
    monthly["total"] = monthly["total"].round(2)
    return monthly.sort_values("mes_referencia").reset_index(drop=True)


def get_top_merchants(df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Top N estabelecimentos por valor gasto."""
    if df.empty:
        return pd.DataFrame(columns=["descricao", "categoria", "total", "transacoes"])

    positives = df[df["valor"] > 0]
    if positives.empty:
        return pd.DataFrame(columns=["descricao", "categoria", "total", "transacoes"])

    merchants = (
        positives.groupby(["descricao", "categoria"])
        .agg(total=("valor", "sum"), transacoes=("valor", "count"))
        .reset_index()
    )
    merchants["total"] = merchants["total"].round(2)
    return merchants.sort_values("total", ascending=False).head(n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Funções públicas de IA
# ---------------------------------------------------------------------------

def get_ai_insights(df: pd.DataFrame, model_name: str = "gemini-2.0-flash") -> str:
    """Gera análise completa e recomendações de gastos usando IA."""
    _ensure_google_key()
    if df.empty:
        return "Nenhum dado disponível para análise."

    spending_data = _spending_summary_text(df)
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.3,
        convert_system_message_to_human=True,
    )
    response = llm.invoke(
        [HumanMessage(content=ANALYSIS_PROMPT.format(spending_data=spending_data))]
    )
    return response.content


def chat_about_spending(
    df: pd.DataFrame, question: str, model_name: str = "gemini-2.0-flash"
) -> str:
    """Responde perguntas sobre os gastos usando IA."""
    _ensure_google_key()
    if df.empty:
        return "Nenhum dado disponível. Por favor, carregue suas faturas primeiro."

    spending_data = _spending_summary_text(df)
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0.3,
        convert_system_message_to_human=True,
    )
    prompt_text = CHAT_PROMPT.format(spending_data=spending_data, question=question)
    response = llm.invoke([HumanMessage(content=prompt_text)])
    return response.content
