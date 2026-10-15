package com.nstut.packetweave.api;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ContextualTransferRegistryTest {
    private final AtomicLong clock=new AtomicLong();
    private final TransferLimits limits=new TransferLimits(4,8,2,1,16,Duration.ofSeconds(1));
    private TransferId id() { return new TransferId("test",UUID.randomUUID(),UUID.randomUUID()); }
    @Test void contextAndBytesShareAllTerminalPaths() {
        ContextualTransferRegistry<String> r=new ContextualTransferRegistry<>(limits,(id,op)->true,clock::get);
        TransferId a=id(); assertTrue(r.begin(a,2,8,"trusted gadget"));
        assertEquals("trusted gadget",r.context(a)); assertNull(r.complete(a));
        assertTrue(r.accept(a,1,new byte[4])); assertTrue(r.accept(a,0,new byte[4]));
        assertEquals(8,r.complete(a).length); assertNull(r.context(a)); assertEquals(0,r.bufferedBytes());
        assertTrue(r.begin(a,1,4,"new")); assertTrue(r.accept(a,0,new byte[4]));
        assertFalse(r.accept(a,0,new byte[4])); assertNull(r.context(a)); assertEquals(0,r.bufferedBytes());
        assertTrue(r.begin(a,1,4,"expired")); clock.set(2_000_000_000L);
        assertNull(r.context(a)); assertEquals(0,r.activeSessions());
    }
    @Test void ownerAndGlobalLimitsAlsoBoundContextAndClearReleasesBoth() {
        ContextualTransferRegistry<String> r=new ContextualTransferRegistry<>(limits,(id,op)->true,clock::get);
        TransferId a=id(), sameOwner=new TransferId("test",a.owner(),UUID.randomUUID()), b=id(), c=id();
        assertTrue(r.beginBounded(a,1,4,"a")); assertFalse(r.beginBounded(sameOwner,1,4,"bad"));
        assertTrue(r.beginBounded(b,1,4,"b")); assertFalse(r.beginBounded(c,1,4,"bad"));
        assertEquals(1,r.cancelOwner(a.owner())); assertNull(r.context(a)); assertEquals("b",r.context(b));
        r.clear(); assertEquals(0,r.activeSessions()); assertNull(r.context(b));
    }
    @Test void authorizationRevocationReleasesPinnedContext() {
        java.util.concurrent.atomic.AtomicBoolean allowed=new java.util.concurrent.atomic.AtomicBoolean(true);
        ContextualTransferRegistry<String> r=new ContextualTransferRegistry<>(limits,(id,op)->allowed.get(),clock::get);
        TransferId a=id(); assertTrue(r.begin(a,1,4,"permission")); allowed.set(false);
        assertFalse(r.accept(a,0,new byte[4])); assertNull(r.context(a));
    }
    @Test void snapshotsAreImmutableOrderedAndDetachedFromLifecycleChanges() {
        ContextualTransferRegistry<String> r=new ContextualTransferRegistry<>(limits,(id,op)->true,clock::get);
        TransferId a=id(), b=id(); assertTrue(r.begin(a,1,4,"first")); assertTrue(r.begin(b,1,4,"second"));
        java.util.Map<TransferId,String> snapshot=r.contexts();
        assertEquals(a,snapshot.keySet().iterator().next());
        assertThrows(UnsupportedOperationException.class,()->snapshot.clear());
        r.cancel(a); assertEquals(2,snapshot.size()); assertEquals(1,r.contexts().size());
    }
    @Test void contextSweepUsesOneExpirySnapshot() {
        java.util.concurrent.atomic.AtomicInteger reads = new java.util.concurrent.atomic.AtomicInteger();
        ContextualTransferRegistry<String> r = new ContextualTransferRegistry<>(limits,
                (id, op) -> true, () -> { reads.incrementAndGet(); return clock.get(); });
        assertTrue(r.begin(id(), 1, 4, "a"));
        assertTrue(r.begin(id(), 1, 4, "b"));
        reads.set(0);
        assertEquals(2, r.contexts().size());
        assertEquals(1, reads.get(), "one expiry instant for the entire context snapshot");
    }

    @Test void authorizationCannotChargeBytesToAReapedSession() {
        java.util.concurrent.atomic.AtomicReference<ContextualTransferRegistry<String>> ref =
                new java.util.concurrent.atomic.AtomicReference<>();
        ContextualTransferRegistry<String> r = new ContextualTransferRegistry<>(limits, (id, op) -> {
            if (op == TransferOperation.ACCEPT_CHUNK) {
                String trusted = ref.get().context(id);
                clock.set(2_000_000_000L);
                ref.get().context(id); // A second policy lookup reaps the session.
                return trusted != null;
            }
            return true;
        }, clock::get);
        ref.set(r);
        TransferId a = id();
        assertTrue(r.begin(a, 1, 4, "trusted"));
        assertFalse(r.accept(a, 0, new byte[4]));
        assertEquals(0, r.activeSessions());
        assertEquals(0, r.bufferedBytes());
    }

    @Test void completionCannotReturnDataFromAReapedSession() {
        java.util.concurrent.atomic.AtomicReference<ContextualTransferRegistry<String>> ref =
                new java.util.concurrent.atomic.AtomicReference<>();
        ContextualTransferRegistry<String> r = new ContextualTransferRegistry<>(limits, (id, op) -> {
            if (op == TransferOperation.COMPLETE) {
                String trusted = ref.get().context(id);
                clock.set(2_000_000_000L);
                ref.get().context(id);
                return trusted != null;
            }
            return true;
        }, clock::get);
        ref.set(r);
        TransferId a = id();
        assertTrue(r.begin(a, 1, 4, "trusted"));
        assertTrue(r.accept(a, 0, new byte[4]));
        assertNull(r.complete(a));
        assertEquals(0, r.activeSessions());
        assertEquals(0, r.bufferedBytes());
    }
}
