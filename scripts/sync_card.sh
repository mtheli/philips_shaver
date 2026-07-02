#!/usr/bin/env bash
# Build the Philips Shaver Card and copy the bundle into the integration.
#
# The card source lives in its own repo (mtheli/philips_shaver_card) but is
# shipped inside this integration (custom_components/philips_shaver/www/).
# The card version is the integration version from manifest.json.
#
# Usage: scripts/sync_card.sh            (card repo expected next to this repo)
#        CARD_REPO=/path/to/card scripts/sync_card.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
CARD_DIR="${CARD_REPO:-$REPO_DIR/../philips_shaver_card}"
MANIFEST="$REPO_DIR/custom_components/philips_shaver/manifest.json"
WWW_DIR="$REPO_DIR/custom_components/philips_shaver/www"
VERSION_JS="$CARD_DIR/src/version.js"

if [[ ! -f "$CARD_DIR/package.json" ]]; then
    echo "Card repo not found at $CARD_DIR (set CARD_REPO)" >&2
    exit 1
fi

VERSION="$(python3 -c "import json; print(json.load(open('$MANIFEST'))['version'])")"

# Stamp version + origin into the card source; restore the dev default afterwards
# so the card repo stays clean for `npm run watch` development.
restore_version_js() {
    cat > "$VERSION_JS" <<'EOF'
// Written by the release sync script (philips_shaver scripts/sync_card.sh).
// The card is versioned together with the philips_shaver integration and is
// normally served by it ("bundled"); "standalone" marks a local dev build.
export const CARD_VERSION = "dev";
export const CARD_ORIGIN = "standalone";
EOF
}
trap restore_version_js EXIT

cat > "$VERSION_JS" <<EOF
// Written by the release sync script (philips_shaver scripts/sync_card.sh).
export const CARD_VERSION = "$VERSION";
export const CARD_ORIGIN = "bundled";
EOF

(cd "$CARD_DIR" && rm -rf dist .parcel-cache && npm run build)

mkdir -p "$WWW_DIR"
cp "$CARD_DIR/dist/philips_shaver_card.js" "$WWW_DIR/philips_shaver_card.js"
echo "Bundled card v$VERSION -> $WWW_DIR/philips_shaver_card.js"
