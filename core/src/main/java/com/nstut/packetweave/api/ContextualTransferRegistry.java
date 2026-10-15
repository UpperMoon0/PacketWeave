package com.nstut.packetweave.api;

import java.util.Iterator;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.function.LongSupplier;

/**
 * Binds trusted, consumer-defined context to a bounded transfer's lifetime.
 * Context must be captured from the authenticated connection; validate it on every chunk.
 * Expiry, rejection, cancellation and completion release context together with byte budgets.
 */
public final class ContextualTransferRegistry<T> {
    private final TransferRegistry transfers;
    private final Map<TransferId,T> contexts = new java.util.LinkedHashMap<>();

    public ContextualTransferRegistry(TransferLimits limits, TransferAuthorizer authorizer) {
        this(limits, authorizer, System::nanoTime);
    }
    public ContextualTransferRegistry(TransferLimits limits, TransferAuthorizer authorizer, LongSupplier clock) {
        transfers = new TransferRegistry(limits, authorizer, clock);
    }
    public synchronized boolean begin(TransferId id, int count, long bytes, T context) {
        reapExpired(); Objects.requireNonNull(context, "context");
        if (!transfers.begin(id,count,bytes)) return false;
        contexts.put(id,context); return true;
    }
    public synchronized boolean beginBounded(TransferId id, int count, long trustedByteLimit, T context) {
        reapExpired(); Objects.requireNonNull(context, "context");
        if (!transfers.beginBounded(id,count,trustedByteLimit)) return false;
        contexts.put(id,context); return true;
    }
    public synchronized T context(TransferId id) { reapExpired(); return contexts.get(id); }
    public synchronized boolean accept(TransferId id, int index, byte[] bytes) {
        boolean accepted=transfers.accept(id,index,bytes); reapExpired(); return accepted;
    }
    public synchronized byte[] complete(TransferId id) {
        byte[] bytes=transfers.complete(id); reapExpired(); return bytes;
    }
    public synchronized boolean cancel(TransferId id) { contexts.remove(id); return transfers.cancel(id); }
    public synchronized int cancelOwner(UUID owner) {
        int cancelled=transfers.cancelOwner(owner); reapExpired(); return cancelled;
    }
    public synchronized void reapExpired() {
        transfers.reapExpired();
        Iterator<TransferId> iterator=contexts.keySet().iterator();
        while(iterator.hasNext()) if(!transfers.containsActive(iterator.next())) iterator.remove();
    }
    /** Immutable admission-ordered snapshot for consumer supersession/eviction policy. */
    public synchronized Map<TransferId,T> contexts() {
        reapExpired(); return java.util.Collections.unmodifiableMap(new java.util.LinkedHashMap<>(contexts));
    }
    public synchronized void clear() { transfers.clear(); contexts.clear(); }
    public synchronized int activeSessions() { reapExpired(); return contexts.size(); }
    public synchronized long bufferedBytes() { reapExpired(); return transfers.bufferedBytes(); }
}
