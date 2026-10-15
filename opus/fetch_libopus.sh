#!/bin/sh
# Download and unpack the official libopus 1.5.2 release (BSD-3-Clause) next to this script,
# then create opus-1.5.2-var: the same sources plus patches/libopus-decoder-only.diff
# (used by the optimised HIFIEC52 build, see `make variant`).
set -e
cd "$(dirname "$0")"
V=opus-1.5.2
SHA=65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1
if [ ! -d $V ]; then
  curl -fLO https://downloads.xiph.org/releases/opus/$V.tar.gz
  echo "$SHA  $V.tar.gz" | sha256sum -c -
  tar xzf $V.tar.gz && rm $V.tar.gz
fi
if [ ! -d $V-var ]; then
  cp -r $V $V-var
  patch -s -d $V-var -p1 < patches/libopus-decoder-only.diff
fi
echo "ready: $V (unmodified) and $V-var (decoder-only variant)"
