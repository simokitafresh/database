"""日付範囲処理ユーティリティ"""
from datetime import date, timedelta
from typing import List, Tuple


def merge_date_ranges(ranges: List[Tuple[date, date]]) -> List[Tuple[date, date]]:
    """重複する日付範囲をマージする"""
    if not ranges:
        return []

    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    merged = [sorted_ranges[0]]

    for current_start, current_end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]

        if current_start <= last_end + timedelta(days=1):
            merged[-1] = (last_start, max(last_end, current_end))
        else:
            merged.append((current_start, current_end))

    return merged


def validate_date_range(start: date, end: date) -> dict:
    """日付範囲の妥当性を検証"""
    if start > end:
        return {
            "valid": False,
            "reason": "start_after_end",
            "message": f"Start date {start} is after end date {end}",
        }

    if end > date.today():
        return {
            "valid": False,
            "reason": "future_date",
            "message": f"End date {end} is in the future",
        }

    min_date = date.today() - timedelta(days=365 * 20)
    if start < min_date:
        return {
            "valid": True,
            "warning": "very_old_date",
            "message": f"Start date {start} is very old, data may not be available",
        }

    return {
        "valid": True,
        "message": "Date range is valid",
    }
