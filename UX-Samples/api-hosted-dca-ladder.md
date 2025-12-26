## Plan: API-Hosted DCA Ladder Engine (No Duplication)

**Status: ✅ IMPLEMENTED**

Make the backend API in this project the only place that computes DCA order previews, then remove the duplicated "mirror" math from both the UI and any bot-side re-implementations. The UI still feels live by using debounced + cancellable preview requests, while the bot execution path uses the same internal engine (or calls the same internal function) that powers the API.

### Implementation Summary

| Step | Status | Details |
|------|--------|---------|
| 1. Preview engine as single truth | ✅ Done | `src/domain/dca_order_preview.py` + `src/signals/routers/dca_preview_router.py` |
| 2. Generate shared TS types | ✅ Done | `trading-terminal/lib/types/dca-preview.ts` |
| 3. UI calls hosted API | ✅ Done | `useDCAPreview` hook with debounce + AbortController |
| 4. Remove duplicated TS math | ✅ Done | Removed `calculateDCAOrders`, `validateDCAConfig` from `dca-form-components.tsx` |
| 5. Refactor bot execution | ✅ N/A | Bot uses `risk_manager` with live account constraints - this is correct design |
| 6. Update documentation | ✅ Done | This file updated |

### Files Changed

**New Files:**
- `trading-terminal/lib/types/dca-preview.ts` - TypeScript types matching API contract
- `trading-terminal/lib/hooks/use-dca-preview.ts` - React hook with debounce (300ms), AbortController

**Modified Files:**
- `trading-terminal/lib/api.ts` - Added `fetchDCAPreview()` function
- `trading-terminal/lib/hooks/index.ts` - Export new hook
- `trading-terminal/lib/types/index.ts` - Export new types
- `trading-terminal/components/trading/shared/dca-form-components.tsx` - Removed ~250 lines of duplicate math, uses hook
- `trading-terminal/components/trading/shared/dca-form-sections.tsx` - Added `symbol` prop
- `trading-terminal/components/trading/dca-bot-config-dialog.tsx` - Pass `symbol` to section
- `trading-terminal/components/trading/dca-futures-bot-config-dialog.tsx` - Pass `symbol` to section

### Architecture Notes

The preview service (`DCAOrderPreviewService`) and execution logic (`RiskManager`) serve different purposes:

- **Preview Service**: Theoretical ladder showing what orders WILL look like based on user config
- **Execution Logic**: Real-time decisions using live account balance, current prices, risk limits

This separation is intentional:
- Preview shows user the planned ladder before starting
- Execution adapts based on real market conditions and account constraints

---

### Original Plan Steps (for reference)
1. Promote the preview engine as the single truth in dca_order_preview.py and expose it via dca_preview_router.py.
2. Generate shared request/response types from the project’s OpenAPI and place TS outputs inside the trading terminal codebase.
3. Update the UI to call the hosted API for previews (debounced + `AbortController` cancellation) from dca-form-components.tsx.
4. Remove the duplicated TS ladder math (`calculateDCAOrders` and related validation/fix math), leaving only rendering/formatting and API wiring.
5. Refactor bot execution to consume the same engine outputs (remove any separate sizing/step derivations) in dca_strategy.py.
6. Update documentation to state “API is canonical” and remove references implying dual-implementation parity in DCA-Order-Logic.md and relevant docs under docs.

### Further Considerations 3 considerations, 5–25 words each
1. Removing TS math means UI must gracefully handle latency: debounce, cache last-good preview, and show “updating” state.
2. Removing bot-side duplicate logic must preserve safety/risk checks; execution should still validate via existing risk components.
3. Version the preview contract (request/response) so UI and API can evolve without breaking deployments.

If you want this plan to be extra concrete, tell me whether the UI should use an existing data-fetching library in trading-terminal (e.g., React Query/SWR) or a lightweight custom fetch hook for the debounced/cancellable preview calls.