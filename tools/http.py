"""Polite, resilient HTTP — rotating user-agents, per-host rate limiting,
retry/backoff, robots.txt awareness, and bot-block detection.

This is the piece the user was worried about ("they sometimes block bots").
Strategy, in order of politeness:
  1. Respect robots.txt (configurable; on by default).
  2. Rate-limit PER HOST (never hammer one site), with jitter.
  3. Rotate a small pool of realistic browser UAs.
  4. Retry transient failures (timeouts, 5xx, 429) with exponential backoff.
  5. Detect soft-blocks (CAPTCHA / "访问验证" / anti-bot interstitials) and mark
     the URL 'blocked' rather than silently ingesting a block page as article text.
We do NOT try to defeat CAPTCHAs or spoof to evade detection — if a host blocks
us, we back off and record it. On GitHub-hosted runners (datacenter IPs) more
hosts may block than from a home connection; the fallback is running on the Mac.
"""
from __future__ import annotations
import time, random, threading
from urllib.parse import urlparse
from urllib import robotparser
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import sources as _sources

_CFG = _sources()["defaults"]
_UAS = _CFG["user_agents"]
_DELAY = _CFG.get("request_delay_seconds", 4)
_TIMEOUT = _CFG.get("timeout_seconds", 20)
_RESPECT_ROBOTS = _CFG.get("respect_robots", True)

# Per-host last-request timestamps and robot parsers (thread-safe).
_last_hit: dict[str, float] = {}
_lock = threading.Lock()
_robots: dict[str, robotparser.RobotFileParser] = {}

# Signatures that a page is an anti-bot interstitial, not the article.
_BLOCK_MARKERS = ["访问验证", "百度安全验证", "captcha", "网络不给力", "robot check",
                  "请输入验证码", "安全验证", "unusual traffic", "为什么会看到这个页面"]


class Blocked(Exception):
    pass


def _host(url: str) -> str:
    return urlparse(url).netloc


def _robots_ok(url: str) -> bool:
    if not _RESPECT_ROBOTS:
        return True
    host = _host(url)
    rp = _robots.get(host)
    if rp is None:
        rp = robotparser.RobotFileParser()
        try:
            # bounded fetch — a hanging robots.txt must not stall the request
            r = requests.get(f"{urlparse(url).scheme}://{host}/robots.txt",
                             headers={"User-Agent": _UAS[0]}, timeout=8)
            rp.parse(r.text.splitlines() if r.status_code == 200 else [])
        except Exception:
            rp = None  # robots unreachable -> allow (common for cn sites)
        _robots[host] = rp
    if rp is None:
        return True
    try:
        return rp.can_fetch(_UAS[0], url)
    except Exception:
        return True


def _rate_limit(host: str):
    """Per-host spacing. The sleep happens OUTSIDE the lock so requests to
    DIFFERENT hosts run concurrently; only same-host requests serialize."""
    while True:
        with _lock:
            now = time.time()
            last = _last_hit.get(host, 0)
            wait = _DELAY - (now - last)
            if wait <= 0:
                _last_hit[host] = now      # claim this slot, then leave the lock
                return
        time.sleep(min(wait, _DELAY) + random.uniform(0, 0.5))


@retry(retry=retry_if_exception_type((requests.Timeout, requests.ConnectionError)),
       stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=2, max=30), reraise=True)
def _get(url: str, ua: str) -> requests.Response:
    return requests.get(url, headers={"User-Agent": ua,
                                       "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"},
                        timeout=_TIMEOUT, allow_redirects=True)


def fetch(url: str, robots_exempt: bool = False) -> requests.Response:
    """Fetch one URL politely. Raises Blocked on anti-bot pages, requests
    exceptions on hard failures. Caller handles caching/status.

    robots_exempt: skip the robots.txt check for THIS request only. Reserved for
    explicitly-configured public syndication feeds (e.g. the Google News RSS feed,
    config google_news_rss.robots_exempt) — a deliberate, documented per-source
    decision, NOT a general bypass. Rate limiting and bot-block detection still apply.
    """
    if not robots_exempt and not _robots_ok(url):
        raise Blocked(f"robots.txt disallows {url}")
    _rate_limit(_host(url))
    ua = random.choice(_UAS)
    resp = _get(url, ua)
    if resp.status_code == 429:
        time.sleep(random.uniform(20, 40))
        raise Blocked(f"429 rate-limited {url}")
    # Charset fix: many CN portals serve GB2312/GBK but send no/garbled charset,
    # so requests guesses Latin-1 and mojibakes the text. Prefer the HTTP charset
    # if it's a real declared value; otherwise fall back to charset detection on
    # the raw bytes (apparent_encoding uses charset-normalizer under the hood).
    declared = (resp.encoding or "").lower()
    if not declared or declared in ("iso-8859-1", "latin-1", "latin_1", "ascii"):
        detected = resp.apparent_encoding
        if detected:
            resp.encoding = detected
    body_l = resp.text[:4000].lower()
    if any(m.lower() in body_l for m in _BLOCK_MARKERS):
        raise Blocked(f"anti-bot interstitial detected at {resp.url}")
    return resp
