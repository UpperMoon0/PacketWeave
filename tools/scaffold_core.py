from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def put(path, body):
    p=ROOT / path
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(body.strip()+"\n",encoding="utf-8",newline="\n")
    print("WROTE", path)

put("core/src/main/java/com/nstut/packetweave/api/TransferId.java", r'''
package com.nstut.packetweave.api;

import java.util.Objects;
import java.util.UUID;

/** Namespace + authenticated sender UUID + random transaction UUID. */
public final class TransferId {
    private final String namespace;
    private final UUID owner;
    private final UUID transaction;

    public TransferId(String namespace, UUID owner, UUID transaction) {
        if (namespace == null || !namespace.matches("[a-z][a-z0-9_.-]{1,63}")) {
            throw new IllegalArgumentException("Invalid transfer namespace");
        }
        this.namespace = namespace;
        this.owner = Objects.requireNonNull(owner, "owner");
        this.transaction = Objects.requireNonNull(transaction, "transaction");
    }
    public String namespace() { return namespace; }
    public UUID owner() { return owner; }
    public UUID transaction() { return transaction; }
    @Override public boolean equals(Object other) {
        if (this == other) return true;
        if (!(other instanceof TransferId)) return false;
        TransferId id = (TransferId) other;
        return namespace.equals(id.namespace) && owner.equals(id.owner) && transaction.equals(id.transaction);
    }
    @Override public int hashCode() { return Objects.hash(namespace, owner, transaction); }
    @Override public String toString() { return namespace + ":" + owner + ":" + transaction; }
}
''')

put("core/src/main/java/com/nstut/packetweave/api/TransferLimits.java", r'''
package com.nstut.packetweave.api;

import java.time.Duration;

/** Explicit, immutable budgets; bytes are accounted before they are retained. */
public final class TransferLimits {
    private final int chunkBytes;
    private final long transferBytes;
    private final int concurrentGlobal;
    private final int concurrentPerOwner;
    private final long bufferedBytes;
    private final long timeoutNanos;

    public TransferLimits(int chunkBytes, long transferBytes, int concurrentGlobal,
                          int concurrentPerOwner, long bufferedBytes, Duration timeout) {
        if (chunkBytes <= 0 || chunkBytes > 1024 * 1024
                || transferBytes <= 0 || transferBytes > Integer.MAX_VALUE
                || concurrentGlobal <= 0 || concurrentPerOwner <= 0
                || concurrentPerOwner > concurrentGlobal || bufferedBytes < chunkBytes
                || bufferedBytes < transferBytes || timeout == null
                || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException("Invalid transfer limits");
        }
        this.chunkBytes = chunkBytes;
        this.transferBytes = transferBytes;
        this.concurrentGlobal = concurrentGlobal;
        this.concurrentPerOwner = concurrentPerOwner;
        this.bufferedBytes = bufferedBytes;
        this.timeoutNanos = timeout.toNanos();
    }
    public static TransferLimits defaults() {
        return new TransferLimits(30 * 1024, 16L * 1024 * 1024, 32, 2,
                64L * 1024 * 1024, Duration.ofSeconds(30));
    }
    public int chunkBytes() { return chunkBytes; }
    public long transferBytes() { return transferBytes; }
    public int concurrentGlobal() { return concurrentGlobal; }
    public int concurrentPerOwner() { return concurrentPerOwner; }
    public long bufferedBytes() { return bufferedBytes; }
    public long timeoutNanos() { return timeoutNanos; }
}
''')

put("core/src/main/java/com/nstut/packetweave/api/TransferOperation.java", r'''
package com.nstut.packetweave.api;

/** Every stage is authorized, not just the initial request. */
public enum TransferOperation {
    BEGIN, ACCEPT_CHUNK, COMPLETE
}
''')

put("core/src/main/java/com/nstut/packetweave/api/TransferAuthorizer.java", r'''
package com.nstut.packetweave.api;

/** Implementations must derive the owner from an authenticated connection, never packet claims. */
@FunctionalInterface
public interface TransferAuthorizer {
    boolean allow(TransferId id, TransferOperation operation);
}
''')

