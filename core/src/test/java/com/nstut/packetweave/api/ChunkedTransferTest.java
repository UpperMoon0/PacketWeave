package com.nstut.packetweave.api;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import static org.junit.jupiter.api.Assertions.*;

class ChunkedTransferTest {
    @TempDir Path directory;
    final UUID owner = UUID.randomUUID();
    TransferId id() { return new TransferId("screens", owner, UUID.randomUUID()); }
    TransferLimits limits() { return new TransferLimits(4, 12, 3, 2, 24, Duration.ofNanos(10)); }

    @Test void legacyPacketsReassembleWithoutExactLengthAndReleaseBudgets() throws Exception {
        TransferRegistry registry = new TransferRegistry(limits(), (id, op) -> true, () -> 0);
        TransferId id = id();
        assertTrue(registry.beginBounded(id, 2, 12));
        assertTrue(registry.accept(id, 1, new byte[]{5}));
        assertTrue(registry.accept(id, 0, new byte[]{1,2,3,4}));
        assertArrayEquals(new byte[]{1,2,3,4,5}, registry.complete(id));
        assertFalse(registry.contains(id));
        assertEquals(0, registry.bufferedBytes());
    }

    @Test void boundedModeRejectsHostileCountsDuplicateChunksAndByteOverflow() {
        TransferRegistry registry = new TransferRegistry(limits(), (id, op) -> true, () -> 0);
        TransferId id = id();
        assertFalse(registry.beginBounded(id, Integer.MAX_VALUE, 12));
        assertFalse(registry.beginBounded(id, 1, Long.MAX_VALUE));
        assertTrue(registry.beginBounded(id, 2, 5));
        assertTrue(registry.accept(id, 0, new byte[]{1,2,3,4}));
        assertFalse(registry.accept(id, 1, new byte[]{5,6}));
        assertEquals(0, registry.bufferedBytes());
        assertTrue(registry.beginBounded(id, 2, 5));
        assertTrue(registry.accept(id, 0, new byte[]{1}));
        assertFalse(registry.accept(id, 0, new byte[]{2}));
        assertFalse(registry.contains(id));
    }

    @Test void globalBytesAndDisconnectCleanupApplyToBoundedTransfers() {
        TransferRegistry registry = new TransferRegistry(limits(), (id, op) -> true, () -> 0);
        TransferId a = id(), b = id();
        TransferId c = new TransferId("screens", UUID.randomUUID(), UUID.randomUUID());
        for (TransferId id : new TransferId[]{a,b,c}) assertTrue(registry.beginBounded(id, 3, 12));
        for (TransferId id : new TransferId[]{a,b}) for (int i=0;i<3;i++) assertTrue(registry.accept(id,i,new byte[4]));
        assertFalse(registry.accept(c,0,new byte[1]));
        assertEquals(24, registry.bufferedBytes());
        assertEquals(2, registry.cancelOwner(owner));
        assertEquals(0, registry.bufferedBytes());
        registry.clear();
        assertEquals(0, registry.activeSessions());
    }

    @Test void expirationIsObservedBeforeMetadataLookup() {
        AtomicLong clock = new AtomicLong();
        TransferRegistry registry = new TransferRegistry(limits(), (id, op) -> true, clock::get);
        TransferId id = id();
        assertTrue(registry.beginBounded(id, 1, 4));
        assertTrue(registry.accept(id, 0, new byte[]{1}));
        clock.set(10);
        assertFalse(registry.contains(id));
        assertEquals(0, registry.bufferedBytes());
    }

    @Test void fileAndMemorySendersUseSameChunkGeometry() throws Exception {
        byte[] bytes = {1,2,3,4,5,6,7,8,9};
        Path file = directory.resolve("media");
        Files.write(file, bytes);
        TransferRegistry registry = new TransferRegistry(limits(), (id, op) -> true, () -> 0);
        for (boolean disk : new boolean[]{false,true}) {
            TransferId id = id();
            assertTrue(registry.begin(id, 3, bytes.length));
            ChunkedTransfer.Consumer sink = (index,total,chunk) -> {
                assertEquals(3,total);
                assertTrue(registry.accept(id,index,chunk));
            };
            if (disk) ChunkedTransfer.streamFile(file,4,sink); else ChunkedTransfer.send(bytes,4,sink);
            assertArrayEquals(bytes,registry.complete(id));
        }
    }

    @Test void shortReadsFillChunksAndChangingFilesFail() throws Exception {
        byte[] bytes = {1,2,3,4,5};
        ByteArrayInputStream shortReads = new ByteArrayInputStream(bytes) {
            @Override public synchronized int read(byte[] b,int off,int len) { return super.read(b,off,Math.min(1,len)); }
        };
        java.util.List<byte[]> chunks = new java.util.ArrayList<>();
        ChunkedTransfer.stream(shortReads,5,4,2,(i,t,b) -> chunks.add(b));
        assertArrayEquals(new byte[]{1,2,3,4},chunks.get(0));
        assertArrayEquals(new byte[]{5},chunks.get(1));
        assertThrows(IOException.class, () -> ChunkedTransfer.stream(new ByteArrayInputStream(bytes),6,4,2,(i,t,b)->{}));
        assertThrows(IOException.class, () -> ChunkedTransfer.stream(new ByteArrayInputStream(bytes),4,4,1,(i,t,b)->{}));
        assertThrows(IllegalArgumentException.class, () -> ChunkedTransfer.send(new byte[0],4,(i,t,b)->{}));
    }

    @Test void dispatchWaitsForConsumerAndPropagatesFailures() throws Exception {
        java.util.concurrent.ExecutorService executor = java.util.concurrent.Executors.newSingleThreadExecutor();
        try {
            java.util.List<Integer> received = new java.util.ArrayList<>();
            ChunkedTransfer.send(new byte[]{1,2,3,4,5},4,
                    ChunkedTransfer.onExecutor(executor, Duration.ofSeconds(5), (i,t,b) -> received.add(i)));
            assertEquals(java.util.Arrays.asList(0,1), received);
            assertThrows(IOException.class, () -> ChunkedTransfer.send(new byte[]{1},4,
                    ChunkedTransfer.onExecutor(executor,Duration.ofSeconds(5),(i,t,b) -> { throw new IOException("disconnected"); })));
        } finally { executor.shutdownNow(); }
    }

    @Test void timedOutDispatchDoesNotSendWhenExecutorLaterResumes() {
        java.util.List<Runnable> pending = new java.util.ArrayList<>();
        java.util.concurrent.atomic.AtomicBoolean sent = new java.util.concurrent.atomic.AtomicBoolean();
        assertThrows(IOException.class, () -> ChunkedTransfer.send(new byte[]{1},4,
                ChunkedTransfer.onExecutor(pending::add,Duration.ofMillis(1),(i,t,b) -> sent.set(true))));
        assertEquals(1,pending.size());
        pending.get(0).run();
        assertFalse(sent.get());
    }

    @Test void trustedFileLimitIsCheckedWhenStreamOpens() throws Exception {
        Path file = directory.resolve("oversize");
        Files.write(file, new byte[]{1,2,3,4,5});
        assertThrows(IOException.class, () -> ChunkedTransfer.streamFile(file,4,4,(i,t,b) -> fail("must not send")));
    }
}
