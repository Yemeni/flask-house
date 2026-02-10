from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

PRICE_RE = re.compile(r"([\d\.]+(?:,[\d]+)?)")


def parse_search_results(html: str, base_url: str = "https://www.kleinanzeigen.de") -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for anchor in soup.select("a[href*='/s-anzeige/']"):
        href = anchor.get("href")
        if not href:
            continue
        full = urljoin(base_url, href)
        if full not in links:
            links.append(full)
    return links


def _extract_number(value: str | None) -> float | None:
    if not value:
        return None
    match = PRICE_RE.search(value.replace(" ", ""))
    if not match:
        return None
    return float(match.group(1).replace(".", "").replace(",", "."))


def _text_selectors(soup: BeautifulSoup, selectors: list[str]) -> str | None:
    for sel in selectors:
        node = soup.select_one(sel)
        if node and node.get_text(strip=True):
            return node.get_text(" ", strip=True)
    return None


def parse_apartment_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    title = _text_selectors(soup, ["h1", "h1#ad-title"])
    description = _text_selectors(soup, ["#viewad-description-text", ".ad-description"])
    location_text = _text_selectors(soup, [".boxedarticle--details--locality", ".addetailslist--detail"]) or ""

    features = [li.get_text(" ", strip=True) for li in soup.select(".addetailslist--detail") if li.get_text(strip=True)]
    images = [img.get("src") for img in soup.select("img") if img.get("src") and "http" in img.get("src")]

    details_text = " ".join([t.get_text(" ", strip=True) for t in soup.select("li, div, span")])
    external_id = _extract_external_id(soup, details_text)
    lat, lon = _extract_coordinates(soup, html)

    return {
        "external_id": external_id,
        "title": title,
        "price_total": _extract_number(_find_label_value(soup, "Preis")),
        "price_cold": _extract_number(_find_label_value(soup, "Kaltmiete")),
        "price_warm": _extract_number(_find_label_value(soup, "Warmmiete")),
        "deposit": _extract_number(_find_label_value(soup, "Kaution")),
        "size_sqm": _extract_number(_find_label_value(soup, "Wohnfläche")),
        "rooms": _extract_number(_find_label_value(soup, "Zimmer")),
        "location_text": location_text,
        "postal_code": _extract_postal_code(location_text + " " + details_text),
        "availability": _find_label_value(soup, "Verfügbar") or _find_label_value(soup, "frei ab"),
        "description": description,
        "features_json": json.dumps(features, ensure_ascii=False),
        "images_json": json.dumps(images, ensure_ascii=False),
        "advertiser_type": _find_label_value(soup, "Anbieter") or _detect_advertiser_type(details_text),
        "lat": lat,
        "lon": lon,
    }


def _find_label_value(soup: BeautifulSoup, label: str) -> str | None:
    for row in soup.select("li, tr, div"):
        text = row.get_text(" ", strip=True)
        if label.lower() in text.lower() and ":" in text:
            return text.split(":", 1)[1].strip()
    return None


def _extract_postal_code(text: str) -> str | None:
    match = re.search(r"\b(\d{5})\b", text)
    return match.group(1) if match else None


def _extract_external_id(soup: BeautifulSoup, details_text: str) -> str | None:
    for attr in ["data-adid", "data-viewad-id"]:
        node = soup.select_one(f"[{attr}]")
        if node:
            return node.get(attr)
    match = re.search(r"(?:anzeige|ad)[-/](\d{6,})", details_text)
    return match.group(1) if match else None


def _extract_coordinates(soup: BeautifulSoup, html: str) -> tuple[float | None, float | None]:
    lat_node = soup.select_one("[data-lat]")
    lon_node = soup.select_one("[data-lon]")
    if lat_node and lon_node:
        try:
            return float(lat_node["data-lat"]), float(lon_node["data-lon"])
        except ValueError:
            pass
    match = re.search(r'"lat"\s*:\s*([0-9\.\-]+).*?"lon"\s*:\s*([0-9\.\-]+)', html, re.S)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None, None


def _detect_advertiser_type(text: str) -> str | None:
    lower = text.lower()
    if "privat" in lower:
        return "private"
    if "gewerb" in lower:
        return "commercial"
    return None
