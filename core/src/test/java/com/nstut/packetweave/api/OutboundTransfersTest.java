package com.nstut.packetweave.api;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import static org.junit.jupiter.api.Assertions.*;

class OutboundTransfersTest {
    @TempDir Path dir;
    Path file() throws Exception { return Files.write(dir.resolve(UUID.randomUUID().toString()), new byte[16385]); }

    @Test void slowPeerCannotQueueWholeFileOrBlockGameplayAndReceiptsAreConnectionBound() throws Exception {
        OutboundTransfers sends = new OutboundTransfers(2, 1, Duration.ofSeconds(3));
        Object peer = new Object(); UUID id = UUID.randomUUID();
        BlockingQueue<Runnable> game = new LinkedBlockingQueue<>();
        AtomicInteger chunks = new AtomicInteger(); CompletableFuture<Void> done = new CompletableFuture<>();
        assertTrue(sends.start(peer,id,file(),20000,game::add,(i,n,b)->chunks.incrementAndGet(),e->{if(e==null)done.complete(null);else done.completeExceptionally(e);}));
        game.poll(1,TimeUnit.SECONDS).run();
        assertEquals(1,chunks.get());
        assertNull(game.poll(50,TimeUnit.MILLISECONDS)); // local dispatch cannot release the next chunk
        sends.acknowledge(new Object(),id,4096);
        sends.acknowledge(peer,id,8192); // future/out-of-window receipt
        assertNull(game.poll(50,TimeUnit.MILLISECONDS));
        AtomicBoolean gameplay = new AtomicBoolean(); game.add(()->gameplay.set(true)); game.take().run();
        assertTrue(gameplay.get());
        long offset=0;
        for(int i=0;i<5;i++) {
            offset += i==4?1:4096;
            sends.acknowledge(peer,id,offset);
            if(i<4) game.poll(1,TimeUnit.SECONDS).run();
        }
        done.get(1,TimeUnit.SECONDS); assertEquals(5,chunks.get()); assertEquals(0,sends.activeSessions());
    }

    @Test void admissionIsBoundedAcrossIdsAndIntegrationsAndCancellationSuppressesQueuedDispatch() throws Exception {
        OutboundTransfers sends=new OutboundTransfers(2,1,Duration.ofSeconds(2));
        Object peer=new Object(); UUID id=UUID.randomUUID(); BlockingQueue<Runnable> game=new LinkedBlockingQueue<>();
        AtomicInteger packets=new AtomicInteger(); CountDownLatch done=new CountDownLatch(1);
        assertTrue(sends.start(peer,id,file(),20000,game::add,(i,n,b)->packets.incrementAndGet(),e->done.countDown()));
        Runnable queued=game.poll(1,TimeUnit.SECONDS); assertNotNull(queued);
        assertFalse(sends.start(peer,UUID.randomUUID(),file(),20000,game::add,(i,n,b)->{},e->{}));
        sends.cancelPeer(peer); assertTrue(done.await(1,TimeUnit.SECONDS)); queued.run();
        assertEquals(0,packets.get()); assertEquals(0,sends.activeSessions());
    }

    @Test void missingReceiptFailsTransferAndReleasesBudget() throws Exception {
        OutboundTransfers sends=new OutboundTransfers(1,1,Duration.ofMillis(100));
        CompletableFuture<java.io.IOException> done=new CompletableFuture<>(); AtomicInteger packets=new AtomicInteger();
        assertTrue(sends.start(new Object(),UUID.randomUUID(),file(),20000,Runnable::run,(i,n,b)->packets.incrementAndGet(),done::complete));
        assertNotNull(done.get(2,TimeUnit.SECONDS)); assertEquals(1,packets.get()); assertEquals(0,sends.activeSessions());
    }

    @Test void receiptBeforeDispatchCannotReleaseTheWindow() throws Exception {
        OutboundTransfers sends = new OutboundTransfers(1, 1, Duration.ofSeconds(2));
        Object peer = new Object(); UUID id = UUID.randomUUID();
        BlockingQueue<Runnable> game = new LinkedBlockingQueue<>();
        CompletableFuture<java.io.IOException> done = new CompletableFuture<>();
        assertTrue(sends.start(peer, id, file(), 20000, game::add, (i,n,b)->{}, done::complete));
        Runnable first = game.poll(1, TimeUnit.SECONDS); assertNotNull(first);
        sends.acknowledge(peer, id, 4096);
        first.run();
        assertNull(game.poll(100, TimeUnit.MILLISECONDS));
        sends.acknowledge(peer, id, 4096);
        assertNotNull(game.poll(1, TimeUnit.SECONDS));
        sends.cancelPeer(peer);
        assertNotNull(done.get(1, TimeUnit.SECONDS));
    }

