"""Deactivate individual stocks and list remaining ETFs for selection."""
import psycopg
from urllib.parse import unquote

DATABASE_URL = "postgresql://postgres.yxmssjhujpazdkzwgvhi:%26K%265sCaJAsT5P-a@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
decoded_url = unquote(DATABASE_URL)

# Individual stocks to deactivate
INDIVIDUAL_STOCKS = [
    'AAPL', 'ACMR', 'AMD', 'AMZN', 'APP', 'ARCC', 'AS', 'AVGO', 'BE', 
    'CCJ', 'CRDO', 'FANG', 'FB', 'GOOGL', 'HIMS', 'HIVE', 'HNGE', 'IREN',
    'MARA', 'META', 'MSFT', 'NBIS', 'NVDA', 'OMDA', 'OSCR', 'PLTR', 
    'RIOT', 'SOFI', 'TSL', 'TSLA', 'TSM', 'UNH'
]

def main():
    with psycopg.connect(decoded_url) as conn:
        with conn.cursor() as cur:
            # Deactivate individual stocks
            print("=== Deactivating Individual Stocks ===")
            for symbol in INDIVIDUAL_STOCKS:
                cur.execute(
                    "UPDATE symbols SET is_active = FALSE WHERE symbol = %s",
                    (symbol,)
                )
                print(f"  Deactivated: {symbol}")
            
            conn.commit()
            print(f"\n✅ Deactivated {len(INDIVIDUAL_STOCKS)} individual stocks")
            
            # List remaining active symbols (ETFs and Indices)
            print("\n=== Remaining Active Symbols (ETFs & Indices) ===")
            cur.execute("""
                SELECT symbol, name 
                FROM symbols 
                WHERE is_active = TRUE 
                ORDER BY symbol
            """)
            rows = cur.fetchall()
            
            print(f"\nTotal active symbols: {len(rows)}\n")
            print(f"{'#':<4} {'Symbol':<10} | {'Name'}")
            print("-" * 60)
            for i, (symbol, name) in enumerate(rows, 1):
                print(f"{i:<4} {symbol:<10} | {name or ''}")
            
            # Save to file for review
            with open("scripts/active_etfs.txt", "w", encoding="utf-8") as f:
                f.write("Active ETFs & Indices for Review\n")
                f.write("=" * 60 + "\n\n")
                for i, (symbol, name) in enumerate(rows, 1):
                    f.write(f"{i:<4} {symbol:<10} | {name or ''}\n")
            
            print(f"\n📄 Saved to scripts/active_etfs.txt")


if __name__ == "__main__":
    main()
