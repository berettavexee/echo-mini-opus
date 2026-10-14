#!/bin/sh
# Download and unpack the official libopus 1.5.2 release (BSD-3-Clause) next to this script.
set -e
cd "$(dirname "$0")"
V=opus-1.5.2
SHA=65c1d2f78b9f2fb20082c38cbe47c951ad5839345876e46941612ee87f9a7ce1
[ -d $V ] && { echo "$V already present"; exit 0; }
curl -fLO https://downloads.xiph.org/releases/opus/$V.tar.gz
echo "$SHA  $V.tar.gz" | sha256sum -c -
tar xzf $V.tar.gz && rm $V.tar.gz
