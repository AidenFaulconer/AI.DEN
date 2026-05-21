# universal-ctags is not in Alpine 3.20 repos — use Debian (same as mcp-server readtags)
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends universal-ctags \
    && rm -rf /var/lib/apt/lists/*
COPY scripts/ctags-index.sh /usr/local/bin/ctags-index.sh
# Strip Windows CRLF so shebang works in Linux (avoids "no such file or directory")
RUN sed -i 's/\r$//' /usr/local/bin/ctags-index.sh && chmod +x /usr/local/bin/ctags-index.sh
WORKDIR /workspace
ENTRYPOINT ["/bin/sh", "/usr/local/bin/ctags-index.sh"]
