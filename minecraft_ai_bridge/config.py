"""Configuration management via YAML + environment variable overrides."""

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml


class MinecraftConfig(BaseSettings):
    host: str = "localhost"
    # RCON settings (kept as optional fallback for admin commands)
    rcon_port: int = 25575
    rcon_password: str = ""
    player_name: str = "AIBot"

    model_config = SettingsConfigDict(env_prefix="minecraft_")


class MCPQConfig(BaseSettings):
    """Connection settings for the MCPQ plugin on a Paper server.

    MCPQ replaces both pyCraft (bot) and most RCON usage — it gives the
    bridge direct world-manipulation and player-control APIs via gRPC.
    """
    host: str = "localhost"
    port: int = 1789
    player_name: str = "AIBot"

    model_config = SettingsConfigDict(env_prefix="mc_api_")


class LLMConfig(BaseSettings):
    provider: Literal["openai", "anthropic", "ollama", "openrouter", "opencode_server"] = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.7
    max_tokens: int = 2048

    # Provider-specific keys set via env vars
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # OpenRouter (OpenAI-compatible proxy)
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_referer: str = ""
    openrouter_title: str = "Minecraft AI Bridge"

    # OpenCode Server (session-based inference API)
    opencode_server_url: str = "http://localhost:4096"
    opencode_server_api_key: str = ""
    opencode_server_model: str = "big-pickle"

    model_config = SettingsConfigDict(env_prefix="llm_")

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def fallback_openai(cls, v: str) -> str:
        if not v:
            import os
            return os.getenv("OPENAI_API_KEY", "")
        return v

    @field_validator("anthropic_api_key", mode="before")
    @classmethod
    def fallback_anthropic(cls, v: str) -> str:
        if not v:
            import os
            return os.getenv("ANTHROPIC_API_KEY", "")
        return v

    @field_validator("openrouter_api_key", mode="before")
    @classmethod
    def fallback_openrouter(cls, v: str) -> str:
        if not v:
            import os
            return os.getenv("OPENROUTER_API_KEY", "")
        return v


class BridgeConfig(BaseSettings):
    max_iterations: int = 100
    cycle_delay: float = 1.0
    memory_window: int = 20
    verbose: bool = True

    model_config = SettingsConfigDict(env_prefix="bridge_")


class GoalConfig(BaseSettings):
    default: str = "Explore the world and gather resources"
    max_depth: int = 5

    model_config = SettingsConfigDict(env_prefix="goals_")


class AppConfig(BaseSettings):
    minecraft: MinecraftConfig = Field(default_factory=MinecraftConfig)
    mc_api: MCPQConfig = Field(default_factory=MCPQConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    bridge: BridgeConfig = Field(default_factory=BridgeConfig)
    goals: GoalConfig = Field(default_factory=GoalConfig)

    model_config = SettingsConfigDict(env_prefix="app_")

    @classmethod
    def from_yaml(cls, path: str | Path = "config.yaml") -> "AppConfig":
        """Load config from a YAML file with env-var overrides.

        Priority: environment vars > YAML > field defaults.
        """
        import os as _os
        path = Path(path)

        # Start from pure env-resolved config (env > defaults)
        cfg = cls()

        if not path.exists():
            return cfg

        with open(path) as f:
            raw = yaml.safe_load(f) or {}
        if not isinstance(raw, dict):
            return cfg

        for section_name in ("minecraft", "mc_api", "llm", "bridge", "goals"):
            yaml_data = raw.get(section_name, {})

            # Gather env-var overrides for this section
            section_model_cls = type(getattr(cfg, section_name))
            prefix: str = section_model_cls.model_config.get("env_prefix", "")
            env_data: dict = {}
            for field_name in section_model_cls.model_fields:
                env_val = _os.getenv((prefix + field_name).upper())
                if env_val is not None:
                    env_data[field_name] = env_val

            # Merge: env > yaml > defaults
            # Re-creating the model applies proper type coercion (e.g.
            # string "1789" → int 1789) which model_copy(update=...) skips.
            merged_data = {**yaml_data, **env_data}
            if merged_data:
                merged = section_model_cls(**merged_data)
                setattr(cfg, section_name, merged)

        return cfg
