from __future__ import annotations

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Text

db = SQLAlchemy()


class Source(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(1000), unique=True, nullable=False)
    refresh_interval_minutes = db.Column(db.Integer, default=360, nullable=False)
    last_crawled_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class Apartment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.Integer, db.ForeignKey("source.id"), nullable=False, index=True)
    external_id = db.Column(db.String(120), nullable=False, index=True)
    url = db.Column(db.String(1200), nullable=False)
    title = db.Column(db.String(500))
    price_total = db.Column(db.Float)
    price_cold = db.Column(db.Float)
    price_warm = db.Column(db.Float)
    deposit = db.Column(db.Float)
    size_sqm = db.Column(db.Float)
    rooms = db.Column(db.Float)
    location_text = db.Column(db.String(300))
    postal_code = db.Column(db.String(20))
    availability = db.Column(db.String(250))
    description = db.Column(Text)
    features_json = db.Column(Text)
    images_json = db.Column(Text)
    advertiser_type = db.Column(db.String(80))
    lat = db.Column(db.Float)
    lon = db.Column(db.Float)
    geocoded_at = db.Column(db.DateTime(timezone=True))
    nearest_station_name = db.Column(db.String(300))
    nearest_station_distance_m = db.Column(db.Float)
    nearest_station_lat = db.Column(db.Float)
    nearest_station_lon = db.Column(db.Float)
    nearest_supermarket_name = db.Column(db.String(300))
    nearest_supermarket_distance_m = db.Column(db.Float)
    nearest_supermarket_lat = db.Column(db.Float)
    nearest_supermarket_lon = db.Column(db.Float)
    first_seen_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (db.UniqueConstraint("source_id", "external_id", name="uq_source_external"),)

    def as_prompt_blob(self) -> str:
        return (
            f"title={self.title}; total={self.price_total}; cold={self.price_cold}; warm={self.price_warm}; "
            f"rooms={self.rooms}; size={self.size_sqm}; location={self.location_text}; availability={self.availability}; "
            f"distance_station={self.nearest_station_distance_m}; description={self.description}"
        )


class AiProvider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    provider_type = db.Column(db.String(40), nullable=False)
    base_url = db.Column(db.String(1000))
    model = db.Column(db.String(160))
    api_key_value = db.Column(db.String(500))
    api_key_env = db.Column(db.String(120))
    headers_json = db.Column(Text)
    request_timeout_seconds = db.Column(db.Integer, default=20, nullable=False)
    enabled = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def masked_token(self) -> str:
        if self.api_key_value:
            return "••••••"
        return ""


class AppSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False)
    value = db.Column(Text, nullable=False)


class AiNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    apartment_id = db.Column(db.Integer, db.ForeignKey("apartment.id"), nullable=False, index=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("ai_provider.id"), nullable=True)
    model_used = db.Column(db.String(160))
    kind = db.Column(db.String(40), nullable=False)
    criteria_text = db.Column(Text)
    result_text = db.Column(Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class GeocodeCache(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location_query = db.Column("query", db.String(500), unique=True, nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lon = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
