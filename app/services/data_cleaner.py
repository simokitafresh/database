"""Data cleaning utilities for fetched price data."""

import pandas as pd
from typing import Optional, Set

class DataCleaner:
    """Helper class for cleaning and validating price data."""
    
    REQUIRED_COLUMNS: Set[str] = {"open", "high", "low", "close", "volume"}
    
    @staticmethod
    def clean_price_data(df: pd.DataFrame) -> Optional[pd.DataFrame]:
        """
        Clean and validate price data from Yahoo Finance.
        
        1. Rename columns to lowercase
        2. Remove 'adj_close' if present
        3. Validate required columns
        
        Returns:
            Cleaned DataFrame or None if validation fails.
        """
        if df is None or df.empty:
            return None
            
        # Rename columns
        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )
        
        # Remove Adj Close if present (we use auto_adjust=True so Close is already adjusted)
        if "adj_close" in df.columns:
            df = df.drop(columns=["adj_close"])
            
        # Validate required columns
        if not DataCleaner.REQUIRED_COLUMNS.issubset(df.columns):
            return None
            
        return df
