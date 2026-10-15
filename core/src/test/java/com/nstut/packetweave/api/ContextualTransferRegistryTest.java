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
}
