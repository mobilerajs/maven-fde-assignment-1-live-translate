# Product Evaluation — Live Translate

- **Student:** Raj Singh
- **Date:** 2026-07-15
- **Video demo:** https://cap.link/43a8rkw1nyh4abk
- **LLM provider / model:** Anthropic Claude / `claude-sonnet-4-6`
- **Backend target:** `http://localhost:8787` (rubric+bench) · `https://raj-livetranslate-gw.fly.dev` (deployed, used for the live-website test)

## Verdict

> Shippable. The backend clears every automated rubric row (70/70) and every SLA with wide margins — cache hits answer in single-digit milliseconds versus ~2.7 s for LLM misses (a ~340× gap), errors are surfaced as 502s rather than silently returning English, and one request ID is greppable across both services' logs. The strongest part is caching correctness under concurrency: a single-flight lock guarantees identical text never triggers two LLM calls even when 5 requests race, and the SQLite tier survives restarts locally and on Fly (volume-backed). The weakest part is not the backend but the **provided extension**, which has two shipped defects (documented in §2 and §5) that prevent its popup-configured backend URL from ever applying; the live-website test therefore used the assignment's console-loader path against the deployed gateway, with the widget file itself served by that gateway.

**Rubric score (from `eval/report.json`):** 70 / 70 auto (+ 30 manual)

## 1. Performance & cost (from `benchmark/bench.py`, cold cache, via gateway)

| Metric | Result | SLA | Pass? |
|---|---|---|---|
| Cache hit p95 | 8 ms | ≤ 60 ms | ✅ |
| Cache miss p95 | 2746 ms | ≤ 3500 ms | ✅ |
| Cache hit rate | 78 % | ≥ 60 % | ✅ |
| Throughput | 1663 req/s | ≥ 20 | ✅ |
| Error rate | 0.0 % | ≤ 1 % | ✅ |
| Cost per miss | $0.000169 | — | — |
| Monthly savings from cache | $65.49 (@500k req/mo: $83.95 uncached → $18.47) | — | — |

`python benchmark/bench.py` exits 0. Earlier independent cold run: miss p95 2366 ms, hit p95 9.8 ms, 242× speedup — consistent across runs.

## 2. Live-website test

- **Sites tested:** `https://www.homedepot.com` (default target — blocked, see Resilience) and `https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/` (permissive real site — full pass, via the **deployed** gateway `https://raj-livetranslate-gw.fly.dev`)
- **Translated whole page?** Yes — books.toscrape.com: all 28 text chunks flipped to Mexican Spanish in ~10.4 s cold; layout intact; deployed `/stats` confirmed the traffic (23 misses, 34 hits recorded server-side).
- **Coverage gaps:** text inside images untouched (expected); a long product-description node mixed EN/ES on the cold pass where the source text itself embeds poem fragments.
- **Cache on re-translate:** Restore → Translate again showed **“28 chunks · 28 cache hits”**, effectively instant vs 10.4 s cold.
- **Resilience (real findings in the PROVIDED frontend, not the backend):**
  1. **Extension config race** — `extension/content.js` reads the popup-saved backend URL from `chrome.storage` *asynchronously*, but `translation-widget.js` copies `window.FDE_CONFIG` *synchronously* at load. The widget therefore always captures the default `http://localhost:8787`; the popup’s saved URL (verified persisted — it reloads into the popup field) never takes effect. Reproduced across multiple page loads.
  2. **HTTPS→localhost blocking** — even with the localhost default, Chrome blocks content-script fetches from public HTTPS pages to `http://localhost:8787` (private-network access); requests never reach the gateway (verified: request counters static on both backends while the widget spun).
  3. **homedepot.com strict CSP** — no widget request left the browser on Home Depot regardless of backend; per the eval instructions this is recorded as a finding and a permissive real site was tested in addition.
  - **Workaround used (sanctioned):** the console-loader path — `window.FDE_CONFIG = { API_URL: "https://raj-livetranslate-gw.fly.dev" }` then loading `…fly.dev/widget.js` (the deployed gateway serves the widget) — worked flawlessly on the permissive site. Backend error handling also verified: with an invalid API key every request returned **502 with a JSON error** (never silent English), e.g. the dependency trap in the starter (`anthropic==0.39.0`, incompatible with httpx ≥ 0.28) was caught precisely because failures are loud; fixed by upgrading the SDK in `requirements.txt`.
