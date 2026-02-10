from __future__ import annotations

from datetime import datetime, timezone

from crawler.fetch import PoliteFetcher
from crawler.kleinanzeigen import parse_apartment_detail, parse_search_results
from models import Apartment, Source, db
from services.pois import geocode_apartment_if_needed


def crawl_source(source_id: int) -> dict:
    source = Source.query.get(source_id)
    result = {
        "source_id": source_id,
        "scanned": 0,
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
    }
    if not source:
        result["errors"].append("Source not found")
        return result

    fetcher = PoliteFetcher()
    ad_urls: list[str] = []

    # Support both search URLs and direct ad detail URLs.
    if "/s-anzeige/" in source.url:
        ad_urls = [source.url]
    else:
        html, reason = fetcher.get(source.url)
        if not html:
            source.last_crawled_at = datetime.now(timezone.utc)
            db.session.commit()
            result["errors"].append(f"Source fetch failed: {reason}")
            return result

        ad_urls = parse_search_results(html)
        if not ad_urls:
            hint = "No ad links found"
            lower = html.lower()
            if "captcha" in lower or "zugriff verweigert" in lower:
                hint += " (possibly anti-bot/captcha page)"
            result["errors"].append(hint)

    now = datetime.now(timezone.utc)
    for ad_url in ad_urls:
        result["scanned"] += 1
        detail_html, error = fetcher.get(ad_url)
        if not detail_html:
            result["skipped"] += 1
            if len(result["errors"]) < 5:
                result["errors"].append(f"{ad_url}: {error}")
            continue

        parsed = parse_apartment_detail(detail_html)
        external_id = parsed.get("external_id") or ad_url.rstrip("/").split("-")[-1]
        apartment = Apartment.query.filter_by(source_id=source.id, external_id=external_id).first()
        created = apartment is None
        if created:
            apartment = Apartment(source_id=source.id, external_id=external_id, url=ad_url)
            db.session.add(apartment)
            apartment.first_seen_at = now

        apartment.url = ad_url
        apartment.last_seen_at = now
        apartment.updated_at = now
        for key, value in parsed.items():
            if hasattr(apartment, key):
                setattr(apartment, key, value)
        geocode_apartment_if_needed(apartment)

        if created:
            result["created"] += 1
        else:
            result["updated"] += 1

    source.last_crawled_at = now
    db.session.commit()
    return result
