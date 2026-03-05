if ! command -v uncrustify >/dev/null; then
apt-get update && \
    apt-get install -y --no-install-recommends cmake && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

wget https://github.com/user-attachments/files/20265227/uncrustify-0.81.0.tar.gz
tar -xf uncrustify-0.81.0.tar.gz
rm uncrustify-0.81.0.tar.gz
cd uncrustify-uncrustify-0.81.0
mkdir build
cd build
cmake -DCMAKE_BUILD_TYPE=Release ..
cmake --build . --config Release
make install
cd ../.. #return to init dir
fi