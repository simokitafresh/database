"""Set only specific symbols as active."""
import psycopg
from urllib.parse import unquote

DATABASE_URL = "postgresql://postgres.yxmssjhujpazdkzwgvhi:%26K%265sCaJAsT5P-a@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
decoded_url = unquote(DATABASE_URL)

# User's final selection (11 symbols)
# Note: LQLD -> assumed QLD (leveraged QQQ ETF)
KEEP_ACTIVE = [
    'TQQQ', 'TECL', 'XLU', 'QLD', 'QQQ', 'SPY', '^VIX', 'GLD', 'GDX', 'TMV', 'TMF'
]

def main():
    with psycopg.connect(decoded_url) as conn:
        with conn.cursor() as cur:
            # First, deactivate ALL symbols
            cur.execute("UPDATE symbols SET is_active = FALSE")
            print(f"Deactivated all symbols")
            
            # Then, activate only the specified ones
            activated = []
            not_found = []
            for symbol in KEEP_ACTIVE:
                cur.execute(
                    "UPDATE symbols SET is_active = TRUE WHERE symbol = %s RETURNING symbol",
                    (symbol,)
                )
                result = cur.fetchone()
                if result:
                    activated.append(symbol)
                else:
                    not_found.append(symbol)
            
            conn.commit()
            
            print(f"\n✅ Activated {len(activated)} symbols:")
            for s in activated:
                print(f"   • {s}")
            
            if not_found:
                print(f"\n⚠️ Not found in database:")
                for s in not_found:
                    print(f"   • {s}")
            
            # Show final status
            print("\n=== Final Active Symbols ===")
            cur.execute("""
                SELECT symbol, name FROM symbols 
                WHERE is_active = TRUE ORDER BY symbol
            """)
            rows = cur.fetchall()
            print(f"Total: {len(rows)}")
            for symbol, name in rows:
                print(f"   {symbol:<10} {name or ''}")


if __name__ == "__main__":
    main()
