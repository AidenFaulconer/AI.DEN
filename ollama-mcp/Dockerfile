# ./ollama-mcp/Dockerfile
FROM python:3.14-slim

WORKDIR /app

# Copy the project files
COPY pyproject.toml ./
COPY server.py ./
COPY research_tools.py ./
COPY library_docs.py ./
COPY project_tasks.py ./
COPY workspace_roots.py ./
# If you have other files (e.g., requirements.txt, src/), copy them too

# readtags + optional docker CLI (compose tests via mounted docker.sock)
RUN apt-get update && apt-get install -y --no-install-recommends \
    universal-ctags \
    docker.io \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir mcp ollama httpx

# Expose the SSE port (default for MCP SSE transport is 5000)
EXPOSE 5000

# Transport/host/port from OLLAMA_MCP_* env (see docker-compose)
CMD ["python", "/app/server.py"]