package com.nstut.packetweave.api;

import org.junit.jupiter.api.Test;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicBoolean;
import static org.junit.jupiter.api.Assertions.*;

class TransferRegistryTest {
    final UUID owner = UUID.randomUUID();
    TransferId id() { return new TransferId("screens", owner, UUID.randomUUID()); }
    TransferLimits limits() { return new TransferLimits(4, 12, 3, 2, 24, Duration.ofSeconds(30)); }

    @Test void reconstructsOutOfOrderChunksAndHashesContent() {
        TransferRegistry registry = new TransferRegistry(limits(), (id, op) -> true);
        TransferId id = id();
        assertTrue(registry.begin(id, 2, 6));
        assertTrue(registry.accept(id, 1, new byte[]{5,6}));
        assertNull(registry.complete(id));
        assertTrue(registry.accept(id, 0, new byte[]{1,2,3,4}));
        assertArrayEquals(new byte[]{1,2,3,4,5,6}, registry.complete(id));
        assertEquals(0, registry.activeSessions());
        assertEquals(0, registry.bufferedBytes());
        assertEquals("7192385c3c0605de55bb9476ce1d90748190ecb32a8eed7f5207b30cf6a1fe89", TransferDigest.sha256(new byte[]{1,2,3,4,5,6}));
    }

    @Test void rejectsDuplicateAndInvalidChunksWithoutRetainingBuffers() {
        TransferRegistry registry = new TransferRegistry(limits(), (id, op) -> true);
        TransferId id = id();
        assertTrue(registry.begin(id, 2, 5));
        assertTrue(registry.accept(id, 0, new byte[]{1,2,3,4}));
        assertFalse(registry.accept(id, 0, new byte[]{1,2,3,4}));
        assertEquals(0, registry.bufferedBytes());
        assertFalse(registry.accept(id, 1, new byte[]{5}));
        assertFalse(registry.begin(id, 0, 5));
        assertFalse(registry.begin(id, 2, 13));
        assertFalse(registry.begin(id, 1, 5));
    }

    @Test void enforcesGlobalAndPerOwnerConcurrency() {
        TransferRegistry r = new TransferRegistry(limits(), (id, op) -> true, () -> 0L);
        TransferId first = id(), second = id();
        TransferId other = new TransferId("other", UUID.randomUUID(), UUID.randomUUID());
        assertTrue(r.begin(first, 1, 1));
        assertTrue(r.begin(second, 1, 1));
        assertFalse(r.begin(id(), 1, 1));
        assertTrue(r.begin(other, 1, 1));
        assertFalse(r.begin(new TransferId("other", UUID.randomUUID(), UUID.randomUUID()), 1, 1));
        assertEquals(2, r.cancelOwner(owner));
        assertEquals(1, r.activeSessions());
    }

    @Test void expirationReleasesBudgetAndAllowsRetry() {
        AtomicLong now = new AtomicLong(10);
        TransferRegistry r = new TransferRegistry(new TransferLimits(4, 12, 3, 2, 24, Duration.ofNanos(10)), (id, op) -> true, now::get);
        TransferId id = id();
        assertTrue(r.begin(id, 1, 3));
        assertTrue(r.accept(id, 0, new byte[]{1,2,3}));
        now.addAndGet(11);
        assertEquals(1, r.reapExpired());
        assertEquals(0, r.bufferedBytes());
        assertTrue(r.begin(id, 1, 3));
    }

    @Test void revocationAbortsTransferAndBlocksCompletion() {
        AtomicBoolean allow = new AtomicBoolean(true);
        TransferRegistry r = new TransferRegistry(limits(), (id, op) -> allow.get());
        TransferId id = id();
        assertTrue(r.begin(id, 1, 1));
        assertTrue(r.accept(id, 0, new byte[]{1}));
        allow.set(false);
        assertNull(r.complete(id));
        assertEquals(0, r.bufferedBytes());
        assertFalse(r.begin(id, 1, 1));
    }

    @Test void invalidNamespaceAndLimitsFailClosed() {
        assertThrows(IllegalArgumentException.class,
                () -> new TransferId("../outside", owner, UUID.randomUUID()));
        assertThrows(IllegalArgumentException.class,
                () -> new TransferLimits(0, 4, 1, 1, 4, Duration.ofSeconds(1)));
        assertThrows(NullPointerException.class,
                () -> new TransferRegistry(limits(), null));
    }

    @Test void hostileSizesCannotCreateOversizedSessions() {
        TransferRegistry r = new TransferRegistry(limits(), (id, op) -> true);
        TransferId id = id();
        assertFalse(r.begin(id, Integer.MAX_VALUE, Long.MAX_VALUE));
        assertFalse(r.begin(id, Integer.MAX_VALUE, 4));
        assertFalse(r.begin(id, 1, 8));
        assertTrue(r.begin(id, 2, 8));
        assertFalse(r.accept(id, -1, new byte[]{1}));
        assertEquals(0, r.bufferedBytes());
    }
}
