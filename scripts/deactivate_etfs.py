"""Deactivate specified ETFs based on user selection."""
import psycopg
from urllib.parse import unquote

DATABASE_URL = "postgresql://postgres.yxmssjhujpazdkzwgvhi:%26K%265sCaJAsT5P-a@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
decoded_url = unquote(DATABASE_URL)

# Mapping from numbers to symbols (from previous output)
SYMBOL_MAP = {
    1: '^MOVE', 2: '^VIX', 3: '^VVIX', 4: '^VXN', 5: 'ACWI', 6: 'AGG',
    7: 'BIL', 8: 'BND', 9: 'BNDX', 10: 'CURE', 11: 'DBC', 12: 'DFEN',
    13: 'DIA', 14: 'DOG', 15: 'EFA', 16: 'EMB', 17: 'ERX', 18: 'ERY',
    19: 'FNGD', 20: 'FNGU', 21: 'GDX', 22: 'GLD', 23: 'GLDM', 24: 'GLU',
    25: 'GOVT', 26: 'HYG', 27: 'IAU', 28: 'IEF', 29: 'IEMG', 30: 'IRX',
    31: 'IWM', 32: 'IXUS', 33: 'JPST', 34: 'LABD', 35: 'LABU', 36: 'LQD',
    37: 'MDY', 38: 'MINT', 39: 'MUB', 40: 'NEAR', 41: 'NUGT', 42: 'NVDU',
    43: 'PDBC', 44: 'PSQ', 45: 'QID', 46: 'QLD', 47: 'QQQ', 48: 'SCHO',
    49: 'SDOW', 50: 'SDS', 51: 'SGOL', 52: 'SH', 53: 'SHV', 54: 'SHY',
    55: 'SLV', 56: 'SOX', 57: 'SOXL', 58: 'SOXX', 59: 'SPXL', 60: 'SPY',
    61: 'SQQQ', 62: 'SVXY', 63: 'TECL', 64: 'TIP', 65: 'TLT', 66: 'TMF',
    67: 'TMV', 68: 'TNA', 69: 'TQQQ', 70: 'ULST', 71: 'UNG', 72: 'UPRO',
    73: 'USO', 74: 'UTSL', 75: 'UVXY', 76: 'VCIT', 77: 'VCSH', 78: 'VEU',
    79: 'VFH', 80: 'VGT', 81: 'VHT', 82: 'VIX', 83: 'VIXY', 84: 'VMOT',
    85: 'VNQ', 86: 'VPU', 87: 'VT', 88: 'VTI', 89: 'VWO', 90: 'VXX',
    91: 'XLB', 92: 'XLC', 93: 'XLE', 94: 'XLF', 95: 'XLI', 96: 'XLK',
    97: 'XLP', 98: 'XLRE', 99: 'XLU', 100: 'XLV', 101: 'XLY', 102: 'XME'
}

# User specified: 1-16, 20-25, 27, 29-32, 36-39, 42-44, 27-52, 70-86
# Combined (unique): 1-16, 20-25, 27-52, 70-86
DEACTIVATE_INDICES = set()
for start, end in [(1, 16), (20, 25), (27, 52), (70, 86)]:
    DEACTIVATE_INDICES.update(range(start, end + 1))

def main():
    # Get symbols to deactivate
    symbols_to_deactivate = [SYMBOL_MAP[i] for i in sorted(DEACTIVATE_INDICES)]
    symbols_to_keep = [SYMBOL_MAP[i] for i in sorted(set(SYMBOL_MAP.keys()) - DEACTIVATE_INDICES)]
    
    print("=== ETFs to DEACTIVATE ===")
    print(", ".join(symbols_to_deactivate))
    print(f"\nTotal: {len(symbols_to_deactivate)}")
    
    print("\n=== ETFs to KEEP ===")
    print(", ".join(symbols_to_keep))
    print(f"\nTotal: {len(symbols_to_keep)}")
    
    with psycopg.connect(decoded_url) as conn:
        with conn.cursor() as cur:
            # Deactivate specified ETFs
            for symbol in symbols_to_deactivate:
                cur.execute(
                    "UPDATE symbols SET is_active = FALSE WHERE symbol = %s",
                    (symbol,)
                )
            conn.commit()
            print(f"\n✅ Deactivated {len(symbols_to_deactivate)} ETFs")
            
            # Show final active list
            print("\n=== FINAL Active Symbols ===")
            cur.execute("""
                SELECT symbol, name FROM symbols 
                WHERE is_active = TRUE ORDER BY symbol
            """)
            rows = cur.fetchall()
            print(f"Total active: {len(rows)}\n")
            for i, (symbol, name) in enumerate(rows, 1):
                print(f"{i:>3}. {symbol:<10} {name or ''}")


if __name__ == "__main__":
    main()
