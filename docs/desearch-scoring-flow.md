# Desearch Scoring & Validation Flow

## Overview

Desearch proof validation and snippet scoring has been refactored into two distinct layers:

1. **Miner-level** -- a single bonus or penalty applied once per miner response based on whether the desearch proofs are valid.
2. **Snippet-level** -- each snippet with `source_type: "desearch"` skips URL/page-fetch checks (trusting desearch-provided URLs) but must prove its **URL** appears in at least one desearch response body; then NLI and AI assessment run (no statement/excerpt/similarity checks).

---

## Constants (`shared/scores.py`)

| Constant | Value | Scope | Description |
|---|---|---|---|
| `DESEARCH_PROOF_VALID_BONUS` | +2 | Miner | Added to final score when all desearch proofs verify successfully |
| `DESEARCH_PROOF_INVALID_PENALTY` | -5 | Miner | Added to final score when any desearch proof fails verification |
| `DESEARCH_EVIDENCE_NOT_IN_RESPONSE` | -1 | Per desearch snippet | Snippet score when URL is not found in any desearch response body (`snippet_found=False`, reason `desearch_evidence_not_in_response`) |
| `SOCIAL_BONUS_DOMAIN_X` | +1 | Per desearch snippet | Added per desearch snippet when domain is x.com or twitter.com |
| `SOCIAL_BONUS_DOMAIN_REDDIT` | +0.5 | Per desearch snippet | Added per desearch snippet when domain is reddit.com |
| `APPROVED_URL_MULTIPLIER` | 3 | Per snippet | For desearch, x.com / twitter.com / reddit.com **or** any domain in the top-site cache get this multiplier; other desearch domains get 1. For web, only top-site cache is used. |

---

## Flow Diagram

```
Miner Response Received
        |
        v
  Desearch proofs provided?
       / \
     No   Yes
      |     |
      |     v
      |   Verify every proof (signature, expiry, coldkey binding)
      |        / \
      |     Invalid  Valid
      |       |        |
      |       v        v
      |    penalty   bonus
      |    (-5)      (+2)
      |       \      /
      |        v    v
      +---> desearch_adjustment set
                |
                v
      Validate each snippet concurrently
                |
         +------+------+
         |             |
   source_type     source_type
     "web"          "desearch"
         |             |
         v             v
   Full validation   Evidence-in-body check
   (URL checks,      (snippet URL must appear
    page fetch,       in at least one desearch
    snippet-in-page,  response body; excerpt
    AI assessment)    not checked in body)
         |           +-----+------+
         |           |            |
         |        Not found     Found
         |           |            |
         |           v            v
         |     snippet_found   NLI + AI assessment
         |     =False,         only (no statement/
         |     reason:         excerpt/similarity
         |     "desearch_      validation)
         |      evidence_
         |      not_in_
         |      response"
         |     snippet_score=-1
         |     (DESEARCH_EVIDENCE_NOT_IN_RESPONSE)
         |                    NLI + AI assessment →
         |                    snippet_found=True, local_score,
         |                    approved_url_multiplier=3 for x.com/twitter/reddit or top_site cache, else 1
         |                          |
         +------------+-------------+
                      |
                      v
         For each snippet_found:
           - Desearch only, and domain is x.com/twitter.com/reddit.com: domain_factor = 1 (no duplicate-domain check)
           - Web, or desearch with other domains: domain_factor = 1/2^times_used (1st use=1.0, 2nd=0.5, 3rd=0.25, ...)
         snippet_score = local_score × domain_factor × approved_url_multiplier
                      |
                      v
         sum_of_snippets = sum of all snippet_score
                      |
                      v
         Social bonus (desearch only, when proofs valid): x.com/twitter.com → +1, reddit.com → +0.5 → social_bonus_total
                      |
                      v
         final_score = (sum_of_snippets × speed_factor) + desearch_adjustment + social_bonus_total
```

---

## Detailed Walkthrough

### Step 1: Proof Validation (api_server.py)

When a miner response includes a `desearch` list, the validator:

1. Looks up the miner's **coldkey** from the metagraph.
2. Iterates over each desearch entry, decoding the base64 response body.
3. Calls `verify_proof()` for each entry, which:
   - Checks the proof has not expired.
   - Reconstructs the signed message: `"{coldkey}|{SHA256(body)}|{timestamp}|{expiry}"`.
   - Verifies the signature against Desearch's public key.
4. Sets `desearch_proof_valid = True` only if **all** proofs pass and all bodies are collected.

### Step 2: Snippet Validation (snippet_validator.py)

Each snippet is validated concurrently. When `source_type == "desearch"`:

**What is checked:**
- The snippet's **URL** must be found in at least one of the decoded desearch response bodies (`_evidence_in_desearch_response`). The excerpt is not checked against the response body.
- If the URL is not found, the snippet fails with `desearch_evidence_not_in_response` (score: -1).
- NLI scoring via `score_statement_distribution` produces `local_score` and entailment/contradiction/neutral probabilities.
- AI statement assessment (`assess_statement_async`) is run with the excerpt as context to populate signals (sentiment, conviction, etc.).

