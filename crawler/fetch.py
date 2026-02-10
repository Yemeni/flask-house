from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib import robotparser

import requests

from models import AppSetting

DEFAULT_UA = "flask-house-crawler/0.1 (+https://localhost)"


class PoliteFetcher:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DEFAULT_UA})
        self.last_request_ts = 0.0
        self.robots_cache: dict[str, robotparser.RobotFileParser] = {}

    def _get_rate_limit(self) -> float:
        setting = AppSetting.query.filter_by(key="crawl_rate_limit_seconds").first()
        return float(setting.value) if setting else 1.5

    def _get_timeout(self) -> int:
        setting = AppSetting.query.filter_by(key="http_timeout_seconds").first()
        return int(float(setting.value)) if setting else 15

    def allowed_by_robots(self, url: str) -> tuple[bool, str]:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = self.robots_cache.get(parsed.netloc)
        if not parser:
            parser = robotparser.RobotFileParser()
            parser.set_url(robots_url)
            try:
                parser.read()
            except Exception as exc:
                return False, f"robots.txt unavailable: {exc}"
            self.robots_cache[parsed.netloc] = parser
        if not parser.can_fetch(DEFAULT_UA, url):
            return False, "Blocked by robots.txt"
        return True, ""

    def get(self, url: str, retries: int = 3) -> tuple[str | None, str | None]:
        allowed, reason = self.allowed_by_robots(url)
        if not allowed:
            return None, reason

        for attempt in range(retries):
            wait = self._get_rate_limit() - (time.time() - self.last_request_ts)
            if wait > 0:
                time.sleep(wait)
            try:
                resp = self.session.get(url, timeout=self._get_timeout())
                self.last_request_ts = time.time()
                if resp.status_code >= 400:
                    return None, f"HTTP {resp.status_code}"
                return resp.text, None
            except requests.RequestException as exc:
                if attempt == retries - 1:
                    return None, f"request failed: {exc}"
                time.sleep(1.5 * (attempt + 1))
        return None, "unknown fetch error"
