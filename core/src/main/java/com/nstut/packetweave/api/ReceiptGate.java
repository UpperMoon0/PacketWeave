package com.nstut.packetweave.api;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

/** Worker-side, one-chunk window. Receipt values are cumulative committed byte counts. */
public final class ReceiptGate {
    private long expected, committed;
    private boolean cancelled;
    public synchronized void expect(long bytes) throws IOException {
        if (cancelled || expected > committed || bytes <= committed)
            throw new IOException("Invalid or cancelled receipt window");
        expected = bytes;
    }
    /** Ignore stale, duplicate and out-of-window receipts. */
    public synchronized void acknowledge(long bytes) {
        if (!cancelled && bytes == expected && bytes > committed) {
            committed = bytes;
            notifyAll();
        }
    }
    public synchronized void await(Duration timeout) throws IOException {
        if (timeout == null || timeout.isNegative() || timeout.isZero())
            throw new IllegalArgumentException("Invalid receipt timeout");
        long deadline = System.nanoTime() + timeout.toNanos();
        while (!cancelled && committed < expected) {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) throw new IOException("Remote chunk receipt timed out");
            try { TimeUnit.NANOSECONDS.timedWait(this, remaining); }
            catch (InterruptedException error) {
                Thread.currentThread().interrupt();
                throw new IOException("Transfer interrupted", error);
            }
        }
        if (cancelled) throw new IOException("Transfer cancelled");
    }
    public synchronized void cancel() { cancelled = true; notifyAll(); }
}
