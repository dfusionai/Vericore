# dFusion Vericore: Semantic Intelligence for Fact Checking at Scale

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Install Dependencies](#2-install-dependencies)
  - [3. Create Wallets](#3-create-wallets)
  - [4. Register Wallets](#4-register-wallets)
- [Running the Miner and Validator](#running-the-miner-and-validator)
  - [Running the Miner](#running-the-miner)
  - [Running the Validator](#running-the-validator)
- [Monitoring and Logging](#monitoring-and-logging)
- [Customization](#customization)
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
├── miner/
    ├── perplexity/
        └── miner.py         # Sample implementation of a naive miner using Perplexity
├── shared/
    ├── log_data.py          # Log settings and format
    ├── proxy_log_handler.py # Log handler
    └── veridex_protocol.py  # Protocol for comms between Validator and Miner
└── validator
    ├── active_tester.py     # Produces tests for the miners
    ├── api_server.py        # Api Server for receiving statements as input
    ├── domain_validator.py  # Handles domain validation
    ├── quality_model.py     # Measure Corroboration or Refutation of statements
    ├── snippet_fetcher.py   # Fetches referenced source material for validation
    ├── validator_daemon.py  # Daemon that handles axons / server tasks
    └── verify_context_quality_model.py
```

## Prerequisites

Before you begin, ensure you have the following installed:

- Python 3.10 or higher (Currently 3.13 isn't supported in certain packages)
- [Git](https://git-scm.com/)
- [Bittensor SDK](https://github.com/opentensor/bittensor)
  - Requirements for bittensor sdk includes Rust and Cargo

## Setup Instructions

### 1. Clone the Repository

Clone this repository to your local machine:

```bash
git clone git@github.com:dfusionai/Vericore.git
cd Vericore
```

### 2. Install Dependencies

Install the required Python packages:

> **Note**: It's recommended to use a virtual environment to manage dependencies.
>
#### Rust and Cargo

Rust is the programming language used in Substrate development. Cargo is Rust package manager.

Install rust and cargo:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Update your shell's source to include Cargo's path:
```bash
source "$HOME/.cargo/env"
```

#### Bittensor Cli

```bash
pip install bittensor
```

### 3. Running a blockchain locally

This section is for running a local blockchain. The full tutorial is found here:
https://github.com/opentensor/bittensor-subnet-template/blob/main/docs/running_on_staging.md

#### Install Substrate dependencies

Update your system packages:

```bash
sudo apt update
```

Install additional required libraries and tools

```bash
sudo apt install --assume-yes make build-essential git clang curl libssl-dev llvm libudev-dev protobuf-compiler
```

#### Install Rust and Cargo

#### Clone the subtensor repo

This step fetches the subtensor codebase to your local machine.

```bash
git clone https://github.com/opentensor/subtensor.git
```

#### Setup Rust

Update to the nightly version of Rust:

```bash
./subtensor/scripts/init.sh
```

#### Initialize local subtensor chain into development

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
https://github.com/opentensor/bittensor-subnet-template/issues/118#issuecomment-2547474216
https://github.com/opentensor/bittensor-subnet-template/issues/118#issuecomment-2552609160

**Note**: Watch for any build or initialization outputs in this step. If you are building the project for the first time, this step will take a while to finish building, depending on your hardware.


#### Mint tokens from faucet

Minting from the faucet requires torch

```bash
pip install torch
```

Mint faucet tokens for the wallet:

```bash
btcli wallet faucet --wallet.name owner --subtensor.chain_endpoint ws://127.0.0.1:9945
```

Look at localnet.sh to see which ports are running.


### 4. Create Wallets

You'll need to create wallets for both the miner and validator.

#### Using `btcli`

The `btcli` tool is used to manage wallets and keys.

1. **Create a Coldkey** (shared between miner and validator):

   ```bash
   btcli w new_coldkey --wallet.name mywallet
   ```

2. **Create Hotkeys**:

   - **Miner Hotkey**:

     ```bash
     btcli w new_hotkey --wallet.name mywallet --wallet.hotkey miner_hotkey
     ```

   - **Validator Hotkey**:

     ```bash
     btcli w new_hotkey --wallet.name mywallet --wallet.hotkey validator_hotkey
     ```

### 4. Create a subnet

The below commands establish a new subnet on the local chain. The cost will be exactly τ1000.000000000 for the first subnet you create and you'll have to run the faucet several times to get enough tokens.

  ```bash
		 btcli subnet create --wallet.name owner --subtensor.chain_endpoint
  ```

> **Note**: If you're not connecting to the Mainnet, add `ws://127.0.0.1:9944` or specify the name of the network you wish to connect to.

### 4. Register Wallets

Register both the miner and validator on the Bittensor network.

- **Register the Miner**:

  ```bash
  btcli s register --wallet.name mywallet --wallet.hotkey miner_hotkey --subtensor.chain_endpoint
  ```

> **Note**: If you're not connecting to the Mainnet, add `ws://127.0.0.1:9944` or specify the name of the network you wish to connect to.

- **Register the Validator**:

  ```bash
  btcli s register --wallet.name mywallet --wallet.hotkey validator_hotkey
  ```

> **Note**: If you're not connecting to the Mainnet, add `ws://127.0.0.1:9944` or specify the name of the network you wish to connect to.

---


## Running the Miner and Validator

### Running the Miner

In one terminal window, navigate to the project directory and run:

```bash
python -m miner.perplexity.miner --wallet.name bittensor --wallet.hotkey miner_hotkey --axon.port 8901 --netuid 70
```

> **Note**: If you're not connecting to the Mainnet, add `ws://127.0.0.1:9944` or specify the name of the network you wish to connect to.


**Arguments**:

- `--wallet.name`: The name of the wallet.
- `--wallet.hotkey`: The hotkey name for the miner.
- `--subtensor.network`: The Bittensor network to connect to.

### Running the Validator

You'll need to run both the server and the daemon. You'll want to make sure to execute these scripts from the same directory. We recommend at least 24 GB GPU, 16 GB RAM, and 250GB storage. You'll also want to additionally expose port 8080 for http traffic.

#### Server:

```bash
python -m validator.api_server --wallet.name bittensor --wallet.hotkey validator_hotkey  --netuid 70
```

> **Note**: If you're not connecting to the Mainnet, add `ws://127.0.0.1:9944` or specify the name of the network you wish to connect to.

#### Daemon:
```bash
python -m validator.validator_daemon --wallet.name bittensor --wallet.hotkey validator_hotkey --subtensor.network ws://127.0.0.1:9944  --netuid 70
```

> **Note**: If you're not connecting to the Mainnet, add `ws://127.0.0.1:9944` or specify the name of the network you wish to connect to.

**Arguments**:

- `--wallet.name`: The name of the wallet.
- `--wallet.hotkey`: The hotkey name for the validator.
- `--subtensor.network`: The Bittensor network to connect to.

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

## Notes and Considerations

TBD

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Feel free to contribute, raise issues, or suggest improvements to this template. Happy mining and validating on the Bittensor network!
