# Magpie

A slowly gathered library of art. Magpie hangs one piece at a time from the Metropolitan Museum's open access collection on a wall painted to suit it. You keep it or pass. Kept pieces go into the hoard, where Claude tags them by period, movement, region, medium, technique and subject, and adds a short note on what to look at if you sketch them.

It runs on the Raspberry Pi at **https://magpie.julianjelfs.co.uk**. That one URL works on the home wifi and, through the Pi's Tailscale subnet route, anywhere on the tailnet.

## Using it

- **Look**: press Keep or Pass, the arrow keys (→ keeps, ← passes), or swipe the picture on a phone. The label beside each piece is the Met's own record, with a link to its page.
- **Rooms**: chooses which Met departments new pieces come from. Paintings, prints and drawings, Asian art, modern art, the Lehman collection, Islamic art and photographs are open to start with. About a quarter of picks come from the Met's highlights in those rooms.
- **Hoard**: every kept piece, filterable by tag. Open a piece for its tags and sketching notes, or to let it go. A piece you let go of is never offered again.

## Offline

The installed app opens with the Pi out of reach. It keeps six pieces on the device, pictures included, so you can still judge them. Verdicts wait in an outbox and go to the Pi when it is back. The hoard shows its last copy, with the time it was taken, and its thumbnails come from the service worker's cache. New pieces, tagging and rooms need the Pi.

## How it works

One FastAPI process on `127.0.0.1:8060` serves the API and the built Svelte app. Caddy terminates TLS in front of it. A background task keeps eight pieces ready: it draws a random object from a department's ID list (cached for a week), shrinks the Met's original (often 8MB or more) to 2000px, and picks a wall colour from the picture. When you keep a piece, the task moves that picture into `backend/images/hoard/`, makes a thumbnail and sends a 1568px copy, with the museum record and the hoard's existing tags, to Claude Opus 5.5 at low effort. Tagging costs about two cents a piece; `magpie status` shows the running total.

The Met retired its v1 search on 2026-10-01. The v1.1 search stops at offset 10,000, which is why random picks come from `/v1/objects?departmentIds=N` instead.

Data lives in `backend/magpie.db` (SQLite) and `backend/images/`. The nightly backup copies the database only. Every kept piece records its museum image URL, and on startup Magpie fetches any picture that is missing from disk.

## Invariants

1. A piece with a verdict, keep or pass, is never offered again. `test_invariant_1_a_piece_with_a_verdict_is_never_offered_again`
2. A verdict given earlier never overrides a later one, whatever order they reach the Pi in. `test_invariant_2_a_stale_verdict_never_undoes_a_newer_one`
3. Sending the same batch of verdicts twice changes nothing. `test_invariant_3_replaying_a_batch_changes_nothing`
4. Letting a piece go removes it from the hoard and deletes its pictures. `test_invariant_4_letting_go_removes_the_piece_and_its_files`
5. A kept piece stays in the hoard when tagging fails, and tagging can be retried. `test_invariant_5_a_keep_survives_failed_tagging_and_can_be_retried`
6. A verdict given with the Pi out of reach survives a reload and reaches the Pi when it is back. `outbox.test.ts`, "invariant 6"
7. A kept piece whose picture is lost from disk gets it back. `test_invariant_7_a_kept_piece_whose_picture_is_lost_is_fetched_again`

The Anthropic API key never reaches the browser or the repo. It lives only in `backend/.env` (gitignored, mode 600) on the Pi and the laptop.

## Development

```bash
scripts/dev.sh                          # API on :8060, Vite on :5180
cd backend && uv run pytest             # invariants 1-5 and 7
cd frontend && npm test                 # invariant 6
cd frontend && npm run check            # svelte-check
```

`backend/.env` holds `ANTHROPIC_API_KEY`. Without it Magpie still runs, and kept pieces wait untagged.

## On the Pi

`scripts/magpie` drives the Pi over SSH. It is linked onto the PATH as `~/.local/bin/magpie`.

```bash
magpie status       # app, Caddy, hoard, Claude spend, backups, certificate, temperature
magpie rebuild      # after pushing: pull on the Pi, build the UI here, copy it across, restart
magpie logs
magpie backup       # back up now and pull the copy to ~/Backups/magpie
```

The repo is cloned to `~/magpie` on the Pi. The service is `magpie.service`, and backups run from `magpie-backup.timer` at 05:15 into `~/magpie-backups`, keeping fourteen. The Caddy block lives in the recipe-for-disaster repo's `deploy/Caddyfile`, which serves every app on the Pi.

Standing it up again from scratch:

```bash
ssh julian_jelfs@pi.local 'git clone https://github.com/julianjelfs/magpie.git'
ssh julian_jelfs@pi.local 'grep ^ANTHROPIC_API_KEY= ~/recipe-for-disaster/backend/.env > ~/magpie/backend/.env && chmod 600 ~/magpie/backend/.env'
(cd frontend && npm run build) && rsync -az frontend/dist/ julian_jelfs@pi.local:magpie/frontend/dist/
ssh julian_jelfs@pi.local 'cd magpie && ./deploy/install-pi.sh'
```

Restore a database with `sqlite3 .backup`, never `cp`, while the service is stopped.

## Later

Exporting favourites to Askance for sketching.
