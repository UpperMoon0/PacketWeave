package com.nstut.packetweave.api;

import java.time.Duration;

/** Explicit, immutable budgets; bytes are accounted before they are retained. */
public final class TransferLimits {
    private final int chunkBytes;
    private final long transferBytes;
    private final int concurrentGlobal;
    private final int concurrentPerOwner;
    private final long bufferedBytes;
    private final long timeoutNanos;

    public TransferLimits(int chunkBytes, long transferBytes, int concurrentGlobal,
                          int concurrentPerOwner, long bufferedBytes, Duration timeout) {
        if (chunkBytes <= 0 || chunkBytes > 1024 * 1024
                || transferBytes <= 0 || transferBytes > Integer.MAX_VALUE
                || concurrentGlobal <= 0 || concurrentPerOwner <= 0
                || concurrentPerOwner > concurrentGlobal || bufferedBytes < chunkBytes
                || bufferedBytes < transferBytes || timeout == null
                || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("Invalid transfer limits");
        }
        this.chunkBytes = chunkBytes;
        this.transferBytes = transferBytes;
        this.concurrentGlobal = concurrentGlobal;
        this.concurrentPerOwner = concurrentPerOwner;
        this.bufferedBytes = bufferedBytes;
        this.timeoutNanos = timeout.toNanos();
    }
    public static TransferLimits defaults() {
        return new TransferLimits(30 * 1024, 16L * 1024 * 1024, 32, 2,
                64L * 1024 * 1024, Duration.ofSeconds(30));
    }
    public int chunkBytes() { return chunkBytes; }
    public long transferBytes() { return transferBytes; }
    public int concurrentGlobal() { return concurrentGlobal; }
    public int concurrentPerOwner() { return concurrentPerOwner; }
    public long bufferedBytes() { return bufferedBytes; }
    public long timeoutNanos() { return timeoutNanos; }
}