    @Test void timedOutDispatchReservationsBoundRetriesUntilExecutorDrains() throws Exception {
        OutboundTransfers sends = new OutboundTransfers(2, 1, Duration.ofMillis(50));
        Object peer = new Object(); BlockingQueue<Runnable> game = new LinkedBlockingQueue<>();
        CompletableFuture<java.io.IOException> done = new CompletableFuture<>();
        AtomicInteger packets = new AtomicInteger();
        Path path = file(); UUID id = UUID.randomUUID();
        assertTrue(sends.start(peer, id, path, 20000, game::add, (i,n,b)->packets.incrementAndGet(), done::complete));
        assertNotNull(done.get(2, TimeUnit.SECONDS));
        assertEquals(0, sends.activeSessions());
        assertFalse(sends.start(peer, UUID.randomUUID(), path, 20000, game::add, (i,n,b)->{}, e->{}));
        Object otherPeer = new Object(); CompletableFuture<java.io.IOException> otherDone = new CompletableFuture<>();
        assertTrue(sends.start(otherPeer, UUID.randomUUID(), path, 20000, game::add, (i,n,b)->{}, otherDone::complete));
        assertNotNull(otherDone.get(2, TimeUnit.SECONDS));
        assertEquals(2, game.size());
        assertFalse(sends.start(new Object(), UUID.randomUUID(), path, 20000, game::add, (i,n,b)->{}, e->{}));
        while (!game.isEmpty()) game.take().run();
        assertEquals(0, packets.get());
        CompletableFuture<java.io.IOException> retry = new CompletableFuture<>();
        assertTrue(sends.start(peer, UUID.randomUUID(), path, 20000, Runnable::run,
                (i,n,b)->sends.cancelPeer(peer), retry::complete));
        assertNotNull(retry.get(2, TimeUnit.SECONDS));
    }


    @Test void cancellationDuringLastAcknowledgedDispatchCannotReportSuccess() throws Exception {
        OutboundTransfers sends = new OutboundTransfers(1, 1, Duration.ofSeconds(2));
        Object peer = new Object(); UUID id = UUID.randomUUID();
        Path finalChunk = Files.write(dir.resolve("last-receipt"), new byte[]{42});
        CountDownLatch sinkEntered = new CountDownLatch(1);
        CountDownLatch sinkReleased = new CountDownLatch(1);
        CompletableFuture<java.io.IOException> finished = new CompletableFuture<>();
        assertTrue(sends.start(peer, id, finalChunk, 64, Runnable::run, (index, total, data) -> {
            assertEquals(0, index);
            assertEquals(1, total);
            sinkEntered.countDown();
            // A deliberately slow final dispatch; ignore worker interruption to
            // make the completion path inspect cancellation rather than rely on it.
            while (sinkReleased.getCount() != 0) {
                try { sinkReleased.await(); }
                catch (InterruptedException ignored) { }
            }
        }, finished::complete));
        assertTrue(sinkEntered.await(1, TimeUnit.SECONDS));
        sends.acknowledge(peer, id, 1);  // final receipt is already available
        sends.cancel(peer, id);          // cancel while the session is still active
        sinkReleased.countDown();
        assertNotNull(finished.get(2, TimeUnit.SECONDS),
                "An accepted cancellation must not complete the final chunk successfully");
        assertEquals(0, sends.activeSessions());
    }

    private java.lang.ref.WeakReference<Object> abandonedQueue(OutboundTransfers sends) throws Exception {
        Object peer = new Object();
        BlockingQueue<Runnable> abandoned = new LinkedBlockingQueue<>();
        CompletableFuture<java.io.IOException> done = new CompletableFuture<>();
        assertTrue(sends.start(peer, UUID.randomUUID(), file(), 20000, abandoned::add, (i,n,b)->{}, done::complete));
        assertNotNull(done.get(2, TimeUnit.SECONDS));
        assertEquals(1, abandoned.size());
        return new java.lang.ref.WeakReference<>(peer);
    }

    @Test void discardedExecutorQueueDoesNotRetainConnectionOrGlobalBudget() throws Exception {
        OutboundTransfers sends = new OutboundTransfers(1, 1, Duration.ofMillis(50));
        java.lang.ref.WeakReference<Object> oldPeer = abandonedQueue(sends);
        long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(5);
        while (oldPeer.get() != null && System.nanoTime() < deadline) {
            System.gc(); Thread.sleep(10);
        }
        assertNull(oldPeer.get(), "Scheduler must not root an abandoned connection/executor graph");
        CompletableFuture<java.io.IOException> done = new CompletableFuture<>();
        Object peer = new Object();
        assertTrue(sends.start(peer, UUID.randomUUID(), file(), 20000, Runnable::run,
                (i,n,b)->sends.cancelPeer(peer), done::complete));
        assertNotNull(done.get(2, TimeUnit.SECONDS));
    }
}
