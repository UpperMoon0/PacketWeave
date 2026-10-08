package com.nstut.packetweave.fabric;
import net.fabricmc.api.ModInitializer;
/** The loader adapter does not depend on Fabric API or Architectury. */
public final class PacketWeaveFabric implements ModInitializer {
    public static final String MOD_ID = "packetweave";
    @Override public void onInitialize() {
        // Packet codecs are not registered by the initial core/scaffolding release.
    }
}
