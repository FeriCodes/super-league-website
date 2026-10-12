import asyncio
from typing import Any, Dict, List, Optional
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
# 2. MULTI-TIER CACHE ARCHITECTURE
# ==========================================
# Short-term cache (60s) for live matches, prov-bonus, and gw points
live_cache = TTLCache(maxsize=1000, ttl=60)

# Long-term cache (6 hours) for bootstrap-static and fixtures
static_cache = TTLCache(maxsize=200, ttl=21600)

# Persistent profile cache (24 hours) for manager and team names
profile_cache = TTLCache(maxsize=500, ttl=86400)

# Semaphore to safeguard against FPL rate limits
fpl_semaphore = asyncio.Semaphore(15)

# ==========================================
# 3. HTTPX ASYNC CLIENT POOL
# ==========================================
limits = httpx.Limits(max_keepalive_connections=40, max_connections=80)
timeout = httpx.Timeout(10.0, connect=4.0)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """Returns a shared, persistent HTTPX async client instance."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(headers=HEADERS, limits=limits, timeout=timeout, http2=False)
    return _client


def _resolve_cache(endpoint: str) -> TTLCache:
    """Routes endpoint to appropriate cache tier based on volatility."""
    if endpoint.startswith("entry/") and not endpoint.endswith("picks"):
        return profile_cache
    if endpoint in ["bootstrap-static", "fixtures"]:
        return static_cache
    return live_cache


# ==========================================
# 4. UNIFIED FETCH FUNCTION
# ==========================================
async def fetch_fpl_api(endpoint: str, bypass_cache: bool = False) -> Optional[Any]:
    """
    Fetch data from official FPL API with tiered caching and rate limiting.
    """
    clean_endpoint = endpoint.strip("/")
    target_cache = _resolve_cache(clean_endpoint)

    if not bypass_cache and clean_endpoint in target_cache:
        return target_cache[clean_endpoint]

    url = f"https://fantasy.premierleague.com/api/{clean_endpoint}/"
    client = get_client()

    async with fpl_semaphore:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

            target_cache[clean_endpoint] = data
            return data

        except httpx.HTTPStatusError as exc:
            print(f"[FPL Client Error] Status {exc.response.status_code} for URL: {url}")
            return None
        except httpx.RequestError as exc:
            print(f"[FPL Client Network Error] {exc} for URL: {url}")
            return None


async def fetch_multiple_endpoints(endpoints: List[str]) -> List[Optional[Any]]:
    """Concurrently fetches multiple endpoints with parallel async tasks."""
    tasks = [fetch_fpl_api(ep) for ep in endpoints]
    return await asyncio.gather(*tasks)


async def close_fpl_client():
    """Gracefully closes HTTPX connection pools during app shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
