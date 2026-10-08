package com.nstut.packetweave.api;

import java.util.HashMap;
import java.util.Iterator;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.LongSupplier;

/**
 * Thread-safe, bounded inbound transfer registry, independent of MC version and loader.
 * No packet is trusted: callers must bind TransferId.owner() to the authenticated sender.
 * Failed authorization aborts a pending transfer; receivers must also validate file content.
 */
public final class TransferRegistry {
    private final TransferLimits limits;
    private final TransferAuthorizer authorizer;
    private final LongSupplier clockNanos;
    private final Map<TransferId, TransferSession> active = new HashMap<>();
    private long buffered;

    public TransferRegistry(TransferLimits limits, TransferAuthorizer authorizer) {
        this(limits, authorizer, System::nanoTime);
    }
    public TransferRegistry(TransferLimits limits, TransferAuthorizer authorizer, LongSupplier clockNanos) {
        this.limits = Objects.requireNonNull(limits, "limits");
        this.authorizer = Objects.requireNonNull(authorizer, "authorizer");
        this.clockNanos = Objects.requireNonNull(clockNanos, "clock");
    }
    public synchronized boolean begin(TransferId id, int totalChunks, long declaredBytes) {
        Objects.requireNonNull(id, "id");
        reapExpired();
        if (!allowed(id, TransferOperation.BEGIN)) return false;
        if (active.containsKey(id) || active.size() >= limits.concurrentGlobal()
                || declaredBytes <= 0 || declaredBytes > limits.transferBytes()
                || totalChunks <= 0 || totalChunks > (declaredBytes + limits.chunkBytes() - 1) / limits.chunkBytes()
                || declaredBytes > (long) totalChunks * limits.chunkBytes()
                || ownedSessions(id.owner()) >= limits.concurrentPerOwner()) return false;
        active.put(id, new TransferSession(totalChunks, declaredBytes, clockNanos.getAsLong()));
        return true;
    }

    public synchronized boolean accept(TransferId id, int index, byte[] bytes) {
        reapExpired();
        TransferSession session = active.get(id);
        if (session == null) return false;
        if (!allowed(id, TransferOperation.ACCEPT_CHUNK)) { cancel(id); return false; }
        if (bytes == null || bytes.length == 0 || bytes.length > limits.chunkBytes()
                || buffered > limits.bufferedBytes() - bytes.length) { cancel(id); return false; }
        if (!session.add(index, bytes, limits.chunkBytes(), clockNanos.getAsLong())) {
            cancel(id);
            return false;
        }
        buffered += bytes.length;
        return true;
    }

    /** Returns one complete byte array and releases retained transfer budgets; null otherwise. */
    public synchronized byte[] complete(TransferId id) {
        reapExpired();
        TransferSession session = active.get(id);
        if (session == null) return null;
        if (!allowed(id, TransferOperation.COMPLETE)) { cancel(id); return null; }
        if (!session.complete()) return null;
        byte[] result = session.join();
        cancel(id);
        return result;
    }

    public synchronized boolean cancel(TransferId id) {
        TransferSession s = active.remove(id);
        if (s == null) return false;
        buffered -= s.bytes();
        return true;
    }
    public synchronized int cancelOwner(UUID owner) {
        int count=0;
        Iterator<Map.Entry<TransferId, TransferSession>> it=active.entrySet().iterator();
        while(it.hasNext()) {
            Map.Entry<TransferId, TransferSession> e=it.next();
            if (e.getKey().owner().equals(owner)) {
                buffered -= e.getValue().bytes();
                it.remove();
                count++;
            }
        }
        return count;
    }
    public synchronized int reapExpired() {
        long now=clockNanos.getAsLong();
        int count=0;
        Iterator<Map.Entry<TransferId, TransferSession>> it=active.entrySet().iterator();
        while(it.hasNext()) {
            TransferSession s=it.next().getValue();
            if(s.expired(now,limits.timeoutNanos())) {
                buffered-=s.bytes();
                it.remove();
                count++;
            }
        }
        return count;
    }
    private boolean allowed(TransferId id, TransferOperation operation) {
        try { return authorizer.allow(id, operation); }
        catch (RuntimeException exception) { return false; }
    }
    private int ownedSessions(UUID owner) {
        int count=0;
        for (TransferId id : active.keySet()) if(id.owner().equals(owner)) count++;
        return count;
    }
    public synchronized long bufferedBytes() { return buffered; }
    public synchronized int activeSessions() { return active.size(); }
}
