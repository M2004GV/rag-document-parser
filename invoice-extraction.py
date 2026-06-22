import io

import streamlit as st
import plotly.express as px
import pandas as pd

import invoiceutil as iu
import expenseutil as eu
import storage
import analytics
import recurring
from categories import available_categories, apply_rules
from ofx_loader import parse_ofx

# Modelos sugeridos no seletor da sidebar (item 3).
MODEL_OPTIONS = ["llama3.2", "llama3.2:1b", "llama3.1", "mistral", "qwen2.5", "phi3"]


def _fmt_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _current_model() -> str:
    return st.session_state.get("model_name", "llama3.2")


def _user_id() -> int:
    return st.session_state.get("user_id", storage.guest_user_id())


def _user_rules():
    return storage.get_category_rules(_user_id())


# --------------------------------------------------------------------------- #
# Sidebar: autenticação (item 14), seletor de modelo (item 3)
# --------------------------------------------------------------------------- #

def render_sidebar():
    st.sidebar.header("Conta")

    username = st.session_state.get("username")
    if username and username != storage.GUEST_USERNAME:
        st.sidebar.success(f"Logado como **{username}**")
        if st.sidebar.button("Sair"):
            for k in ("user_id", "username", "expense_df", "ai_insights", "chat_history"):
                st.session_state.pop(k, None)
            st.rerun()
    else:
        with st.sidebar.expander("Entrar / Criar conta", expanded=False):
            mode = st.radio("Ação", ["Entrar", "Criar conta"], horizontal=True, key="auth_mode")
            u = st.text_input("Usuário", key="auth_user")
            p = st.text_input("Senha", type="password", key="auth_pass")
            if st.button("Confirmar", key="auth_submit"):
                _handle_auth(mode, u, p)
        st.sidebar.caption("Sem login, os dados ficam no perfil **convidado**.")

    st.sidebar.divider()
    st.sidebar.header("Modelo (Ollama)")
    st.session_state["model_name"] = st.sidebar.selectbox(
        "Modelo de linguagem",
        MODEL_OPTIONS,
        index=0,
        help="O modelo precisa estar baixado no Ollama (`ollama pull <modelo>`).",
    )


def _handle_auth(mode: str, username: str, password: str):
    if not username or not password:
        st.sidebar.warning("Informe usuário e senha.")
        return
    try:
        if mode == "Criar conta":
            uid = storage.create_user(username, password)
            st.sidebar.success("Conta criada!")
        else:
            uid = storage.verify_user(username, password)
            if uid is None:
                st.sidebar.error("Usuário ou senha inválidos.")
                return
        st.session_state["user_id"] = uid
        st.session_state["username"] = username.strip().lower()
        st.session_state.pop("expense_df", None)
        st.rerun()
    except ValueError as e:
        st.sidebar.error(str(e))


# --------------------------------------------------------------------------- #
# Exportação CSV/Excel (item 1)
# --------------------------------------------------------------------------- #

def _download_buttons(df: pd.DataFrame, basename: str, key: str):
    c1, c2 = st.columns(2)
    c1.download_button(
        "⬇️ Baixar CSV",
        df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{basename}.csv",
        mime="text/csv",
        key=f"{key}_csv",
    )
    buffer = io.BytesIO()
    try:
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="dados")
        c2.download_button(
            "⬇️ Baixar Excel",
            buffer.getvalue(),
            file_name=f"{basename}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key=f"{key}_xlsx",
        )
    except ImportError:
        c2.caption("Instale `openpyxl` para exportar em Excel.")


# --------------------------------------------------------------------------- #
# Categorias customizáveis (item 6) + orçamentos (item 7)
# --------------------------------------------------------------------------- #

