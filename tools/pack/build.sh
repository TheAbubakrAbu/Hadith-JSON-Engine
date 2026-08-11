#!/bin/bash
# Build the app-ready hadith packs from this repo's JSONs.
#
#   tools/pack/build.sh [path-to-Al-Islam-iOS]
#
# Default target is ../Al-Islam-iOS, i.e. the app checked out beside this repo. Writes:
#
#   <app>/Resources/Data/Hadith/*.hpk           the 17 packs the app ships
#   <app>/Resources/Data/Hadith/manifest.json   what was built: shapes, sizes, sha256 per pack
#   <app>/iPhone/Hadith/HadithFold.swift      a verbatim copy of tools/pack/HadithFold.swift
#
# The fold is copied rather than referenced because the app has to compile it; the packer stamps a
# fingerprint of it into every pack, and the app checks its own against that at launch - so a drifted
# copy is caught immediately instead of quietly breaking search.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(cd "$here/../.." && pwd)"
app="${1:-$(cd "$repo/.." && pwd)/Al-Islam-iOS}"

if [ ! -d "$app/iPhone/Hadith" ]; then
    echo "error: no app at $app (pass its path as the first argument)" >&2
    exit 1
fi

out="$app/Resources/Data/Hadith"
build="$(mktemp -d)"
trap 'rm -rf "$build"' EXIT

echo "==> compiling the packer"
swiftc -O -parse-as-library \
    "$here/HadithFold.swift" "$here/pack-hadith.swift" \
    -o "$build/pack-hadith"

echo "==> packing $repo/db/by_book -> $out"
mkdir -p "$out"
"$build/pack-hadith" "$repo/db/by_book" "$out" "$here/daily-blocked-words.txt"

echo "==> syncing the fold into the app"
cp "$here/HadithFold.swift" "$app/iPhone/Hadith/HadithFold.swift"

# The gate. Packing successfully is not the same as packing CORRECTLY: a stale rebuild, an edited
# JSON, or a packer bug all produce files that decode perfectly and ship the wrong text. This
# re-derives every string from db/by_book and refuses the build if any of them disagrees.
echo "==> verifying the packs against db/by_book"
python3 "$repo/tools/verify_packs.py" "$out"

echo "==> done"
ls -la "$out"
