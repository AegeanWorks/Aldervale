# Asset Manifest

Every model, sprite, terrain texture and sound is generated at run time by the Python source, which
is licensed under AGL-1.1. The repository additionally ships AI-generated brand artwork and capture
stills under `assets/`, likewise offered under AGL-1.1. No third-party art, audio, font or level
asset files are included. Per `LICENSE` Sec 1.2, the table below is the authoritative list of Game
Assets covered by AGL-1.1; commercial extraction or redistribution needs the Aegean Commercial
License 1.0 (ACL-1.0) plus a written asset grant (see COMMERCIAL.md).

| Path or pattern | Type | Rights holder | License | Notes |
|---|---|---|---|---|
| `aldervale/` | code (procedural models, sprites, terrain) | AegeanWorks | AGL-1.1 | no separate assets; runtime-generated |
| `assets/logo.jpg` | AI-generated brand artwork, human-reviewed | AegeanWorks | AGL-1.1 | banner/logo identity; see `.aikit/media.json` |
| `assets/social-preview.png` | AI-generated brand artwork, human-reviewed | AegeanWorks | AGL-1.1 | social preview; see `.aikit/media.json` |
| `assets/screenshots/*` | capture stills via `--inspect` / `--gfx-shot` / `--web-shot` | AegeanWorks | AGL-1.1 | review evidence, not runtime assets |
