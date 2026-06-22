import expenseutil as eu


class TestParseValue:
    def test_int_and_float(self):
        assert eu._parse_value(10) == 10.0
        assert eu._parse_value(12.5) == 12.5

    def test_brazilian_format(self):
        assert eu._parse_value("1.234,56") == 1234.56
        assert eu._parse_value("R$ 1.234,56") == 1234.56

    def test_us_format(self):
        assert eu._parse_value("1234.56") == 1234.56

    def test_comma_decimal_only(self):
        assert eu._parse_value("99,90") == 99.90

    def test_negative(self):
        assert eu._parse_value("-50,00") == -50.0

    def test_garbage_returns_zero(self):
        assert eu._parse_value("abc") == 0.0
        assert eu._parse_value(None) == 0.0


class TestFilterStatementText:
    def test_keeps_lines_with_dates(self):
        text = "CABECALHO BANCO\n01/03 IFOOD 45,90\nrodape juridico irrelevante"
        out = eu._filter_statement_text(text)
        assert "IFOOD" in out
        assert "CABECALHO BANCO" not in out

    def test_keeps_lines_with_amounts(self):
        text = "texto qualquer\nNETFLIX 39,90\n"
        out = eu._filter_statement_text(text)
        assert "NETFLIX 39,90" in out

    def test_respects_max_chars(self):
        text = "01/03 X 1,00\n" * 1000
        out = eu._filter_statement_text(text, max_chars=50)
        assert len(out) <= 50

    def test_empty_returns_original(self):
        assert eu._filter_statement_text("sem nada relevante") == "sem nada relevante"


class TestRobustJsonParse:
    def test_plain_json(self):
        assert eu._robust_json_parse('{"a": 1}') == {"a": 1}

    def test_json_with_surrounding_text(self):
        assert eu._robust_json_parse('lixo antes {"a": 1} lixo depois') == {"a": 1}

    def test_trailing_comma(self):
        assert eu._robust_json_parse('{"a": 1,}') == {"a": 1}

    def test_single_quotes(self):
        assert eu._robust_json_parse("{'a': 1}") == {"a": 1}

    def test_empty_or_invalid(self):
        assert eu._robust_json_parse("") == {}
        assert eu._robust_json_parse("não é json") == {}
