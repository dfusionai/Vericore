# Miner rejection and snippet reasons

Canonical list of miner-level status values and snippet-level score/rejection reasons for Subnet 70 (Vericore), for dashboards, ops, and miner tooling. For the high-level scoring formula and domain/speed factors, see [scoring_mechanics_subnet_70.md](scoring_mechanics_subnet_70.md).

---

## 1. Miner-level status (rejection) reasons

**Source:** [validator/api_server.py](../validator/api_server.py) — `VericoreMinerStatementResponse.status` and associated scores.

| Status | Score | When |
|--------|-------|------|
| `invalid_miner` | 0 | Miner UID not found for hotkey |
| `unreachable_miner` | -10 | No `axon_info` or `not axon_info.is_serving` |
| `no_response` | -10 | Miner response is None, or `veridex_response` is None, or exception during `call_axon` |
| `no_statements_provided` | -5 | Miner returned empty list of evidence |
| `ok` | (computed) | Normal path; score from snippets + speed factor |
| `error` | -10 | Exception in `process_miner_response` |
| `duplicate_miner_statements` | 0 | Same excerpts/URLs as another miner, slower response |

Constants: `UNREACHABLE_MINER_SCORE`, `INVALID_RESPONSE_MINER_SCORE`, `NO_STATEMENTS_PROVIDED_SCORE`, `DUPLICATE_EXACT_MINER_STATEMENTS` from [shared/scores.py](../shared/scores.py).

---

## 2. Snippet-level reasons (`snippet_score_reason`)

**Source:** [validator/snippet_validator.py](../validator/snippet_validator.py) (and one in [validator/api_server.py](../validator/api_server.py)). Each snippet gets a `VericoreStatementResponse` with `snippet_score_reason` and `snippet_score`.

| snippet_score_reason | Score | Description |
|----------------------|-------|-------------|
| `query_parameter_same_as_evidence` | -5 | URL query/path too similar to statement (search gaming) |
| `using_search_in_url_as_evidence` | -5 | Path contains "search" |
| `using_search_as_part_of_url` | -5 | Last path part looks like a search sentence |
| `using_search_as_evidence:%20` | -5 | Last path part contains "%20" (search-like) |
| `excerpt_is_same_as_url` | -5 | Excerpt matches URL path (search gaming) |
| `blacklisted_url` | -5 | Domain on blacklist |
| `domain_is_recently_registered` | -1 | Domain registration too recent |
| `ssl_url_required` | -2 | Non-HTTPS URL |
| `no_snippet_provided` | -5 | Empty excerpt |
| `snippet_same_as_statement` | -10 | Excerpt identical to statement |
| `invalid_excerpt` | -5 | Fails `is_valid_separator_sentence` (e.g. too short) |
| `excerpt_too_similar` | -5 | Snippet too similar to statement |
| `could_not_extract_html_from_url` | 0 | Page fetch returned empty text |
| `is_search_web_page` | -5 | Page content detected as search results page (or assessment `is_search_url`) |
| `unrelated_page_snippet` | 0 | AI: excerpt unrelated to statement |
| `fake_page_snippet` | -5 | AI: excerpt fake/vague/evasive |
| `snippet_not_verified_in_url` | -1 | Snippet text not found in fetched page |
| `too_many_snippets` | 0 | Snippets beyond MAX_MINER_RESPONSES (api_server) |
| `error_verifying_miner_snippet` | -1 | Exception during snippet validation |

---

## 3. rejection_reason (AI free-text)

`rejection_reason` is set from `assessment_result.get("reason")` only when the validator uses the AI assessment and returns UNRELATED, FAKE, or `is_search_url` — i.e. in [validator/snippet_validator.py](../validator/snippet_validator.py) for `snippet_result == "UNRELATED"`, `snippet_result == "FAKE"`, or when `is_search_url` is true.

Known patterns from [validator/open_ai_client_handler.py](../validator/open_ai_client_handler.py) (when assessment fails or is filtered):

- `"Prompt was filtered due to policy violation in category '{category}'."` — snippet_status set to FAKE
- `"Error: {error_str}."` — snippet_status set to ERROR
- `"Error Parsing Json: {e}."` — snippet_status set to ERROR

Otherwise the reason is free-text from the AI model (e.g. why excerpt was classified UNRELATED or FAKE). If storing `rejection_reason`, consider aggregating phrases or a word cloud for miner feedback.

