# Hosted API Backend

The GitHub repo contains the code, docs, tests, and client examples. The source
registry, downloaded source files, processed corpus files, models, embeddings,
FAISS index, logs, reports, and secrets stay on the CCI server.

Runtime path:

```text
Client
  -> public demo URL
  -> Cloudflare quick tunnel running on CCI
  -> CCI localhost public API wrapper, port 8020
  -> CCI localhost RAG API, port 8010
  -> CCI localhost vLLM Qwen3-32B, port 8000
```

## Start Hosted Demo

On CCI:

```bash
cd /data/L202500484/cell_rag
scripts/ensure_hosted_demo.sh
```

The script:

- ensures the LLM, RAG API, and public API wrapper are healthy;
- generates or reuses the hosted API key file;
- updates `.env` with `PUBLIC_API_KEY`;
- restarts the public API wrapper so auth is active;
- installs `tools/cloudflared` if missing;
- starts a public quick tunnel;
- attempts a server-side public smoke test.

Some CCI runtime images can create the tunnel but cannot resolve their own
`trycloudflare.com` hostname. In that case, verify the public URL from an
external client:

```bash
export CELL_RAG_DEMO_URL="https://your-public-demo-url"
export CELL_RAG_DEMO_API_KEY="your-api-key"
python examples/smoke_hosted_demo.py
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File examples\windows_client.ps1 `
  -BaseUrl "https://your-public-demo-url" `
  -ApiKey "your-api-key"
```

## Find The URL

```bash
scripts/status_public_demo_tunnel.sh
```

The public URL is also stored in:

```text
logs/public_demo_tunnel.<host>.url
```

Cloudflare quick-tunnel URLs are ephemeral. If the tunnel process stops, the URL
usually changes when restarted. A stable production URL requires a named
Cloudflare Tunnel, a domain, or a CCI-managed public port mapping.

## API Key

The public API key is stored on CCI at:

```text
secrets/public_api_key.txt
```

Requests to `/ask` and `/search` must include:

```text
Authorization: Bearer <api-key>
```

## Public Endpoints

- `GET /health`
- `GET /examples`
- `POST /ask`
- `POST /search`
- `GET /docs`

## Stop Hosted Demo

```bash
scripts/stop_public_demo_tunnel.sh
```

To stop everything:

```bash
scripts/stop_all.sh
```
