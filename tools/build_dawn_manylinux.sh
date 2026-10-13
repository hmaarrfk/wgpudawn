#!/bin/bash
# Build Dawn (see build_dawn.py) inside the manylinux image that the Linux
# wheels are built in, so that it only needs the glibc of that image.
#
#   tools/build_dawn_manylinux.sh <prefix-dir> [image]
#
# The prefix dir (on the host) is where Dawn gets installed.
set -euo pipefail

PREFIX=$(mkdir -p "$1" && cd "$1" && pwd)
IMAGE=${2:-quay.io/pypa/manylinux_2_28_$(uname -m)}
ROOT=$(cd "$(dirname "$0")/.." && pwd)

docker run --rm -v "$PREFIX:/dawn-prefix" -v "$ROOT:/src:ro" "$IMAGE" bash -euc '
  # Headers only: the window-system libraries are loaded at runtime
  dnf install -y -q libX11-devel libxcb-devel wayland-devel
  export PATH=/opt/python/cp312-cp312/bin:$PATH
  pip install -q cmake ninja
  python /src/tools/build_dawn.py --prefix /dawn-prefix --work-dir /tmp/dawn-build
  chmod -R a+rX /dawn-prefix
'
