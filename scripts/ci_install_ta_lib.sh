#!/usr/bin/env bash
# GitHub Actions (ubuntu-latest) 向け: TA-Lib C ライブラリを /usr/local にビルドし ldconfig 登録。
# pip の TA-Lib ホイールが使えない環境のフォールバックにもなる。
set -euo pipefail

if [[ "${RUNNER_OS:-Linux}" != "Linux" ]]; then
  echo "ci_install_ta_lib: skip (RUNNER_OS=${RUNNER_OS:-unset})"
  exit 0
fi

if ldconfig -p 2>/dev/null | grep -q 'libta_lib.so'; then
  echo "ci_install_ta_lib: libta_lib already in cache"
  exit 0
fi

sudo apt-get update
sudo apt-get install -y build-essential wget

WORKDIR="${TMPDIR:-/tmp}/ta-lib-src"
mkdir -p "$WORKDIR"
cd "$WORKDIR"
rm -rf ta-lib ta-lib-0.4.0 ta-lib-0.4.0-src.tar.gz 2>/dev/null || true

wget -q --retry-connrefused --waitretry=1 --read-timeout=30 --timeout=30 -t 3 \
  http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz
tar -xzf ta-lib-0.4.0-src.tar.gz
BUILD_DIR=$(find . -maxdepth 1 -type d \( -name 'ta-lib' -o -name 'ta-lib-*' \) | head -1)
if [[ -z "${BUILD_DIR}" ]]; then
  echo "ci_install_ta_lib: could not find extracted ta-lib directory"
  ls -la
  exit 1
fi
cd "${BUILD_DIR}"
./configure --prefix=/usr/local
make -j"$(nproc 2>/dev/null || echo 2)"
sudo make install
sudo ldconfig

echo "ci_install_ta_lib: installed under /usr/local"