def render_settings_expander(df: pd.DataFrame):
    uid = _user_id()
    with st.expander("⚙️ Categorias e orçamentos"):
        st.markdown("**Regras de categorização** — descrição contém → categoria")
        rules = _user_rules()
        if rules:
            for r in rules:
                rc1, rc2 = st.columns([5, 1])
                rc1.write(f"`{r['pattern']}` → **{r['categoria']}**")
                if rc2.button("✕", key=f"delrule_{r['id']}"):
                    storage.delete_category_rule(r["id"])
                    st.rerun()

        gc1, gc2, gc3 = st.columns([3, 3, 1])
        novo_pat = gc1.text_input("Texto (ex.: ifood)", key="new_rule_pat")
        novo_cat = gc2.selectbox("Categoria", available_categories(), key="new_rule_cat")
        if gc3.button("Add", key="add_rule"):
            storage.add_category_rule(uid, novo_pat, novo_cat)
            st.rerun()

        st.divider()
        st.markdown("**Orçamento mensal por categoria** (deixe 0 para remover)")
        budgets = storage.get_budgets(uid)
        bc1, bc2, bc3 = st.columns([3, 3, 1])
        cat_b = bc1.selectbox("Categoria", available_categories(), key="budget_cat")
        val_b = bc2.number_input(
            "Teto (R$)", min_value=0.0, step=50.0,
            value=float(budgets.get(cat_b, 0.0)), key="budget_val",
        )
        if bc3.button("Salvar", key="save_budget"):
            storage.set_budget(uid, cat_b, val_b)
            st.rerun()


# --------------------------------------------------------------------------- #
# Aba de gastos
# --------------------------------------------------------------------------- #

def render_expense_tab():
    st.header("Analisador de Gastos do Cartão de Crédito")
    st.write("Faça upload de faturas em PDF ou extratos OFX para extrair e analisar seus gastos.")

    uploaded = st.file_uploader(
        "Selecione faturas (PDF) ou extratos (OFX)",
        type=["pdf", "ofx"],
        accept_multiple_files=True,
        key="expense_uploader",
    )

    c1, c2, c3 = st.columns([2, 2, 2])
    extract_btn = c1.button("Extrair Transações", type="primary")
    load_btn = c2.button("Carregar histórico")
    clear_btn = c3.button("Limpar histórico")

    # Carregar histórico salvo do banco (item 2).
    if load_btn:
        hist = storage.load_transactions(_user_id())
        if hist.empty:
            st.info("Nenhuma transação salva no histórico ainda.")
        else:
            st.session_state["expense_df"] = hist
            st.success(f"{len(hist)} transações carregadas do histórico.")

    # Limpar o histórico persistido (recupera de uma base poluída por duplicatas).
    if clear_btn:
        storage.clear_transactions(_user_id())
        st.session_state.pop("expense_df", None)
        st.success("Histórico apagado. Reimporte seus arquivos para começar do zero.")
        st.rerun()

    if extract_btn:
        if not uploaded:
            st.warning("Selecione ao menos um arquivo.")
        else:
            _do_extract(uploaded)

    df: pd.DataFrame = st.session_state.get("expense_df", pd.DataFrame())
    render_settings_expander(df)

    if df.empty:
        return

    # Reaplica regras locais ao df em memória (item 6).
    df = apply_rules(df, _user_rules())
    st.session_state["expense_df"] = df

    _render_kpis(df)
    _render_forecast(df)
    st.divider()
    _render_transactions_table(df)
    st.divider()
    _render_charts(df)
    _render_budget(df)
    _render_recurring(df)
    _render_month_comparison(df)
    st.divider()
    _render_ai_analysis(df)


def _do_extract(uploaded):
    pdfs = [f for f in uploaded if f.name.lower().endswith(".pdf")]
    ofxs = [f for f in uploaded if f.name.lower().endswith(".ofx")]
    frames = []

    rules = _user_rules()
    if pdfs:
        with st.spinner(f"Extraindo {len(pdfs)} fatura(s) PDF com {_current_model()}..."):
            try:
                frames.append(eu.extract_transactions(pdfs, model_name=_current_model(), rules=rules))
            except RuntimeError as e:
                st.error(str(e))
                return
    if ofxs:
        with st.spinner(f"Importando {len(ofxs)} extrato(s) OFX..."):
            for f in ofxs:
                frames.append(parse_ofx(f, rules))

    df = pd.concat([f for f in frames if not f.empty], ignore_index=True) if frames else pd.DataFrame()
    if df is None or df.empty:
        st.error("Não foi possível extrair transações. Verifique os arquivos enviados.")
        return

    # Remove repetições dentro do próprio lote (ex.: mesmo arquivo carregado 2x).
    df = df.drop_duplicates(
        subset=["arquivo", "mes_referencia", "data", "descricao", "valor", "parcela"]
    ).reset_index(drop=True)

    st.session_state["expense_df"] = df
    saved = storage.save_transactions(_user_id(), df)  # persiste (item 2), idempotente
    skipped = len(df) - saved
    msg = f"{len(df)} transações extraídas de {len(uploaded)} arquivo(s) — {saved} novas no histórico."
    if skipped:
        msg += f" {skipped} já existiam e foram ignoradas."
    st.success(msg)


