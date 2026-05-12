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
MCPQ_JAR_URL="https://github.com/mcpq/mcpq-plugin/releases/download/v${MCPQ_VERSION}/mcpq-${MCPQ_VERSION}.jar"

mkdir -p "$PLUGINS_DIR"

# ── MCPQ ──
if [ -f "${PLUGINS_DIR}/mcpq-${MCPQ_VERSION}.jar" ]; then
    echo "✓ MCPQ ${MCPQ_VERSION} already downloaded."
else
    echo "↓ Downloading MCPQ ${MCPQ_VERSION} from GitHub releases..."
    if command -v curl &>/dev/null; then
        curl -sL "$MCPQ_JAR_URL" -o "${PLUGINS_DIR}/mcpq-${MCPQ_VERSION}.jar"
    elif command -v wget &>/dev/null; then
        wget -q "$MCPQ_JAR_URL" -O "${PLUGINS_DIR}/mcpq-${MCPQ_VERSION}.jar"
    else
        echo "✗ Need curl or wget." >&2
        exit 1
    fi
    echo "✓ Saved mcpq-${MCPQ_VERSION}.jar"
fi

# ── Bot plugin (replaces fakeplayer + CommandAPI) ──
# Build from source in bot-plugin/ — requires Maven + Java 25
BOT_PLUGIN_JAR=$(ls "${PLUGINS_DIR}/mc-bot-plugin-"*.jar 2>/dev/null || true)
if [ -n "$BOT_PLUGIN_JAR" ]; then
    echo "✓ Bot plugin already present: $(basename "$BOT_PLUGIN_JAR")"
else
    echo "ℹ  Bot plugin not found in ${PLUGINS_DIR}."
    echo "   Build it with: cd bot-plugin && mvn clean package -DskipTests"
    echo "   Then copy target/mc-bot-plugin-*.jar to ${PLUGINS_DIR}/"
fi
