package com.nstut.packetweave.api;

/** Every stage is authorized, not just the initial request. */
public enum TransferOperation {
    BEGIN, ACCEPT_CHUNK, COMPLETE
}
