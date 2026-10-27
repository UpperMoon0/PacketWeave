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
}
