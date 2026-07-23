# Hosted Cell RAG API Examples

Set these values first:

```bash
export CELL_RAG_DEMO_URL="https://bags-vary-bridge-madrid.trycloudflare.com"
export CELL_RAG_DEMO_API_KEY="your-api-key"
```

If the quick-tunnel URL changes, check the stable endpoint manifest:

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
