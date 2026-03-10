# dFusion Vericore: Semantic Intelligence for Fact Checking at Scale

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
  - [Setting up a validator or miner](#setting-up-a-validator-or-miner)
  - [Register Wallets](#register-wallets)
- [Scoring Mechanics](#scoring-mechanics)
- [Monitoring and Logging](#monitoring-and-logging)
- [Running a blockchain locally](#running-a-blockchain-locally)
- [Notes and Considerations](#notes-and-considerations)
- [License](#license)

---

## Overview

Vericore is a Bittensor subnet seeking to improve large-scale semantic fact-checking and verification. The subnet processes statements and returns evidence-based validation through relevant quotes and source materials that either support or contradict the input claims.

### Key Features

- **Semantic Analysis**: Processes natural language statements and understands their semantic meaning
- **Source Verification**: Returns precise quotes and segments from sources
- **Dual Validation**: Provides both corroborating and contradicting evidence when available
- **Scale-Oriented**: Designed to incentivize high-volume fact-checking operations
- **Source Attribution**: All returned evidence includes traceable source information

### Use Cases

- Media fact-checking
- Research validation
- Content verification
- Information integrity assessment
- Source validation and cross-referencing

## Project Structure

```
Vericore/
├── docs/
│   ├── desearch-scoring-flow.md            # Desearch scoring and validation flow
│   ├── miner_rejection_and_snippet_reasons.md
│   └── scoring_mechanics_subnet_70.md      # Scoring mechanics documentation
├── keys/
│   └── validator_jwt_public.pem            # JWT public key for API auth
├── miner/
│   ├── desearch/
│   │   └── miner.py                        # Miner implementation using Desearch API
│   ├── perplexica/
│   │   └── miner.py                        # Sample miner using Perplexica
│   └── perplexity/
│       └── miner.py                        # Sample miner using Perplexity
├── shared/
│   ├── blacklisted_domain_cache.py         # Domain blacklist cache
│   ├── debug_util.py                       # Debug utilities
│   ├── desearch_proof.py                   # Desearch proof signature verification
│   ├── environment_variables.py            # Environment variable definitions
│   ├── exceptions.py                       # Shared exception types
│   ├── log_data.py                         # Log settings and format
│   ├── proxy_log_handler.py                # Log handler
│   ├── scores.py                           # Scoring constants (penalties, bonuses)
│   ├── store_results_handler.py            # Results storage handler
│   ├── top_site_cache.py                   # Approved top-site cache
│   ├── validator_results_data.py           # Validator results data models
│   ├── veridex_protocol.py                 # Protocol for comms between Validator and Miner
│   └── wallet_api_key_utils.py             # Wallet-linked API key utilities
├── tests/
│   ├── manual/                             # Manual integration tests
│   └── unit_tests/                         # Automated unit tests
├── utils/
│   ├── generate_wallet_linked_token.py     # Generate wallet-linked JWT tokens
│   ├── link_desearch_miner.py              # Link a miner wallet to Desearch
│   ├── test_desearch_verify.py             # Test Desearch signature verification
│   └── validate_desearch_signature.py      # Validate Desearch API signatures
├── validator/
│   ├── active_tester.py                    # Produces tests for the miners
│   ├── api_server.py                       # API server for receiving statements
│   ├── context_similarity_validator.py     # Context similarity scoring
│   ├── domain_validator.py                 # Domain validation (age, registration)
│   ├── open_ai_client_handler.py           # OpenAI client handler
│   ├── open_ai_proxy_server_handler.py     # OpenAI proxy server handler
│   ├── quality_model.py                    # Measure corroboration/refutation of statements
│   ├── similarity_quality_model.py         # Text similarity quality model
│   ├── snippet_fetcher.py                  # Fetches referenced source material
│   ├── snippet_validator.py                # Snippet validation and scoring
│   ├── statement_context_evaluator.py      # AI-based statement assessment
│   ├── validator_daemon.py                 # Daemon that handles axons / server tasks
│   └── web_page_validator.py               # Web page content validation
└── requirements.txt
```

## Prerequisites

Before you begin, ensure you have the following installed:

- Python 3.10 or higher (Currently 3.13 isn't supported in certain packages)
- [Git](https://git-scm.com/)
- [Bittensor SDK](https://github.com/opentensor/bittensor)
  - Requirements for bittensor sdk includes Rust and Cargo

## Setup Instructions

### Setting up a validator or miner

Instructions for installing and setting up a miner can be found in [Miner Installation](miner/README.md)

Instructions for installing and setting up a validator can be found in [Validator Installation](validator/README.md)

### Register Wallets

Register both the miner and validator on the Bittensor network.

- **Register the Miner**:
  ```bash
  btcli s register --wallet.name mywallet --wallet.hotkey miner_hotkey
  ```

> **Note**: If you're not connecting to the Mainnet, add `ws://127.0.0.1:9944` or specify the name of the network you wish to connect to.

- **Register the Validator**:
  ```bash
  btcli s register --wallet.name mywallet --wallet.hotkey validator_hotkey
  ```

> **Note**: If you're not connecting to the Mainnet, add `ws://127.0.0.1:9944` or specify the name of the network you wish to connect to.

---

## Scoring Mechanics

For detailed information on how miners are scored and ranked in Subnet 70, see the [Scoring Mechanics Documentation](docs/scoring_mechanics_subnet_70.md).

This document covers:

- Individual snippet scoring
- Validation penalties and bonuses
- Moving average system (EWMA)
- Miner ranking for weight distribution
- Emission control
- Advanced AI assessment signals

---

## Monitoring and Logging

Both the miner and validator will output logs to the console and save logs to files in the following directory structure:

```
~/.bittensor/wallets/<wallet.name>/<wallet.hotkey>/netuid<netuid>/<miner or validator>/
```

- **Miner Logs**: Located in the `miner` directory.
- **Validator Logs**: Located in the `validator` directory.

You can monitor these logs to observe the interactions and performance metrics.

---

## Running a blockchain locally

This section is for running a local blockchain. The full tutorial is found here:
[https://github.com/opentensor/bittensor-subnet-template/blob/main/docs/running_on_staging.md](https://github.com/opentensor/bittensor-subnet-template/blob/main/docs/running_on_staging.md)

### Install Substrate dependencies

Update your system packages:

```bash
sudo apt update
```

Install additional required libraries and tools

```bash
sudo apt install --assume-yes make build-essential git clang curl libssl-dev llvm libudev-dev protobuf-compiler
```

### Install Rust and Cargo

### Clone the subtensor repo

This step fetches the subtensor codebase to your local machine.

```bash
git clone https://github.com/opentensor/subtensor.git
```

### Setup Rust

Update to the nightly version of Rust:

```bash
./subtensor/scripts/init.sh
```

### Initialize local subtensor chain into development

First run localnet.sh to build the binary with fast-blocks switched off:

```bash
BUILD_BINARY=1 ./scripts/localnet.sh False
```

> **Note**: You should first go into the subtensor directory before running this command.

**Note**: The --features pow-faucet option in the above is required if we want to use the command btcli wallet faucet See the below Mint tokens step.

Next, run the localnet script with build binary off, no fast block, and to not purge history:

```bash
BUILD_BINARY=0 ./scripts/localnet.sh False --no-purge
```

We are running with fast-block off and using localnet.sh due to the following issues:

[https://github.com/opentensor/bittensor-subnet-template/issues/118#issuecomment-2547474216](https://github.com/opentensor/bittensor-subnet-template/issues/118#issuecomment-2547474216)

[https://github.com/opentensor/bittensor-subnet-template/issues/118#issuecomment-2552609160](https://github.com/opentensor/bittensor-subnet-template/issues/118#issuecomment-2552609160)

**Note**: Watch for any build or initialization outputs in this step. If you are building the project for the first time, this step will take a while to finish building, depending on your hardware.

### Mint tokens from faucet

Minting from the faucet requires torch

```bash
pip install torch
```

Mint faucet tokens for the wallet:

```bash
btcli wallet faucet --wallet.name owner --subtensor.chain_endpoint ws://127.0.0.1:9945
```

Look at localnet.sh to see which ports are running.

---

## Notes and Considerations

TBD

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Feel free to contribute, raise issues, or suggest improvements to this template. Happy mining and validating on the Bittensor network!