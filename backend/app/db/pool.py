from typing import Any, Iterable, Optional, Sequence
from psycopg_pool import AsyncConnectionPool
from psycopg.rows import dict_row
from ..core.config import settings

pool: Optional[AsyncConnectionPool] = None

async def init_pool():
    global pool
    if pool is None:
        pool = AsyncConnectionPool(conninfo=settings.DATABASE_URL, max_size=10, kwargs={"autocommit": True})

async def close_pool():
    global pool
    if pool:
        await pool.close()
        pool = None

async def execute(query: str, params: Optional[Sequence[Any]] = None) -> int:
    assert pool is not None, "DB pool not initialized"
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(query, params or [])
            return cur.rowcount

async def fetch_all(query: str, params: Optional[Sequence[Any]] = None):
    assert pool is not None, "DB pool not initialized"
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params or [])
            return await cur.fetchall()

async def fetch_one(query: str, params: Optional[Sequence[Any]] = None):
    assert pool is not None, "DB pool not initialized"
    async with pool.connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params or [])
            return await cur.fetchone()
