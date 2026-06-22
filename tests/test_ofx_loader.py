import ofx_loader as o


class _Upload:
    def __init__(self, name, content: bytes):
        self.name = name
        self._content = content

    def getbuffer(self):
        return self._content


_OFX = b"""<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKTRANLIST>
<STMTTRN><TRNAMT>-50.00<DTPOSTED>20260215<MEMO>Compra Fev</STMTTRN>
<STMTTRN><TRNAMT>-30.00<DTPOSTED>20260305<MEMO>Compra Mar</STMTTRN>
</BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>"""


class TestMonthFromFilename:
    def test_iso_date(self):
        assert o._month_from_filename("Nubank_2026-03-01.ofx") == "03/2026"

    def test_year_month_only(self):
        assert o._month_from_filename("extrato_2026-07.ofx") == "07/2026"

    def test_compact(self):
        assert o._month_from_filename("Nubank20251201.ofx") == "12/2025"

    def test_no_date(self):
        assert o._month_from_filename("extrato.ofx") == ""

    def test_rejects_invalid_month(self):
        assert o._month_from_filename("file_2026-13-01.ofx") == ""


class TestParseOfx:
    def test_reference_month_comes_from_filename(self):
        """Todas as transações herdam o mês do extrato (nome do arquivo)."""
        df = o.parse_ofx(_Upload("Nubank_2026-03-01.ofx", _OFX))
        assert list(df["mes_referencia"]) == ["03/2026", "03/2026"]
        # Mas a data real de cada lançamento é preservada.
        assert list(df["data"]) == ["15/02/2026", "05/03/2026"]

    def test_falls_back_to_transaction_date(self):
        """Sem data no nome, mantém o mês derivado de cada transação."""
        df = o.parse_ofx(_Upload("extrato.ofx", _OFX))
        assert list(df["mes_referencia"]) == ["02/2026", "03/2026"]

    def test_amount_sign_flipped(self):
        df = o.parse_ofx(_Upload("x.ofx", _OFX))
        assert list(df["valor"]) == [50.0, 30.0]
