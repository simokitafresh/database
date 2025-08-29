from alembic import op

# revision identifiers, used by Alembic.
revision = "002_fn_prices_resolved"
down_revision = "001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION get_prices_resolved(_symbol text, _from date, _to date)
        RETURNS TABLE (
            symbol text,
            date date,
            open double precision,
            high double precision,
            low double precision,
            close double precision,
            volume bigint,
            source text,
            last_updated timestamptz,
            source_symbol text
        )
        LANGUAGE sql
        AS $$
        WITH sc AS (
            SELECT old_symbol, new_symbol, change_date
              FROM symbol_changes
             WHERE new_symbol = _symbol
             LIMIT 1
        )
        SELECT p.symbol,
               p.date,
               p.open::double precision,
               p.high::double precision,
               p.low::double precision,
               p.close::double precision,
               p.volume,
               p.source,
               p.last_updated,
               NULL::text AS source_symbol
          FROM prices p
     LEFT JOIN sc ON TRUE
         WHERE p.symbol = _symbol
           AND p.date BETWEEN _from AND _to
           AND (sc.change_date IS NULL OR p.date >= sc.change_date)

        UNION ALL

        SELECT _symbol AS symbol,
               p.date,
               p.open::double precision,
               p.high::double precision,
               p.low::double precision,
               p.close::double precision,
               p.volume,
               p.source,
               p.last_updated,
               p.symbol AS source_symbol
          FROM prices p
          JOIN sc ON sc.old_symbol = p.symbol
         WHERE p.date BETWEEN _from AND _to
           AND p.date < sc.change_date

         ORDER BY date;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS get_prices_resolved(text, date, date);")

