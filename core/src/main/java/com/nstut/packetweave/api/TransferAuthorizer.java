package com.nstut.packetweave.api;

/** Implementations must derive the owner from an authenticated connection, never packet claims. */
@FunctionalInterface
public interface TransferAuthorizer {
    boolean allow(TransferId id, TransferOperation operation);
}
