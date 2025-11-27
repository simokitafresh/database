import logging
from datetime import date, datetime, timedelta
from typing import List, Optional

import pandas as pd
import requests
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.db.models import EconomicIndicator

logger = logging.getLogger(__name__)

class FredService:
    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch_dtb3_data(self, start_date: Optional[date] = None, end_date: Optional[date] = None) -> List[dict]:
        """
        Fetch DTB3 (3-Month Treasury Bill Secondary Market Rate) data from FRED.
        """
        if not self.api_key:
            logger.warning("FRED_API_KEY is not set. Skipping fetch.")
            return []

        params = {
            "series_id": "DTB3",
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date.strftime("%Y-%m-%d") if start_date else None,
            "observation_end": end_date.strftime("%Y-%m-%d") if end_date else None,
        }

        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=settings.FETCH_TIMEOUT_SECONDS)
            response.raise_for_status()
            data = response.json()
            
            observations = data.get("observations", [])
            results = []
            for obs in observations:
                try:
                    # FRED returns "." for missing values
                    value = obs.get("value")
                    if value == ".":
                        continue
                        
                    results.append({
                        "date": datetime.strptime(obs["date"], "%Y-%m-%d").date(),
                        "value": float(value),
                        "symbol": "DTB3"
                    })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse observation {obs}: {e}")
                    continue
            
            return results

        except requests.RequestException as e:
            logger.error(f"Error fetching data from FRED: {e}")
            return []

    def save_economic_data(self, db: Session, data: List[dict]):
        """
        Save economic data to the database (Sync version).
        """
        if not data:
            return

        stmt = insert(EconomicIndicator).values(data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "date"],
            set_={"value": stmt.excluded.value, "last_updated": datetime.now()}
        )

        try:
            db.execute(stmt)
            db.commit()
            logger.info(f"Saved {len(data)} economic indicators to database.")
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving economic data: {e}")
            raise

    async def save_economic_data_async(self, db: AsyncSession, data: List[dict]):
        """
        Save economic data to the database (Async version).
        """
        if not data:
            return

        stmt = insert(EconomicIndicator).values(data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol", "date"],
            set_={"value": stmt.excluded.value, "last_updated": datetime.now()}
        )

        try:
            await db.execute(stmt)
            await db.commit()
            logger.info(f"Saved {len(data)} economic indicators to database.")
        except Exception as e:
            await db.rollback()
            logger.error(f"Error saving economic data: {e}")
            raise

def get_fred_service() -> FredService:
    return FredService(api_key=settings.FRED_API_KEY)
