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
scripts/init_public_demo.sh
```

The script:

- ensures the LLM, RAG API, and public API wrapper are healthy;
- generates or reuses the hosted API key file;
- updates `.env` with `PUBLIC_API_KEY`;
- restarts the public API wrapper so auth is active;
- installs `tools/cloudflared` if missing;
- starts a public quick tunnel;
- writes the current public URL to `docs/current_endpoint.json`;
- attempts a server-side public smoke test.

To force a new quick-tunnel URL:

```bash
scripts/init_public_demo.sh --restart-tunnel
```

To update the GitHub endpoint manifest from CCI after generating a URL:

```bash
scripts/init_public_demo.sh --publish-endpoint
```

From Windows, if SSH access to CCI is configured:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\init_public_demo_from_windows.ps1
```

The helper uses `CELL_RAG_SSH_KEY` when set, otherwise it checks the current
user's `.ssh` directory for `public_key`, `id_ed25519`, or `id_rsa`. Use
`-IdentityFile C:\path\to\key` to select a different key.

Some CCI runtime images can create the tunnel but cannot resolve their own
`trycloudflare.com` hostname. In that case, verify the public URL from an
external client:

```bash
export CELL_RAG_DEMO_API_KEY="your-api-key"
python examples/smoke_hosted_demo.py
```

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File examples\windows_client.ps1 `
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
usually changes when restarted.

The repo provides a stable discovery manifest:

```text
docs/current_endpoint.json
```

Its GitHub raw URL is stable:

```text
https://raw.githubusercontent.com/CenturiesLoD/CUHK_RAG_CELL/main/docs/current_endpoint.json
```

The example clients use this manifest automatically when `CELL_RAG_DEMO_URL` or
`--base-url` is not provided. After restarting the quick tunnel, update the
manifest on CCI:

```bash
scripts/init_public_demo.sh --publish-endpoint
```

## Automatic Manifest Publishing

The CCI runtime directory is not a Git checkout. The automatic publisher uses a
small checkout dedicated to GitHub updates:

```text
/data/L202500484/cell_rag/.endpoint_repo
```

The publisher uses GitHub SSH over port `443` by default:

```text
ssh://git@ssh.github.com:443/CenturiesLoD/CUHK_RAG_CELL.git
```

This avoids CCI networks that block outbound SSH on port `22`.

The flow is:

```text
Cloudflare tunnel writes logs/public_demo_tunnel.<host>.url
  -> scripts/write_public_endpoint_manifest.sh writes docs/current_endpoint.json
  -> scripts/publish_public_endpoint.sh clones or updates .endpoint_repo
  -> the manifest is copied into .endpoint_repo/docs/current_endpoint.json
  -> Git commits and pushes only that manifest change
```

Configure a deploy key once:

```bash
scripts/setup_public_endpoint_publisher.sh
```

Add the printed public key in GitHub:

```text
CenturiesLoD/CUHK_RAG_CELL -> Settings -> Deploy keys -> Add deploy key
```

Enable:

```text
Allow write access
```

Then test the publish path:

```bash
PUBLISH_ENDPOINT_PUSH=1 scripts/publish_public_endpoint.sh
```

After that, restarting the hosted demo can update GitHub automatically:

```bash
scripts/init_public_demo.sh --restart-tunnel --publish-endpoint
```

A true stable API hostname requires one of these infrastructure options:

- Cloudflare Named Tunnel plus a domain, such as `https://cell-rag.example.com`;
- a CCI-managed public port mapping with a stable hostname;
- another stable reverse proxy in front of the CCI backend.

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
