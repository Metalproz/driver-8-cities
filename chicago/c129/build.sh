#!/bin/sh
# C129: build the civ-AI core for the host (reference) and mipsel (PS1 path), export the road blobs, write the reference
# paths of the test routes and check host == mipsel (the mipsel harness runs in mipsrun, a MIPS I interpreter).
# Run from Git Bash: sh build.sh [CITY ...] (default VEGAS).
# The MIPS toolchain is called by its full D:/ path (the only allowed form, NOTES "C129 toolchain").
set -e
cd "$(dirname "$0")"
mkdir -p out
TC=D:/recomps/tools/gcc-mipsel-none-elf-12.3.0/bin
GCC=$TC/mipsel-none-elf-g++
HOSTBIN=/c/Users/domin/.local/share/retcomm/toolchains/cmake-clang-v1/latest/bin
HOSTCXX=$HOSTBIN/clang++
HOSTCC=$HOSTBIN/clang
MFLAGS="-O2 -march=r3000 -mtune=r3000 -mabi=32 -msoft-float -mno-abicalls -fno-pic -G0 -mno-gpopt -fno-exceptions -fno-rtti -ffreestanding -fno-builtin"
for f in d2civ compat mips_main; do $GCC $MFLAGS -c $f.cpp -o out/${f}_mips.o; done
$TC/mipsel-none-elf-gcc -march=r3000 -mabi=32 -c crt0.s -o out/crt0_mips.o
$TC/mipsel-none-elf-ld -T link.ld -o out/c129_mips.elf out/crt0_mips.o out/mips_main_mips.o out/d2civ_mips.o out/compat_mips.o
$TC/mipsel-none-elf-objcopy -O binary out/c129_mips.elf out/c129_mips.bin
$TC/mipsel-none-elf-size out/d2civ_mips.o out/compat_mips.o out/c129_mips.elf
$HOSTCXX -O1 -std=c++17 -fno-exceptions -Wno-everything -o out/host_main.exe host_main.cpp d2civ.cpp compat.cpp
$HOSTCC -O2 -Wno-everything -o out/mipsrun.exe mipsrun.c
for c in ${@:-VEGAS}; do
    python export_roads.py $c out
done
# Las Vegas test routes (C129 study: 3+ diagonals, 3+ large curves, chains through junctions)
ROUTES="199 201 202 204 205 0x4004 0x4001 0x4005 0x4007 0x4009"
if [ -f out/vegas_roads.bin ]; then
    : > out/vegas_ref_paths.txt
    MARGS=""
    for r in $ROUTES; do
        out/host_main.exe out/vegas_roads.bin out/rcossin.bin $r 2400 40 30 >> out/vegas_ref_paths.txt
        MARGS="$MARGS $r:2400:40:30:-1"
    done
    out/mipsrun.exe out/c129_mips.bin out/vegas_roads.bin out/rcossin.bin $MARGS > out/vegas_mips_paths.txt
    grep -c "" out/vegas_ref_paths.txt
    grep "^#\|CONFUSED" out/vegas_ref_paths.txt
    if cmp -s out/vegas_ref_paths.txt out/vegas_mips_paths.txt; then echo "host == mipsel: identical"; else echo "host != mipsel: DIFFERENT"; exit 1; fi
fi
