# Kalodata Sniper — Advanced Route SOP (Momentum Academy)

The advanced version of Automate Your Product Research. Instead of watching Claude drive your browser, this runs the whole hunt through a cloud browser and drops a finished CSV in your folder. More setup, way more hands-off, and less glitchy than screen-driving. This is the same engine Momentum's own Weekly Drop runs on.

**Simple route vs this route:** the simple route (Claude in Chrome, in the vault guide) is interactive, you watch it work. This route is fire-and-forget: one command → CSV. Start simple; graduate here when you're running research every week.

## SOP 1 — One-time setup (15 minutes)

1. **Save the 4 presets in YOUR Kalodata** (Product page → set filters → "Save selected filters"). Exact names matter: `HighTicket`, `Lurkers`, `Hardcore`, `100 GAP`. **The exact filter values for each preset are in the app** → Resources → Automate Your Product Research. (They're Momentum IP, so they live in the app, not in this file.)

2. **Get a Firecrawl key** (the cloud browser): firecrawl.dev → sign up → copy your API key. Free credits cover your first weeks; the hobby plan (~$16/mo) covers heavy use. This is what makes the route "less glitchy": TikTok/Kalodata block normal scripts, the cloud browser walks right in.

3. **Install Python 3** if you don't have it (python.org, or it's already on every Mac).

4. **Make your sniper folder**: put `snipe.py` (from this kit) in a folder, and create a file named `.env` next to it:
```
KALODATA_EMAIL=you@email.com
KALODATA_PASSWORD=yourpassword
FIRECRAWL_API_KEY=fc-yourkey
```
Your credentials stay in that file on YOUR computer. They are sent only to the cloud browser session that logs in as you, same as typing them yourself.

## SOP 2 — Running it (10 seconds of work)

```
python3 snipe.py HighTicket
```
(or `Lurkers`, `Hardcore`, `"100 GAP"`)

**Your own filters:** you are not limited to the Momentum presets. Save any filter set in your Kalodata under a name you pick (e.g. `MyHunt`), then run `python3 snipe.py MyHunt`. The Product Sniper agent in the app has a "Start a new hunt" wizard that walks you through either path and hands you the exact command.

It logs in, runs the preset, applies the Momentum math (cuts anything under $15K/week revenue or paying under $1.25 a sale, cuts restricted brands: Crocs, Ninja, Shark, Liquid IV), then vets the top 12 the way the coaches do: opens each product, counts the purple AD icons on the top 10 videos (7+ = green, under 5 = cut), and checks the shop matches the brand (QVC allowed). Five to ten minutes later:

**`snipe-HighTicket-2026-07-16.csv`** appears next to the script: product, image file, image URL, price, revenue, growth, commission, per-sale $, creators, AD count, shop, TikTok Shop link, a caption from the universal bank, and an AI scene prompt. It also drops a **`sniped-products/`** folder with each winner's product photo downloaded, ready to feed straight into the AI Director (SOP 3).

## SOP 3 — Send it to the AI Director

Two ways to turn the hunt into videos. Both end with the products queued in **Bulk Factory** inside the app, where you review them and hit **Generate All**. (It never auto-renders, so a bad find never burns your credits.)

**Route A — drag and drop (no setup):**
1. Open the **AI Video Director → Bulk Factory** in the app.
2. Drag the whole **`sniped-products/`** folder onto it (up to 10 at a time).
3. Drop the **`snipe-…csv`** on top. Each product's name, caption, and scene prompt fill in automatically by matching the image filename.
4. Pick your caption style, hit **Generate All**. Videos land in **My Videos**.

**Route B — auto-push (one-time setup, then it's hands-free):**
1. In the app, open **AI Video Director → Connect your Sniper** and copy your **ingest key**.
2. Add one line to your `.env` next to `snipe.py`:
```
DIRECTOR_INGEST_KEY=paste-your-key-here
```
3. That's it. Every future `python3 snipe.py …` run pushes its winners straight into your Director inbox. Open the app, glance at the **Sniper Inbox**, load them into Bulk Factory, and Generate All. No files to drag.

Keep the review step either way. The sniper is good, but you still eyeball the products before spending render credits.

### Claude Code power move (optional)
If you run Claude Code, open it in your sniper folder and just say "run the sniper on Lurkers and tell me which 3 products fit my account best." It runs the script AND reasons over the CSV for you.

### Automate it weekly (optional)
- **Mac:** System Settings aren't needed, one line in Terminal: `echo '0 7 * * 1 cd ~/sniper && /usr/bin/python3 snipe.py HighTicket' | crontab -` (Mondays 7am)
- **Windows:** Task Scheduler → Create Basic Task → weekly → `python snipe.py HighTicket`

## Rules (same as always)
- YOUR account, YOUR credentials, YOUR computer. Never send your login to another person or tool you don't control.
- One or two runs a week is plenty. Hammering Kalodata gets sessions flagged.
- The vetting is the point. Never post a product the script cut, the AD icons and shop checks are what keep your account alive.
- Captions come from the universal bank only. Never put a discount percentage on screen unless you're tracking it (ask the coaches about the discount rules).

Stuck? Screenshot the error into the Discord and tag a coach.
