import pandas as pd

import categories
import recurring
import analytics


def _sample_df():
    return pd.DataFrame(
        [
            {"arquivo": "f", "mes_referencia": "01/2026", "data": "05/01/2026",
             "descricao": "NETFLIX *123", "categoria": "Outros", "valor": 39.90, "parcela": ""},
            {"arquivo": "f", "mes_referencia": "02/2026", "data": "05/02/2026",
             "descricao": "Netflix", "categoria": "Outros", "valor": 39.90, "parcela": ""},
            {"arquivo": "f", "mes_referencia": "02/2026", "data": "10/02/2026",
             "descricao": "IFOOD restaurante", "categoria": "Outros", "valor": 50.0, "parcela": ""},
            {"arquivo": "f", "mes_referencia": "01/2026", "data": "10/01/2026",
             "descricao": "IFOOD lanche", "categoria": "Outros", "valor": 30.0, "parcela": ""},
        ]
    )


class TestCategories:
    def test_builtin_rule_match(self):
        assert categories.categorize("Pagamento NETFLIX") == "Streaming"
        assert categories.categorize("Corrida UBER") == "Transporte"

    def test_user_rule_priority(self):
        rules = [{"pattern": "netflix", "categoria": "Lazer"}]
        assert categories.categorize("netflix", rules) == "Lazer"

    def test_no_match_returns_none(self):
        assert categories.categorize("loja desconhecida xyz") is None

    def test_apply_rules_overrides_column(self):
        df = _sample_df()
        out = categories.apply_rules(df)
        assert out.loc[0, "categoria"] == "Streaming"

    def test_normalize_merchant(self):
        assert categories.normalize_merchant("NETFLIX *123 05/01") == "netflix"


class TestRecurring:
    def test_detects_netflix_subscription(self):
        rec = recurring.detect_recurring(_sample_df())
        netflix = rec[rec["descricao"].str.lower().str.contains("netflix")]
        assert not netflix.empty
        assert bool(netflix.iloc[0]["is_assinatura"]) is True

    def test_empty_df(self):
        assert recurring.detect_recurring(pd.DataFrame()).empty


class TestAnalytics:
    def test_budget_status_flags_overflow(self):
        df = _sample_df()
        status = analytics.budget_status(categories.apply_rules(df), {"Alimentação": 40.0})
        assert not status.empty
        row = status[status["categoria"] == "Alimentação"].iloc[0]
        assert row["gasto"] == 80.0
        assert row["estourou"]

    def test_month_over_month(self):
        mom = analytics.month_over_month(_sample_df())
        assert "variacao_%" in mom.columns

    def test_forecast_no_data(self):
        fc = analytics.forecast_current_month(pd.DataFrame())
        assert fc["projecao"] == 0.0
