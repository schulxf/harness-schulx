# Asset License Register

All visual assets bundled for the optional `harness-hub` pixel client are
tracked here for auditability, even when attribution is not required.

## Downloaded Assets

| Asset | Author | License | Source | Local path | Added |
|---|---|---|---|---|---|
| Tiny Town 1.1 | Kenney | CC0 1.0 Universal | https://kenney.nl/assets/tiny-town | `hub/client/assets/vendor/kenney_tiny-town/` | 2026-05-29 |
| Tiny Dungeon 1.0 | Kenney | CC0 1.0 Universal | https://kenney.nl/assets/tiny-dungeon | `hub/client/assets/vendor/kenney_tiny-dungeon/` | 2026-05-29 |
| Ninja Adventure Asset Pack | Pixel-Boy and AAA | CC0 1.0 Universal | https://pixel-boy.itch.io/ninja-adventure-asset-pack and https://github.com/pixel-boy/NinjaAdventure | `hub/client/assets/vendor/ninja_adventure/` | 2026-05-29 |
| Harness Agent Spritesheet | Harness, derived from Ninja Adventure | CC0 1.0 Universal | https://github.com/pixel-boy/NinjaAdventure | `hub/client/assets/sprites/agents.png` | 2026-05-29 |
| xterm.js browser assets | xterm.js authors | MIT | https://github.com/xtermjs/xterm.js | `hub/client/assets/vendor/xterm/` | 2026-05-29 |

## License Notes

- Kenney packs include their own `License.txt` files in each downloaded folder.
- The Ninja Adventure itch.io page states the pack is released under Creative
  Commons Zero (CC0) and attribution is appreciated but not required.
- CC0 assets can be used for personal, educational, and commercial projects.
- The vendored xterm.js files are copied from the npm packages declared in
  `hub/package.json` and keep the upstream MIT license.

## Intended Use

- `kenney_tiny-town`: default warm repo map theme.
- `kenney_tiny-dungeon`: alternate infrastructure/security repo map theme.
- `ninja_adventure`: animated top-down character sprites and optional map props.
- `assets/sprites/agents.png`: compact runtime sheet consumed by the browser UI.
- `vendor/xterm`: self-contained browser module/CSS for the live agent terminal.

## Maintenance Rule

When adding or replacing assets, add the source URL, author, license, local path,
and date here before wiring the asset into the client.
