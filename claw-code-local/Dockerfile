# Claw Code (Rust CLI) — https://github.com/ultraworkers/claw-code-local
# Context: AI.DEN repo root.

FROM rust:1-bookworm AS builder
WORKDIR /src

# Native deps sometimes pulled by transitive crates during workspace build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends cmake pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY claw-code-local/rust/Cargo.toml claw-code-local/rust/Cargo.lock ./
COPY claw-code-local/rust/crates ./crates

RUN cargo build --workspace --release -p rusty-claude-cli

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git ripgrep \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /src/target/release/claw /usr/local/bin/claw
ENTRYPOINT ["/usr/local/bin/claw"]
