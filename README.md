# Pokémon Card Restock Alerts – Gulf Breeze, FL

Your phone gets an alert when Pokémon cards show up at **Target**, **Walmart** (test), or a **local card shop** within 50 miles of Gulf Breeze (Pensacola, Navarre, Milton, Pace, Fort Walton Beach, Destin, Crestview).

**Your alert name is already set:** `pokemon_Hernandawgs69`

---

## Step 1 – Get the app (2 minutes)
1. Download **ntfy** on your phone (free).
2. Tap **+**.
3. Type `pokemon_Hernandawgs69` exactly, then tap **Subscribe**.
4. Allow notifications.

## Step 2 – Put it online so it runs 24/7 (15 minutes, free)
1. Make a free account at **github.com**.
2. Click **New repository**, name it `pokemon-restock`, choose **Public**, and click **Create**.
3. Click **uploading an existing file**, drag in everything from this folder, and click **Commit**.
4. Open the **Actions** tab, click the green button to turn it on, then click **Pokemon restock monitor → Run workflow**.

It now checks stores every 5 to 15 minutes on its own, even when your computer is off.

---

## What an alert looks like
> 🚨 POKÉMON RESTOCK ALERT 🚨
> Store: Target – Pensacola
> Product: Pokémon 30th Anniversary Booster Bundle
> Price: $29.99 (MSRP)
> Status: Confirmed in stock
> Distance: 10 miles from Gulf Breeze

Tap the alert to open the product page.

- ⭐ PRIORITY means it's an Elite Trainer Box, Booster Bundle, or 30th Anniversary item.
- You won't get the same alert twice unless the store sells out and restocks.

## Walmart (test)
Ten Walmarts are being checked: Gulf Breeze, five in Pensacola, Milton, Navarre, Fort Walton Beach and Destin.

Walmart often blocks automated checks. If it blocks this one, Walmart is skipped and the other stores keep working. You won't get any warning alerts about it.

## Local card shops
These shops are already added: **TBS Comics** (Pensacola & Fort Walton Beach), **Ben's Card World** and **Emerald Collectibles**.

The system can only read a shop's stock if its website runs on Shopify. To see which shops work:
1. Go to the **Actions** tab.
2. Click **Run workflow**.
3. Open the run and look at **"Which stores can be monitored"**.
   - ✅ means it's being watched.
   - ❌ means it can't be read (or Walmart blocked it). It's skipped without causing any false alerts.

Know another shop with a website? Send me the name and website and I'll add it.

## Good to know
- **Best Buy** can be added later if you get a free Best Buy developer key, which needs a business email. GameStop, CVS, Walgreens, Dollar General, Publix and Barnes & Noble don't let anyone check their store stock online.
- **Keep your alert name private.** Anyone who knows it could see your alerts.
- **Make a small edit every month or two.** GitHub pauses jobs on repositories that haven't changed in 60 days. Edit any file and click Commit.
- **If you get a "checks have failed" alert,** a store changed its website. Come back to me and I'll fix it.
