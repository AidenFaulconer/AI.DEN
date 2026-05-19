# ./ollama-mcp/Dockerfile
FROM python:3.14-slim

WORKDIR /app

# Copy the project files
COPY pyproject.toml ./
COPY server.py ./
# If you have other files (e.g., requirements.txt, src/), copy them too

# Install dependencies inside the container (no SSL issues here because we use Debian's CA certs)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir mcp ollama

# Expose the SSE port (default for MCP SSE transport is 5000)
EXPOSE 5000

# Transport/host/port from OLLAMA_MCP_* env (see docker-compose)
CMD ["python", "/app/server.py"]