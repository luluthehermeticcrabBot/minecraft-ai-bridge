"""Async wrapper around the MCPQ plugin connection.

MCPQ (Minecraft Protobuf Queries) replaces both pyCraft (bot) and most
RCON usage — it connects to a Paper server's mcpq plugin via gRPC and
provides direct world interaction, player control, and command execution.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcpq import Minecraft, Vec3

logger = logging.getLogger(__name__)


class McpqClient:
    """Async wrapper around a gRPC connection to the MCPQ plugin.

    All potentially-blocking gRPC calls are dispatched to a thread-pool
    so the rest of the bridge can stay async.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1789,
        player_name: str = "AIBot",
    ) -> None:
        self._host = host
        self._port = port
        self._player_name = player_name
        self._mc: Minecraft | None = None

    # ── Connection ────────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        return self._mc is not None

    async def connect(
        self,
        retries: int = 20,
        delay: float = 5.0,
    ) -> None:
        """Open a gRPC channel to the MCPQ plugin.

        Retries with backoff so the bridge can wait for the Paper server
        to finish starting up (downloads + builds on first run).

        Parameters
        ----------
        retries : max number of attempts (default 20 → ~2 min at 5 s intervals)
        delay : seconds between attempts (doubles each retry, caps at 30 s)
        """
        last_exc: Exception | None = None

        for attempt in range(1, retries + 1):
            try:
                self._mc = await asyncio.to_thread(
                    Minecraft,
                    host=self._host,
                    port=self._port,
                )
                # Verify the connection by fetching the Minecraft version
                version = await self._run(self._mc.getMinecraftVersion)
                server = await self._run(self._mc.getServerVersion)
                logger.info(
                    "Connected to MCPQ plugin — %s (MC %s)",
                    server,
                    version,
                )
                return
            except Exception as exc:
                last_exc = exc
                self._mc = None
                if attempt < retries:
                    wait = min(delay * (1.5 ** (attempt - 1)), 30.0)
                    logger.warning(
                        "MCPQ not ready yet (attempt %d/%d): %s  Retrying in %.0fs …",
                        attempt,
                        retries,
                        exc.__class__.__name__,
                        wait,
                    )
                    await asyncio.sleep(wait)

        # All retries exhausted
        raise ConnectionError(
            f"Failed to connect to MCPQ plugin at {self._host}:{self._port} "
            f"after {retries} attempts.  Is the server running and the "
            f"plugin installed?  Last error: {last_exc}"
        ) from last_exc

    async def disconnect(self) -> None:
        """Close the gRPC channel."""
        if self._mc is not None:
            # gRPC channel close is best-effort
            self._mc = None
            logger.info("Disconnected from MCPQ plugin")

    # ── Thread-pool helper ────────────────────────────────────────────

    async def _run(self, func: callable, *args: Any, **kwargs: Any) -> Any:
        """Run a synchronous function in a thread-pool."""
        return await asyncio.to_thread(func, *args, **kwargs)

    # ── Player methods ────────────────────────────────────────────────

    async def get_player(self):
        """Return the configured player's Player object, or *None*."""
        assert self._mc is not None
        try:
            return await self._run(self._mc.getPlayer, self._player_name)
        except Exception:
            return None

    async def get_player_pos(self) -> tuple[float, float, float] | None:
        """Get (x, y, z) of the configured player, or *None*."""
        player = await self.get_player()
        if player is not None:
            return (player.pos.x, player.pos.y, player.pos.z)
        return None

    async def get_player_info(self) -> dict[str, Any]:
        """Return structured info about the configured player."""
        player = await self.get_player()
        if player is None:
            return {"online": False}

        nbt = None
        try:
            nbt = await self._run(player.getNbt)
        except Exception:
            pass

        info: dict[str, Any] = {
            "online": True,
            "name": player.name,
            "pos": {"x": player.pos.x, "y": player.pos.y, "z": player.pos.z},
            "world": player.world.name if player.world else None,
        }

        if nbt is not None:
            info["health"] = nbt.get("Health")
            info["food"] = nbt.get("foodLevel")
            info["gamemode"] = nbt.get("playerGameType")

        return info

    @property
    def player_name(self) -> str:
        """The configured player name."""
        return self._player_name

    async def run_as_player(self, command: str) -> str:
        """Run a Minecraft command **as** the configured player.

        Replaces ``@p`` with the actual player name so the command
        always targets the bot, never a human player who happens to
        be nearest.
        """
        substituted = command.replace("@p", self._player_name)
        return await self.run_command_blocking(substituted)

    async def get_chat_events(self):
        """Poll for recent chat events via MCPQ's event system.

        Returns a list of ``ChatEvent`` objects, each with ``.player.name``
        and ``.message`` attributes.  Call this periodically from the
        chat command handler to detect ``!commands``.
        """
        if self._mc is None:
            return []
        return await self._run(self._mc.events.chat.poll)

    async def teleport_player(self, x: float, y: float, z: float) -> None:
        """Teleport the configured player to an absolute position.

        Uses ``/tp`` command because MCPQ's ``player.teleport(Vec3)`` gRPC
        call silently fails on Paper 26.1.2 (reports success but doesn't
        actually move the player).
        """
        await self.run_as_player(f"tp @p {x} {y} {z}")

    # ── World methods ─────────────────────────────────────────────────

    async def get_block(self, x: int, y: int, z: int) -> str:
        """Return the block type name at (x, y, z), e.g. ``"stone"``."""
        assert self._mc is not None
        block = await self._run(self._mc.getBlock, Vec3(x, y, z))
        return str(block.name) if block else "unknown"

    async def set_block(
        self,
        block_type: str,
        x: int,
        y: int,
        z: int,
    ) -> None:
        """Place ``block_type`` at (x, y, z), overwriting anything there."""
        assert self._mc is not None
        await self._run(self._mc.setBlock, block_type, Vec3(x, y, z))

    async def set_sign(
        self,
        x: int,
        y: int,
        z: int,
        lines: list[str],
        color: str = "black",
        glowing: bool = False,
        direction: str = "south",
        sign_block: str = "oak_sign",
    ) -> None:
        """Place a sign with text at (x, y, z).

        Parameters
        ----------
        x, y, z : block coordinates
        lines : up to 4 strings for each sign line
        """
        assert self._mc is not None
        await self._run(
            self._mc.setSign,
            Vec3(x, y, z),
            lines,
            color=color,
            glowing=glowing,
            direction=direction,
            sign_block=sign_block,
        )

    # ── Commands ──────────────────────────────────────────────────────

    async def run_command(self, command: str) -> None:
        """Run a server command (fire-and-forget)."""
        assert self._mc is not None
        await self._run(self._mc.runCommand, command)

    async def run_command_blocking(self, command: str) -> str:
        """Run a server command and return its output."""
        assert self._mc is not None
        return await self._run(self._mc.runCommandBlocking, command)

    # ── Chat ──────────────────────────────────────────────────────────

    async def post_to_chat(self, message: str) -> None:
        """Broadcast a chat message to all players."""
        assert self._mc is not None
        await self._run(self._mc.postToChat, message)

    # ── Utility ───────────────────────────────────────────────────────

    async def get_server_version(self) -> str:
        """Return the Paper server version string."""
        assert self._mc is not None
        return await self._run(self._mc.getServerVersion)

    async def get_biome(self, x: int, y: int, z: int) -> str:
        """Detect the biome at a given position using surface-block heuristics
        and (fallback) command-based checks.

        Paper 1.21.4 removed the ``/locatebiome`` command (it's now
        ``/locate biome <type>`` and requires a biome argument), so we use
        a two-pronged approach:

        1. **Block heuristics** — check the surface block and infer the
           biome from known block-climate mappings.  Fast and reliable.
        2. **Command fallback** — try ``/execute if biome`` checks for
           common biomes when heuristics are ambiguous.

        Returns the biome name (e.g. ``"plains"``) or ``"unknown"``.
        """
        # ── Heuristic: surface block → biome mapping ───────────────
        try:
            surface = await self.get_block(x, y - 1, z)
            block_id = surface.lower()

            # Known block-biome mappings (extend as needed)
            block_to_biome: dict[str, str] = {
                "grass_block": "plains",
                "sand": "desert",
                "red_sand": "badlands",
                "snow_block": "snowy_plains",
                "mycelium": "mushroom_fields",
                "podzol": "old_growth_taiga",
                "terracotta": "badlands",
                "water": "ocean",
                "gravel": "ocean",
                "stone": "windswept_hills",
                "coarse_dirt": "savanna",
            }

            for prefix, biome in block_to_biome.items():
                if prefix in block_id:
                    return biome

            # ── Secondary heuristic: check nearby blocks ────────────
            # If the surface block is generic (e.g., dirt or grass),
            # check adjacent blocks for climate indicators.
            neighbors = [
                await self.get_block(x + 1, y - 1, z),
                await self.get_block(x - 1, y - 1, z),
                await self.get_block(x, y - 1, z + 1),
                await self.get_block(x, y - 1, z - 1),
            ]

            neighbor_ids = " ".join(n.lower() for n in neighbors)

            if "snow" in neighbor_ids or "ice" in neighbor_ids:
                return "snowy_plains"
            if "sand" in neighbor_ids and "red_sand" in neighbor_ids:
                return "beach"
            if "water" in neighbor_ids or "kelp" in neighbor_ids:
                # Check if mostly surrounded by water → ocean
                water_count = sum(1 for n in neighbors if "water" in n.lower())
                if water_count >= 3:
                    return "ocean"
                return "beach" if "sand" in neighbor_ids else "river"
            if "terracotta" in neighbor_ids or "red_sand" in neighbor_ids:
                return "badlands"
            if "podzol" in neighbor_ids:
                return "taiga"
            if "mycelium" in neighbor_ids:
                return "mushroom_fields"

        except Exception:
            pass

        # ── Fallback: try /execute if biome for common biomes ──────
        # This works on Paper 1.21.4 but is slow — only run when
        # heuristics don't give a clear answer.
        common_biomes = [
            "plains",
            "desert",
            "forest",
            "taiga",
            "snowy_plains",
            "badlands",
            "ocean",
            "river",
            "swamp",
            "jungle",
        ]
        for biome in common_biomes:
            try:
                check_cmd = (
                    f"execute if biome {x} {y} {z} in minecraft:{biome} run say __biome_{biome}__"
                )
                resp = await self.run_command_blocking(check_cmd)
                if f"__biome_{biome}__" in resp:
                    return biome
            except Exception:
                continue

        return "unknown"

    async def get_time(self) -> str:
        """Query the current in-game time.

        Uses ``time query day`` instead of the legacy ``time query daytime``
        which is broken on Paper 26.1.2 (throws CommandException).
        The result gives total in-game ticks (days × 24000 + daytime).
        """
        return await self.run_command_blocking("time query day")

    async def get_players_online(self) -> list[str]:
        """Return list of online player names."""
        assert self._mc is not None
        players = await self._run(self._mc.getPlayerList)
        return [p.name for p in players]