---

## 4. Recommended charts (validator / ops)

- **Miner status distribution** — Bar or pie of `status` counts (ok vs unreachable_miner vs no_response vs no_statements_provided vs error vs duplicate_miner_statements vs invalid_miner) to see overall health.
- **Snippet reason distribution** — Bar chart of `snippet_score_reason` counts (over all snippets or per request) to see main failure modes.
- **Snippet reasons over time** — Time series of counts per `snippet_score_reason` to spot trends (e.g. rise of search-as-evidence).
- **Snippet reasons by miner** — Heatmap or stacked bar: miner_uid (or hotkey) vs top `snippet_score_reason` to see which miners get which failures.
- **Score by miner status** — Distribution of `final_score` by `status` (e.g. box plot) to confirm score mapping.
- **Top rejection_reason phrases** — If storing `rejection_reason`: word cloud or aggregated phrases for UNRELATED/FAKE/search to guide miner feedback (optional).

---

## 5. Veridex protocol (response shapes and timing)

Types and constants are defined in [shared/veridex_protocol.py](../shared/veridex_protocol.py). The validator returns nested responses; timing and fetcher status are available both at top level (legacy) and in a `timing` object.

### Snippet fetcher status constants

Used for **fetch-by-HTTP** and **fetch-by-Selenium** status (Selenium is not always run; e.g. when HTTP succeeds):

| Constant | Value | Meaning |
|----------|--------|--------|
| `SNIPPET_FETCHER_STATUS_OK` | `"ok"` | That fetch ran and returned usable content (e.g. HTTP 200 or Selenium fallback 200). |
| `SNIPPET_FETCHER_STATUS_ERROR` | `"error"` | That fetch ran but failed (non-200, exception, or Selenium attempted and failed). |
| `SNIPPET_FETCHER_STATUS_NOT_RUN` | `"not_run"` | That fetch was never invoked (e.g. Selenium not run when HTTP succeeded; or snippet fetcher not called for this snippet). |

### Timing DTOs (nested under `timing`)

- **StatementResponseTiming** — Per-snippet: `verify_miner_time_taken_secs`, `fetch_page_time_taken_secs`, `assess_statement_time_taken_secs`, `fetch_by_http_time_secs`, `fetch_by_selenium_time_secs`, `snippet_fetcher_total_time_secs`, `cleaning_html_time_taken_secs`, `fetch_by_http_status`, `fetch_by_selenium_status`.
- **MinerResponseTiming** — Per-miner: `elapsed_time`, `total_fetch_time_secs`, `total_ai_time_secs`, `total_other_time_secs`, `avg_snippet_time_secs`, `max_snippet_time_secs`, `snippet_count`.
- **QueryResponseTiming** — Per-query: `total_elapsed_time`, `timestamp`, `total_fetch_time_secs`, `total_ai_time_secs`, `total_other_time_secs`, `avg_snippet_time_secs`, `max_snippet_time_secs`, `total_snippet_count`, `miner_count`.

Legacy timing fields remain at top level on each response; `timing` duplicates them in a single nested object for consumers that prefer a structured view.

### VericoreStatementResponse (per-snippet)

In addition to the fields in section 2, each snippet response includes:

- **Legacy (top-level):** `verify_miner_time_taken_secs`, `fetch_page_time_taken_secs`, `assess_statement_time_taken_secs`, `snippet_fetcher_http_time_secs`, `snippet_fetcher_selenium_time_secs`, `snippet_fetcher_total_time_secs`, `cleaning_html_time_taken_secs`, `fetch_by_http_status`, `fetch_by_selenium_status`.
- **timing:** `StatementResponseTiming` — same values as above, plus all timing/status in one object. Use `timing.fetch_by_http_status` / `timing.fetch_by_selenium_status` and `timing.cleaning_html_time_taken_secs` for fetch-by-HTTP/Selenium status and cleaning_html timing.
- **social_bonus_contribution:** Per-excerpt contribution to the miner’s social bonus. `0` for web snippets or when desearch proofs are invalid; `1.0` for a desearch snippet from x.com/twitter.com; `0.5` for a desearch snippet from reddit.com (only when proofs are valid). The miner’s `social_bonus_score` is the sum of this field across all snippets.

### VericoreMinerStatementResponse (per-miner)

