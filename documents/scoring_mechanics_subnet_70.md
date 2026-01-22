# Subnet 70 (Vericore) Scoring Mechanics for Miners

## Overview

Subnet 70, known as Vericore, is a Bittensor subnet focused on semantic fact-checking and verification at scale. Miners in this subnet process natural language statements and provide evidence-based validation through relevant quotes and source materials that either support or contradict the input claims.

This document outlines the comprehensive scoring system used to evaluate miner performance and distribute rewards.

## Scoring Components

### 1. Individual Snippet Scoring

Each miner response consists of multiple snippets (evidence pieces) that are individually scored. The scoring is based on several factors:

#### Quality Model Scoring (Local Score)
- **Model**: RoBERTa Large MNLI (Multi-Genre Natural Language Inference)
- **Purpose**: Determines whether a snippet corroborates, contradicts, or is neutral to the input statement
- **Output**: Probability distribution across three categories:
  - `contradiction`: Probability the snippet contradicts the statement
  - `neutral`: Probability the snippet is neutral/indeterminate
  - `entailment`: Probability the snippet supports/entails the statement

- **Local Score Formula**: `local_score = contradiction + entailment`
  - Neutral probability is intentionally excluded to penalize ambiguous responses
  - Higher scores indicate stronger evidence (either supporting or contradicting)

#### Validation Penalties and Bonuses

Miners receive penalties for various validation failures:

| Penalty Type | Score | Description |
|-------------|--------|-------------|
| Unreachable Miner | -10 | Miner fails to respond |
| No Statements Provided | -5 | Miner provides empty response |
| Invalid Response | -10 | Malformed or corrupted response |
| Non-HTTPS URL | -2 | Evidence URL doesn't use HTTPS protocol |
| Blacklisted Domain | -5 | Evidence comes from blacklisted domain |
| Snippet Not Found in URL | -1 | Provided snippet doesn't exist in the referenced webpage |
| Context Too Similar | -5 | Snippet is too similar to the original statement |
| Using Search as Evidence | -5 | Evidence URL appears to be from a search engine |
| Fake Snippet | -5 | Snippet is determined to be fabricated |
| Unrelated Page Snippet | 0 | Snippet content unrelated to statement (not penalized) |
| Invalid Snippet Excerpt | -5 | Snippet is too short (< 5 words) or malformed |
| Search Web Page | -5 | Evidence URL is a search results page |
| Duplicate Exact Statements | 0 | Multiple miners provide identical statements |

#### Validation Bonuses

| Bonus Type | Multiplier | Description |
|------------|------------|-------------|
| Approved URL Multiplier | 3x | Evidence comes from pre-approved, high-quality domains |

### 2. Miner Response Aggregation

For each miner response containing multiple snippets:

1. **Individual Snippet Validation**: Each snippet undergoes the validation process above
2. **Snippet Score Calculation**: `snippet_score = local_score + penalties + bonuses`
3. **Response Aggregation**: Final miner score combines all valid snippets

#### Final Score Calculation

For each miner response, the scoring process is:

1. **Process up to 5 snippets** (MAX_MINER_RESPONSES = 5)
2. **Individual snippet scoring**: Each snippet gets validated and scored
3. **Domain deduplication**: Penalize repeated use of same domain within response
4. **Speed factor application**: Response time bonus/penalty
5. **Final aggregation**: Combine all factors into final_score

**Formula per miner:**
```
# Step 1: Individual snippet scoring
snippet_score = local_score × domain_factor × approved_url_multiplier

# Step 2: Domain deduplication (prevents gaming with same source)
domain_factor = 1.0 / (2^(times_used - 1))  # First use = 1.0, second = 0.5, third = 0.25, etc.

# Step 3: Sum all valid snippet scores
sum_of_snippets = Σ(snippet_score for all valid snippets)

# Step 4: Apply speed factor
speed_factor = max(1, 2.0 - (response_time_seconds / 30.0))

# Step 5: Final score for ranking
final_score = sum_of_snippets × speed_factor
```

**Speed Factor Details:**
- Response time ≤ 30 seconds: factor = 2.0 - (time/30)
- Response time > 30 seconds: factor = 1.0 (minimum)
- Faster responses get higher multipliers, slower responses get neutral scoring

## Moving Average Scoring System

Subnet 70 uses a sophisticated moving average system to ensure stable and fair scoring:

### Immunity Period (New Miner Protection)

New miners receive special treatment for their first 100 responses:

- **Immunity Weight**: 0.5 (50% weight on new scores)
- **Protection Period**: 100 requests
- **Formula**: `calculated_score = previous_score × (1 - 0.5) + new_score × 0.5`

This ensures new miners have time to prove themselves without being immediately penalized for initial poor performance.

### Established Miner Scoring

After the immunity period:

- **Initial Weight**: 0.7 (70% weight on previous scores)
- **Formula**: `calculated_score = previous_score × 0.7 + new_score × 0.3`

