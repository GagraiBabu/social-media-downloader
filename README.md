# Social Media Video Downloader API

A Python/FastAPI backend for retrieving public media information and downloads where supported by the underlying extractors and applicable platform rules.

## Project

- FastAPI backend
- yt-dlp-based extraction where supported
- Docker/Render ready
- Temporary download handling
- CORS configuration
- API documentation at `/docs`

## Important limitations

Platform support depends on the current capabilities of the extractor, public availability of the media, authentication requirements, and platform terms. The API must not bypass private content, authentication, paywalls, or access controls.

Do not use the service to infringe copyright or violate platform terms.

## Run locally

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Then open `/docs`.

## Render

This repository includes a Render-optimized Dockerfile, startup script, health check, and `render.yaml`. Render supplies the `PORT` environment variable at runtime. The default configuration keeps one media job at a time on a small/free instance to reduce RAM/CPU pressure; increase `MAX_CONCURRENT_JOBS` only on a larger instance.

## Main endpoints

- `GET /health`
- `POST /api/detect`
- `POST /api/info`
- `POST /api/download`

See the FastAPI Swagger UI at `/docs` for the current request and response schemas.


## Webshare Residential Proxy

This backend can route **yt-dlp metadata extraction and downloads** through a Webshare residential proxy. Keep proxy credentials only in Render Environment Variables.

### Render Environment Variables

```text
WEBSHARE_PROXY_ENABLED=true
WEBSHARE_HOST=p.webshare.io
WEBSHARE_PORT=80
WEBSHARE_USERNAME=YOUR_WEBSHARE_USERNAME
WEBSHARE_PASSWORD=YOUR_WEBSHARE_PASSWORD
WEBSHARE_COUNTRY=
WEBSHARE_SESSION=
WEBSHARE_ROTATE=true
```

Webshare's Backbone connection uses `p.webshare.io`; username/password authentication supports ports including `80`, `1080`, `3128`, and `9999-19999`. Country targeting can be added to the username, and `-rotate` requests rotating IP behavior. See Webshare's current connection documentation for the exact options available to your plan.

The API never returns the proxy username/password to clients. `/health` and `/` expose only whether a proxy is active.

### Verify

After deployment, call:

```text
GET /health
```

and confirm:

```json
"proxy_enabled": true
```

For residential proxy testing, use the Webshare Endpoint Generator/dashboard to confirm the endpoint, country, and session mode for your plan.