def _render_kpis(df):
    positives = df[df["valor"] > 0]
    k1, k2, k3 = st.columns(3)
    k1.metric("Total Gasto", _fmt_brl(positives["valor"].sum()))
    k2.metric("Transações", len(positives))
    k3.metric("Meses Analisados", df["mes_referencia"].nunique())


def _render_forecast(df):
    """Previsão de gasto do mês corrente (item 13)."""
    fc = analytics.forecast_current_month(df)
    if fc["projecao"] <= 0:
        return
    st.caption(f"📈 Previsão para {fc['mes']} ({fc['dias_restantes']} dias restantes)")
    f1, f2, f3 = st.columns(3)
    f1.metric("Gasto até agora", _fmt_brl(fc["gasto_atual"]))
    f2.metric("Projeção do mês", _fmt_brl(fc["projecao"]))
    f3.metric("Média histórica", _fmt_brl(fc["media_historica"]))


def _render_transactions_table(df):
    with st.expander("Ver todas as transações", expanded=False):
        cats = sorted(df["categoria"].unique().tolist())
        meses = sorted(df["mes_referencia"].unique().tolist())
        fc1, fc2 = st.columns(2)
        filtro_cat = fc1.multiselect("Filtrar por categoria", cats, default=cats)
        filtro_mes = fc2.multiselect("Filtrar por mês", meses, default=meses)
        df_filtered = df[df["categoria"].isin(filtro_cat) & df["mes_referencia"].isin(filtro_mes)]
        st.dataframe(
            df_filtered.style.format({"valor": "R$ {:.2f}"}),
            use_container_width=True,
            hide_index=True,
        )
        _download_buttons(df_filtered, "transacoes", "tx")


