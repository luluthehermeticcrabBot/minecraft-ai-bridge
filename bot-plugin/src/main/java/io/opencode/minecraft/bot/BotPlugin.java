package io.opencode.minecraft.bot;

import com.google.common.base.Charsets;
import com.mojang.authlib.GameProfile;
import io.opencode.minecraft.bot.network.FakePlayerConnection;
import net.minecraft.server.MinecraftServer;
import net.minecraft.server.level.ClientInformation;
import net.minecraft.server.level.ServerLevel;
import net.minecraft.server.level.ServerPlayer;
import net.minecraft.server.network.CommonListenerCookie;
import net.minecraft.server.players.PlayerList;
import org.bukkit.Bukkit;
import org.bukkit.command.Command;
import org.bukkit.command.CommandSender;
import org.bukkit.craftbukkit.CraftServer;
import org.bukkit.plugin.java.JavaPlugin;
import org.jetbrains.annotations.NotNull;

import java.net.InetAddress;
import java.util.UUID;

/**
 * A minimal Paper plugin that creates a fake player (bot) entity on the server.
 * The bot is a real ServerPlayer that exists in the PlayerList, allowing
 * MCPQ to detect it and player-relative commands to work.
 *
 * Usage: /botsummon <name>
 * Note: This running Paper version must equal <api-version> for bot to work.
 */
public class BotPlugin extends JavaPlugin {

    private static final String OFFLINE_PLAYER_PREFIX = "OfflinePlayer:";

    @Override
    public void onEnable() {
        getLogger().info("MCPQ-Bot plugin enabled");
        getLogger().info("Server version: " + Bukkit.getMinecraftVersion());
        getLogger().info("Server Bukkit version: " + Bukkit.getVersion());
    }

    @Override
    public boolean onCommand(
            @NotNull CommandSender sender,
            @NotNull Command command,
            @NotNull String label,
            @NotNull String[] args
    ) {
        if (args.length < 1) {
            sender.sendMessage("Usage: /botsummon <name>");
            return true;
        }

        String playerName = args[0];

        if (playerName.length() > 16) {
            sender.sendMessage("Player name too long (max 16 characters)");
            return true;
        }

        try {
            summonBot(playerName);
            sender.sendMessage("Summoned bot: " + playerName);
        } catch (Exception e) {
            sender.sendMessage("Failed to summon bot: " + e.getMessage());
            getLogger().severe("Failed to summon bot '" + playerName + "': " + e.getMessage());
            e.printStackTrace();
        }

        return true;
    }

    /**
     * Creates a fake player on the server using Paper's NMS internals.
     * The player gets a real ServerPlayer entity in the PlayerList,
     * making them visible to MCPQ and player-relative commands.
     */
    private void summonBot(@NotNull String name) throws Exception {
        CraftServer craftServer = (CraftServer) Bukkit.getServer();
        MinecraftServer nmsServer = craftServer.getServer();
        ServerLevel world = nmsServer.overworld();

        // Create a consistent UUID from the player name (offline mode style)
        UUID uuid = UUID.nameUUIDFromBytes(
                (OFFLINE_PLAYER_PREFIX + name).getBytes(Charsets.UTF_8)
        );

        GameProfile profile = new GameProfile(uuid, name);

        // Create the ServerPlayer entity
        ServerPlayer player = new ServerPlayer(
                nmsServer,
                world,
                profile,
                ClientInformation.createDefault()
        );

        // Create a fake network connection
        FakePlayerConnection connection = new FakePlayerConnection(
                InetAddress.getLoopbackAddress()
        );

        // Create the initial login cookie
        CommonListenerCookie cookie = CommonListenerCookie.createInitial(profile, false);

        // Register the player with the server's PlayerList
        PlayerList playerList = craftServer.getHandle();
        playerList.placeNewPlayer(connection, player, cookie);

        getLogger().info("Bot '" + name + "' summoned at " +
                player.getX() + ", " + player.getY() + ", " + player.getZ());
    }
}
