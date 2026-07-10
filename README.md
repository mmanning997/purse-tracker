# Purse Resale Tracker

A local dashboard of Ashley's handbag collection and each bag's current resale
value — treated like an investment portfolio (paid vs. current, gain/loss,
value trend over time).

## Views (tabs)

- **Collection** — the holdings table: condition, authentication, paid vs.
  resale, value sparkline, gain/loss. Filter by All / Gaining / Losing.
- **Lookbook** — a visual grid of the bags (photos, or a monogram tile until
  you add one). Tap any bag to edit or attach a photo.
- **Insights** — a value-by-brand donut and a collection-value-over-time chart.
- **Wishlist** — dream bags with a target price and current price, flagged when
  they're at/under target.
- **Archived** — bags Ashley has sold or let go: what she paid, what it sold
  for, and the realized gain/loss, with a running realized total.

## Selling / letting a bag go — Archive vs. Delete

Open the bag and choose:

- **Archive** — reveals a "sold for" price + date; hit Save and the bag moves to
  the **Archived** tab. It leaves the current-collection totals (resale value,
  invested, portfolio return, charts all recompute on active bags only) but the
  record and its realized profit are kept. **Restore to collection** reverses it.
- **Delete** — permanently removes the bag and its value history. For genuine
  mistakes, not for bags she sold — use Archive for those so you keep the P&L.

Archived bags carry `archived: true`, plus optional `soldPrice` / `soldDate`.
`refresh.py` skips them on `--fetch` (no comps needed) and reports realized
gains in its summary.

## Adding & editing — no JSON required

Everything is editable in the browser:

- **+ Add bag** / tap any bag opens a form for every field, including a **photo
  upload** and a **current value you type in yourself**.
- Edits **save to this browser** (localStorage) and survive reloads.
- **Export** downloads a `purse-data.json` bundle; **Import** loads one back;
  **Reset** discards local edits and reloads the committed file.
- To make browser edits permanent in the repo:
  `python3 refresh.py --import purse-data.json` — it splits the bundle back into
  the `data/` stores and regenerates `data.js`.

Manual values and eBay coexist: a value you type always wins; bags left blank
get filled by `--fetch` when your eBay key is set up.

## Files

- `index.html` — the dashboard. Open it in a browser; no server needed.
- `data.js` — generated payload the dashboard reads (`window.PURSE_DATA`).
- `data/bags.json` — canonical collection, one entry per bag (hand-edit freely).
- `data/history.json` — value snapshots over time, `{ bag_id: [{date, value}] }`.
  The sparklines and the value-over-time chart are drawn from this.
- `data/wishlist.json` — dream bags, one entry per item.
- `refresh.py` — regenerates `data.js`; `--fetch` pulls resale comps from eBay
  and appends a dated snapshot; `--import <bundle>` folds browser edits back in.
  Pure stdlib, no `pip install`.
- `config.example.json` — template for eBay credentials. Copy to `config.json`
  (gitignored) and fill in your keys.

## Photos

Uploaded photos are downscaled (max ~560px, JPEG) and stored as data URIs — in
the browser's localStorage day to day, and in `data/bags.json` once you Export +
`--import`. Fine for a personal collection; keep an eye on it if you attach very
large images to dozens of bags.

## A bag entry

```json
{
  "id": "chanel-classic-flap-med",
  "brand": "Chanel",
  "model": "Classic Flap Medium",
  "specs": "Black caviar, gold hardware",
  "condition": "Excellent",          // Excellent | Good | Fair
  "authenticated": true,
  "pricePaid": 6800,                  // optional — omit for no gain/loss
  "acquiredDate": "2023-05-14",       // optional
  "manualValue": null,                // optional — overrides the eBay estimate
  "ebayQuery": "Chanel Classic Flap Medium caviar",
  "notes": ""
}
```

- **pricePaid** is optional. With it, the bag shows gain/loss and counts toward
  the portfolio return; without it, only the current value shows.
- **manualValue** wins over the fetched estimate — use it when you've spotted a
  better comp yourself. Set it back to `null` to hand valuation back to eBay.
- **ebayQuery** is the search string used to pull comps. Tighter queries
  (include leather/hardware/size) give better estimates.

## Everyday use

Edit the collection, then regenerate the dashboard:

```
python3 refresh.py            # rebuild data.js from the stores
```

Refresh resale values from eBay and record a new snapshot:

```
python3 refresh.py --fetch          # needs eBay credentials
python3 refresh.py --fetch --dry    # preview the queries, no key needed
```

## eBay setup (the resale values)

1. Register at https://developer.ebay.com/ and get a **Production** keyset from
   https://developer.ebay.com/my/keys (App ID / Client ID + Cert ID / Secret).
2. `cp config.example.json config.json` and paste the two values in. `config.json`
   is gitignored, so the secret never leaves your machine.
3. Run `python3 refresh.py --fetch`.

**Value source — read this.** Until you're approved for eBay's *Marketplace
Insights* API (actual **sold** prices), fetch uses the *Browse* API — current
**active listing asking prices**, median of the comps. Asking prices run a bit
high, so treat the numbers as a ballpark. Once Insights access is granted, set
`"useSold": true` in `config.json` and you get real sold comps with no other
change. Values are indicative, not appraisals.

## Sample data

The collection ships seeded with 8 sample bags and 12 months of illustrative
history so the dashboard renders out of the box. Replace `data/bags.json` with
Ashley's real bags and run `python3 refresh.py`. To start the value history
clean, empty `data/history.json` to `{}` before the first real `--fetch`.

## Hosting

Runs as a local file today. To share with Ashley, it can go on GitHub Pages like
the other trackers — `data.js` is a static file, so nothing server-side is
needed. `config.json` and your eBay secret stay local and are never published.
