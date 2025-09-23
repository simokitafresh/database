"""Update get_prices_resolved to support multiple symbols"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 既存の関数を削除
    op.execute("DROP FUNCTION IF EXISTS get_prices_resolved(text, date, date);")

    # 新しいバッチ対応関数を作成
    op.execute(
        """
        CREATE OR REPLACE FUNCTION get_prices_resolved(_symbols text[], _from date, _to date)
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
        SELECT DISTINCT
            pr.symbol,
            pr.date,
            pr.open::double precision,
            pr.high::double precision,
            pr.low::double precision,
            pr.close::double precision,
            pr.volume,
            pr.source,
            pr.last_updated,
            pr.source_symbol
        FROM (
            SELECT p.symbol,
                   p.date,
                   p.open,
                   p.high,
                   p.low,
                   p.close,
                   p.volume,
                   p.source,
                   p.last_updated,
                   NULL::text AS source_symbol,
                   sc.old_symbol,
                   sc.new_symbol,
                   sc.change_date
              FROM prices p
         LEFT JOIN symbol_changes sc ON sc.new_symbol = p.symbol
             WHERE p.symbol = ANY(_symbols)
               AND p.date BETWEEN _from AND _to
               AND (sc.change_date IS NULL OR p.date >= sc.change_date)

            UNION ALL

            SELECT _symbol AS symbol,
                   p.date,
                   p.open,
                   p.high,
                   p.low,
                   p.close,
                   p.volume,
                   p.source,
                   p.last_updated,
                   p.symbol AS source_symbol,
                   sc.old_symbol,
                   sc.new_symbol,
                   sc.change_date
              FROM prices p
              JOIN symbol_changes sc ON sc.old_symbol = p.symbol
             WHERE sc.new_symbol = ANY(_symbols)
               AND p.date BETWEEN _from AND _to
               AND p.date < sc.change_date
        ) pr
        ORDER BY pr.symbol, pr.date;
        $$;
        """
    )


def downgrade() -> None:
    # 新しい関数を削除
    op.execute("DROP FUNCTION IF EXISTS get_prices_resolved(text[], date, date);")

    # 古い関数を復元
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