from pathlib import Path

from crawler.kleinanzeigen import parse_apartment_detail, parse_search_results


def test_parse_search_results_extracts_ads():
    html = Path("tests/fixtures/search_results_sample.html").read_text()
    urls = parse_search_results(html)
    assert len(urls) == 2
    assert urls[0].startswith("https://www.kleinanzeigen.de/s-anzeige/")


def test_parse_apartment_detail_extracts_core_fields():
    html = Path("tests/fixtures/apartment_detail_sample.html").read_text()
    data = parse_apartment_detail(html)
    assert data["external_id"] == "1234567890"
    assert data["title"] == "Schöne 2-Zimmer Wohnung"
    assert data["price_total"] == 950.0
    assert data["rooms"] == 2.0
    assert data["postal_code"] == "52066"
