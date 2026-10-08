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
