if ! command -v go >/dev/null; then
wget https://go.dev/dl/go1.18.10.linux-amd64.tar.gz
tar -C /usr/local -xzf go1.18.10.linux-amd64.tar.gz
export PATH=$PATH:/usr/local/go/bin
source ~/.bashrc
rm go1.18.10.linux-amd64.tar.gz
fi