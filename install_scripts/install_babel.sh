packages=("@babel/parser@^7.28.5" "@babel/generator@^7.28.5")

for pkg in "${packages[@]}"; do
  if ! npm list "$pkg" --depth=0 --silent &> /dev/null; then
    npm install $pkg
  fi
done