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


## Decodo Residential Proxy

This backend can route **yt-dlp metadata extraction and downloads** through a Decodo residential proxy. Configure the proxy only with Render Environment Variables (do not commit credentials).

### Render Environment Variables

```text
DECODO_PROXY_ENABLED=true
DECODO_HOST=gate.decodo.com
DECODO_PORT=7000
DECODO_USERNAME=YOUR_DECODO_USERNAME
DECODO_PASSWORD=YOUR_DECODO_PASSWORD
DECODO_COUNTRY=in
DECODO_SESSION=
```

- `DECODO_PORT=7000` can be used with Decodo's rotating residential gateway.
- `DECODO_COUNTRY=in` targets an India residential IP when supported by your Decodo residential setup.
- Leave `DECODO_SESSION` empty when you want rotating behavior.
- For a sticky session, use the sticky endpoint/port supplied by your Decodo dashboard and set a stable session ID if your endpoint supports it.

The API never returns the proxy username/password to clients. `/health` and `/` expose only whether a proxy is active.

### Verify the proxy

After deployment, call:

```text
GET /health
```

and confirm:

```json
"proxy_enabled": true
```

For an end-to-end IP check, test from the Render service using the Decodo endpoint documented in your Decodo dashboard. Decodo documents `gate.decodo.com` with authenticated HTTP(S)/SOCKS5 proxy access and recommends storing credentials outside source code.
