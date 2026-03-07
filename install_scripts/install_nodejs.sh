if ! command -v node >/dev/null; then
    apt-get update
    apt-get install -y ca-certificates curl gnupg
    apt-get clean 
    rm -rf /var/lib/apt/lists/*

    mkdir -p /etc/apt/keyrings
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg

    NODE_MAJOR=24
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list

    apt-get update
    apt-get install -y nodejs
    apt-get clean 
    rm -rf /var/lib/apt/lists/*

    node -v
    npm -v
fi