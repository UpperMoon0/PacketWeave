package com.nstut.packetweave.api;

import java.util.Arrays;

/** A single finite, indexed transfer. Only TransferRegistry should own this instance. */
final class TransferSession {
    private final byte[][] chunks;
    private final long declaredBytes;
    private long receivedBytes;
    private int receivedChunks;
    private long touchedAtNanos;

    TransferSession(int totalChunks, long declaredBytes, long nowNanos) {
        this.chunks = new byte[totalChunks][];
        this.declaredBytes = declaredBytes;
        this.touchedAtNanos = nowNanos;
    }

    boolean add(int index, byte[] bytes, int maxChunkBytes, long nowNanos) {
        if (index < 0 || index >= chunks.length || bytes == null || bytes.length == 0
                || bytes.length > maxChunkBytes || chunks[index] != null
                || receivedBytes + bytes.length > declaredBytes) return false;
        chunks[index] = Arrays.copyOf(bytes, bytes.length);
        receivedBytes += bytes.length;
        receivedChunks++;
        touchedAtNanos = nowNanos;
        return true;
    }

    boolean complete() { return receivedChunks == chunks.length && receivedBytes == declaredBytes; }
    boolean expired(long nowNanos, long timeoutNanos) {
        return nowNanos - touchedAtNanos >= timeoutNanos;
    }
    long bytes() { return receivedBytes; }
    int receivedChunks() { return receivedChunks; }
    int totalChunks() { return chunks.length; }
    byte[] join() {
        if (!complete()) throw new IllegalStateException("Transfer not complete");
        byte[] output = new byte[(int) receivedBytes];
        int offset = 0;
        for (byte[] chunk : chunks) {
            System.arraycopy(chunk, 0, output, offset, chunk.length);
            offset += chunk.length;
        }
        return output;
    }
}
