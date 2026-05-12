FROM python:3.13-slim

WORKDIR /app

# Install the bridge package
COPY pyproject.toml README.md ./
COPY minecraft_ai_bridge/ minecraft_ai_bridge/
RUN pip install --no-cache-dir -e .

# Default command (override via compose or CLI)
ENTRYPOINT ["minecraft-ai-bridge"]
CMD []
