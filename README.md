# AI Content Pipeline Starter

[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://github.com/nothingser0/ai-content-pipeline-starter/pkgs/container/ai-content-pipeline-starter)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A production-grade, modular AI content generation and scheduling starter kit for multiple social media accounts (X / Twitter). Built with Clean Architecture, automated weekly rotation, Jaccard deduplication, self-healing QC autofix, Buffer GraphQL integration, and a low-footprint Docker scheduler daemon (<10MB RAM).

---

## 📌 Table of Contents
- [Features](#-features)
- [Project Architecture](#-project-architecture)
- [Prerequisites](#-prerequisites)
- [Quick Start](#-quick-start)
  - [1. Docker Compose (Recommended)](#1-docker-compose-recommended)
  - [2. Local Python Environment](#2-local-python-environment)
- [CLI Cheatsheet](#-cli-cheatsheet)
- [Adding New Accounts](#-adding-new-accounts)
- [Environment Configuration](#-environment-configuration-env)
- [License](#-license)

---

## ✨ Features

- **Multi-Account & Persona Architecture**: Easily manage dozens of accounts with individual personas, niche focus, tone markers, and content pillars (`accounts/01-*`, `accounts/02-*`, etc.).
- **4 Flexible Content Formats**:
  - `Single Tweet` (concise short-form <280 chars)
  - `Twitter Thread` (structured multi-tweet chains, 8–12 tweets)
  - `Poll` (engaging debate questions with 4 balanced options)
  - `Image Copywriting` (visual briefs + copy captions)
- **Modular AI Roles with Automatic Fallback**:
  - **Strategist AI**: Generates 10 diverse angles from fresh news/pillars and selects the highest-impact angle.
  - **Writer AI**: Crafts voice-tailored copy matching modern industry landscape and recency standards.
  - **QC & Autofix**: Automatic scoring (0–10) with self-healing repairs for character bounds, formatting markers, and dates.
  - **Fallback Routing**: Every role supports *Primary $\rightarrow$ Fallback 1 $\rightarrow$ Fallback 2*.
- **Smart Anti-Duplication**: Jaccard similarity detection (threshold 0.70) against `.content_history.json` to prevent repetitive topics or recycled angles.
- **Automated Daily Rotation (`--cron-daily`)**:
  - Runs daily post batches across accounts with weekly quota enforcement (default max 5 posts/account/week).
  - Sequential processing with 2-second cooldown to stay safe from provider rate limits.
  - Automatic Monday state reset.
- **Ultra-Lightweight Scheduler**: Runs 24/7 in Docker with **<10 MB idle RAM**, triggering daily batches at **03:00 WIB**.
- **Distribution & Integrations**:
  - **Buffer GraphQL API**: Direct scheduling into Buffer queues.
  - **Discord Bot**: Asynchronous, non-blocking webhook notifications for angle reviews (Channel A) and final packages (Channel B).
- **Auto-Pruning Utility**: Deletes old content drafts (`>7 days` or keeping newest 5 per account) to protect server disk space while safely preserving deduplication history.

---

## 📁 Project Architecture

```text
ai-content-pipeline-starter/
├── accounts/                  # Account configurations & persona prompts
│   ├── 01-ai-automation/     # Sample Account: AI & Automation
│   ├── 02-tech-news/         # Sample Account: Tech Trends & News
│   └── 03-personal-finance/  # Sample Account: Personal Finance & Investing
├── data/                      # Weekly state tracking (weekly_state.json)
├── output/                    # Generated content packages & history
├── prompts/                   # Global format templates (single, thread, poll, image)
├── scripts/                   # Account scaffolding and helpers (create_account.py)
├── src/                       # Application source code (Clean Architecture)
│   ├── application/           # Orchestrator & AI role services
│   ├── domain/                # Entities, validators, & deduplication
│   ├── infrastructure/        # API client, config loader, logging, & rotator
│   └── integrations/          # External API clients (Discord, Buffer)
├── .dockerignore              # Docker build context optimizations
├── .env.example               # Environment variables template
├── .gitignore                 # Secret, venv, and artifact ignore rules
├── Dockerfile                 # Multi-arch image definition (AMD64 & ARM64)
├── docker-compose.yml         # Container orchestration setup
├── requirements.txt           # Production dependencies
├── run.py                     # Main CLI runner
└── scheduler_daemon.py        # 24/7 background scheduler daemon
```

---

## 🔧 Prerequisites

- **Docker & Docker Compose** (Recommended for production) OR
- **Python 3.12+** & **pip**
- Any OpenAI-compatible API endpoint (Groq, OpenRouter, OpenAI, or local gateways)

---

## 🚀 Quick Start

### 1. Docker Compose (Recommended)

1. Clone the repository and navigate into the folder:
   ```bash
   git clone https://github.com/nothingser0/ai-content-pipeline-starter.git
   cd ai-content-pipeline-starter
   ```
2. Copy environment template and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
3. Start the container in background:
   - **Method A: Pull prebuilt image from GHCR (Fastest)**
     ```bash
     docker compose pull
     docker compose up -d
     ```
   - **Method B: Build from local source**
     ```bash
     docker compose up -d --build
     ```
4. View live logs:
   ```bash
   docker compose logs -f
   ```

The container will sleep quietly and automatically trigger daily batches at **03:00 WIB** (or your configured `CRON_SCHEDULE`).

---

### 2. Local Python Environment

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy environment configuration:
   ```bash
   cp .env.example .env
   ```
4. Run the scheduler daemon:
   ```bash
   python scheduler_daemon.py
   ```

---

## 💻 CLI Cheatsheet

`run.py` provides rich commands for manual testing and automation:

### Daily Cron Batch
```bash
# Dry-run simulation (no API calls):
python run.py --cron-daily --dry-run --force

# Live execution:
python run.py --cron-daily --force
```

### Single Account Execution
```bash
# Auto-generate topic and random format for a specific account:
python run.py --account 01-ai-automation --auto --random-format

# Specific format (Single Tweet, Thread, Poll, Image):
python run.py --account 01-ai-automation --auto --format "Single Tweet"

# Custom topic:
python run.py --account 01-ai-automation --topic "5 Practical AI Workflows" --format "Thread"

# Schedule to Buffer for tomorrow at 10:00:
python run.py --account 01-ai-automation --auto --format "Thread" --schedule "tomorrow"
```

### Storage Maintenance
```bash
# Keep newest 5 drafts per account and delete the rest:
python run.py --prune --keep-max 5

# Delete drafts older than 7 days:
python run.py --prune --keep-days 7
```

### List Available Accounts
```bash
python run.py --list
```

---

## ➕ Adding New Accounts

You can scaffold a new account in seconds using the built-in generator script:

```bash
python scripts/create_account.py
```
This prompts for the account ID, niche, handle, and persona, and automatically scaffolds:
- `accounts/{id}/config.json`
- `accounts/{id}/writer_prompt.txt`
- `accounts/{id}/strategist_prompt.txt`
- `accounts/{id}/buffer.json.example`

---

## ⚙️ Environment Configuration (`.env`)

Key configuration variables available in `.env`:

| Variable | Description | Default |
| :--- | :--- | :--- |
| `OPENCODE_BASE_URL` | AI API Base URL (OpenAI-compatible) | `http://localhost:1430/v1` |
| `OPENCODE_API_KEY` | API authentication key | - |
| `MODEL_STRATEGIST_PRIMARY` | Primary model for Strategist | `cbcn/deepseek-v4.1-flash` |
| `MODEL_WRITER_PRIMARY` | Primary model for Writer | `cx/gpt-6-luna` |
| `MODEL_QC_PRIMARY` | Primary model for QC & Autofix | `cx/gpt-6-luna` |
| `TIMEZONE` | Timezone for scheduler and logs | `Asia/Jakarta` |
| `CRON_SCHEDULE` | Daily batch trigger time (`HH:MM`) | `03:00` |
| `CRON_MAX_ACCOUNTS` | Daily batch posts quota | `3` |
| `WEEKLY_MAX_POSTS_PER_ACCOUNT` | Weekly quota per account | `5` |
| `RUN_ON_STARTUP` | Run batch immediately upon container startup | `false` |
| `BUFFER_ENABLED` | Toggle Buffer auto-scheduling | `true` |
| `DISCORD_TOKEN` | Discord bot token (optional) | - |

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
