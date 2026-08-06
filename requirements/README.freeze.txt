These files were frozen from the original working CCI host.

old_qwen_env_freeze.txt:
  For <CCI_RUNTIME_DIR>/qwen_env
  RAG retriever/search/answer API environment.

old_vllm_env_freeze.txt:
  For <CCI_RUNTIME_DIR>/vllm_env
  Local Qwen3-32B vLLM serving environment.

The runtime project path should be shared across compatible CCI images so the
existing virtual environments are visible there. The requirements were
installed/verified from the runtime host with pip install -r and pip check.
