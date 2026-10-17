#!/bin/bash
# Build PyAV for Pyodide, with FFmpeg compiled to WebAssembly: imageio reads
# and writes video with it (its "pyav" plugin), as on a desktop. Neither PyPI
# nor Pyodide has it.
#
#   website/build_pyav.sh <out-dir>
#
# Needs the Emscripten of the target Pyodide on the PATH (emcc), and
# pyodide-build with its cross-build environment (`pyodide build`).
#
# FFmpeg is one shared library (an Emscripten side module) that the ~40
# extension modules of PyAV load, as on a desktop; linked into each of them,
# it would be there 40 times. It has the decoders, demuxers and parsers of
# common video and audio formats, and encoders that need no external library
# (no x264: that is GPL). LGPL, like FFmpeg's own default.
set -euo pipefail

OUT=$(mkdir -p "$1" && cd "$1" && pwd)
PYAV_VERSION=19.0.1
FFMPEG_VERSION=9.0.2
FLAGS="-fPIC -fwasm-exceptions -sSUPPORT_LONGJMP=wasm -O2"
# Not the flags of a host compiler (e.g. of a conda environment)
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS

WORK=${WORK:-$(mktemp -d)}
[ -n "${KEEP_WORK:-}" ] || trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK"
cd "$WORK"
PREFIX=$WORK/prefix

if [ ! -f "$PREFIX/lib/libffmpeg.so" ]; then
  [ -d "ffmpeg-$FFMPEG_VERSION" ] || curl -sSL "https://ffmpeg.org/releases/ffmpeg-$FFMPEG_VERSION.tar.xz" | tar -xJ
  embuilder build zlib --pic > /dev/null
  (
    cd "ffmpeg-$FFMPEG_VERSION"
    emconfigure ./configure --prefix="$PREFIX" \
      --target-os=none --arch=x86_32 --enable-cross-compile \
      --cc=emcc --cxx=em++ --ar=emar --ranlib=emranlib --nm=emnm \
      --disable-asm --disable-inline-asm --disable-x86asm --disable-runtime-cpudetect \
      --disable-programs --disable-doc --disable-debug --disable-network --disable-autodetect \
      --disable-pthreads --disable-w32threads --disable-os2threads --enable-pic \
      --disable-everything --enable-zlib \
      --enable-avcodec --enable-avformat --enable-avutil --enable-avfilter \
      --enable-avdevice --enable-swscale --enable-swresample \
      --enable-decoder=h264,hevc,mpeg4,mpeg1video,mpeg2video,vp8,vp9,av1,mjpeg,png,gif,rawvideo \
      --enable-decoder=mp3,mp3float,aac,opus,vorbis,flac,pcm_s16le,pcm_f32le \
      --enable-encoder=mpeg4,mjpeg,png,gif,rawvideo,pcm_s16le,aac \
      --enable-demuxer=mov,matroska,avi,mp3,ogg,wav,gif,image2,flac,aac,mpegts,mpegps,rawvideo \
      --enable-muxer=mp4,mov,matroska,avi,gif,image2,wav,rawvideo,null \
      --enable-parser=h264,hevc,mpeg4video,mpegvideo,vp8,vp9,av1,aac,mpegaudio,opus,vorbis,flac,mjpeg,png,gif \
      --enable-bsf=h264_mp4toannexb,hevc_mp4toannexb,aac_adtstoasc,vp9_superframe \
      --enable-protocol=file,pipe \
      --enable-filter=buffer,buffersink,abuffer,abuffersink,format,aformat,scale,aresample \
      --enable-filter=null,anull,fps,setpts,asetpts,transpose,hflip,vflip,crop,pad,copy \
      --enable-filter=split,asplit,volume,loudnorm \
      --extra-cflags="$FLAGS -sUSE_ZLIB=1" --extra-ldflags="$FLAGS -sUSE_ZLIB=1" \
      > ../ffmpeg-configure.log 2>&1 || { tail -30 ffbuild/config.log; exit 1; }
    emmake make -j"$(nproc)" > ../ffmpeg-make.log 2>&1 || { tail -40 ../ffmpeg-make.log; exit 1; }
    emmake make install > /dev/null
  )
  # The static libraries, as one side module (with zlib)
  echo "" > empty.c
  emcc $FLAGS -sSIDE_MODULE=1 empty.c -Wl,--whole-archive \
    "$PREFIX"/lib/{libavdevice,libavfilter,libavformat,libavcodec,libswresample,libswscale,libavutil}.a \
    -Wl,--no-whole-archive -sUSE_ZLIB=1 -o "$PREFIX/lib/libffmpeg.so" \
    -Wl,--allow-multiple-definition  # framepool.o is in libavfilter and libswscale
fi
ls -l "$PREFIX/lib/libffmpeg.so"

# PyAV, linked to that library, which goes in the package (av/libffmpeg.so).
# Its modules are in av/ and in subpackages of it: they find it via rpath,
# one entry per directory (Pyodide replaces only one $ORIGIN in an entry).
rm -rf "av-$PYAV_VERSION" dist
curl -sSL "https://files.pythonhosted.org/packages/source/a/av/av-$PYAV_VERSION.tar.gz" | tar -xz
(
  cd "av-$PYAV_VERSION"
  python - "$PREFIX" <<'EOF'
import re, sys
s = open("setup.py").read()
s, n1 = re.subn(r"FFMPEG_LIBRARIES = \[[^\]]*\]", 'FFMPEG_LIBRARIES = ["ffmpeg"]', s)
s, n2 = re.subn(r"^FFMPEG_DIR = None$", f"FFMPEG_DIR = {sys.argv[1]!r}", s, flags=re.M)
assert n1 == n2 == 1, "setup.py of PyAV changed"
open("setup.py", "w").write(s)
EOF
  # (PIP_CONFIG_FILE: not the pip settings of the machine)
  PIP_CONFIG_FILE=/dev/null LDFLAGS='-Wl,-rpath,$ORIGIN -Wl,-rpath,$ORIGIN/.. -Wl,-rpath,$ORIGIN/../..' pyodide build -o ../dist > ../pyav-build.log 2>&1 \
    || { tail -40 ../pyav-build.log; exit 1; }
)
WHEEL=$(ls dist/av-*.whl)
python -m wheel unpack -d unpacked "$WHEEL" > /dev/null
cp "$PREFIX/lib/libffmpeg.so" unpacked/av-*/av/
python -m wheel pack -d "$OUT" unpacked/av-* > /dev/null
ls -l "$OUT"/av-*.whl
