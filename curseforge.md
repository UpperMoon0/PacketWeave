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

The transfer core is functional. Simply Screens 0.8.10 requires the standalone PacketWeave 0.1.1+ mod on clients and dedicated servers and calls its public API for media transfers. PacketWeave supplies the library API; installing it by itself does not register a network protocol or enable uploads.

Consuming mods supply their own native packets, authenticated sender identity, permissions, content validation, and media handling. PacketWeave manages the transfer state within that integration. It adds no blocks, items, or player-facing interface.

## Platform targets

| Minecraft | Loaders |
|---|---|
| 1.16.5 | Fabric, Forge |
| 1.20.1 | Fabric, Forge |
| 1.21.1 | Fabric, NeoForge |
| 26.1.2 | Fabric, NeoForge |

Choose the native mod file matching your Minecraft version and loader. Do not install the development-only core jar as a replacement. The mod adds no independent network protocol; consumers provide the game integration.

## For mod developers

Compile against the public API, install the native PacketWeave runtime mod, and declare the required minimum version in loader metadata. Do not duplicate the public API classes inside a consuming mod. PacketWeave itself does not require Architectury API or Fabric API.

See the [integration guide and API example](https://github.com/UpperMoon0/PacketWeave#runtime-library-integration) for runtime dependency declarations, transfer limits, and adapter responsibilities.

## Support and license

- [Source code and documentation](https://github.com/UpperMoon0/PacketWeave)
- [Report bugs](https://github.com/UpperMoon0/PacketWeave/issues)
- [MIT license](https://github.com/UpperMoon0/PacketWeave/blob/main/LICENSE)
