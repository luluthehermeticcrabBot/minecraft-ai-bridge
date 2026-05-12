package io.opencode.minecraft.bot.network;

import io.netty.channel.ChannelFutureListener;
import net.minecraft.network.Connection;
import net.minecraft.network.protocol.Packet;
import net.minecraft.network.protocol.PacketFlow;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.net.InetAddress;

/**
 * A fake NetworkManager connection that mimics a real Minecraft client connection.
 * All packets sent to this connection are silently dropped.
 * The connection always reports as connected.
 */
public class FakePlayerConnection extends Connection {

    public FakePlayerConnection(@NotNull InetAddress address) {
        super(PacketFlow.SERVERBOUND);
        this.channel = new FakeChannel(null, address);
        this.address = this.channel.remoteAddress();
    }

    @Override
    public boolean isConnected() {
        return true;
    }

    @Override
    public void send(Packet<?> packet) {
    }

    @Override
    public void send(Packet<?> packet, @Nullable ChannelFutureListener listener) {
    }

    @Override
    public void send(Packet<?> packet, @Nullable ChannelFutureListener listener, boolean flush) {
    }
}
