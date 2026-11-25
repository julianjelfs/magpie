# Magpie

A slowly gathered library of art. Magpie hangs one piece at a time from the open collections of the Metropolitan Museum, the Cleveland Museum of Art and SMK in Copenhagen, and from Wikimedia Commons, on a wall painted to suit it. You keep it or pass. Kept pieces go into the hoard, where Claude tags them by period, movement, region, medium, technique and subject, and adds a short note on what to look at if you sketch them.

It runs on the Raspberry Pi at **https://magpie.julianjelfs.co.uk**. That one URL works on the home wifi and, through the Pi's Tailscale subnet route, anywhere on the tailnet.

## Using it

- **Look**: press Keep or Pass, the arrow keys (→ keeps, ← passes), or swipe right or left anywhere on the screen. The label beside each piece is the museum's own record, with a link to its page. On a phone the picture gets the whole screen and the label comes up on demand: tap the picture or the ⓘ button. It stays up for the next pieces until you close it.
- **Rooms**: chooses which Met departments new pieces come from. Paintings, prints and drawings, Asian art, modern art, the Lehman collection, Islamic art and photographs are open to start with. Whatever the room, Magpie offers pictures only: paintings, drawings, prints, photographs, manuscript pages and calligraphy. "Sculpture too" adds sculpture. "Modern painting (Wikimedia Commons)" adds paintings by about a hundred artists from Monet to Mondrian, from Wikidata and Wikimedia Commons. Cleveland (paintings, drawings, prints, photographs) and SMK (paintings, drawings, prints) have a room each per kind. About a quarter of Met picks come from its highlights.
- **Hoard**: every kept piece, filterable by tag. Open a piece for its tags and sketching notes, or to let it go. A piece you let go of is never offered again.
- **What you keep** (linked from the hoard): how often you keep what you're shown, by room, century, kind and highlights, subject and source, plus artists kept more than once. It also shows how new pieces are being steered, and whether steered picks are kept more often than open ones.

## Steering

Rooms you keep more from come up more often. A room's weight is its keep rate, smoothed towards your overall keep rate (ten pretend verdicts at that rate), so a room seen twice and kept once doesn't leap to the top and a room not yet tried isn't punished. Every open room gets at least 5% of picks. The share of picks drawn from the Met's highlights moves between 10% and 40% depending on whether you keep more highlights than other pieces; it stays at 25% until there are 30 verdicts. Both use the museum record stored with every verdict, passes included, so steering costs no extra requests. 

Within a room, 30% of picks are open: one random piece, taste ignored. The rest are steered. A steered pick draws three pieces from the room and chooses between them by score. The score multiplies how much more or less often than usual you keep pieces with the same artist, century, kind, culture, school and subjects. One trait moves a score by at most a factor of three, a score stays between 0.2 and 5, and anything not seen before scores 1. So the least likely piece of three still has a chance, and unfamiliar work is never marked down.

An artist kept twice or more, at a better rate than you keep things in general, is followed. Up to 15% of picks look for another piece by a followed artist, trying the sources in random order, so Hokusai kept at the Met brings Hokusai from Cleveland. Pass eight in a row by an artist and Magpie stops following them.

Every piece records how it was picked (`pick` in its record). The taste page shows the keep rate for open, steered and followed picks side by side. Open picks are the control: if steered picks don't beat them, turn `EXPLORE` up.

Subjects come from the Met's subject terms and Wikidata's genre. Cleveland and SMK publish none. Verdicts given before subjects were stored are filled in from the Met ten at a time on each pass of the background loop.

The numbers live in `backend/app/taste.py`.

## Offline

The installed app opens with the Pi out of reach. It keeps six pieces on the device, pictures included, so you can still judge them. Verdicts wait in an outbox and go to the Pi when it is back. The hoard shows its last copy, with the time it was taken, and its thumbnails come from the service worker's cache. New pieces, tagging and rooms need the Pi.

## How it works

One FastAPI process on `127.0.0.1:8060` serves the API and the built Svelte app. Caddy terminates TLS in front of it. A background task keeps eight pieces ready: it draws a random object from a department's ID list (cached for a week), shrinks the Met's original (often 8MB or more) to 2000px, and picks a wall colour from the picture. When you keep a piece, the task moves that picture into `backend/images/hoard/`, makes a thumbnail and sends a 1568px copy, with the museum record and the hoard's existing tags, to Claude Sonnet 5.5 at low effort. Tagging costs about a cent a piece. Every charge goes in a `spend` ledger, apart from the piece, so the total survives letting a piece go; the taste page and `magpie status` show it.

