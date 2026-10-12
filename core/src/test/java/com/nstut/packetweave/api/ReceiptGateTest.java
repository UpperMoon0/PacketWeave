package com.nstut.packetweave.api;
import org.junit.jupiter.api.Test;
import java.io.IOException;
import java.time.Duration;
import static org.junit.jupiter.api.Assertions.*;
class ReceiptGateTest {
    @Test void onlyExactReceiptOpensWindow() throws Exception {
        ReceiptGate gate = new ReceiptGate();
        gate.expect(32);
        gate.acknowledge(64);
        gate.acknowledge(0);
        assertThrows(IOException.class, () -> gate.await(Duration.ofMillis(5)));
        gate.acknowledge(32);
        gate.await(Duration.ofSeconds(1));
        gate.expect(64);
        gate.acknowledge(32);
        assertThrows(IOException.class, () -> gate.await(Duration.ofMillis(5)));
        gate.acknowledge(64);
        gate.await(Duration.ofSeconds(1));
    }
    @Test void cancellationWakesWaiterAndRejectsNewWindows() throws Exception {
        ReceiptGate gate = new ReceiptGate();
        gate.expect(1);
        gate.cancel();
        assertThrows(IOException.class, () -> gate.await(Duration.ofSeconds(1)));
        assertThrows(IOException.class, () -> gate.expect(2));
    }
}