**What is skipped (compared to `source_type: "web"`):**
- Statement/excerpt checks (empty excerpt, same-as-statement, excerpt validity, excerpt-too-similar).
- Context similarity and statement similarity (set to 0 for desearch).
- Domain blacklist check, domain age check, search URL detection.
- Page fetching (HTTP + Selenium) and snippet-in-page verification.
- **Top sites for desearch**: x.com, twitter.com, and reddit.com are always treated as approved (top) sites; **and** any domain in the top-site cache (dashboard) also counts as approved. Approved domains get `approved_url_multiplier` = 3; others get 1. (Web uses only the top-site cache.)

### Step 3: Final Score Calculation (api_server.py)

Snippets are processed in order. For each response with `snippet_found=True`:

1. **Domain diversity factor**  
   - **Desearch only, and domain is x.com, twitter.com, or reddit.com**: `domain_factor = 1` (no duplicate-domain check).
   - **Web, or desearch with any other domain**: For each domain we track how many times it has been used so far in this response. The first snippet from a domain gets no penalty; repeated use of the same domain is discounted:
     - First use of domain: `domain_factor = 1.0`
     - Second use: `domain_factor = 0.5`
     - Third use: `domain_factor = 0.25`
     - Fourth use: `domain_factor = 0.125`
     - etc. (formula: `domain_factor = 1 / 2^times_used`)

2. **Per-snippet score**
   ```
   snippet_score = local_score × domain_factor × approved_url_multiplier
   ```
   `local_score` comes from NLI (entailment + contradiction; see quality model). For **desearch snippets from x.com, twitter.com, or reddit.com**, `domain_factor` is always 1; for **web snippets** and **desearch from other domains**, `domain_factor` = 1 / 2^times_used for that domain. For **desearch**, `approved_url_multiplier` = 3 when the domain is x.com, twitter.com, reddit.com **or** is in the top-site cache; otherwise 1. For **web**, `approved_url_multiplier` is 3 if the domain is on the dashboard top-site list, else 1.

3. **Aggregation**
   ```
   sum_of_snippets = sum of snippet_score over all snippets (including those with snippet_found=False, which contribute 0)
   final_score = (sum_of_snippets × speed_factor) + desearch_adjustment + social_bonus_total
   ```

Where:
- `speed_factor` = miner response time factor (e.g. 1.0 for normal latency).
- `desearch_adjustment` = `+2` if desearch proofs valid, `-5` if any proof invalid, `0` if no desearch proofs provided.
- `social_bonus_total` = sum of per-snippet social bonus **for desearch snippets only and only when desearch proofs are valid**: +1 per snippet from x.com or twitter.com, +0.5 per snippet from reddit.com. Web snippets do not receive social bonus.

The desearch adjustment is additive and independent of the speed factor. The social bonus rewards desearch snippets from social domains (X, Reddit) on top of the base snippet and desearch proof scoring.

---

## Key Design Decisions

1. **Miner-level, not per-snippet**: The desearch proof bonus/penalty is applied once per miner response rather than per snippet. This prevents miners from inflating scores by submitting many desearch snippets, while still rewarding the use of verifiable sources.

2. **Trust desearch URLs, verify URL in body**: Desearch responses are cryptographically signed, so we trust URLs from them (skip blacklist, domain age, SSL, page fetch). We still require the miner's claimed **URL** to appear in at least one signed response body, preventing miners from claiming arbitrary content came from desearch.

3. **NLI and assessment, no excerpt checks**: For desearch we skip statement/excerpt/similarity checks and run only NLI and AI assessment. Snippets are scored on relevance (local_score) and approved_url_multiplier, plus social bonus when applicable.

4. **No duplicate-domain discount for desearch social domains only**: Desearch snippets from x.com, twitter.com, or reddit.com use `domain_factor = 1`. Web snippets (and desearch from other domains) use the domain-diversity penalty (repeated use of the same domain gets 0.5, 0.25, etc.).

---

## Files Changed

| File | Change |
|---|---|
| `shared/scores.py` | `DESEARCH_PROOF_VALID_BONUS` (+2), `DESEARCH_PROOF_INVALID_PENALTY` (-5), `SOCIAL_BONUS_DOMAIN_X` (+1), `SOCIAL_BONUS_DOMAIN_REDDIT` (+0.5) |
| `validator/api_server.py` | Miner-level `desearch_adjustment`; per-snippet `snippet_score = local_score × domain_factor × approved_url_multiplier`; **domain diversity**: **desearch + x.com/twitter.com/reddit.com** use `domain_factor=1`; **web** and **desearch other domains** use first use `domain_factor=1.0`, second `0.5`, etc. (`1/2^times_used`); social bonus only for desearch snippets when proofs valid |
| `validator/snippet_validator.py` | Desearch: evidence-in-body (URL in body); no statement/excerpt/similarity checks; NLI + AI assessment; **top sites for desearch**: x.com, twitter.com, reddit.com or domain in top_site cache get `approved_url_multiplier` = 3; sets `verify_miner_time_taken_secs` in callees via `_with_verify_time` (always set) |
| `shared/veridex_protocol.py` | `desearch` as `List[Desearch]`; `desearch_bonus_score` in response |