def _render_charts(df):
    cat_summary = eu.get_category_summary(df)
    monthly_summary = eu.get_monthly_summary(df)
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Gastos por Categoria")
        if not cat_summary.empty:
            fig_pie = px.pie(
                cat_summary, values="total", names="categoria", hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set3,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            fig_pie.update_layout(showlegend=False, margin=dict(t=10, b=10))
            st.plotly_chart(fig_pie, use_container_width=True)
    with col2:
        st.subheader("Gastos por Mês")
        if not monthly_summary.empty:
            fig_bar = px.bar(
                monthly_summary, x="mes_referencia", y="total", text_auto=".2f",
                color_discrete_sequence=["#636EFA"],
                labels={"mes_referencia": "Mês", "total": "Total (R$)"},
            )
            fig_bar.update_traces(texttemplate="R$ %{text}", textposition="outside")
            fig_bar.update_layout(margin=dict(t=10, b=10))
            st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("Top 10 Estabelecimentos")
    top = eu.get_top_merchants(df, 10)
    if not top.empty:
        fig_top = px.bar(
            top, x="total", y="descricao", orientation="h", color="categoria",
            text_auto=".2f", labels={"total": "Total (R$)", "descricao": "Estabelecimento"},
            color_discrete_sequence=px.colors.qualitative.Pastel,
        )
        fig_top.update_layout(yaxis={"categoryorder": "total ascending"}, margin=dict(t=10))
        fig_top.update_traces(texttemplate="R$ %{text}", textposition="outside")
        st.plotly_chart(fig_top, use_container_width=True)


def _render_budget(df):
    """Status de orçamento por categoria (item 7)."""
    budgets = storage.get_budgets(_user_id())
    status = analytics.budget_status(df, budgets)
    if status.empty:
        return
    st.divider()
    st.subheader("Orçamento por Categoria")
    for _, row in status.iterrows():
        pct = min(row["percentual"] / 100, 1.0)
        label = (
            f"{'🔴' if row['estourou'] else '🟢'} **{row['categoria']}** — "
            f"{_fmt_brl(row['gasto'])} de {_fmt_brl(row['limite'])} ({row['percentual']:.0f}%)"
        )
        st.write(label)
        st.progress(pct)
        if row["estourou"]:
            st.warning(f"Orçamento de {row['categoria']} estourado!")


def _render_recurring(df):
    """Gastos recorrentes / assinaturas (item 4)."""
    rec = recurring.detect_recurring(df)
    if rec.empty:
        return
    st.divider()
    st.subheader("Gastos Recorrentes e Assinaturas")
    assinaturas = rec[rec["is_assinatura"]]
    if not assinaturas.empty:
        st.caption(f"💳 {len(assinaturas)} provável(is) assinatura(s) detectada(s)")
    st.dataframe(
        rec.rename(columns={
            "descricao": "Estabelecimento", "categoria": "Categoria",
            "ocorrencias": "Ocorrências", "meses": "Meses",
            "valor_medio": "Valor médio", "total": "Total", "is_assinatura": "Assinatura?",
        }).style.format({"Valor médio": "R$ {:.2f}", "Total": "R$ {:.2f}"}),
        use_container_width=True, hide_index=True,
    )


def _render_month_comparison(df):
    """Comparação mês a mês com variação % (item 8)."""
    mom = analytics.month_over_month(df)
    if mom.empty or "variacao_%" not in mom.columns or mom["variacao_%"].isna().all():
        return
    st.divider()
    st.subheader("Comparação Mês a Mês")
    st.caption("Variação % entre os dois meses mais recentes, por categoria.")
    st.dataframe(mom, use_container_width=True, hide_index=True)


def _render_ai_analysis(df):
    st.subheader("Análise e Recomendações com IA")
    if st.button("Gerar Análise Completa"):
        with st.spinner("Analisando seus gastos..."):
            st.session_state["ai_insights"] = eu.get_ai_insights(df, model_name=_current_model())
    if "ai_insights" in st.session_state:
        st.markdown(st.session_state["ai_insights"])
        st.download_button(
            "⬇️ Baixar análise (Markdown)",
            st.session_state["ai_insights"].encode("utf-8"),
            file_name="analise.md",
            mime="text/markdown",
        )


# --------------------------------------------------------------------------- #
# Aba de chat
# --------------------------------------------------------------------------- #

def render_chat_tab():
    st.header("Assistente Financeiro")
    st.write("Faça perguntas sobre seus gastos e receba respostas personalizadas.")

    df: pd.DataFrame = st.session_state.get("expense_df", pd.DataFrame())
    if df.empty:
        st.info("Carregue suas faturas na aba **Gastos do Cartão** primeiro.")
        return

    with st.expander("Exemplos de perguntas"):
        st.markdown(
            """
- Qual categoria eu mais gastei?
- Quanto gastei com alimentação no mês passado?
- Quais gastos posso cortar para economizar R$ 200?
- Tenho algum gasto recorrente que poderia cancelar?
- Como meus gastos variaram entre os meses?
"""
        )

    st.session_state.setdefault("chat_history", [])
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
                answer = eu.chat_about_spending(df, question, model_name=_current_model())
            st.markdown(answer)
            st.session_state["chat_history"].append({"role": "assistant", "content": answer})


# --------------------------------------------------------------------------- #
# Aba de notas fiscais
# --------------------------------------------------------------------------- #

def render_invoice_tab():
    st.header("Extração de Dados de Notas Fiscais")
    st.write("Extraia campos estruturados de notas fiscais em PDF.")

    pdf = st.file_uploader(
        "Selecione notas fiscais (PDF)", type=["pdf"],
        accept_multiple_files=True, key="invoice_uploader",
    )

    if st.button("Extrair Dados"):
        if not pdf:
            st.warning("Selecione ao menos um arquivo PDF.")
            return
        with st.spinner(f"Extraindo dados com {_current_model()}..."):
            try:
                df = iu.create_docs(pdf, model_name=_current_model())
            except RuntimeError as e:
                st.error(str(e))
                return
        if df.empty:
            st.info("Nenhum arquivo processado ou sem dados extraídos.")
        else:
            st.dataframe(df, use_container_width=True)
            _download_buttons(df, "notas_fiscais", "nf")
            st.success("Extração concluída!")


def main():
    st.set_page_config(page_title="Analisador de Gastos", page_icon="💳", layout="wide")
    storage.init_db()
    st.session_state.setdefault("user_id", storage.guest_user_id())
    st.session_state.setdefault("username", storage.GUEST_USERNAME)

    st.title("💳 Analisador de Gastos — Cartão de Crédito")
    render_sidebar()

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
