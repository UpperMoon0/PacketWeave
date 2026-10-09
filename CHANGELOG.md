# Changelog

## 0.1.1

- Add bounded receive mode for existing indexed packet adapters.
- Share file and memory chunk senders, including short-read and file-change checks.
- Bound worker-to-game-thread dispatch and check trusted file size limits at stream open.
- Add expiry-aware session lookup and connection-wide cleanup.
- Test bounded legacy transfers, limits, sender parity, and cancellation.