- **Legacy (top-level):** `elapsed_time`, `total_fetch_time_secs`, `total_ai_time_secs`, `total_other_time_secs`, `avg_snippet_time_secs`, `max_snippet_time_secs`, `snippet_count`.
- **timing:** `MinerResponseTiming` — same aggregated timing in one object.
- **desearch_bonus_score:** Miner-level desearch proof bonus or penalty. `+2` when all desearch proofs verify successfully, `-5` when any proof fails, `0` when no desearch proofs are provided.
- **social_bonus_score:** Sum of per-snippet social bonus for **desearch** snippets only, and only when desearch proofs are valid. `+1` per snippet from x.com or twitter.com, `+0.5` per snippet from reddit.com; web snippets do not contribute. If proofs are invalid or absent, this is 0. Added to `final_score` along with `desearch_bonus_score`.

### VericoreQueryResponse (per-query)

- **Legacy (top-level):** `timestamp`, `total_elapsed_time`, `total_fetch_time_secs`, `total_ai_time_secs`, `total_other_time_secs`, `avg_snippet_time_secs`, `max_snippet_time_secs`, `total_snippet_count`, `miner_count`.
- **timing:** `QueryResponseTiming` — same query-level timing in one object.

---

## 6. Charts against veridex_protocol (for the miner)

Charts that miners (or miner dashboards) can build using the protocol types in [shared/veridex_protocol.py](../shared/veridex_protocol.py).

### Miner request/response (VericoreMinerStatementResponse)

- **status** — Bar or pie of `status` (ok, unreachable_miner, no_response, no_statements_provided, error, duplicate_miner_statements) so miners see their own outcome mix.
- **final_score vs elapsed_time** — Scatter: `final_score` (y) vs `elapsed_time` (x) to see speed–score tradeoff.
- **raw_score vs speed_factor** — How much of `final_score` comes from content (`raw_score`) vs speed (`speed_factor`).
- **snippet_count** — Distribution of `snippet_count` per request (how many snippets sent).
- **Time breakdown** — Stacked bar or area: `total_fetch_time_secs`, `total_ai_time_secs`, `total_other_time_secs` per request (or use `timing` for the same values in one object).
- **avg_snippet_time_secs / max_snippet_time_secs** — Time series or distribution to spot slow snippets (also in `timing`).

### Per-snippet (VericoreStatementResponse)

- **snippet_score_reason** — Bar chart of `snippet_score_reason` counts (miner’s own snippets) to see why snippets fail or get low scores.
- **snippet_found** — Proportion of snippets with `snippet_found=True` vs False.
- **local_score vs snippet_score** — Scatter or box: effect of `domain_factor` and `approved_url_multiplier`.
- **NLI probs** — Distribution of `contradiction`, `neutral`, `entailment` (e.g. small histograms or ternary) to see support/contradict mix.
- **Timing** — Use top-level fields or `timing`: `verify_miner_time_taken_secs`, `fetch_page_time_taken_secs`, `assess_statement_time_taken_secs`, `fetch_by_http_time_secs`, `fetch_by_selenium_time_secs`, `snippet_fetcher_total_time_secs`, `cleaning_html_time_taken_secs` to see fetch vs AI vs cleaning_html vs other.
- **Fetch-by status** — `fetch_by_http_status` and `fetch_by_selenium_status` (values: `ok`, `error`, `not_run`) to see when HTTP vs Selenium was used or failed; use `timing.fetch_by_http_status` / `timing.fetch_by_selenium_status` if reading from the nested object.
- **Signals** — Optional: distributions of `sentiment`, `conviction`, `source_credibility`, `narrative_momentum`, `risk_reward_sentiment`, `catalyst_detection`, `political_leaning` for accepted snippets.

### Miner output (VericoreSynapse / SourceEvidence)

- **Snippets per request** — Distribution of `len(veridex_response)` (how many `SourceEvidence` items sent).
- **Excerpt length** — Distribution of `len(excerpt)` (or word count) per snippet.
- **URL/domain** — Domain (or TLD) distribution of `url` to see source diversity and overuse of one domain.

### Optional: request-level (VericoreQueryResponse)

- If the miner sees query-level aggregates: **miner_count**, **total_snippet_count**, **total_elapsed_time** vs **total_fetch_time_secs** / **total_ai_time_secs** for context (e.g. validator-side totals). The same fields are available under **timing** (`QueryResponseTiming`) for a single nested object.
