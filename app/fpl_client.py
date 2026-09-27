import asyncio
from typing import Any, Optional
import httpx
from cachetools import TTLCache

# ==========================================
# 1. NETWORK & HEADER CONFIGURATION
# ==========================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://fantasy.premierleague.com/",
    "Origin": "https://fantasy.premierleague.com",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# ==========================================
# 2. IN-MEMORY CACHE (TTL = Time To Live)
# ==========================================
# 120 seconds cache: perfect balance between live score updates and zero server load
fpl_cache = TTLCache(maxsize=1500, ttl=120)

# Semaphore: never blast more than 10 requests at the exact same millisecond to FPL
fpl_semaphore = asyncio.Semaphore(10)

# ==========================================
# 3. HTTPX ASYNC CLIENT POOL
# ==========================================
limits = httpx.Limits(max_keepalive_connections=30, max_connections=60)
timeout = httpx.Timeout(12.0, connect=5.0)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """Returns a shared, persistent HTTPX async client instance."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(headers=HEADERS, limits=limits, timeout=timeout, http2=False)
    return _client


# ==========================================
# 4. UNIFIED FETCH FUNCTION
# ==========================================
async def fetch_fpl_api(endpoint: str, bypass_cache: bool = False) -> Optional[Any]:
    """
    Core function to fetch data from official Fantasy Premier League API.
    Handles caching, connection pooling, and rate-limit safety automatically.
    """
    clean_endpoint = endpoint.strip("/")
    cache_key = clean_endpoint

    # 1. Cache hit check
    if not bypass_cache and cache_key in fpl_cache:
        return fpl_cache[cache_key]

    url = f"https://fantasy.premierleague.com/api/{clean_endpoint}/"
    client = get_client()

    # 2. Safe request via semaphore
    async with fpl_semaphore:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            # Save in memory
            fpl_cache[cache_key] = data
            return data

        except httpx.HTTPStatusError as exc:
            print(f"[FPL Client Error] Status code {exc.response.status_code} for URL: {url}")
            return None
        except httpx.RequestError as exc:
            print(f"[FPL Client Network Error] {exc} for URL: {url}")
            return None


async def close_fpl_client():
    """Gracefully closes HTTPX connection pools during app shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
