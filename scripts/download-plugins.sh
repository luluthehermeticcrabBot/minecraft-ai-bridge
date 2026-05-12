#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────
# Download the MCPQ plugin jar into the mounted plugins dir.
# Run once before `docker compose up`.
#
#   chmod +x scripts/download-plugins.sh
#   ./scripts/download-plugins.sh
#
# See: https://github.com/mcpq/mcpq-plugin/releases
# ──────────────────────────────────────────────────────────
set -euo pipefail

MCPQ_VERSION="${MCPQ_VERSION:-2.2}"
PLUGINS_DIR="${PLUGINS_DIR:-./mcpq-plugins}"
JAR_URL="https://github.com/mcpq/mcpq-plugin/releases/download/v${MCPQ_VERSION}/mcpq-${MCPQ_VERSION}.jar"

mkdir -p "$PLUGINS_DIR"

if [ -f "${PLUGINS_DIR}/mcpq-${MCPQ_VERSION}.jar" ]; then
    echo "✓ MCPQ ${MCPQ_VERSION} already downloaded."
    exit 0
fi

echo "↓ Downloading MCPQ ${MCPQ_VERSION} from GitHub releases..."
if command -v curl &>/dev/null; then
    curl -sL "$JAR_URL" -o "${PLUGINS_DIR}/mcpq-${MCPQ_VERSION}.jar"
elif command -v wget &>/dev/null; then
    wget -q "$JAR_URL" -O "${PLUGINS_DIR}/mcpq-${MCPQ_VERSION}.jar"
else
    echo "✗ Need curl or wget." >&2
    exit 1
fi

echo "✓ Saved to ${PLUGINS_DIR}/mcpq-${MCPQ_VERSION}.jar"
