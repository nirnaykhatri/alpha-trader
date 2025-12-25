The order preview in the Create DCA Bot dialog is generated entirely on the frontend from the current form values. The “backend-equivalent” implementation should mirror the same inputs, unit conventions, rounding rules, and validation/fix logic.

**Where the logic lives**
- Core preview math + validation: dca-form-components.tsx
- Form sections + wiring (incl. passing `symbol`, `assetClass`, `strategy`): dca-form-sections.tsx
- Dialog state + current price fetch for preview: dca-bot-config-dialog.tsx
- Types (DCA config shape): bot.ts

---

## 1) Inputs the preview uses

From the DCA config (simplified):
- `symbol` (e.g., `AAPL` or `BTC/USD`)
- `assetClass` (crypto/forex/stock/etf)
- `strategy` (long/short)
- `currentPrice` (quote fetched by the UI; used only for preview)
- Base order:
  - `baseOrderAmount`
- Averaging orders:
  - `totalAmount`
  - `orderCount`
  - `amountMultiplier` (geometric sizing)
  - `stepPercent` (distance between orders)
  - `stepMultiplier` (geometric widening)

---

## 2) Unit conventions (this is the biggest “gotcha”)

The preview treats “what the user typed” differently depending on `assetClass` and `strategy`:

### A) Crypto / Forex
- **Long**
  - Inputs are treated as **quote currency** (USD/USDT) amounts.
  - Units purchased per order are derived: $units = \frac{\text{quoteAmount}}{\text{price}}$.
- **Short**
  - Inputs are treated as **base units** (e.g., BTC).
  - USD/quote value per order is derived: $\text{quoteValue} = \text{baseUnits} \times \text{price}$.
- Precision: allow many decimals for units (UI uses higher precision for crypto/forex inputs).

### B) Stocks / ETFs
- **Long**
  - Inputs are treated as **USD** amounts.
  - Shares are derived: $\text{shares} = \frac{\text{usdAmount}}{\text{price}}$.
- **Short**
  - Inputs are treated as **shares** (base units).
  - USD value is derived: $\text{usdValue} = \text{shares} \times \text{price}$.
- Rounding: shares must be **whole integers**.

If you implement backend preview, you’ll want the backend request to include `assetClass` + `strategy` (or infer from bot type) so it can apply the same unit rules.

---

## 3) Order ladder generation (prices + sizing)

### A) Order prices
- Base order target price is the `currentPrice`.
- Safety order $i$ (1-indexed) target price is derived from cumulative step moves:
  - For **long**, price steps go “down”:  
    $$P_i = P_0 \times (1 - d_i)$$
  - For **short**, price steps go “up”:  
    $$P_i = P_0 \times (1 + d_i)$$
- The cumulative deviation $d_i$ is formed using `stepPercent` and `stepMultiplier` as a geometric series:
  - $s_1 = \text{stepPercent}$
  - $s_k = \text{stepPercent} \times (\text{stepMultiplier})^{k-1}$
  - $d_i = \sum_{k=1}^{i} s_k$

The preview also shows “Dev.” per order as approximately $d_i$ relative to current price.

### B) Order sizes
Safety-order sizing is geometric using `amountMultiplier`:

- Given total budget for averaging orders = `totalAmount`, distribute it across `N = orderCount` orders using weights:
  - $w_i = (\text{amountMultiplier})^{i-1}$ for $i=1..N$
  - $W = \sum_{i=1}^{N} w_i$
  - For **long quote-input**: $\text{quoteAmount}_i = \text{totalAmount} \times \frac{w_i}{W}$
  - For **short base-input**: $\text{baseUnits}_i = \text{totalAmount} \times \frac{w_i}{W}$

Base order is handled separately using `baseOrderAmount`.

---

## 4) Average price after each order

The preview computes a running weighted average entry after each order:

Let cumulative filled quantities after order $k$ be:
- Total base units: $U_k = \sum_{j=0}^{k} u_j$
- Total quote spent/received (for display as “investment”): $Q_k = \sum_{j=0}^{k} q_j$

Then:
- Average entry price:  
  $$\text{AvgPrice}_k = \frac{Q_k}{U_k}$$

Where:
- For **long**: $q_j$ is quote spent (USD), $u_j$ is units acquired.
- For **short**: preview still uses the same “value/units” math for an average reference price (it’s a visualization of average fill price), but backend should ensure it matches your actual execution semantics.

---

## 5) Rounding + formatting rules (to avoid regressions)

### A) Stocks/ETFs (whole shares)
- Any computed share quantity must be an integer.
- The preview includes validation around:
  - **0-share orders** (caused by distributing too few shares across too many orders)
  - **Over-allocation** (rounding causing sum of shares to exceed the configured share “budget”)
- It does **not** silently “fix” configuration; it shows an error and a “Fix” action that adjusts the config to the closest valid values.

### B) Crypto/Forex (fractional units)
- Do **not** round units down to 2 decimals. The UI allows high precision for crypto/forex inputs (so `0.0001 BTC` is valid).
- Any USD display values are formatted as currency; unit values are formatted with higher decimal precision.

Backend implementation note: prefer `Decimal` everywhere; avoid float drift when distributing totals across geometric weights.

---

## 6) Validation + “Fix” behavior (what backend should replicate)

The preview flags invalid states and offers a one-click “Fix” similar to the “price below 0” fix you asked for earlier.

### A) Long: target price goes ≤ 0
- Happens when cumulative deviation exceeds 100%.
- Fix suggests reducing `orderCount` to the maximum that keeps all target prices > 0 (given `stepPercent` and `stepMultiplier`).

### B) Stock/ETF short: some safety orders compute to 0 shares
- Happens when total shares distributed across `orderCount` with `amountMultiplier` results in early orders < 1 share.
- Fix suggests reducing `orderCount` so each order gets at least 1 share.

### C) Stock/ETF short: rounding makes total shares exceed the configured share budget
- Example you reported: configured total shares = base + averaging, but preview sums to more due to rounding.
- Fix suggests reducing `orderCount` (or increasing total shares) so rounded per-order shares sum to ≤ budget.

If you want the backend to behave identically, implement a deterministic “max valid orderCount” computation that re-simulates the ladder and finds the largest `orderCount` that satisfies all constraints, then return that as a suggested fix.

---

## 7) What to implement in backend (recommended API contract)

To keep frontend + backend consistent, I’d implement a backend endpoint that returns exactly what the preview table needs:

- Request:
  - `symbol`, `assetClass`, `strategy`, `currentPrice`
  - base order + averaging order config (amounts, multipliers, orderCount, step params)
- Response:
  - rows: `{ kind: base|so, units, quoteValue, targetPrice, deviationPct, avgPriceAfter }`
  - totals: `{ totalUnits, totalQuoteValue, finalAvgPrice, maxDeviationPct }`
  - validation: `{ isValid, issues[], suggestedFix?: { newOrderCount? ... } }`

That lets the backend bot use the same “preview engine” internally (same math/validation) and keeps the UI always consistent with live bot behavior.

If you want, I can implement this backend “preview engine” as a pure domain service (no FastAPI imports) and wire it to a small API route so the UI can stop doing the preview math locally.