package com.nstut.packetweave.api;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.*;
import java.nio.file.*;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicReference;
import static org.junit.jupiter.api.Assertions.*;

class BoundedFileReceiverTest {
    @TempDir Path dir;
    TransferId id(UUID owner) { return new TransferId("test", owner, UUID.randomUUID()); }
    static final class Probe implements BoundedFileReceiver.Listener {
        final BlockingQueue<Long> receipts = new LinkedBlockingQueue<>();
        final CountDownLatch failed = new CountDownLatch(1);
        final AtomicReference<Exception> error = new AtomicReference<>();
        volatile boolean complete;
        public void committed(long bytes, boolean complete) {
            this.complete = complete;
            receipts.add(bytes);
        }
        public void failed(Exception error) { this.error.set(error); failed.countDown(); }
        long receipt() throws Exception {
            Long bytes = receipts.poll(10, TimeUnit.SECONDS);
            assertNotNull(bytes, "writer did not commit");
            return bytes;
        }
    }
    @Test void sixtyMiBUsesFixedWindowAndPreservesContent() throws Exception {
        int chunk = 32000;
        long size = 60L * 1024 * 1024;
        Probe probe = new Probe();
        TransferId id = id(UUID.randomUUID());
        Path path = dir.resolve("large.part");
        byte[] data = new byte[chunk];
        java.util.Arrays.fill(data, (byte) 71);
        try (BoundedFileReceiver receiver = new BoundedFileReceiver(chunk, size, 5, 1, Duration.ofSeconds(60))) {
            assertTrue(receiver.begin(id, path, size, probe));
            long offset = 0;
            for (int index = 0; offset < size; index++) {
                int count = (int) Math.min(chunk, size - offset);
                assertTrue(receiver.accept(id, index, count == chunk ? data : java.util.Arrays.copyOf(data, count)));
                offset += count;
                assertEquals(offset, probe.receipt());
            }
            assertTrue(probe.complete);
            assertEquals(size, Files.size(path));
            try (InputStream in = Files.newInputStream(path)) {
                byte[] buffer = new byte[8192];
                int count;
                while ((count = in.read(buffer)) != -1)
                    for (int i = 0; i < count; i++) assertEquals(71, buffer[i]);
            }
        }
    }
    @Test void blockedDiskDoesNotBlockAdmissionOrGrowQueues() throws Exception {
        CountDownLatch entered = new CountDownLatch(1), release = new CountDownLatch(1);
        Probe probe = new Probe();
        TransferId id = id(UUID.randomUUID());
        try (BoundedFileReceiver receiver = new BoundedFileReceiver(16, 64, 2, 1, Duration.ofSeconds(5),
                path -> new OutputStream() {
                    public void write(int value) { }
                    public void write(byte[] bytes) throws IOException {
                        entered.countDown();
                        try { if (!release.await(10, TimeUnit.SECONDS)) throw new IOException("stalled test"); }
                        catch (InterruptedException e) { throw new IOException(e); }
                    }
                })) {
            assertTrue(receiver.begin(id, dir.resolve("slow"), 32, probe));
            assertTrue(receiver.accept(id, 0, new byte[16]));
            assertTrue(entered.await(2, TimeUnit.SECONDS));
            long start = System.nanoTime();
            for (int i = 0; i < 10000; i++) assertFalse(receiver.accept(id, 1, new byte[16]));
            assertTrue(System.nanoTime() - start < TimeUnit.SECONDS.toNanos(2));
            assertFalse(receiver.begin(id(id.owner()), dir.resolve("same-owner"), 16, new Probe()));
            TransferId second = id(UUID.randomUUID());
            assertTrue(receiver.begin(second, dir.resolve("other"), 16, new Probe()));
            assertFalse(receiver.begin(id(UUID.randomUUID()), dir.resolve("full"), 16, new Probe()));
            receiver.cancel(id);
            release.countDown();
            assertTrue(probe.failed.await(2, TimeUnit.SECONDS));
            assertTrue(probe.receipts.isEmpty());
        } finally { release.countDown(); }
    }
    @Test void rejectsReplayOversizeEmptyAndChangedOrder() throws Exception {
        Probe probe = new Probe();
        TransferId id = id(UUID.randomUUID());
        try (BoundedFileReceiver receiver = new BoundedFileReceiver(4, 8, 2, 1, Duration.ofSeconds(5))) {
            assertTrue(receiver.begin(id, dir.resolve("ordered"), 8, probe));
            assertFalse(receiver.begin(id, dir.resolve("replacement"), 8, probe));
            assertFalse(receiver.accept(id, 1, new byte[4]));
            assertFalse(receiver.accept(id, 0, new byte[0]));
            assertFalse(receiver.accept(id, 0, new byte[5]));
            assertTrue(receiver.accept(id, 0, new byte[4]));
            assertEquals(4, probe.receipt());
            assertFalse(receiver.accept(id, 0, new byte[4]));
            assertTrue(receiver.accept(id, 1, new byte[4]));
            assertEquals(8, probe.receipt());
        }
    }
    @Test void timeoutDisconnectAndShutdownCleanPartialFiles() throws Exception {
        for (int mode = 0; mode < 3; mode++) {
            Probe probe = new Probe();
            TransferId id = id(UUID.randomUUID());
            Path path = dir.resolve("cleanup-" + mode);
            BoundedFileReceiver receiver = new BoundedFileReceiver(4, 8, 1, 1, Duration.ofMillis(150));
            assertTrue(receiver.begin(id, path, 8, probe));
            assertTrue(receiver.accept(id, 0, new byte[4]));
            probe.receipt();
            if (mode == 1) receiver.cancelOwner(id.owner());
            if (mode == 2) receiver.close();
            assertTrue(probe.failed.await(3, TimeUnit.SECONDS));
            long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(3);
            while (Files.exists(path) && System.nanoTime() < deadline) Thread.yield();
            assertFalse(Files.exists(path));
            receiver.close();
        }
    }
    @Test void existingPathsAreNotTruncatedOrDeletedOnFailure() throws Exception {
        Path existing = dir.resolve("existing");
        Files.write(existing, new byte[]{7});
        Probe probe = new Probe();
        TransferId id = id(UUID.randomUUID());
        try (BoundedFileReceiver receiver = new BoundedFileReceiver(4, 8, 1, 1, Duration.ofSeconds(1))) {
            assertTrue(receiver.begin(id, existing, 4, probe));
            assertTrue(receiver.accept(id, 0, new byte[4]));
            assertTrue(probe.failed.await(2, TimeUnit.SECONDS));
            assertArrayEquals(new byte[]{7}, Files.readAllBytes(existing));
        }
    }
}
