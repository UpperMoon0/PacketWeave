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
