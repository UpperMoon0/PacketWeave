package com.nstut.packetweave.api;

import java.io.IOException;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.time.Duration;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * Sequential file ingestion with one pending chunk per authenticated transfer.
 * Admission never performs disk I/O or waits for a writer. All file operations and
 * callbacks run on a dedicated worker; callbacks must dispatch game changes themselves.
 * Paths must be unique, trusted temporary paths. Successful files belong to the callback;
 * cancelled, expired, failed and shutdown sessions are deleted by the worker.
 * Failed cleanup is logged and retried, retaining the session's bounded capacity
 * until its stream is closed and its partial file is deleted, including after close().
 */
public final class BoundedFileReceiver implements AutoCloseable {
    public interface Listener {
        void committed(long bytes, boolean complete) throws Exception;
        void failed(Exception error);
    }
    private final int chunkBytes, maxSessions, perOwner;
    private final long byteLimit, timeoutNanos;
    private final Map<TransferId, Session> sessions = new HashMap<>();
    private final ArrayBlockingQueue<Runnable> queue;
    private final Thread worker;
    interface Opener { OutputStream open(Path path) throws IOException; }
    interface Deleter { void delete(Path path) throws IOException; }
    private final Opener opener;
    private final Deleter deleter;
    private boolean closed;

    public BoundedFileReceiver(int chunkBytes, long byteLimit, int maxSessions,
                               int perOwner, Duration timeout) {
        this(chunkBytes, byteLimit, maxSessions, perOwner, timeout,
                path -> Files.newOutputStream(path, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE));
    }
    BoundedFileReceiver(int chunkBytes, long byteLimit, int maxSessions, int perOwner,
                        Duration timeout, Opener opener) {
        this(chunkBytes, byteLimit, maxSessions, perOwner, timeout, opener, Files::deleteIfExists);
    }
    BoundedFileReceiver(int chunkBytes, long byteLimit, int maxSessions, int perOwner,
                        Duration timeout, Opener opener, Deleter deleter) {
        if (chunkBytes <= 0 || chunkBytes > 1024 * 1024 || byteLimit <= 0 ||
                maxSessions <= 0 || perOwner <= 0 || perOwner > maxSessions ||
                timeout == null || timeout.isNegative() || timeout.isZero())
            throw new IllegalArgumentException("Invalid file receive limits");
        this.opener = java.util.Objects.requireNonNull(opener, "opener");
        this.deleter = java.util.Objects.requireNonNull(deleter, "deleter");
        this.chunkBytes = chunkBytes;
        this.byteLimit = byteLimit;
        this.maxSessions = maxSessions;
        this.perOwner = perOwner;
        this.timeoutNanos = timeout.toNanos();
        queue = new ArrayBlockingQueue<>(maxSessions);
        worker = new Thread(this::run, "PacketWeave File Receiver");
        worker.setDaemon(true);
        worker.start();
    }

    /** Pure metadata admission. The file is created lazily on the worker. */
    public synchronized boolean begin(TransferId id, Path path, long bytes, Listener listener) {
        if (closed || id == null || path == null || listener == null || bytes <= 0 ||
                bytes > byteLimit || sessions.containsKey(id) || sessions.size() >= maxSessions)
            return false;
        long owned = sessions.keySet().stream().filter(k -> k.owner().equals(id.owner())).count();
        if (owned >= perOwner || sessions.values().stream().anyMatch(s -> s.path.equals(path))) return false;
        sessions.put(id, new Session(id, path, bytes, listener));
        return true;
    }

    /** Ordered, indexed, single-flight admission. A false result means reject/cancel, never retry blindly. */
    public synchronized boolean accept(TransferId id, int index, byte[] data) {
        Session s = sessions.get(id);
        if (closed || s == null || s.cancelled || s.pending || index != s.index ||
                data == null || data.length == 0 || data.length > chunkBytes ||
                data.length > s.size - s.received) return false;
        s.pending = true;
        s.activity = System.nanoTime();
        byte[] copy = data.clone();
        if (!queue.offer(() -> write(s, copy))) {
            s.pending = false;
            return false;
        }
        return true;
    }

