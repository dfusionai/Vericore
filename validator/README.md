# Validator Installation

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Setup Instructions](#setup-instructions)
  - [1. Clone the Repository](#1-clone-the-repository)
  - [2. Install Dependencies](#2-install-dependencies)
  - [3. Create Wallets](#3-create-wallets)
  - [4. Register Wallets](#4-register-wallets)
- [Running the Validator](#running-the-validator)
- [Monitoring and Logging](#monitoring-and-logging)
- [License](#license)

---

## Overview
This guide outlines the steps to install and run a Vericore validator on the Bittensor network.


## Prerequisites

Before beginning the setup, ensure you have the following installed:

- Python 3.10 or higher (Note: Python 3.13 is currently not supported by some packages)
- [Git](https://git-scm.com/)
- [Bittensor SDK](https://github.com/opentensor/bittensor)
  - The Bittensor SDK requires **Rust** and **Cargo** (Rust's package manager).

## Setup Instructions

### 1. Clone the Repository

Clone this repository to your local machine:

```bash
git clone git@github.com:dfusionai/Vericore.git
cd Vericore
```

### 2. Install Dependencies

Install the necessary Python packages:

> **Note**: It's recommended to use a virtual environment to manage dependencies.
>
#### Rust and Cargo

Bittensor relies on Rust, and Cargo is the Rust package manager. To install them:


```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Ensure Cargo is available by adding it to your shell’s path:
```bash
source "$HOME/.cargo/env"
```

#### Bittensor Cli

```bash
pip install bittensor
```

### 3. Create Wallets

You'll need to create wallets for the validator.

#### Using `btcli`

The `btcli` tool is used to manage wallets and keys.

1. **Create a Coldkey**

   ```bash
   btcli w new_coldkey --wallet.name mywallet
   ```

2. **Create a Hotkeys**:

     ```bash
     btcli w new_hotkey --wallet.name mywallet --wallet.hotkey validator_hotkey
     ```

### 4. Register Wallets

Register the validator wallet on the Bittensor network.

- **Register the Validator**:

  ```bash
  btcli s register --wallet.name mywallet --wallet.hotkey validator_hotkey --netuid 70
  ```

> **Note**: If you're not connecting to the Mainnet, use the following to specify a different network:
> ```bash
>  --subtensor.chain_endpoint ws://127.0.0.1:9944`
>  ```
---

## Running the Validator

You'll need to run both the server and the daemon. Ensure you're executing the following commands in the same directory.

### Hardware Requirements
- At least **24 GB GPU**, **16 GB RAM**, and **250 GB storage** are recommended.
- Expose **port 8080** for HTTP traffic.

### Server:

```bash
python -m validator.api_server --wallet.name bittensor --wallet.hotkey validator_hotkey  --netuid 70 --axon.ip=<EXTERNAL_IP>
```

**Arguments**:

- `--wallet.name`: The name of the wallet.
- `--wallet.hotkey`: The hotkey name for the validator.
- `--axon.ip`: The external ip address of the validator


> **Note**: If you're not connecting to the Mainnet, use the following to specify a different network:
> ```bash
>  --subtensor.network ws://127.0.0.1:9944
>  ```

### Daemon:
```bash
python -m validator.validator_daemon --wallet.name bittensor --wallet.hotkey validator_hotkey --netuid 70
```

> **Note**: If you're not connecting to the Mainnet, use the following to specify a different network:
> ```bash
>  --subtensor.network ws://127.0.0.1:9944
>  ```

**Arguments**:

- `--wallet.name`: The name of the wallet.
- `--wallet.hotkey`: The hotkey name for the validator.
- `--subtensor.network`: The Bittensor network to connect to.

---

## Monitoring and Logging

The validator will output logs to the console and save logs to files in the following directory structure:

```
~/.bittensor/wallets/<wallet.name>/<wallet.hotkey>/netuid<netuid>/<validator>/
```

- **Validator Logs**: Located in the `validator` directory.

You can monitor these logs to observe the interactions and performance metrics.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

Feel free to contribute, raise issues, or suggest improvements to this template. Happy mining and validating on the Bittensor network!
