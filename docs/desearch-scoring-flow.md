# Desearch Scoring & Validation Flow

## Overview

Desearch proof validation and snippet scoring has been refactored into two distinct layers:

1. **Miner-level** -- a single bonus or penalty applied once per miner response based on whether the desearch proofs are valid.
2. **Snippet-level** -- each snippet with `source_type: "desearch"` skips URL/page-fetch checks (trusting desearch-provided URLs) but still undergoes quality checks and must prove its URL and excerpt exist in the desearch response body.

---

## Constants (`shared/scores.py`)

| Constant | Value | Scope | Description |
|---|---|---|---|
| `DESEARCH_PROOF_VALID_BONUS` | +2 | Miner | Added to final score when all desearch proofs verify successfully |
| `DESEARCH_PROOF_INVALID_PENALTY` | -5 | Miner | Added to final score when any desearch proof fails verification |
| `SOCIAL_BONUS_DOMAIN_X` | +1 | Per desearch snippet | Added per desearch snippet when domain is x.com or twitter.com |
| `SOCIAL_BONUS_DOMAIN_REDDIT` | +0.5 | Per desearch snippet | Added per desearch snippet when domain is reddit.com |

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
   (URL checks,      (URL + excerpt must
    page fetch,       appear in desearch
    snippet-in-page,  response body)
    AI assessment)          |
         |           +-----+------+
         |           |            |
         |        Not found     Found
         |           |            |
         |           v            v
         |     Score: 0       Quality checks only:
         |     reason:        - excerpt not empty
         |     "desearch_     - excerpt != statement
         |      evidence_     - excerpt validity (5+ words)
         |      not_in_       - similarity to statement
         |      response"     - context similarity
         |                    - NLI scoring (entailment/
         |                      contradiction/neutral)
         |                          |
         |                          v
         |                    snippet_found=True
         |                    local_score from NLI
         |                    approved_url_multiplier=1
         |                    (no page fetch, no AI assessment)
         |                          |
         +------------+-------------+
                      |
                      v
         Per-snippet scores aggregated into sum_of_snippets
                      |
                      v
         Social bonus (desearch snippets only, and only when proofs valid): x.com/twitter.com → +1, reddit.com → +0.5
         Summed into social_bonus_total
                      |
                      v
         final_score = (sum_of_snippets * speed_factor) + desearch_adjustment + social_bonus_total
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
- The snippet's URL must be found in at least one of the decoded desearch response bodies (`_evidence_in_desearch_response`); the excerpt is not checked.
- Excerpt is not empty (`NO_SNIPPET_PROVIDED`, score: -5).
- Excerpt is not identical to the original statement (`SNIPPET_SAME_AS_STATEMENT`, score: -10).
- Excerpt passes validity check -- at least 5 words (`INVALID_SNIPPET_EXCERPT`, score: -5).
- Excerpt is not too semantically similar to the statement (`EXCERPT_TOO_SIMILAR`, score: -5).
- Context similarity score is computed (statement vs excerpt).
- NLI scoring via `score_statement_distribution` produces `local_score` and entailment/contradiction/neutral probabilities.

**What is skipped (compared to `source_type: "web"`):**
- SSL / HTTPS enforcement
- Domain blacklist check
- Domain age check (recently registered)
- Search URL detection (query params, `/search/` path)
- Page fetching (HTTP + Selenium)
- Snippet-in-page verification (fuzzy matching against fetched page text)
- Approved URL multiplier (hardcoded to 1 for desearch)

**What is run (same as web for signal values):**
- AI statement assessment (`assess_statement_async`) is called with the excerpt as webpage context (no full page fetch), so desearch snippets get the same signal fields: sentiment, conviction, source_credibility, narrative_momentum, risk_reward_sentiment, catalyst_detection, political_leaning, and `assess_statement_time_taken_secs` is populated.

### Step 3: Final Score Calculation (api_server.py)

```
final_score = (sum_of_snippets * speed_factor) + desearch_adjustment + social_bonus_total
```

Where:
- `sum_of_snippets` = sum of all per-snippet scores (including domain diversity factor)
- `speed_factor` = miner response time factor
- `desearch_adjustment` = `+2` if proofs valid, `-5` if proofs invalid, `0` if no desearch proofs provided
- `social_bonus_total` = sum of per-snippet social bonus **for desearch snippets only and only when desearch proofs are valid**: +1 per snippet from x.com or twitter.com, +0.5 per snippet from reddit.com; web snippets do not receive social bonus. If proofs are invalid or absent, no social bonus is applied.

The desearch adjustment is additive and independent of the speed factor -- it rewards miners for providing cryptographically verifiable evidence or penalizes them for submitting invalid proofs. The social bonus rewards desearch snippets from social domains (X, Reddit) on top of the base snippet and desearch proof scoring.

---

## Key Design Decisions

1. **Miner-level, not per-snippet**: The desearch proof bonus/penalty is applied once per miner response rather than per snippet. This prevents miners from inflating scores by submitting many desearch snippets, while still rewarding the use of verifiable sources.

2. **Trust desearch URLs, verify content**: Since desearch responses are cryptographically signed by the Desearch API, we trust that the URLs within them are legitimate (skip blacklist, domain age, SSL, page fetch). However, we still verify that the miner's claimed URL and excerpt actually appear in the signed response body -- preventing miners from submitting arbitrary content and claiming it came from desearch.

3. **Quality checks still apply**: Even with trusted URLs, snippet quality checks (empty excerpt, same-as-statement, excerpt validity, similarity, NLI scoring) still run. This ensures desearch snippets are scored on their relevance and quality, not just their provenance.

---

## Files Changed

| File | Change |
|---|---|
| `shared/scores.py` | Replaced `DESEARCH_SNIPPET_BONUS`, `DESEARCH_PROOF_INVALID`, `DESEARCH_PROOF_EXPIRED` with `DESEARCH_PROOF_VALID_BONUS` (+2) and `DESEARCH_PROOF_INVALID_PENALTY` (-5) |
| `validator/api_server.py` | Removed per-snippet desearch bonus from scoring loop; added miner-level `desearch_adjustment` to final score; removed `desearch_proof_valid` from snippet task calls |
| `validator/snippet_validator.py` | Removed `desearch_proof_valid` parameter; replaced short-circuit return with evidence-in-body check followed by full quality checks; removed `DESEARCH_SNIPPET_BONUS` usage |
| `shared/veridex_protocol.py` | Renamed `desearch_bonus` to `desearch_bonus_score`; updated to `Optional[List[Desearch]]` default |
