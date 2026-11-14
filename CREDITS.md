# PlayFeat! prototype: audio credits

Every audio file in `audio/` and where it comes from. Licenses were checked on the source pages on 2026-11-09.

## Music

| File | Title | Author | License | Source | Changes |
|---|---|---|---|---|---|
| `audio/music/shake_and_bake.m4a` | Shake and Bake | Matthew Pablo (www.matthewpablo.com) | CC-BY 3.0 | https://opengameart.org/content/shake-and-bake | Re-encoded MP3 to AAC 96 kbps; played as a loop between 27.42 s and 102.42 s |
| `audio/music/outer_space_loop.m4a` | Outer Space Loop | wipics | CC0 1.0 | https://opengameart.org/content/outer-space-loop | Re-encoded MP3 to AAC 80 kbps; looped 0 to 68.56 s (skips encoder silence at the end) |

**Required attribution (CC-BY 3.0):** "Shake and Bake", Music by Matthew Pablo, www.matthewpablo.com, licensed under CC-BY 3.0 (https://creativecommons.org/licenses/by/3.0/). Source: https://opengameart.org/content/shake-and-bake.
The author's credit line format, from his attribution page, is "Music by Matthew Pablo / www.matthewpablo.com".

## Sound effects

| Files | Title | Author | License | Source | Changes |
|---|---|---|---|---|---|
| `audio/mixkit/bowl_placed.m4a` | Bowl placed on table (#1799) | Mixkit | Mixkit Sound Effects Free License (https://mixkit.co/license/#sfxFree), which explicitly allows use in video games | https://mixkit.co/free-sound-effects/kitchen/ | Trimmed, mono AAC |
| `audio/mixkit/oven_ding.m4a` | Kitchen oven ding (#1838) | Mixkit | Mixkit Sound Effects Free License | https://mixkit.co/free-sound-effects/kitchen/ | Trimmed, mono AAC |
| `audio/mixkit/frying_eggs_loop.m4a` | Frying eggs on hot pan (#121) | Mixkit | Mixkit Sound Effects Free License | https://mixkit.co/free-sound-effects/kitchen/ | 6 s cut with a crossfaded loop seam, mono AAC |
| `audio/kenney/interface-sounds/*.m4a` (100 files) | Interface Sounds | Kenney (www.kenney.nl) | CC0 1.0 | https://kenney.nl/assets/interface-sounds | Silence trimmed, mono AAC |
| `audio/kenney/digital-audio/*.m4a` (62 files) | Digital Audio | Kenney (www.kenney.nl) | CC0 1.0 | https://kenney.nl/assets/digital-audio | Silence trimmed, mono AAC |
| `audio/kenney/sci-fi-sounds/*.m4a` (73 files) | Sci-fi Sounds | Kenney (www.kenney.nl) | CC0 1.0 | https://kenney.nl/assets/sci-fi-sounds | Silence trimmed, mono AAC |

The Mixkit license does not allow redistributing the sounds on their own. They are included only as part of this game.

The full Kenney packs are included so the sound test screen can swap any file. These Kenney files are used by default: `interface-sounds/click_001` (button), `interface-sounds/pluck_001` (bubble pop), `digital-audio/pepSound3` (grab), `digital-audio/twoTone1` (customer arrives), and `sci-fi-sounds/lowFrequency_explosion_001` (angry alien arrives).

## Code-made sounds

These are generated at runtime with the Web Audio API in `index.html`: the burn warning tick, burnt "fzzt", angry hiss, serve chime, wrong-dish bonk, customer-leaves blip, last-10-seconds tick, day-end bell, the three star notes and the marathon run-over notes. No AI-generated audio is used.

`audio/manifest.json` lists every file with its title, author, license and source link.