- **Screenshots:** attached to submission (before EN / after es-MX / cache-hit badges).

### Sample translations (from the live page + deployed API)

| Original (EN) | Translation (es-MX) | Numbers/prices/codes kept? | OK? |
|---|---|---|---|
| Books to Scrape — We love being scraped! | Libros para Raspar — ¡Nos encanta que nos hagan scraping! | — | ✅ |
| A Light in the Attic | Un Rayo de Luz en el Ático | — | ✅ |
| In stock (22 available) | En existencia (22 disponibles) | 22 ✅ | ✅ |
| £51.77 | £51.77 (untouched) | ✅ | ✅ |
| Add to cart | Agregar al carrito (not Castilian “Añadir a la cesta”) | — | ✅ |
| Sign in | Iniciar sesión | — | ✅ |
| Forgot your password? | ¿Olvidaste tu contraseña? (Mexican informal register) | — | ✅ |
| The XZ-200 drill is 15% off — now $129.99 (SKU-4471). | El taladro XZ-200 tiene 15% de descuento — ahora $129.99 (SKU-4471). | XZ-200, 15%, $129.99, SKU-4471 all ✅ | ✅ |

## 3. Dimension scorecard

| Dimension | Pass / Partial / Fail | Evidence |
|---|---|---|
| Translation accuracy | Pass | Sample pairs above; fluent, translation-only output, no preamble/quotes |
| Mexican-Spanish register (es-MX) | Pass | “Agregar al carrito”, “¿Olvidaste tu contraseña?”, no vosotros/Castilian forms |
| Numbers / prices / codes preserved | Pass | $129.99, £51.77, 15%, XZ-200, SKU-4471, UPC hash all verbatim |
| Page coverage | Pass | 28/28 text chunks on live page; images/alt text out of scope |
| Cache effectiveness | Pass | 28/28 hits on re-translate; server /stats corroborates; survives restart locally + on Fly volume |
| Latency vs SLA | Pass | bench exit 0; hit p95 8 ms vs miss p95 2746 ms |
| Error handling (no silent English) | Pass | Invalid-key test → 502 JSON at gateway, ERROR line with requestId in ai-service.log |
| Resilience on a real site | Partial | Backend resilient; provided extension cannot apply its configured URL (race) and HTTPS→localhost is browser-blocked — findings §2; console-loader path fully worked |
| UX polish | Pass | Widget badges show chunks/hits/ms; restore works; no layout breakage |

## 4. Top fixes before shipping

1. **Fix the extension config race** (needs a change to the provided `extension/` code, out of bounds for this assignment): read `chrome.storage` in the widget itself or gate widget init on the storage callback; today the popup-saved backend URL never applies.
2. **Route extension traffic through a background service worker** so real HTTPS sites can reach a localhost/dev gateway without private-network blocking, and strict-CSP sites (homedepot.com) work — the README describes this architecture but the shipped MV3 extension has no background worker.
3. **Batch-level partial failure handling**: one failed item currently 502s the whole batch; per-item error entries would let 39/40 strings still render.

## 5. Red-line checks

- ✅ No secrets committed (`.env`, `*.db`, `*.log`, `node_modules/`, `.venv/` gitignored)
- ✅ No edits to provided `widget/`, `extension/`, `benchmark/`, `eval/`, `loader/`, `demo-pages/` (`git diff --stat` empty)
- ✅ All numbers in this report from actual runs (`eval/report.json`, `benchmark` output, live server `/stats`)
