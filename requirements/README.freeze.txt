These files were frozen from the original working CCI host.

old_qwen_env_freeze.txt:
  For /data/L202500484/cell_rag/qwen_env
  RAG retriever/search/answer API environment.

old_vllm_env_freeze.txt:
  For /data/L202500484/cell_rag/vllm_env
  Local Qwen3-32B vLLM serving environment.

The /data/L202500484/cell_rag project path is shared on the new host, so the existing virtual environments are visible there. The requirements were installed/verified from the new host with pip install -r and pip check.