The Met retired its v1 search on 2026-10-01. Rooms that hold only pictures (Drawings and Prints, European Paintings, Photographs) are listed whole from `/v1/objects?departmentIds=N`. Every other room is listed from v1.1 searches filtered by type (`medium=Paintings` and so on), because the v1.1 search stops at offset 10,000. Each fetched record is checked against the picture types before its image is downloaded. Objects that can never be used are remembered in `backend/cache/rejected.json` and never fetched again. The Met's firewall blocks the house IP for a few minutes after a burst of requests, so Magpie sends one a second and rests five minutes after a 403. The laptop shares that IP, so heavy use of the API from it starves the Pi.

Modern painting comes from Wikidata and Wikimedia Commons, because open museum collections only publish public-domain images and modern work mostly isn't. In the UK a painting stays in copyright until the end of the 70th year after its artist's death, so an artist who died in 1955 is public domain from 2026. `backend/app/artists.json` lists the artists (name, Wikidata ID, dates, nationality, group); edit it to add or drop people. Each artist is checked against that rule every time, so later artists join on their own each January. Wikidata's query service times out on broad questions but answers per artist in a second or two, so each artist's paintings are listed with one small query and cached for a week. Requests are spaced two seconds apart, and a 429 means waiting as long as Wikidata asks. A pick is a random artist, then a random painting with an image.

Cleveland (`openaccess-api.clevelandart.org`, filtered to `cc0=1&has_image=1`) and SMK (`api.smk.dk`, filtered to `public_domain:true`) need no key and filter on the server, so a pick is one request at a random offset into the filtered list. Each is asked once a second at most. SMK's records are in Danish. A new museum with an API like these is a subclass of `OffsetSource` in `backend/app/openaccess.py`, a block of room numbers, and a line in `sources.py`.

Data lives in `backend/magpie.db` (SQLite) and `backend/images/`. The nightly backup copies the database only. Every kept piece records its museum image URL, and on startup Magpie fetches any picture that is missing from disk.

## Invariants

1. A piece with a verdict, keep or pass, is never offered again. `test_invariant_1_a_piece_with_a_verdict_is_never_offered_again`
2. A verdict given earlier never overrides a later one, whatever order they reach the Pi in. `test_invariant_2_a_stale_verdict_never_undoes_a_newer_one`
3. Sending the same batch of verdicts twice changes nothing. `test_invariant_3_replaying_a_batch_changes_nothing`
4. Letting a piece go removes it from the hoard and deletes its pictures. `test_invariant_4_letting_go_removes_the_piece_and_its_files`
5. A kept piece stays in the hoard when tagging fails, and tagging can be retried. `test_invariant_5_a_keep_survives_failed_tagging_and_can_be_retried`
6. A verdict given with the Pi out of reach survives a reload and reaches the Pi when it is back. `outbox.test.ts`, "invariant 6"
7. A kept piece whose picture is lost from disk gets it back. `test_invariant_7_a_kept_piece_whose_picture_is_lost_is_fetched_again`
8. Only pictures are offered, and sculpture only when it is switched on. `test_invariant_8_only_pictures_are_offered_and_sculpture_only_when_on`
9. Steering favours rooms you keep from, and never gives an open room less than 5% of picks. `test_invariant_9_steering_favours_kept_rooms_and_never_shuts_one_out`
10. A modern painting is offered only once its artist has been dead for more than 70 full years. `test_invariant_10_only_artists_dead_more_than_70_years_are_offered`
11. Money spent tagging stays in the running total, even after the piece is let go or tagged again. `test_invariant_11_what_tagging_cost_is_never_forgotten`
12. At least 30% of picks are open: one random piece from the room, with taste ignored. `test_invariant_12_a_fixed_share_of_picks_ignores_taste`
13. Steering never puts a piece out of reach, and a piece unlike anything seen before is not marked down. `test_invariant_13_no_piece_is_scored_out_of_reach_and_the_unfamiliar_is_not_marked_down`
14. Followed artists take no more than 15% of picks, and an artist is dropped after eight passes in a row. `test_invariant_14_followed_artists_keep_to_their_share_and_are_dropped_when_passed`
15. Cleveland and SMK offer only pictures the museum marks CC0 or public domain. `test_invariant_15_cleveland_and_smk_offer_only_public_domain_pictures`
16. A room added to Magpie opens by default without reopening a room you closed. `test_invariant_16_new_rooms_open_without_reopening_a_room_you_closed`

The Anthropic API key never reaches the browser or the repo. It lives only in `backend/.env` (gitignored, mode 600) on the Pi and the laptop.

## Development

```bash
scripts/dev.sh                          # API on :8060, Vite on :5180
cd backend && uv run pytest             # invariants 1-5 and 7-16
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
