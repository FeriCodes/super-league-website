import asyncio
import random
from typing import Any, Dict, List, Optional, Sequence

import httpx
from cachetools import TTLCache

BASE_URL = "https://fantasy.premierleague.com/api/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://fantasy.premierleague.com/",
    "Origin": "https://fantasy.premierleague.com",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}

# ==========================================
# 1. CACHE TIERS
# ==========================================
# Live GW data (event/{gw}/live): refreshed every minute while matches are on.
live_cache = TTLCache(maxsize=500, ttl=60)

# Picks of a running GW: lineups/chips/hits are locked at the deadline, so 2 hours is completely safe.
picks_cache = TTLCache(maxsize=2000, ttl=7200)

# bootstrap-static / fixtures: 5 minutes, so injury news and data_checked stay fresh.
static_cache = TTLCache(maxsize=50, ttl=300)

# Manager names rarely change (24 hours).
profile_cache = TTLCache(maxsize=2000, ttl=86400)

# Finished and data_checked GW data. Never changes, so it is kept for 6 hours.
final_cache = TTLCache(maxsize=5000, ttl=6 * 3600)

# Last successful response for every endpoint as fallback.
stale_cache: Dict[str, Any] = {}

# ==========================================
# 2. CONCURRENCY AND RETRY POLICY
# ==========================================
MAX_CONCURRENCY = 4
MAX_ATTEMPTS = 3
BASE_RETRY_DELAY = 0.35
MAX_RETRY_AFTER = 5.0
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}

fpl_semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

limits = httpx.Limits(max_keepalive_connections=20, max_connections=30)
timeout = httpx.Timeout(4.5, connect=2.5)

_client: Optional[httpx.AsyncClient] = None


def get_client() -> httpx.AsyncClient:
    """Returns the shared HTTPX client."""
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(headers=HEADERS, limits=limits, timeout=timeout, http2=False)
    return _client


def _resolve_cache(endpoint: str) -> TTLCache:
    """Picks the cache tier for an endpoint."""
    if endpoint.startswith("entry/"):
        if "/picks" in endpoint:
            return picks_cache
        return profile_cache
    if endpoint in ("bootstrap-static", "fixtures"):
        return static_cache
    return live_cache


def _retry_after_seconds(response: httpx.Response) -> Optional[float]:
    value = response.headers.get("Retry-After", "")
    if value.isdigit():
        return min(float(value), MAX_RETRY_AFTER)
    return None


# ==========================================
# 3. FETCH FUNCTIONS
# ==========================================
async def fetch_fpl_api(
    endpoint: str,
    final: bool = False,
    allow_stale: bool = True,
    bypass_cache: bool = False,
) -> Optional[Any]:
    """
    Fetch one FPL endpoint safely with caching, fast retries, and stale fallback.
    """
    clean = endpoint.strip("/")
    cache = final_cache if final else _resolve_cache(clean)

    if not bypass_cache and clean in cache:
        return cache[clean]

    url = BASE_URL + clean + "/"
    client = get_client()
    reason = "unknown"

    for attempt in range(1, MAX_ATTEMPTS + 1):
        retry_after = None
        try:
            async with fpl_semaphore:
                if not bypass_cache and clean in cache:
                    return cache[clean]
                response = await client.get(url)

            if response.status_code == 200:
                data = response.json()
                cache[clean] = data
                stale_cache[clean] = data
                return data

            if response.status_code in RETRY_STATUS_CODES:
                reason = f"status {response.status_code}"
                retry_after = _retry_after_seconds(response)
            else:
                print(f"[FPL] status {response.status_code} for {url}")
                reason = f"status {response.status_code}"
                break

        except httpx.RequestError as exc:
            reason = f"network error: {exc!r}"
        except ValueError as exc:
            reason = f"invalid json: {exc}"
            break

        if attempt < MAX_ATTEMPTS:
            delay = retry_after if retry_after is not None else BASE_RETRY_DELAY * attempt
            await asyncio.sleep(delay + random.uniform(0.05, 0.15))

    print(f"[FPL] giving up on {clean} after {attempt} attempt(s): {reason}")

    if allow_stale and clean in stale_cache:
        print(f"[FPL] using last good copy of {clean}")
        return stale_cache[clean]
    return None


async def fetch_many(
    endpoints: Sequence[str],
    final: bool = False,
    allow_stale: bool = True,
) -> List[Optional[Any]]:
    """Fetch multiple endpoints with controlled concurrency."""
    return list(await asyncio.gather(*(fetch_fpl_api(ep, final=final, allow_stale=allow_stale) for ep in endpoints)))


async def fetch_multiple_endpoints(endpoints: List[str]) -> List[Optional[Any]]:
    """Alias for backward compatibility."""
    return await fetch_many(endpoints, allow_stale=True)


async def close_fpl_client():
    """Closes the HTTPX pool on shutdown."""
    global _client
    if _client is not None and not _client.is_closed:
        await _client.aclose()
