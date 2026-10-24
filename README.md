# Rapture TCG

A trading card game where the **Rapture ARC 1** NFTs on LitVM Liteforge (chain 4441) are your cards and champions.
Built with [Tessaract](https://github.com/strodanodev/tessaract).

- **Your NFT is your champion.** Its on-chain ERC-6699 stats set your life, spell power, unit attack and opening hand, and its element picks your hero power (Lava Strike, Water Bolt, Earth Ward, Metal Forge).
- **Your wallet is your deck.** Build a 36-card deck from the cards you hold, or use the suggested deck to practice.
- **Every match replays.** One integer log per match; the browser, the relay and a LitNode ruleset run the same rules, so results can be shared as links and settled on chain.
- **Modes:** practice against easy, normal or hard bots; the Gauntlet (eight matches with rewards); a daily "win this turn" puzzle; two-player matches with spectators; a profile with history and replays.

## Run it

```bash
pnpm install
pnpm run build       # fetch the Rapture snapshot and art from forge.litvm.games, then build the site
pnpm run dev         # http://127.0.0.1:4173
```

| Script | What it does |
|---|---|
| `fetch-collection` | Downloads the collection snapshot and card art into `collection/` (never committed) |
| `web` | Builds the site in `web/` from the game file and the collection |
| `sim` | Bot-vs-bot balance and fun targets, strict (fails on a miss) |
| `rebuild-cards` | Regenerates the card set from the snapshot with Tessaract's design kit, keeping this game's settings |
| `title` | Builds the LitNode ruleset and checks compatibility |
| `relay` | A two-player relay (`TCG_DEV=1` for local play) |

The game is `games/rapture-duel.game.json`. Its ruleset id stays `rapture-duel.vN` (the game was called Rapture Duel before it became its own product), so existing replay links and saved decks keep working. Any rules or card change needs the next `vN`.

## Deploy

The site is static: `web/` plus the headers in `vercel.json`. Build first (`pnpm run build`), then deploy `web/` to any static host. `.vercelignore` keeps the upload to the built site.

## License

- **Code:** Apache-2.0 (`LICENSE`).
- **Rapture characters, names, art and avatars:** © LitVM Games, all rights reserved, and not in this repository. See `NOTICE`. To build on them, open a "Rapture character use request" issue.
