# Ollama with the models already inside the image, run next to the app on Cloud Run with a GPU
# (see deploy/cloudrun-gpu.yaml). Baking the models in means nothing is downloaded at start.
# To use another chat model, change CHAT_MODEL here and deploy with the same CHAT_MODEL.
FROM ollama/ollama:latest

ARG CHAT_MODEL=qwen3.5:9b
ARG EMBED_MODEL=nomic-embed-text
ENV OLLAMA_MODELS=/models \
    # Cloud Run only routes outside traffic to the app's port (8080), so this port stays private
    # to the instance; listening on all interfaces lets Cloud Run's startup probe reach it.
    OLLAMA_HOST=0.0.0.0:11434 \
    # Keep models loaded in GPU memory so no answer waits for a model to load.
    OLLAMA_KEEP_ALIVE=-1 \
    OLLAMA_NUM_PARALLEL=4

RUN ollama serve & \
    for i in $(seq 1 30); do ollama list >/dev/null 2>&1 && break; sleep 1; done; \
    ollama pull "$CHAT_MODEL" && ollama pull "$EMBED_MODEL"

ENTRYPOINT ["ollama", "serve"]