This creates a stable scoring system that rewards consistent performance while allowing for gradual improvement or decline.

## Miner Ranking for Weight Distribution

### How Miners Are Ranked

1. **Individual Performance**: Each miner gets a `final_score` per request based on their response quality and speed
2. **Moving Average**: Each miner's historical performance is tracked using exponential moving averages
3. **Ranking Basis**: Miners are ranked by their **moving average score** (not individual request scores)

### Ranking-Based Weight Distribution

Subnet 70 uses a ranking-based geometric progression for weight distribution:

1. **Top Ranked Miner** (by moving average): Receives 50% of total weight allocation
2. **Second Ranked Miner**: Receives 25% of total weight allocation
3. **Third Ranked Miner**: Receives 12.5% of total weight allocation
4. **Subsequent Ranked Miners**: Each receives half the weight of the previous rank

**Example Weight Distribution:**
```
Rank 1 (Best performer): 50% of total weight
Rank 2: 25% of total weight
Rank 3: 12.5% of total weight
Rank 4: 6.25% of total weight
Rank 5: 3.125% of total weight
...
```

**Key Point**: Ranking is based on **long-term moving average performance**, not single request scores. This ensures stability and prevents gaming through occasional high scores.

### Emission Control

The subnet implements emission control mechanisms:

- **Emission Control Percentage**: 50% of total emissions
- **Target UID**: Reserved for emission control (burn miner)
- **Distribution**: Remaining 50% distributed among active miners based on ranking

### Validator Exclusion

Validators are completely excluded from weight distribution to prevent conflicts of interest.

## Additional Scoring Signals

Beyond basic validation, the system incorporates advanced AI assessment signals:

### Statement Context Assessment

Each snippet undergoes comprehensive analysis providing:

- **Sentiment**: Emotional tone of the evidence (-1.0 to 1.0)
- **Conviction**: Confidence level in the evidence (0.0 to 1.0)
- **Source Credibility**: Perceived reliability of the source (0.0 to 1.0)
- **Narrative Momentum**: How the evidence fits into broader context (0.0 to 1.0)
- **Risk-Reward Sentiment**: Risk assessment of the information (0.0 to 1.0)
- **Catalyst Detection**: Whether the evidence represents significant new information (0.0 to 1.0)
- **Political Leaning**: Political orientation of the content (-1.0 left-leaning to 1.0 right-leaning)

### Performance Metrics

- **Speed Factor**: Bonus for faster response times
- **Context Similarity Score**: Semantic relevance measurement
- **Domain Registration Check**: Penalty for recently registered domains (< 30 days)

## Complete Scoring and Ranking Flow

### Per Request Scoring → Moving Average → Ranking → Weight Distribution

1. **Individual Request Processing**:
   - Miner submits up to 5 evidence snippets
   - Each snippet validated (authenticity, relevance, source quality)
   - ML model scores semantic quality (corroboration/contradiction)
   - Domain deduplication prevents source repetition
   - Speed factor rewards fast, accurate responses
   - **Result**: `final_score` per request

2. **Historical Performance Tracking**:
   - New miners: 100-request immunity period with 50% weight on new scores
   - Established miners: 70% weight on history + 30% on new performance
   - **Result**: Moving average score per miner

3. **Miner Ranking**:
   - All miners sorted by their moving average scores (highest to lowest)
   - Validators excluded from ranking
   - **Result**: Ranked list of miners by long-term performance

4. **Weight Distribution**:
   - Top ranked miner: 50% of total weight (65,535)
   - Each subsequent rank: Half the weight of previous rank
   - Weights converted to integers and set on blockchain
   - **Result**: Emission distribution proportional to ranking

### Why This System Works

- **Stability**: Moving averages prevent score volatility
- **Fairness**: New miners get time to prove themselves
- **Quality Incentives**: Rewards accuracy over speed gaming
- **Anti-Gaming**: Domain deduplication, source validation, semantic analysis
- **Scalability**: Automated ML-based evaluation at scale

## Key Design Principles

### Fairness
- Immunity period protects new miners
- Moving averages prevent score volatility
- Comprehensive validation prevents gaming

### Quality Incentives
- Rewards accurate, relevant evidence
- Penalizes fabricated or low-quality responses
- Bonuses for authoritative sources

### Stability
- Exponential moving averages ensure gradual score changes
- Emission control prevents extreme reward concentration
- Multi-factor validation reduces manipulation risks

### Scalability
- Automated ML-based quality assessment
- Batch processing capabilities
- Distributed validation across multiple validators

## Monitoring and Analytics

The system provides comprehensive tracking:

- **Real-time Scoring**: Live score updates per request
- **Historical Tracking**: Moving average progression over time
- **Performance Analytics**: Response times, validation success rates
- **Weight Distribution Logs**: Complete audit trail of emission allocation

This scoring system ensures that subnet 70 miners are incentivized to provide high-quality, verifiable evidence while maintaining network stability and preventing various forms of gaming or manipulation.
