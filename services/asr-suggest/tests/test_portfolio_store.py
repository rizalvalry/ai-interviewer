import portfolio_store


class TestValidate:
    def test_empty_name_rejected(self):
        assert portfolio_store.validate("", "isi CV") == "empty-name"

    def test_whitespace_only_name_rejected(self):
        assert portfolio_store.validate("   ", "isi CV") == "empty-name"

    def test_name_too_long_rejected(self):
        assert portfolio_store.validate("x" * 101, "isi CV") == "name-too-long"

    def test_name_at_max_len_accepted(self):
        assert portfolio_store.validate("x" * 100, "isi CV") is None

    def test_empty_content_rejected(self):
        assert portfolio_store.validate("CV", "") == "empty-content"

    def test_content_too_long_rejected(self):
        assert portfolio_store.validate("CV", "x" * 30001) == "content-too-long"

    def test_content_at_max_len_accepted(self):
        assert portfolio_store.validate("CV", "x" * 30000) is None

    def test_valid_input_passes(self):
        assert portfolio_store.validate("CV", "isi CV") is None


class TestCRUD:
    def test_list_empty_store_returns_empty_list(self, portfolio_db):
        assert portfolio_store.list_portfolios() == []

    def test_insert_then_list_shows_size_not_content(self, portfolio_db):
        portfolio_store.upsert_portfolio("CV-A", "isi CV lengkap")
        rows = portfolio_store.list_portfolios()
        assert len(rows) == 1
        assert rows[0]["name"] == "CV-A"
        assert rows[0]["size"] == len("isi CV lengkap")
        assert "content" not in rows[0]

    def test_get_by_id_returns_full_content(self, portfolio_db):
        created = portfolio_store.upsert_portfolio("CV-A", "isi CV lengkap")
        record = portfolio_store.get_portfolio(created["id"])
        assert record["content"] == "isi CV lengkap"

    def test_get_missing_id_returns_none(self, portfolio_db):
        assert portfolio_store.get_portfolio(999) is None

    def test_upsert_same_name_replaces_content_not_new_row(self, portfolio_db):
        first = portfolio_store.upsert_portfolio("CV-A", "versi 1")
        second = portfolio_store.upsert_portfolio("CV-A", "versi 2")
        assert first["id"] == second["id"]
        assert len(portfolio_store.list_portfolios()) == 1
        assert portfolio_store.get_portfolio(second["id"])["content"] == "versi 2"

    def test_different_names_create_separate_rows(self, portfolio_db):
        portfolio_store.upsert_portfolio("CV-A", "isi A")
        portfolio_store.upsert_portfolio("CV-B", "isi B")
        assert len(portfolio_store.list_portfolios()) == 2

    def test_delete_removes_row(self, portfolio_db):
        created = portfolio_store.upsert_portfolio("CV-A", "isi")
        assert portfolio_store.delete_portfolio(created["id"]) is True
        assert portfolio_store.list_portfolios() == []

    def test_delete_missing_id_returns_false(self, portfolio_db):
        assert portfolio_store.delete_portfolio(999) is False

    def test_data_survives_reconnect(self, portfolio_db):
        """Simulates docker compose down/up: same file path, fresh connection object."""
        created = portfolio_store.upsert_portfolio("CV-A", "isi CV")
        portfolio_store._reset_connection_for_tests()  # forces a brand-new sqlite3.connect()
        assert portfolio_store.get_portfolio(created["id"])["content"] == "isi CV"
