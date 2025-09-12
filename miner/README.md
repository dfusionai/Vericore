# Sample Miner Installation

## Table of Contents
- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Install Dependencies](#2-install-dependencies)
  - [3. Create Wallets](#3-create-wallets)
  - [4. Register Wallets](#4-register-wallets)
  - [5. Additional Requirements](#5-additional-requirements)
    - [Perplexity](#perplexicity-miner)
    - [Perplexica](#perplexica-miner)
- [Running the Miner](#running-the-miner)
- [Monitoring and Logging](#monitoring-and-logging)
- [License](#license)

---

## Overview

## Overview

This guide outlines the installation process for a Vericore miner.

Two sample miners are provided:

- **Perplexity Naive Miner** – Integrated with [Perplexity](https://www.perplexity.ai/)
- **Perplexica Naive Miner** – Integrated with [Perplexica](https://github.com/ItzCrazyKns/Perplexica)

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
pip install bittensor-cli
```

### 3. Create Wallets

You'll need to create wallets for the miner.

#### Using `btcli`

The `btcli` tool is used to manage wallets and keys.

1. **Create a Coldkey** (can be shared between miner and validator):

   ```bash
   btcli w new_coldkey --wallet.name mywallet
   ```

2. **Create Hotkeys**:

   - **Miner Hotkey**:

     ```bash
     btcli w new_hotkey --wallet.name mywallet --wallet.hotkey miner_hotkey
     ```

### 4. Register Wallets

Register the miner on the Bittensor network.

- **Register the Miner**:

  ```bash
  btcli s register --wallet.name mywallet --wallet.hotkey miner_hotkey  --netuid 70
  ```

> **Note**: If you're not connecting to the Mainnet, use the following to specify a different network:
> ```bash
>  --subtensor.chain_endpoint ws://127.0.0.1:9944`
>  ```

### 5. Additional Requirements

#### Perplexity Miner

**Perplexity** can be used to fetch the required information from the subnet. To use this miner, set the Perplexity API Key as an environment variable:

```sh
export PERPLEXITY_API_KEY=<your_api_key>
```

or on Windows

```powershell
$env:PERPLEXITY_API_KEY="<your_api_key>"
```

#### Perplexica Miner

**Perplexica** is a required dependency for this Perplexica Miner. It must be installed locally before use.

##### Installation
Follow the installation instructions provided in the Perplexica repository:

➡ [Installation Guide](https://github.com/ItzCrazyKns/Perplexica/blob/master/README.md#installation)

##### Search Engine Endpoint
The search engine endpoint is used to fetch the required information. More details can be found here:

➡ [Search API Documentation](https://github.com/ItzCrazyKns/Perplexica/blob/master/docs/API/SEARCH.md)

##### Configuration
Set the Perplexica URL in your environment variables as follows:

```sh
export PERPLEXICA_URL=<your_perplexica_url>
```

or on Windows

```powershell
$env:PERPLEXICA_URL="<your_perplexica_url>"
```

## Running the Miner

In one terminal window, navigate to the project directory and run:

```bash
python -m miner.perplexity.miner --wallet.name bittensor --wallet.hotkey miner_hotkey --axon.ip=<EXTERNAL_IP> --axon.port 8901 --netuid 70
```
> **Note**: If you're not connecting to the Mainnet, use the following to specify a different network:
> ```bash
>  --subtensor.network ws://127.0.0.1:9944`
>  ```


**Arguments**:

- `--wallet.name`: The name of the wallet.
- `--wallet.hotkey`: The hotkey name for the miner.
- `--subtensor.network`: The Bittensor network to connect to.
- `--axon.ip`: The external ip address of the miner

## Monitoring and Logging

The miner will output logs to the console and save logs to files in the following directory structure:

```
~/.bittensor/wallets/<wallet.name>/<wallet.hotkey>/netuid<netuid>/miner/
```

- **Miner Logs**: Located in the `miner` directory.

You can monitor these logs to observe the interactions and performance metrics.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Feel free to contribute, raise issues, or suggest improvements to this template. Happy mining and validating on the Bittensor network!
