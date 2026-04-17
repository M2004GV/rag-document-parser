import streamlit as st
from dotenv import load_dotenv
import plotly.express as px
import pandas as pd

import invoiceutil as iu
import expenseutil as eu


def _fmt_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def render_expense_tab():
    st.header("Analisador de Gastos do Cartão de Crédito")
    st.write(
        "Faça upload de uma ou mais faturas em PDF para extrair e analisar seus gastos."
    )

    uploaded = st.file_uploader(
        "Selecione as faturas (PDF)",
        type=["pdf"],
        accept_multiple_files=True,
        key="expense_uploader",
    )

    col1, col2 = st.columns([1, 4])
    extract_btn = col1.button("Extrair Transações", type="primary")

    if extract_btn:
        if not uploaded:
            st.warning("Selecione ao menos uma fatura em PDF.")
            return

        with st.spinner("Extraindo transações das faturas..."):
            try:
                df = eu.extract_transactions(uploaded)
            except RuntimeError as e:
                st.error(str(e))
                return

        if df.empty:
            st.error("Não foi possível extrair transações. Verifique os arquivos enviados.")
            return

        st.session_state["expense_df"] = df
        st.success(f"{len(df)} transações extraídas de {len(uploaded)} fatura(s).")

    df: pd.DataFrame = st.session_state.get("expense_df", pd.DataFrame())

    if df.empty:
        return

    # ------------------------------------------------------------------ #
    # KPIs rápidos
    # ------------------------------------------------------------------ #
    positives = df[df["valor"] > 0]
    total_gasto = positives["valor"].sum()
    n_transacoes = len(positives)
    n_meses = df["mes_referencia"].nunique()

    k1, k2, k3 = st.columns(3)
    k1.metric("Total Gasto", _fmt_brl(total_gasto))
    k2.metric("Transações", n_transacoes)
    k3.metric("Meses Analisados", n_meses)

    st.divider()

    # ------------------------------------------------------------------ #
    # Tabela de transações com filtros
    # ------------------------------------------------------------------ #
    with st.expander("Ver todas as transações", expanded=False):
        categorias_disponiveis = sorted(df["categoria"].unique().tolist())
        meses_disponiveis = sorted(df["mes_referencia"].unique().tolist())

        fc1, fc2 = st.columns(2)
        filtro_cat = fc1.multiselect(
            "Filtrar por categoria",
            categorias_disponiveis,
            default=categorias_disponiveis,
        )
        filtro_mes = fc2.multiselect(
            "Filtrar por mês",
            meses_disponiveis,
            default=meses_disponiveis,
        )

        df_filtered = df[
            df["categoria"].isin(filtro_cat) & df["mes_referencia"].isin(filtro_mes)
        ]

        st.dataframe(
            df_filtered.style.format({"valor": "R$ {:.2f}"}),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # ------------------------------------------------------------------ #
    # Gráficos
    # ------------------------------------------------------------------ #
    cat_summary = eu.get_category_summary(df)
    monthly_summary = eu.get_monthly_summary(df)

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        st.subheader("Gastos por Categoria")
        if not cat_summary.empty:
            fig_pie = px.pie(
                cat_summary,
                values="total",
                names="categoria",
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)

    with chart_col2:
        st.subheader("Gastos por Mês")
        if not monthly_summary.empty:
            fig_bar = px.bar(
                monthly_summary,
                x="mes_referencia",
                y="total",
                text_auto=".2f",
                color_discrete_sequence=["#636EFA"],
                labels={"mes_referencia": "Mês", "total": "Total (R$)"},
            )
            fig_bar.update_traces(texttemplate="R$ %{text}", textposition="outside")
            fig_bar.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig_bar, use_container_width=True)

    # ------------------------------------------------------------------ #
    # Top estabelecimentos
    # ------------------------------------------------------------------ #
    st.subheader("Top 10 Estabelecimentos")
    top = eu.get_top_merchants(df, 10)
    if not top.empty:
        fig_top = px.bar(
            top,
            x="total",
            y="descricao",
            orientation="h",
            color="categoria",
            text_auto=".2f",
            labels={"total": "Total (R$)", "descricao": "Estabelecimento"},
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_top.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(t=10))
        fig_top.update_traces(texttemplate="R$ %{text}", textposition="outside")
        st.plotly_chart(fig_top, use_container_width=True)

    st.divider()

    # ------------------------------------------------------------------ #
    # Análise de IA
    # ------------------------------------------------------------------ #
    st.subheader("Análise e Recomendações com IA")

    if st.button("Gerar Análise Completa"):
        with st.spinner("Analisando seus gastos..."):
            insights = eu.get_ai_insights(df)
        st.session_state["ai_insights"] = insights

    if "ai_insights" in st.session_state:
        st.markdown(st.session_state["ai_insights"])


def render_chat_tab():
    st.header("Assistente Financeiro")
    st.write("Faça perguntas sobre seus gastos e receba respostas personalizadas.")

    df: pd.DataFrame = st.session_state.get("expense_df", pd.DataFrame())

    if df.empty:
        st.info("Carregue suas faturas na aba **Gastos do Cartão** primeiro.")
        return

    # Exemplos de perguntas
    with st.expander("Exemplos de perguntas"):
        st.markdown(
            """
- Qual categoria eu mais gastei?
- Quanto gastei com alimentação no mês passado?
- Quais gastos posso cortar para economizar R$ 200?
- Tenho algum gasto recorrente que poderia cancelar?
- Como meus gastos variaram entre os meses?
- Qual estabelecimento visitei mais vezes?
"""
        )

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    for msg in st.session_state["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("Pergunte sobre seus gastos...")

    if question:
        st.session_state["chat_history"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Pensando..."):
                answer = eu.chat_about_spending(df, question)
            st.markdown(answer)
            st.session_state["chat_history"].append(
                {"role": "assistant", "content": answer}
            )


def render_invoice_tab():
    st.header("Extração de Dados de Notas Fiscais")
    st.write("Extraia campos estruturados de notas fiscais em PDF.")

    pdf = st.file_uploader(
        "Selecione notas fiscais (PDF)",
        type=["pdf"],
        accept_multiple_files=True,
        key="invoice_uploader",
    )

    if st.button("Extrair Dados"):
        if not pdf:
            st.warning("Selecione ao menos um arquivo PDF.")
            return
        with st.spinner("Extraindo dados..."):
            try:
                df = iu.create_docs(pdf)
            except RuntimeError as e:
                st.error(str(e))
                return
        if df.empty:
            st.info("Nenhum arquivo processado ou sem dados extraídos.")
        else:
            st.dataframe(df, use_container_width=True)
            st.success("Extração concluída!")


def main():
    load_dotenv()

    st.set_page_config(
        page_title="Analisador de Gastos",
        page_icon="💳",
        layout="wide",
    )

    st.title("💳 Analisador de Gastos — Cartão de Crédito")

    tab_expenses, tab_chat, tab_invoices = st.tabs(
        ["📊 Gastos do Cartão", "🤖 Assistente Financeiro", "🧾 Notas Fiscais"]
    )

    with tab_expenses:
        render_expense_tab()

    with tab_chat:
        render_chat_tab()

    with tab_invoices:
        render_invoice_tab()


if __name__ == "__main__":
    main()
