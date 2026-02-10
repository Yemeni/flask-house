from __future__ import annotations

from datetime import datetime, timezone

from crawler.fetch import PoliteFetcher
from crawler.kleinanzeigen import parse_apartment_detail, parse_search_results
from models import Apartment, Source, db
from services.pois import geocode_apartment_if_needed


def crawl_source(source_id: int) -> None:
    source = Source.query.get(source_id)
    if not source:
        return
    fetcher = PoliteFetcher()
    html, reason = fetcher.get(source.url)
    if not html:
        source.last_crawled_at = datetime.now(timezone.utc)
        db.session.commit()
        return

    ad_urls = parse_search_results(html)
    now = datetime.now(timezone.utc)
    for ad_url in ad_urls:
        detail_html, error = fetcher.get(ad_url)
        if not detail_html:
            continue
        parsed = parse_apartment_detail(detail_html)
        external_id = parsed.get("external_id") or ad_url.rstrip("/").split("-")[-1]
        apartment = Apartment.query.filter_by(source_id=source.id, external_id=external_id).first()
        if not apartment:
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

    source.last_crawled_at = now
    db.session.commit()
