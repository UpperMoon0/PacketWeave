# PacketWeave

PacketWeave is a shared library for Minecraft mods that transfer binary assets between clients and servers. Its transfer core helps mod developers split and reconstruct media, structure files, and other custom payloads with explicit resource limits.

## Features

- **Chunked transfers:** Split files and byte arrays into indexed chunks and reconstruct chunks received out of order.
- **Resource limits:** Bound individual transfers, sessions per sender, total sessions, and memory use.
- **Authorization hooks:** Let the consuming mod check permissions when a transfer begins, receives chunks, and completes.
- **Transfer cleanup:** Cancel transfers, expire inactive sessions, and release state when a connection closes.
- **Input checks:** Reject duplicate chunks and invalid transfer geometry, detect files that change during sending, and provide SHA-256 digest utilities.
- **Shared core:** Use the same Java 8-compatible transfer implementation across supported loaders and Minecraft versions.

## Current status

The transfer core is functional and is embedded by Simply Screens for its media transfers. PacketWeave's native loader entrypoints are currently scaffolds: installing the standalone mod does not register a network protocol or enable uploads by itself.

Consuming mods supply their own native packets, authenticated sender identity, permissions, content validation, and media handling. PacketWeave manages the transfer state within that integration. It adds no blocks, items, or player-facing interface.

## Platform targets

| Minecraft | Loaders |
|---|---|
| 1.16.5 | Fabric, Forge |
| 1.20.1 | Fabric, Forge |
| 1.21.1 | Fabric, NeoForge |
| 26.1.2 | Fabric, NeoForge |

Choose a file matching your Minecraft version and loader. These are build targets; they do not imply a completed standalone networking integration.

## For mod developers

The core can be embedded in a consuming mod without installing a separate PacketWeave mod. Each native target also includes the core classes in its own JAR. PacketWeave does not require Architectury API or Fabric API.

See the [integration guide and API example](https://github.com/UpperMoon0/PacketWeave#embedded-core-integration) for embedding, transfer limits, and adapter responsibilities.

## Support and license

- [Source code and documentation](https://github.com/UpperMoon0/PacketWeave)
- [Report bugs](https://github.com/UpperMoon0/PacketWeave/issues)
- [MIT license](https://github.com/UpperMoon0/PacketWeave/blob/main/LICENSE)
