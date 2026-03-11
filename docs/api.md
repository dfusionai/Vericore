# Validator API

HTTP API for the Vericore validator. The server runs by default on **port 8080**.

**Base URL:** `http://<validator_host>:8080`

---

## Authentication

All endpoints except **GET /version** and **OPTIONS** (CORS preflight) require a valid JWT in the `Authorization` header:

```
Authorization: Bearer <token>
```

- **Algorithm:** RS512 (configurable via `VALIDATOR_JWT_ALGORITHM`).
- **Expected claim:** `sub` = `"validator_proxy"`.
- **401** — Missing/invalid token or wrong `sub`.
- **503** — Server not configured (no JWT public key).

`GET /version` does not require authentication.

---

## Endpoints

### GET /version

Returns the validator version string (e.g. `v0.0.43.5`). No request body. No auth required.

**Response:** Plain text or JSON (version string).

**Example:**
```http
GET /version
```

---

### POST /veridex_query

Runs a Veridex query: sends the statement to miners, validates snippets, and returns aggregated results.

**Request**

- **Content-Type:** `application/json`
- **Body:**

| Field        | Type     | Required | Description |
|-------------|----------|----------|-------------|
| `statement` | string   | Yes      | The claim/statement to verify. |
| `sources`   | string[] | No       | Optional preferred sources or references. Default: `[]`. |
| `request_id` | string | No       | Client-provided request ID. If omitted, server generates one. |

**Example:**
```json
{
  "statement": "Bitcoin price exceeded $100k in 2024.",
  "sources": [],
  "request_id": "my-req-001"
}
```

**Response**

- **200** — JSON object (see **VericoreQueryResponse** below).
- **400** — Invalid JSON or missing `statement`.

**VericoreQueryResponse** (top level)

| Field | Type | Description |
|-------|------|-------------|
| `validator_hotkey` | string | Validator hotkey SS58. |
| `validator_uid` | int | Validator UID on subnet. |
| `status` | string | `"ok"`. |
| `request_id` | string | Echo of request ID or generated. |
| `statement` | string | Echo of statement. |
| `sources` | list | Echo of sources. |
| `timestamp` | float | Unix timestamp when response was finalized. |
| `total_elapsed_time` | float | Total request duration (seconds). |
| `results` | array | One **VericoreMinerStatementResponse** per miner. |
| `total_fetch_time_secs` | float | Sum of miner fetch times. |
| `total_ai_time_secs` | float | Sum of miner AI times. |
| `total_other_time_secs` | float | Sum of other times. |
| `avg_snippet_time_secs` | float | Mean snippet validation time. |
| `max_snippet_time_secs` | float | Max snippet validation time. |
| `total_snippet_count` | int | Total snippets across all miners. |
| `miner_count` | int | Number of miners in `results`. |
| `timing` | object | **QueryResponseTiming** — same stats in one nested object. |

**VericoreMinerStatementResponse** (each item in `results`)

| Field | Type | Description |
|-------|------|-------------|
| `miner_hotkey` | string | Miner hotkey SS58. |
| `miner_uid` | int | Miner UID. |
| `status` | string | Miner outcome: `ok`, `unreachable_miner`, `no_response`, `no_statements_provided`, `error`, `duplicate_miner_statements`, `desearch_proof_missing`, `desearch_proof_incomplete`, etc. |
| `vericore_responses` | array | One **VericoreStatementResponse** per snippet. |
| `speed_factor` | float | Speed component of score. |
| `raw_score` | float | Content score before speed. |
| `final_score` | float | Total score for this miner. |
| `elapsed_time` | float | Miner response time (seconds). |
| `total_fetch_time_secs`, `total_ai_time_secs`, `total_other_time_secs` | float | Aggregated timing. |
| `avg_snippet_time_secs`, `max_snippet_time_secs` | float | Snippet timing. |
| `snippet_count` | int | Number of snippets. |
| `timing` | object | **MinerResponseTiming** — same stats in one nested object. |
| `desearch_bonus_score` | float | +2 if all Desearch proofs valid, -5 if any invalid, 0 if no Desearch. |
| `social_bonus_score` | float | Sum of per-snippet social bonus (desearch only: x.com/twitter +1, reddit +0.5). |

**VericoreStatementResponse** (each item in `vericore_responses`)

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | Snippet URL. |
| `excerpt` | string | Snippet text. |
| `domain` | string | Extracted domain. |
| `snippet_found` | bool | Whether snippet was verified on page (or in Desearch body). |
| `local_score`, `snippet_score` | float | Per-snippet scores. |
| `snippet_score_reason` | string | Reason code (e.g. `blacklisted_url`, `desearch_evidence_not_in_response`, `snippet_not_verified_in_url`). See [miner_rejection_and_snippet_reasons.md](miner_rejection_and_snippet_reasons.md). |
| `rejection_reason` | string | Optional AI/free-text reason. |
| `category` | string | `"Web"` or `"Social"` (Social = x.com, twitter.com, reddit.com). |
| `social_bonus_contribution` | float | This snippet’s contribution to miner `social_bonus_score` (0, 0.5, or 1.0). |
| `contradiction`, `neutral`, `entailment` | float | NLI probabilities. |
| `timing` | object | **StatementResponseTiming** — per-snippet timing and fetcher status. |
| *(other)* | | Legacy timing fields, assessment_result, sentiment, etc. |

**Example response (minimal):**
```json
{
  "validator_hotkey": "5F3sa2T...",
  "validator_uid": 0,
  "status": "ok",
  "request_id": "my-req-001",
  "statement": "Bitcoin price exceeded $100k in 2024.",
  "sources": [],
  "timestamp": 1234567890.123,
  "total_elapsed_time": 12.5,
  "results": [
    {
      "miner_hotkey": "5Grwva...",
      "miner_uid": 1,
      "status": "ok",
      "vericore_responses": [
        {
          "url": "https://example.com/article",
          "excerpt": "Bitcoin reached...",
          "domain": "example.com",
          "snippet_found": true,
          "snippet_score_reason": "",
          "category": "Web",
          "social_bonus_contribution": 0.0
        }
      ],
      "final_score": 2.5,
      "desearch_bonus_score": 0.0,
      "social_bonus_score": 0.0
    }
  ],
  "miner_count": 1,
  "total_snippet_count": 1
}
```

---

## CORS

The server allows all origins (`*`), credentials, methods, and headers. OPTIONS preflight requests are not authenticated.

---

## References

- Miner-level and snippet-level status/reason values: [miner_rejection_and_snippet_reasons.md](miner_rejection_and_snippet_reasons.md)
- Scoring and Desearch flow: [desearch-scoring-flow.md](desearch-scoring-flow.md)
- Protocol types: `shared/veridex_protocol.py`
