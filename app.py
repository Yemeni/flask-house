from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, flash, redirect, render_template, request, url_for

from crawler.runner import crawl_source
from models import AiNote, AiProvider, Apartment, AppSetting, Source, db
from services.ai_client import AiClientError, test_provider_connection
from services.pois import refresh_pois_for_apartments

scheduler = BackgroundScheduler(timezone="UTC")


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///app.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        ensure_default_settings()
        ensure_scheduler_jobs()

    register_routes(app)


    @app.template_filter("from_json")
    def from_json_filter(value: str):
        try:
            return json.loads(value or "[]")
        except json.JSONDecodeError:
            return []


    if not scheduler.running:
        scheduler.start()

    return app


def ensure_default_settings() -> None:
    defaults = {
        "crawl_rate_limit_seconds": os.getenv("CRAWL_RATE_LIMIT_SECONDS", "1.5"),
        "http_timeout_seconds": os.getenv("HTTP_TIMEOUT_SECONDS", "15"),
        "active_ai_provider_id": "",
    }
    for key, value in defaults.items():
        if not AppSetting.query.filter_by(key=key).first():
            db.session.add(AppSetting(key=key, value=value))
    db.session.commit()


def ensure_scheduler_jobs() -> None:
    for source in Source.query.all():
        schedule_source(source)


def schedule_source(source: Source) -> None:
    job_id = f"crawl_source_{source.id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    scheduler.add_job(
        func=crawl_source,
        trigger="interval",
        minutes=max(1, source.refresh_interval_minutes),
        args=[source.id],
        id=job_id,
        replace_existing=True,
    )