    public synchronized void cancel(TransferId id) {
        Session s = sessions.get(id);
        if (s != null) s.cancelled = true;
    }
    public synchronized void cancelOwner(java.util.UUID owner) {
        for (Session s : sessions.values()) if (s.id.owner().equals(owner)) s.cancelled = true;
    }
    public synchronized int activeSessions() { return sessions.size(); }

    private void write(Session s, byte[] bytes) {
        try {
            if (s.cancelled) return;
            if (s.out == null) {
                s.out = opener.open(s.path);
                s.created = true;
            }
            s.out.write(bytes);
            boolean complete;
            synchronized (this) {
                s.received += bytes.length;
                s.index++;
                complete = s.received == s.size;
            }
            if (complete) { s.out.close(); s.out = null; }
            if (s.cancelled) return;
            // Keep pending true until the commit callback finishes. No second disk task can
            // overlap this session, and final validation is included in the session budget.
            synchronized (this) { if (!complete) s.pending = false; }
            s.listener.committed(s.received, complete);
            synchronized (this) {
                // Cancellation and successful completion have one atomic terminal boundary.
                // In particular, a final callback may have spent seconds validating a file.
                if (s.cancelled) return;
                if (complete) { s.success = true; sessions.remove(s.id); }
                else { s.activity = System.nanoTime(); }
            }
        } catch (Exception error) {
            s.cancelled = true;
            notifyFailure(s, error);
        }
    }

    private void notifyFailure(Session s, Exception error) {
        if (s.notified) return;
        s.notified = true;
        try { s.listener.failed(error); } catch (RuntimeException ignored) { }
    }

    private void reap() {
        Session[] snapshot;
        synchronized (this) { snapshot = sessions.values().toArray(new Session[0]); }
        for (Session s : snapshot) {
            synchronized (this) {
                // Admission renews activity and sets pending under this same lock. A
                // freshly accepted chunk must not lose to a stale idle-timeout read.
                if (!s.cancelled && !s.pending && System.nanoTime() - s.activity > timeoutNanos)
                    s.cancelled = true;
            }
            if (!s.cancelled) continue;
            notifyFailure(s, new IOException("Transfer cancelled, expired or receiver closed"));
            if (System.nanoTime() - s.nextCleanupAttempt < 0) continue;
            try {
                if (s.out != null) { s.out.close(); s.out = null; }
                if (!s.success && s.created) deleter.delete(s.path);
                synchronized (this) { sessions.remove(s.id); }
            } catch (IOException error) {
                // Retain ownership of the path AND its session capacity. There can never be
                // an unbounded orphan queue, even when the filesystem remains unavailable.
                s.nextCleanupAttempt = System.nanoTime() + TimeUnit.MILLISECONDS.toNanos(100);
                if (!s.cleanupWarning) {
                    s.cleanupWarning = true;
                    java.util.logging.Logger.getLogger(BoundedFileReceiver.class.getName()).log(
                            java.util.logging.Level.WARNING, "Partial-file cleanup failed; retrying " + s.path, error);
                }
            }
        }
    }

    private void run() {
        try {
            while (true) {
                Runnable task = queue.poll(100, TimeUnit.MILLISECONDS);
                if (task != null) task.run();
                reap();
                synchronized (this) { if (closed && sessions.isEmpty()) return; }
            }
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
        } finally {
            synchronized (this) { closed = true; for (Session s : sessions.values()) s.cancelled = true; }
            reap();
            queue.clear();
        }
    }
    /**
     * Nonblocking shutdown without cancelling an already accepted final callback.
     * Rejects all new sessions and chunks, processes queued writes, and expires idle
     * incomplete sessions. Call cancel() for any sessions that should not drain.
     */
    public synchronized void drainAndClose() { closed = true; }

    /** Nonblocking. Cleanup occurs on the writer after any current disk call returns. */
    @Override public synchronized void close() {
        closed = true;
        for (Session s : sessions.values()) s.cancelled = true;
    }

    private static final class Session {
        final TransferId id;
        final Path path;
        final long size;
        final Listener listener;
        OutputStream out;
        long received;
        int index;
        volatile boolean cancelled;
        boolean pending, success, notified, created, cleanupWarning;
        long nextCleanupAttempt;
        long activity = System.nanoTime();
        Session(TransferId id, Path path, long size, Listener listener) {
            this.id = id; this.path = path; this.size = size; this.listener = listener;
        }
    }
}
