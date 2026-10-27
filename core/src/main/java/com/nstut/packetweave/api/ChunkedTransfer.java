package com.nstut.packetweave.api;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Objects;
import java.time.Duration;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/** Loader-neutral outbound chunking. Consumers provide their own authenticated packet adapter. */
public final class ChunkedTransfer {
    public static final int CHUNK_BYTES = 30 * 1024;
    private ChunkedTransfer() { }

    @FunctionalInterface
    public interface Consumer {
        void accept(int index, int totalChunks, byte[] data) throws IOException;
    }

    private static int count(long bytes, int chunkBytes) {
        if (chunkBytes <= 0 || chunkBytes > 1024 * 1024 || bytes <= 0 || bytes > Integer.MAX_VALUE)
            throw new IllegalArgumentException("Invalid transfer size");
        return (int) ((bytes + chunkBytes - 1) / chunkBytes);
    }

    public static void send(byte[] bytes, int chunkBytes, Consumer consumer) throws IOException {
        Objects.requireNonNull(bytes, "bytes");
        Objects.requireNonNull(consumer, "consumer");
        int total = count(bytes.length, chunkBytes);
        for (int index = 0; index < total; index++) {
            int start = index * chunkBytes;
            consumer.accept(index, total, Arrays.copyOfRange(bytes, start,
                    (int) Math.min((long) bytes.length, (long) start + chunkBytes)));
        }
    }

    public static void streamFile(Path file, int chunkBytes, Consumer consumer) throws IOException {
        streamFile(file, chunkBytes, Integer.MAX_VALUE, consumer);
    }

    public static void streamFile(Path file, int chunkBytes, long byteLimit, Consumer consumer) throws IOException {
        Objects.requireNonNull(consumer, "consumer");
        long size = Files.size(file);
        if (byteLimit <= 0 || size > byteLimit) throw new IOException("File exceeds receiver policy");
        int total = count(size, chunkBytes);
        try (InputStream input = Files.newInputStream(file)) {
            stream(input, size, chunkBytes, total, consumer);
        }
    }

    /**
     * Streams bounded batches through an executor with one outstanding dispatch per
     * worker. At most {@code batchChunks * chunkBytes} payload bytes are retained;
     * each dispatch sends no more than batchChunks packets. Call off the executor
     * thread. This bounds local dispatch, not the remote peer's network buffers.
     */
    public static void streamFileBatched(Path file, int chunkBytes, long byteLimit,
                                         int batchChunks, Executor executor, Duration timeout,
                                         Consumer sink) throws IOException {
        if (batchChunks <= 0 || batchChunks > 32)
            throw new IllegalArgumentException("Batch size must be between 1 and 32");
        Objects.requireNonNull(sink, "sink");
        java.util.List<byte[]> batch = new java.util.ArrayList<>(batchChunks);
        Consumer dispatch = onExecutor(executor, timeout, (last, total, ignored) -> {
            int first = last - batch.size() + 1;
            for (int i = 0; i < batch.size(); i++) sink.accept(first + i, total, batch.get(i));
        });
        streamFile(file, chunkBytes, byteLimit, (index, total, data) -> {
            batch.add(data);
            if (batch.size() == batchChunks || index == total - 1) {
                dispatch.accept(index, total, data);
                batch.clear();
            }
        });
    }

    /**
     * Backpressure for a worker streaming through a game-thread executor: only one dispatched
     * chunk is outstanding per worker. Call the returned consumer from a different thread.
     * This acknowledges local dispatch, not receipt by the remote peer.
     */
    public static Consumer onExecutor(Executor executor, Duration timeout, Consumer sink) {
        Objects.requireNonNull(executor, "executor");
        Objects.requireNonNull(sink, "sink");
        if (timeout == null || timeout.isZero() || timeout.isNegative())
            throw new IllegalArgumentException("Invalid dispatch timeout");
        final long nanos = timeout.toNanos();
        return (index, total, data) -> {
            CompletableFuture<Void> dispatched = new CompletableFuture<>();
            java.util.concurrent.atomic.AtomicReference<byte[]> payload =
                    new java.util.concurrent.atomic.AtomicReference<>(data);
            try {
                executor.execute(() -> {
                    if (dispatched.isDone()) return;
                    byte[] chunk = payload.getAndSet(null);
                    if (chunk == null || dispatched.isDone()) return;
                    try { sink.accept(index, total, chunk); dispatched.complete(null); }
                    catch (Exception exception) { dispatched.completeExceptionally(exception); }
                });
                dispatched.get(nanos, TimeUnit.NANOSECONDS);
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException("Transfer dispatch interrupted", exception);
            } catch (ExecutionException | TimeoutException | RuntimeException exception) {
                throw new IOException("Transfer dispatch failed", exception);
            } finally {
                // Prevent a timed-out task that has not started from sending stale chunks later.
                dispatched.cancel(false);
                // A stalled executor may retain this task after its worker exits.
                payload.set(null);
            }
        };
    }

    // Fill each chunk even when an InputStream returns short reads; detect files changing mid-transfer.
    static void stream(InputStream input, long size, int chunkBytes, int total, Consumer consumer) throws IOException {
        long remaining = size;
        for (int index = 0; index < total; index++) {
            byte[] chunk = new byte[(int) Math.min(remaining, chunkBytes)];
            int offset = 0;
            while (offset < chunk.length) {
                int read = input.read(chunk, offset, chunk.length - offset);
                if (read < 0) throw new IOException("File shortened during transfer");
                if (read == 0) {
                    int value = input.read();
                    if (value < 0) throw new IOException("File shortened during transfer");
                    chunk[offset++] = (byte) value;
                } else offset += read;
            }
            consumer.accept(index, total, chunk);
            remaining -= chunk.length;
        }
        if (input.read() != -1) throw new IOException("File grew during transfer");
    }
}
