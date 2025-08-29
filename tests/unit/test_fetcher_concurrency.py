from datetime import date

import anyio
import pandas as pd
import pytest

from app.db import queries


@pytest.mark.anyio
async def test_fetch_prices_df_respects_concurrency_limit(mocker):
    max_running = 0
    running = 0

    async def fake_run_in_threadpool(func, *args, **kwargs):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await anyio.sleep(0.01)
        running -= 1
        return pd.DataFrame()

    mocker.patch("app.db.queries.run_in_threadpool", side_effect=fake_run_in_threadpool)
    mocker.patch("app.db.queries.fetch_prices")
    queries._fetch_semaphore = anyio.Semaphore(2)

    async with anyio.create_task_group() as tg:
        for _ in range(5):
            tg.start_soon(
                queries.fetch_prices_df, "AAPL", date(2024, 1, 1), date(2024, 1, 2)
            )

    assert max_running <= 2
