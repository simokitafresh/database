from alembic import op


# revision identifiers, used by Alembic.
revision = "002_fn_prices_resolved"
down_revision = "001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION get_prices_resolved(
            _symbol text,
            _from date,
            _to date
        )
        RETURNS TABLE (
            symbol text,
            source_symbol text,
            date date,
            open double precision,
            high double precision,
            low double precision,
            close double precision,
            volume bigint,
            source text,
            last_updated timestamptz
        )
        LANGUAGE SQL
        AS $$
            SELECT
                _symbol AS symbol,
                p.symbol AS source_symbol,
                p.date,
                p.open,
                p.high,
                p.low,
                p.close,
                p.volume,
                p.source,
                p.last_updated
            FROM prices p
            WHERE p.symbol = _symbol
              AND p.date BETWEEN _from AND _to
            UNION ALL
            SELECT
                _symbol AS symbol,
                p.symbol AS source_symbol,
                p.date,
                p.open,
                p.high,
                p.low,
                p.close,
                p.volume,
                p.source,
                p.last_updated
            FROM symbol_changes sc
            JOIN prices p
              ON p.symbol = sc.old_symbol
             AND p.date < sc.change_date
            WHERE sc.new_symbol = _symbol
              AND p.date BETWEEN _from AND _to
            ORDER BY date
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS get_prices_resolved(text, date, date);")
