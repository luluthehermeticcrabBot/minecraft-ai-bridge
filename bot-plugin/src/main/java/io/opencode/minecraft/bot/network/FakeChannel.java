package io.opencode.minecraft.bot.network;

import io.netty.channel.*;
import org.jetbrains.annotations.NotNull;
import org.jetbrains.annotations.Nullable;

import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;

/**
 * A fake Netty Channel that mimics a client connection.
 * All I/O operations are no-ops.
 * The channel always reports as open, active, and connected.
 * Uses a real DefaultChannelPipeline so NMS internals don't explode.
 */
public class FakeChannel extends AbstractChannel {

    private static final EventLoop EVENT_LOOP = new DefaultEventLoop();
    private final ChannelConfig config = new DefaultChannelConfig(this);
    private final InetAddress address;

    public FakeChannel(@Nullable Channel parent, @NotNull InetAddress address) {
        super(parent);
        this.address = address;
    }

    @Override
    public ChannelConfig config() {
        config.setAutoRead(true);
        return config;
    }

    @Override
    protected void doBeginRead() {
    }

    @Override
    protected void doBind(SocketAddress localAddress) {
    }

    @Override
    protected void doClose() {
    }

    @Override
    protected void doDisconnect() {
    }

    @Override
    protected void doWrite(ChannelOutboundBuffer in) {
        for (; ; ) {
            Object msg = in.current();
            if (msg == null) {
                break;
            }
            in.remove();
        }
    }

    @Override
    public boolean isActive() {
        return true;
    }

    @Override
    protected boolean isCompatible(EventLoop loop) {
        return true;
    }

    @Override
    public boolean isOpen() {
        return true;
    }

    @Override
    protected SocketAddress localAddress0() {
        return new InetSocketAddress(address, 25565);
    }

    @Override
    public ChannelMetadata metadata() {
        return new ChannelMetadata(true);
    }

    @Override
    protected AbstractUnsafe newUnsafe() {
        return new AbstractUnsafe() {
            @Override
            public void connect(SocketAddress remoteAddress, SocketAddress localAddress, ChannelPromise promise) {
                safeSetSuccess(promise);
            }
        };
    }

    @Override
    protected SocketAddress remoteAddress0() {
        return new InetSocketAddress(address, 25565);
    }

    @Override
    public EventLoop eventLoop() {
        return EVENT_LOOP;
    }
}
