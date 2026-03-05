if ! pip3 show tensorflow &> /dev/null; then
pip3 install tensorflow==2.13 --no-cache-dir
fi