def register_routes(app: Flask) -> None:
    @app.get("/")
    def dashboard():
        stats = {
            "sources": Source.query.count(),
            "apartments": Apartment.query.count(),
            "notes": AiNote.query.count(),
            "providers": AiProvider.query.count(),
        }
        return render_template("dashboard.html", stats=stats)

    @app.route("/sources", methods=["GET", "POST"])
    def sources():
        if request.method == "POST":
            urls = request.form.get("urls", "").splitlines()
            interval = int(request.form.get("refresh_interval_minutes", "360"))
            for raw_url in urls:
                url = raw_url.strip()
                if not url:
                    continue
                if not Source.query.filter_by(url=url).first():
                    source = Source(url=url, refresh_interval_minutes=interval)
                    db.session.add(source)
            db.session.commit()
            for source in Source.query.all():
                schedule_source(source)
            flash("Sources saved.", "success")
            return redirect(url_for("sources"))
        return render_template("sources.html", sources=Source.query.order_by(Source.created_at.desc()).all())

    @app.post("/sources/<int:source_id>/crawl")
    def crawl_source_now(source_id: int):
        crawl_source(source_id)
        flash("Crawl completed.", "info")
        return redirect(url_for("sources"))

    @app.get("/apartments")
    def apartments():
        query = Apartment.query
        min_price = request.args.get("min_price", type=float)
        max_price = request.args.get("max_price", type=float)
        min_size = request.args.get("min_size", type=float)
        rooms = request.args.get("rooms", type=float)
        avail = request.args.get("availability", type=str)
        max_train_dist = request.args.get("max_train_dist", type=float)
        if min_price is not None:
            query = query.filter(Apartment.price_total >= min_price)
        if max_price is not None:
            query = query.filter(Apartment.price_total <= max_price)
        if min_size is not None:
            query = query.filter(Apartment.size_sqm >= min_size)
        if rooms is not None:
            query = query.filter(Apartment.rooms >= rooms)
        if avail:
            query = query.filter(Apartment.availability.ilike(f"%{avail}%"))
        if max_train_dist is not None:
            query = query.filter(Apartment.nearest_station_distance_m <= max_train_dist)
        apartments_ = query.order_by(Apartment.updated_at.desc()).limit(300).all()
        return render_template("apartments.html", apartments=apartments_)

    @app.get("/apartments/<int:apartment_id>")
    def apartment_detail(apartment_id: int):
        apartment = Apartment.query.get_or_404(apartment_id)
        notes = AiNote.query.filter_by(apartment_id=apartment_id).order_by(AiNote.created_at.desc()).all()
        providers = AiProvider.query.filter_by(enabled=True).all()
        return render_template("apartment_detail.html", apartment=apartment, notes=notes, providers=providers)

    @app.post("/apartments/<int:apartment_id>/summarize")
    def summarize_apartment(apartment_id: int):
        apartment = Apartment.query.get_or_404(apartment_id)
        provider_id = request.form.get("provider_id", type=int) or get_active_provider_id()
        prompt = f"Summarize this apartment with pros/cons and key facts: {apartment.as_prompt_blob()}"
        try:
            text, model_used = test_provider_connection(provider_id, prompt=prompt)
            note = AiNote(apartment_id=apartment_id, provider_id=provider_id, model_used=model_used, kind="summary", result_text=text)
            db.session.add(note)
            db.session.commit()
            flash("Summary created.", "success")
        except AiClientError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("apartment_detail", apartment_id=apartment_id))

    @app.post("/apartments/<int:apartment_id>/evaluate")
    def evaluate_apartment(apartment_id: int):
        apartment = Apartment.query.get_or_404(apartment_id)
        criteria = request.form.get("criteria", "")
        provider_id = request.form.get("provider_id", type=int) or get_active_provider_id()
        prompt = (
            "Evaluate apartment fit. Return concise bullet points with score 1-10 and rationale.\n"
            f"Criteria: {criteria}\nApartment: {apartment.as_prompt_blob()}"
        )
        try:
            text, model_used = test_provider_connection(provider_id, prompt=prompt)
            note = AiNote(
                apartment_id=apartment_id,
                provider_id=provider_id,
                model_used=model_used,
                kind="evaluation",
                criteria_text=criteria,
                result_text=text,
            )
            db.session.add(note)
            db.session.commit()
            flash("Evaluation created.", "success")
        except AiClientError as exc:
            flash(str(exc), "danger")
        return redirect(url_for("apartment_detail", apartment_id=apartment_id))

    @app.route("/pois", methods=["GET", "POST"])
    def pois():
        if request.method == "POST":
            refresh_pois_for_apartments()
            flash("POIs refreshed.", "success")
            return redirect(url_for("pois"))
        return render_template("pois.html", apartments=Apartment.query.count())

    @app.get("/map")
    def map_view():
        apartments_ = Apartment.query.filter(Apartment.lat.isnot(None), Apartment.lon.isnot(None)).all()
        markers = [{
            "id": a.id,
            "title": a.title,
            "price_total": a.price_total,
            "size_sqm": a.size_sqm,
            "nearest_station_distance_m": a.nearest_station_distance_m,
            "lat": a.lat,
            "lon": a.lon,
        } for a in apartments_]
        return render_template("map.html", apartments=markers)

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if request.method == "POST":
            for key in ["crawl_rate_limit_seconds", "http_timeout_seconds"]:
                setting = AppSetting.query.filter_by(key=key).first()
                setting.value = request.form.get(key, setting.value)
            db.session.commit()
            flash("Settings updated.", "success")
            return redirect(url_for("settings"))
        settings_map = {s.key: s.value for s in AppSetting.query.all()}
        return render_template("settings.html", settings=settings_map)

    @app.route("/ai-settings", methods=["GET", "POST"])
    def ai_settings():
        if request.method == "POST":
            action = request.form.get("action")
            if action == "save_provider":
                provider_id = request.form.get("provider_id", type=int)
                provider = AiProvider.query.get(provider_id) if provider_id else AiProvider()
                provider.name = request.form.get("name", "")
                provider.provider_type = request.form.get("provider_type", "openai_compatible")
                provider.base_url = request.form.get("base_url", "")
                provider.model = request.form.get("model", "")
                provider.api_key_env = request.form.get("api_key_env", "")
                api_key_value = request.form.get("api_key_value", "")
                if api_key_value and api_key_value != "••••••":
                    provider.api_key_value = api_key_value
                provider.headers_json = request.form.get("headers_json", "")
                provider.request_timeout_seconds = request.form.get("request_timeout_seconds", type=int) or 20
                provider.enabled = bool(request.form.get("enabled"))
                provider.updated_at = datetime.now(timezone.utc)
                if not provider_id:
                    db.session.add(provider)
                db.session.commit()
                flash("Provider saved.", "success")
            elif action == "set_active":
                provider_id = request.form.get("active_provider_id", "")
                setting = AppSetting.query.filter_by(key="active_ai_provider_id").first()
                setting.value = provider_id
                db.session.commit()
                flash("Active provider updated.", "success")
            elif action == "delete_provider":
                provider = AiProvider.query.get_or_404(request.form.get("provider_id", type=int))
                db.session.delete(provider)
                db.session.commit()
                flash("Provider deleted.", "info")
            elif action == "test_provider":
                provider_id = request.form.get("provider_id", type=int)
                try:
                    _, model_used = test_provider_connection(provider_id)
                    flash(f"Connection OK (model: {model_used}).", "success")
                except AiClientError as exc:
                    flash(f"Connection failed: {exc}", "danger")
            return redirect(url_for("ai_settings"))

        providers = AiProvider.query.order_by(AiProvider.created_at.desc()).all()
        active_provider_id = get_active_provider_id()
        return render_template("ai_settings.html", providers=providers, active_provider_id=active_provider_id)


def get_active_provider_id() -> int | None:
    setting = AppSetting.query.filter_by(key="active_ai_provider_id").first()
    if not setting or not setting.value:
        return None
    return int(setting.value)


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
