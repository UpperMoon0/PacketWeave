package com.nstut.packetweave.fabric;
import net.fabricmc.api.ModInitializer;
/** The loader adapter does not depend on Fabric API or Architectury. */
public final class PacketWeaveFabric implements ModInitializer {
    public static final String MOD_ID = "packetweave";
    @Override public void onInitialize() {
        // Consumers own authenticated packets and connection-scoped transfer registries.
        // This library intentionally registers no global network channel or session.
    }
}
