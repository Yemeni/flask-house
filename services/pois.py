from __future__ import annotations

import math
from datetime import datetime, timezone

import requests

from crawler.fetch import DEFAULT_UA
from models import Apartment, GeocodeCache, db

NOMINATIM_URL = "https://nominatim.openstreetmap.org"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def geocode_apartment_if_needed(apartment: Apartment) -> None:
    if apartment.lat is not None and apartment.lon is not None:
        return
    location_query = apartment.location_text or ""
    if apartment.postal_code:
        location_query = f"{location_query} {apartment.postal_code}"
    if not location_query.strip():
        return
    cached = GeocodeCache.query.filter_by(location_query=location_query).first()
    if cached:
        apartment.lat, apartment.lon = cached.lat, cached.lon
        apartment.geocoded_at = datetime.now(timezone.utc)
        return

    headers = {"User-Agent": DEFAULT_UA}
    resp = requests.get(
        f"{NOMINATIM_URL}/search",
        params={"q": location_query, "format": "json", "limit": 1},
        timeout=20,
        headers=headers,
    )
    if resp.status_code != 200:
        return
    data = resp.json()
    if not data:
        return
    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    apartment.lat, apartment.lon = lat, lon
    apartment.geocoded_at = datetime.now(timezone.utc)
    db.session.add(GeocodeCache(location_query=location_query, lat=lat, lon=lon))


def find_nearest_poi(lat: float, lon: float, category: str) -> dict | None:
    if category == "train_station":
        query = f"""
[out:json][timeout:25];
node(around:3000,{lat},{lon})[railway=station];
out body;
"""
    else:
        query = f"""
[out:json][timeout:25];
node(around:3000,{lat},{lon})[shop=supermarket];
out body;
"""
    resp = requests.post(OVERPASS_URL, data=query, timeout=30, headers={"User-Agent": DEFAULT_UA})
    if resp.status_code != 200:
        return None
    elements = resp.json().get("elements", [])
    nearest = None
    for elem in elements:
        distance = haversine_m(lat, lon, elem["lat"], elem["lon"])
        entry = {
            "name": elem.get("tags", {}).get("name", "unknown"),
            "distance": distance,
            "lat": elem["lat"],
            "lon": elem["lon"],
        }
        if not nearest or entry["distance"] < nearest["distance"]:
            nearest = entry
    return nearest


def refresh_pois_for_apartments() -> None:
    apartments = Apartment.query.all()
    for apt in apartments:
        geocode_apartment_if_needed(apt)
        if apt.lat is None or apt.lon is None:
            continue
        station = find_nearest_poi(apt.lat, apt.lon, "train_station")
        market = find_nearest_poi(apt.lat, apt.lon, "supermarket")
        if station:
            apt.nearest_station_name = station["name"]
            apt.nearest_station_distance_m = station["distance"]
            apt.nearest_station_lat = station["lat"]
            apt.nearest_station_lon = station["lon"]
        if market:
            apt.nearest_supermarket_name = market["name"]
            apt.nearest_supermarket_distance_m = market["distance"]
            apt.nearest_supermarket_lat = market["lat"]
            apt.nearest_supermarket_lon = market["lon"]
    db.session.commit()
