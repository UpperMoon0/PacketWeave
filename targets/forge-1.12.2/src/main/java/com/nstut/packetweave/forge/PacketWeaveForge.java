package com.nstut.packetweave.forge;

import net.minecraftforge.fml.common.Mod;

/**
 * Makes the shared transfer API available as a native FML dependency on either side.
 * Consumers own authenticated packet handling and connection-scoped registry cleanup;
 * this library intentionally registers no global network channel or transfer registry.
 */
@Mod(modid = "packetweave", name = "PacketWeave", useMetadata = true,
        acceptedMinecraftVersions = "[1.12.2]", acceptableRemoteVersions = "*")
public final class PacketWeaveForge {
}
