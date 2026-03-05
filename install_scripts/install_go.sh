if ! command -v go >/dev/null; then
apt-get update && \
    apt-get install -y --no-install-recommends golang && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
fi