# Flask House (Kleinanzeigen apartment crawler)

A Flask + Jinja app managed with **uv** for collecting apartment listings from Kleinanzeigen search URLs, enriching with OSM POIs, and adding AI-generated notes.

## Features
- Source management with per-source refresh interval and manual crawl.
- Polite crawling (`requests`): rate limits, retries with backoff, timeouts, robots.txt checks.
- Parser resilience with multiple selectors and graceful null handling.
- Apartment list, filters, detail view, and Leaflet map pins.
- OSM geocoding/POI enrichment (nearest train station + supermarket).
- AI provider registry (Ollama, OpenAI-compatible, OpenAI, Anthropic, Gemini, custom HTTP).
- AI actions per apartment: summarize + suitability evaluation.

## Quickstart (uv)
1. Install Python and `uv`.
2. Install dependencies:
   ```bash
   uv sync
   ```
3. Run development server:
   ```bash
   uv run flask --app app run --debug --host 0.0.0.0 --port 8005
   ```
4. Open `http://127.0.0.1:8005`.


## Run from VS Code
1. Open the folder in VS Code.
2. Run `uv sync` (Terminal or **Tasks: Run Task** -> `uv sync`).
3. Start debugging with **Run and Debug** -> `Flask House (uv)`.
4. App runs on `http://127.0.0.1:8005` and stores data in `app.db` by default.

## Docker (Raspberry Pi / arm64)
```bash
docker compose up --build
```
Open: `http://<pi-ip>:8005`.

### Environment variables
- `FLASK_SECRET_KEY`
- `DATABASE_URL` (optional; default is file-based `sqlite:///app.db`)
- `CRAWL_RATE_LIMIT_SECONDS`
- `HTTP_TIMEOUT_SECONDS`
- Optional token vars like `AI_PROVIDER_OPENAI_KEY` (map by setting provider `api_key_env`).

## AI provider notes
- **Ollama** uses `/api/generate` endpoint.
- **OpenAI/OpenAI-compatible** uses `/v1/chat/completions`.
- **Custom HTTP**: set `base_url`, and use `model` as optional path template suffix.
- API keys are masked in UI and never logged. Prefer `api_key_env` over storing key in DB.

Example custom HTTP:
- `base_url`: `http://192.168.1.10:8080`
- `model`: `/my/generate`
- Request JSON: `{"prompt":...,"system":...,"model":...,"temperature":...}`

## Tests
Parser tests with local fixtures (dummy HTML):
```bash
uv run pytest
```

Add your own fixtures by saving sanitized HTML files to `tests/fixtures/` and extending `tests/test_parsers.py`.

## Routes
- `GET /` dashboard
- `GET/POST /sources`
- `POST /sources/<id>/crawl`
- `GET /apartments`
- `GET /apartments/<id>`
- `POST /apartments/<id>/summarize`
- `POST /apartments/<id>/evaluate`
- `GET/POST /pois`
- `GET /map`
- `GET/POST /settings`
- `GET/POST /ai-settings`

## Safety/compliance behavior
- Checks robots.txt before each fetch.
- If blocked or inaccessible, listing fetch is skipped.
- No anti-bot bypass logic is implemented.

## Troubleshooting
- **Parsing misses fields**: Kleinanzeigen layout may vary; extend selectors in `crawler/kleinanzeigen.py`.
- **robots blocked**: source or detail URL disallowed in robots.txt; app intentionally skips and continues.
- **No apartments after crawl**: click **Crawl now** and check flash messages on Sources; the app now reports scanned/created/skipped counts and top fetch errors (robots/captcha/HTTP).
- **Direct ad URL as source**: supported; the crawler treats `/s-anzeige/...` as a single listing source.
- **Geocoding/Overpass limits**: retry later and keep rate limits conservative.
- **AI timeouts/errors**: verify base URL, model name, token env var, and timeout in AI settings.
