## Plan: API-Hosted DCA Ladder Engine (No Duplication)

Make the backend API in this project the only place that computes DCA order previews, then remove the duplicated “mirror” math from both the UI and any bot-side re-implementations. The UI still feels live by using debounced + cancellable preview requests, while the bot execution path uses the same internal engine (or calls the same internal function) that powers the API.

### Steps 6 steps, 5–20 words each
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