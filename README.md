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

This repository includes a Dockerfile and `render.yaml`. Render supplies the `PORT` environment variable at runtime.

## Main endpoints

- `GET /health`
- `POST /api/detect`
- `POST /api/info`
- `POST /api/download`

See the FastAPI Swagger UI at `/docs` for the current request and response schemas.
