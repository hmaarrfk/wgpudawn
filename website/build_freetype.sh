#!/bin/bash
# Build freetype-py for Pyodide: its (pure Python, ctypes) package plus
# FreeType itself as an Emscripten side module. pygfx needs it to import, and
# neither PyPI nor Pyodide has it.
#
#   website/build_freetype.sh <out-dir>
#
# Needs the Emscripten of the target Pyodide on the PATH (emcc, emcmake),
# cmake and ninja. The flags must match how Pyodide itself is built
# (`pyodide config list`): wasm exceptions and wasm longjmp.
set -euo pipefail

OUT=$(mkdir -p "$1" && cd "$1" && pwd)
FREETYPE_PY_VERSION=2.5.1
FREETYPE_VERSION=2.13.3
PLATFORM_TAG=${PLATFORM_TAG:-pyemscripten_2026_0_wasm32}
FLAGS="-fPIC -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -O2"

WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cd "$WORK"

python -m pip download -q --no-deps --no-binary :all: --no-build-isolation \
  -d sdist "freetype-py==$FREETYPE_PY_VERSION" 2>/dev/null \
  || curl -sSL -o sdist/freetype-py.zip --create-dirs \
    "https://files.pythonhosted.org/packages/source/f/freetype-py/freetype-py-$FREETYPE_PY_VERSION.zip"
python -c "import shutil, glob; shutil.unpack_archive(glob.glob('sdist/*')[0], 'py')"

curl -sSL "https://download.savannah.gnu.org/releases/freetype/freetype-$FREETYPE_VERSION.tar.gz" | tar -xz
emcmake cmake -S "freetype-$FREETYPE_VERSION" -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="$FLAGS" -DBUILD_SHARED_LIBS=OFF \
  -DFT_DISABLE_HARFBUZZ=ON -DFT_DISABLE_PNG=ON -DFT_DISABLE_BZIP2=ON \
  -DFT_DISABLE_BROTLI=ON -DFT_DISABLE_ZLIB=ON > cmake.log 2>&1 || { cat cmake.log; exit 1; }
cmake --build build >> cmake.log 2>&1 || { cat cmake.log; exit 1; }

# freetype-py loads libfreetype.so from its own package directory
PKG=$(ls -d py/freetype-py-*/freetype)
echo "" > empty.c
emcc $FLAGS -sSIDE_MODULE=1 empty.c -Wl,--whole-archive build/libfreetype.a \
  -Wl,--no-whole-archive -o "$PKG/libfreetype.so"

# Not a complete wheel (no metadata): the site unpacks it into site-packages
WHEEL="$OUT/freetype_py-$FREETYPE_PY_VERSION-py3-none-$PLATFORM_TAG.whl"
rm -f "$WHEEL"
(cd "$(dirname "$PKG")" && python -m zipfile -c "$WHEEL" freetype)
ls -l "$WHEEL"