put("core/src/main/java/com/nstut/packetweave/api/TransferSession.java", r'''
package com.nstut.packetweave.api;

import java.util.Arrays;

/** A single finite, indexed transfer. Only TransferRegistry should own this instance. */
final class TransferSession {
    private final byte[][] chunks;
    private final long declaredBytes;
    private long receivedBytes;
    private int receivedChunks;
    private long touchedAtNanos;

    TransferSession(int totalChunks, long declaredBytes, long nowNanos) {
        this.chunks = new byte[totalChunks][];
        this.declaredBytes = declaredBytes;
        this.touchedAtNanos = nowNanos;
    }

    boolean add(int index, byte[] bytes, int maxChunkBytes, long nowNanos) {
        if (index < 0 || index >= chunks.length || bytes == null || bytes.length == 0
                || bytes.length > maxChunkBytes || chunks[index] != null
                || receivedBytes + bytes.length > declaredBytes) return false;
        chunks[index] = Arrays.copyOf(bytes, bytes.length);
        receivedBytes += bytes.length;
        receivedChunks++;
        touchedAtNanos = nowNanos;
        return true;
    }

    boolean complete() { return receivedChunks == chunks.length && receivedBytes == declaredBytes; }
    boolean expired(long nowNanos, long timeoutNanos) {
        return nowNanos - touchedAtNanos >= timeoutNanos;
    }
    long bytes() { return receivedBytes; }
    int receivedChunks() { return receivedChunks; }
    int totalChunks() { return chunks.length; }
    byte[] join() {
        if (!complete()) throw new IllegalStateException("Transfer not complete");
        byte[] output = new byte[(int) receivedBytes];
        int offset = 0;
        for (byte[] chunk : chunks) {
            System.arraycopy(chunk, 0, output, offset, chunk.length);
            offset += chunk.length;
        }
        return output;
    }
}
''')

put("core/src/main/java/com/nstut/packetweave/api/TransferRegistry.java", r'''
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
''')

put("core/src/main/java/com/nstut/packetweave/api/TransferDigest.java", r'''
package com.nstut.packetweave.api;

import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;

/** Integrity helper; hash checks do not replace sender authorization or content validation. */
public final class TransferDigest {
    private TransferDigest() {}
    public static String sha256(byte[] bytes) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(bytes);
            StringBuilder out = new StringBuilder(hash.length * 2);
            for (byte b : hash) {
                int x = b & 0xff;
                if (x < 16) out.append('0');
                out.append(Integer.toHexString(x));
            }
            return out.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("Missing SHA-256", e);
        }
    }
}
''')

put("core/src/test/java/com/nstut/packetweave/api/TransferRegistryTest.java", r'''
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
''')

put("settings.gradle", r'''
rootProject.name = 'packetweave'
include 'core'
''')
put("build.gradle", r'''
plugins {
    id 'base'
}
group = 'com.nstut'
version = '0.1.0'
tasks.register('testCore') { dependsOn ':core:test' }
''')
put("core/build.gradle", r'''
plugins {
    id 'java-library'
}
group = 'com.nstut'
version = '0.1.0'
java {
    toolchain.languageVersion = JavaLanguageVersion.of(17)
    withSourcesJar()
}
repositories { mavenCentral() }\ndependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
    options.release = 8
}
test { useJUnitPlatform() }
''')
put(".gitignore", r'''
.gradle/
**/.gradle/
**/build/
**/run/
**/out/
**/.idea/
*.iml
*.log
.cache/
.pytest_cache/
__pycache__/
''')
put("gradle.properties", r'''
org.gradle.jvmargs=-Xmx2G
org.gradle.parallel=true
org.gradle.caching=true
org.gradle.configuration-cache=false
''')
put("LICENSE", r'''
MIT License

Copyright (c) 2026 UpperMoon0

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
''')
