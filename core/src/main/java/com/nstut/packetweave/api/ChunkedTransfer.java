package com.nstut.packetweave.api;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Arrays;
import java.util.Objects;

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
        Objects.requireNonNull(consumer, "consumer");
        long size = Files.size(file);
        int total = count(size, chunkBytes);
        try (InputStream input = Files.newInputStream(file)) {
            stream(input, size, chunkBytes, total, consumer);
        }
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
