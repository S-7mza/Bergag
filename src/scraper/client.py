import asyncio
import logging
import random
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.config.settings import settings

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,ar;q=0.8,en-US;q=0.7,en;q=0.6",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1"
}

class PortalHttpClient:
    """
    WAF-resilient HTTP client using httpx.AsyncClient with persistent cookies 
    (TS01c367b8, DCOOKIE, SERVERID) and browser headers.
    """
    def __init__(self, base_url: str = "https://www.marchespublics.gov.ma"):
        self.base_url = base_url
        self.rate_limit_seconds = settings.scraper_rate_limit_seconds
        self.proxy_url = settings.proxy_url
        self.client: httpx.AsyncClient | None = None
        self._session_initialized = False

    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None or self.client.is_closed:
            self.client = httpx.AsyncClient(
                headers=DEFAULT_HEADERS,
                timeout=httpx.Timeout(connect=15.0, read=45.0, write=15.0, pool=60.0),
                follow_redirects=True,
                proxy=self.proxy_url if self.proxy_url else None
            )
            self._session_initialized = False
        return self.client

    async def _ensure_session(self, client: httpx.AsyncClient):
        """Initial handshake to acquire F5 ASM session cookies (TS01c367b8, DCOOKIE)"""
        if not self._session_initialized:
            try:
                handshake_url = f"{self.base_url}/bdc/entreprise/consultation/"
                logger.debug(f"Performing initial WAF session handshake with {handshake_url}")
                resp = await client.get(handshake_url)
                if resp.status_code == 200:
                    self._session_initialized = True
            except Exception as e:
                logger.warning(f"Initial WAF handshake notice: {e}")

    async def _polite_delay(self):
        """Applies a jittered polite rate delay (e.g. 1.0s +/- 0.3s)"""
        jitter = random.uniform(-0.25, 0.35)
        delay = max(0.5, self.rate_limit_seconds + jitter)
        await asyncio.sleep(delay)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=10),
        retry=retry_if_exception_type((httpx.RequestError, TimeoutError))
    )
    async def get(self, url: str, params: dict | None = None) -> str:
        client = await self._get_client()
        await self._ensure_session(client)
        await self._polite_delay()

        full_url = url if url.startswith("http") else f"{self.base_url}{url}"
        
        # Protect against unencoded brackets triggering F5 WAF RFC violations
        if "[" in full_url or "]" in full_url:
            full_url = full_url.replace("[", "%5B").replace("]", "%5D")

        logger.debug(f"Fetching URL: {full_url}")

        response = await client.get(full_url, params=params)
        
        if response.status_code == 403:
            logger.error(f"F5 WAF 403 Forbidden encountered at {full_url}")
            raise httpx.RequestError(f"WAF 403 Forbidden on {full_url}")

        response.raise_for_status()
        return response.text

    async def download_binary(self, url: str) -> bytes:
        client = await self._get_client()
        await self._polite_delay()

        full_url = url if url.startswith("http") else f"{self.base_url}{url}"
        response = await client.get(full_url)
        response.raise_for_status()
        return response.content

    async def close(self):
        if self.client and not self.client.is_closed:
            await self.client.aclose()
            self.client = None
