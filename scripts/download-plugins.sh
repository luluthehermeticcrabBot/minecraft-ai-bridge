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
# Build from source in bot-plugin/ — requires Java 25+ (the project includes a Gradle wrapper)
BOT_PLUGIN_DIR="${BOT_PLUGIN_DIR:-./bot-plugin}"
BOT_PLUGIN_JAR="${PLUGINS_DIR}/mc-bot-plugin-1.0.0.jar"
if [ ! -x "${BOT_PLUGIN_DIR}/gradlew" ]; then
    echo "✗ Bot plugin Gradle wrapper not found at ${BOT_PLUGIN_DIR}/gradlew." >&2
    exit 1
fi
echo "↓ Building bot plugin against the latest Paper 26.2 dev bundle..."
(cd "$BOT_PLUGIN_DIR" && ./gradlew clean build --no-daemon)
cp "${BOT_PLUGIN_DIR}/build/libs/mc-bot-plugin-1.0.0.jar" "$BOT_PLUGIN_JAR"
echo "✓ Saved $(basename "$BOT_PLUGIN_JAR")"
