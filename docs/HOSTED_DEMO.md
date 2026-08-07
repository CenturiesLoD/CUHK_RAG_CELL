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
cd <CCI_RUNTIME_DIR>
scripts/init_public_demo.sh --publish-endpoint
```

The script:

- checks and installs required CCI system packages if missing;
- ensures the LLM, RAG API, and public API wrapper are healthy;
- generates or reuses the hosted API key file;
- updates `.env` with `PUBLIC_API_KEY`;
- restarts the public API wrapper so auth is active;
- installs `tools/cloudflared` if missing;
- starts a public quick tunnel;
- writes the current public URL to `docs/current_endpoint.json`;
- attempts a server-side public smoke test.

The package check is handled by `scripts/ensure_system_packages.sh`. By default
it installs missing packages with `apt-get` because fresh CCI images may not
include tools such as `git`. Set `CELL_RAG_AUTO_INSTALL_SYSTEM_PACKAGES=0` to
turn the check into a fail-fast verification step.

To force a new quick-tunnel URL:

```bash
scripts/init_public_demo.sh --restart-tunnel --publish-endpoint
```

To update the GitHub endpoint manifest from CCI after generating a URL:

```bash
scripts/init_public_demo.sh --publish-endpoint
```

From Windows, if SSH access to CCI is configured:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\init_public_demo_from_windows.ps1 `
  -HostName <CCI_HOST> `
  -Port <CCI_SSH_PORT> `
  -User <CCI_USER> `
  -RuntimeDir <CCI_RUNTIME_DIR> `
  -PublishEndpoint
```

The helper uses `CELL_RAG_SSH_KEY` when set, otherwise it checks the current
user's `.ssh` directory for `public_key`, `id_ed25519`, or `id_rsa`. It also
accepts `CELL_RAG_SSH_HOST`, `CELL_RAG_SSH_PORT`, `CELL_RAG_SSH_USER`, and
`CELL_RAG_RUNTIME_DIR`. Use `-IdentityFile C:\path\to\key` to select a
different key. Keep the concrete CCI host, SSH user, SSH port, and runtime path
outside Git.

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

The smoke test verifies the service. For a normal user-facing session, use the
terminal below instead of the raw JSON client.

## User-Mode Terminal

For a normal interactive terminal instead of raw JSON output:

```bash
export CELL_RAG_DEMO_API_KEY="your-api-key"
python rag_chat.py
```

Windows PowerShell:

```powershell
$env:CELL_RAG_DEMO_API_KEY="your-api-key"
python rag_chat.py
```

This command enters user mode. Type questions at the `rag>` prompt. The terminal
prints a readable answer, confidence, citation status, and optional compact
sources. Use `/sources` to toggle source display, `/help` to see commands, and
`/exit` to leave.

Simple greetings and connectivity checks such as `hi` or `test` should return a
short uncited response with no sources. If a greeting shows a biomedical source
ID, rerun the hosted smoke test and restart the RAG server with the latest code.

For one-off integration tests, keep using `examples/python_client.py`,
`examples/windows_client.ps1`, `examples/smoke_hosted_demo.py`, or
`examples/curl_examples.md`; those intentionally expose raw API behavior.

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

Clients read it through GitHub's contents API, which updates more reliably than
`raw.githubusercontent.com` immediately after a tunnel URL change:

```text
https://api.github.com/repos/CenturiesLoD/CUHK_RAG_CELL/contents/docs/current_endpoint.json?ref=main
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
<CCI_RUNTIME_DIR>/.endpoint_repo
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
