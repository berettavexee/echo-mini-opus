#!/bin/bash
cd $(dirname $0)
for f in files/*.opus; do printf "%-26s " $(basename $f .opus); ./bench.sh $1 $PWD/$f 2>&1 | sed 's/open_insns=[0-9]* //;s/frames=[0-9]* //'; done
