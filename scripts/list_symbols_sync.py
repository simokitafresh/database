"""List all symbols in the database using synchronous psycopg."""
import psycopg
from urllib.parse import unquote

# Database URL (sync version)
DATABASE_URL = "postgresql://postgres.yxmssjhujpazdkzwgvhi:%26K%265sCaJAsT5P-a@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"

# Decode URL-encoded password
decoded_url = unquote(DATABASE_URL)

def main():
    with psycopg.connect(decoded_url) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT symbol, name, exchange, is_active 
                FROM symbols 
                ORDER BY symbol
            """)
            rows = cur.fetchall()
            
            output_lines = []
            output_lines.append(f"Total symbols: {len(rows)}")
            output_lines.append("")
            output_lines.append(f"{'Symbol':<10} | {'Name':<40} | {'Exchange':<10} | {'Active'}")
            output_lines.append("-" * 80)
            for r in rows:
                symbol, name, exchange, is_active = r
                output_lines.append(f"{symbol:<10} | {str(name or '')[:40]:<40} | {str(exchange or ''):<10} | {is_active}")
            
            # Print and save to file
            for line in output_lines:
                print(line)
            
            with open("scripts/symbols_list.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(output_lines))
            print(f"\nSaved to scripts/symbols_list.txt")


if __name__ == "__main__":
    main()

