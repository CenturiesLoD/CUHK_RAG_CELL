# Hosted Cell RAG API Examples

Resolve the current quick-tunnel URL from the stable GitHub manifest, then set
the API key supplied separately by the server operator:

```bash
export CELL_RAG_DEMO_URL="$(python examples/endpoint_discovery.py)"
export CELL_RAG_DEMO_API_KEY="your-api-key"
```

To inspect the manifest directly:

```bash
curl -s https://raw.githubusercontent.com/CenturiesLoD/CUHK_RAG_CELL/main/docs/current_endpoint.json
```

Check health:

```bash
curl -s "$CELL_RAG_DEMO_URL/health"
```

Ask a cited question:

```bash
curl -s "$CELL_RAG_DEMO_URL/ask" \
  -H "Authorization: Bearer $CELL_RAG_DEMO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"What is a regulatory T cell?","top_k":5}'
```

Inspect retrieval only:

```bash
curl -s "$CELL_RAG_DEMO_URL/search" \
  -H "Authorization: Bearer $CELL_RAG_DEMO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query":"What markers identify Tregs?","top_k":5}'
```
