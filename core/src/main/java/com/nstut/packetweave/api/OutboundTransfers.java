package com.nstut.packetweave.api;

import java.io.IOException;
import java.nio.file.Path;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.UUID;
import java.util.concurrent.Executor;
import java.lang.ref.WeakReference;
import java.util.ArrayList;
import java.util.List;

/**
 * Bounded, receipt-driven file sending. The shared instance budgets all integrations
 * together: use the authenticated connection object as peer, not a name or UUID.
 * Never wait on a game/network thread. A receipt must follow successful receiver
 * admission or disk write; local packet dispatch is not a receipt.
 */
public final class OutboundTransfers {
    public static final int CHUNK_BYTES = 4096;
    private static final OutboundTransfers SHARED = new OutboundTransfers(32, 2, Duration.ofSeconds(10));
    public static OutboundTransfers shared() { return SHARED; }

    public interface Completion { void finished(IOException failure); }
    private final int globalLimit, peerLimit;
    private final Duration timeout;
    private final Map<Key, Send> active = new HashMap<>();
    // Keep stalled executor tasks bounded even after their sending workers time out.
    private final List<PendingDispatch> pendingDispatches = new ArrayList<>();

    public OutboundTransfers(int globalLimit, int peerLimit, Duration timeout) {
        if (globalLimit <= 0 || peerLimit <= 0 || peerLimit > globalLimit || timeout == null
                || timeout.isZero() || timeout.isNegative()) throw new IllegalArgumentException("Invalid sending limits");
        this.globalLimit = globalLimit; this.peerLimit = peerLimit; this.timeout = timeout;
    }

    /** Nonblocking admission; false means busy/duplicate. No waiting work queue. */
    public boolean start(Object peer, UUID id, Path file, long byteLimit, Executor dispatch,
                         ChunkedTransfer.Consumer sink, Completion completion) {
        Objects.requireNonNull(peer); Objects.requireNonNull(id); Objects.requireNonNull(file);
        Objects.requireNonNull(dispatch); Objects.requireNonNull(sink); Objects.requireNonNull(completion);
        if (byteLimit <= 0) throw new IllegalArgumentException("Invalid byte limit");
        Key key = new Key(peer, id);
        Send send = new Send(key);
        synchronized (this) {
            pruneDispatches();
            if (active.size() >= globalLimit || active.containsKey(key)
                    || pendingDispatches.size() >= globalLimit) return false;
            int count = 0;
            for (Key other : active.keySet()) if (other.peer == peer) count++;
            if (count >= peerLimit) return false;
            count = 0;
            for (PendingDispatch other : pendingDispatches) if (other.peer.get() == peer) {
                if (other.id.equals(id)) return false;
                count++;
            }
            if (count >= peerLimit) return false;
            active.put(key, send);
        }
        Thread worker = new Thread(() -> {
            IOException failure = null;
            try {
                long[] offset = {0};
                Executor boundedDispatch = task -> {
                    PendingDispatch reservation = new PendingDispatch(peer, id);
                    Runnable queued = () -> {
                        synchronized (OutboundTransfers.this) { pendingDispatches.remove(reservation); }
                        task.run();
                    };
                    reservation.task = new WeakReference<>(queued);
                    synchronized (OutboundTransfers.this) {
                        pruneDispatches();
                        int count = 0;
                        for (PendingDispatch other : pendingDispatches) if (other.peer.get() == peer) count++;
                        if (send.cancelled || pendingDispatches.size() >= globalLimit || count >= peerLimit)
                            throw new java.util.concurrent.RejectedExecutionException("Dispatch budget exhausted");
                        pendingDispatches.add(reservation);
                    }
                    try {
                        dispatch.execute(queued);
                    } catch (RuntimeException error) {
                        synchronized (OutboundTransfers.this) { pendingDispatches.remove(reservation); }
                        throw error;
                    }
                };
                ChunkedTransfer.Consumer emit = ChunkedTransfer.onExecutor(boundedDispatch, timeout, (index, total, data) -> {
                    synchronized (OutboundTransfers.this) {
                        if (active.get(key) != send || send.cancelled) throw new IOException("Transfer cancelled");
                    }
                    // Do not accept a guessed receipt while the dispatch is still queued.
                    send.gate.expect(offset[0] + data.length);
                    sink.accept(index, total, data);
                });
                ChunkedTransfer.streamFile(file, CHUNK_BYTES, byteLimit, (index, total, data) -> {
                    emit.accept(index, total, data);
                    send.gate.await(timeout);
                    offset[0] += data.length;
                });
            } catch (IOException error) { failure = error; }
            catch (RuntimeException error) { failure = new IOException("Transfer failed", error); }
            finally {
                // Cancellation and successful termination share one atomic boundary.
                // A cancel accepted before removal must never publish success,
                // including when the final receipt already released the gate.
                synchronized (OutboundTransfers.this) {
                    if (send.cancelled && failure == null) failure = new IOException("Transfer cancelled");
                    active.remove(key, send);
                }
            }
            try { completion.finished(failure); } catch (RuntimeException ignored) { }
        }, "PacketWeave acknowledged send");
        worker.setDaemon(true);
        send.worker = worker;
        try { worker.start(); }
        catch (RuntimeException error) {
            synchronized (this) { active.remove(key, send); }
            throw error;
        }
        return true;
    }

    /** Bind peer to the actual authenticated packet context. Negative bytes reject. */
    public synchronized void acknowledge(Object peer, UUID id, long committedBytes) {
        Send send = active.get(new Key(peer, id));
        if (send == null) return;
        if (committedBytes < 0) cancel(send);
        else send.gate.acknowledge(committedBytes);
    }
    public synchronized void cancel(Object peer, UUID id) {
        Send send = active.get(new Key(peer, id)); if (send != null) cancel(send);
    }
    public synchronized void cancelPeer(Object peer) {
        for (Send send : active.values()) if (send.key.peer == peer) cancel(send);
    }
    private void cancel(Send send) {
        send.cancelled = true; send.gate.cancel();
        Thread worker = send.worker; if (worker != null) worker.interrupt();
    }
    public synchronized int activeSessions() { return active.size(); }
    private void pruneDispatches() {
        pendingDispatches.removeIf(pending -> pending.task.get() == null);
    }
    // Do not root an abandoned server/executor through the shared scheduler. Live
    // executor queues retain their tasks; discarded queues release their reservations.
    private static final class PendingDispatch {
        final WeakReference<Object> peer;
        final UUID id;
        WeakReference<Runnable> task;
        PendingDispatch(Object peer, UUID id) { this.peer = new WeakReference<>(peer); this.id = id; }
    }
    private static final class Send {
        final Key key; final ReceiptGate gate = new ReceiptGate();
        volatile boolean cancelled; volatile Thread worker;
        Send(Key key) { this.key = key; }
    }
    private static final class Key {
        final Object peer; final UUID id;
        Key(Object peer, UUID id) { this.peer = peer; this.id = id; }
        public int hashCode() { return 31 * System.identityHashCode(peer) + id.hashCode(); }
        public boolean equals(Object other) {
            return other instanceof Key && ((Key) other).peer == peer && ((Key) other).id.equals(id);
        }
    }
}
