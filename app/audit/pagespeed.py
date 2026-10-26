"""Google PageSpeed Insights: mobile performance score for a page."""
import logging
import os
import time

import httpx

from app.audit.checks import PAGESPEED, Finding

log = logging.getLogger(__name__)

API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedError(Exception):
    pass


def run_pagespeed(url: str, *, transport: httpx.BaseTransport | None = None, sleep=time.sleep) -> Finding:
    """Ask Google to test the page on a simulated phone. Takes 10-60 seconds."""
    params = {"url": url, "strategy": "mobile", "category": "performance"}
    key = os.getenv("GOOGLE_PAGESPEED_API_KEY")
    if key:
        params["key"] = key
    last = "no response"
    with httpx.Client(timeout=120, transport=transport) as client:
        for attempt in range(3):
            try:
                r = client.get(API_URL, params=params)
            except httpx.HTTPError as e:
                last = type(e).__name__
            else:
                if r.status_code == 200:
                    return _finding(r.json())
                # Google's error message never includes the key, but keep it short anyway.
                last = f"HTTP {r.status_code}"
                if r.status_code not in (429, 500, 502, 503, 504):
                    if r.status_code in (400, 403) and not key:
                        last += " (add GOOGLE_PAGESPEED_API_KEY to .env)"
                    break
            if attempt < 2:
                sleep(5 * (attempt + 1))
    raise PageSpeedError(last)


def _finding(data: dict) -> Finding:
    lh = data.get("lighthouseResult") or {}
    score = ((lh.get("categories") or {}).get("performance") or {}).get("score")
    if score is None:
        raise PageSpeedError("no performance score in the response")
    score = round(score * 100)
    lcp = ((lh.get("audits") or {}).get("largest-contentful-paint") or {}).get("displayValue")
    detail = f" Main content took {lcp} to appear on a simulated phone." if lcp else ""
    evidence = f"PageSpeed Insights mobile performance score: {score}/100.{detail}"
    if score < 30:
        return Finding(PAGESPEED, False, "high", evidence)
    if score < 50:
        return Finding(PAGESPEED, False, "medium", evidence)
    return Finding(PAGESPEED, True, "low", evidence)
