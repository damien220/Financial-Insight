# Financial Insight — AI-Powered Financial Analysis Platform

A financial asset tracking and analysis platform that fetches real-time prices (gold, stocks/ETFs), aggregates financial news, and generates AI-powered insights via LLM (online or offline). Built on top of the `mcp_server` core package, leveraging its tool system, dispatcher, and configuration infrastructure.

Designed as the foundation for a future AI trading platform — every design decision favors extensibility, clean data interfaces, and pluggable strategy patterns.

---

## Features

- **Real-time price data** — Gold futures (GC=F) and any stock/ETF via yfinance
- **Financial news aggregation** — Multi-source RSS feeds + optional Finnhub/NewsAPI
- **Data aggregation** — Combines price + news + technical indicators (SMA, RSI-14, volatility) into LLM-ready prompts
- **Dual-mode LLM insights** — Online (OpenAI / Anthropic) or offline (Ollama) with auto-fallback
- **Interactive dashboard** — Streamlit UI with candlestick charts, news feed, and AI insight panel
- **Automated scheduling** — APScheduler with market-hours awareness and price-change detection
- **SQLite persistence** — Async via aiosqlite, WAL mode, upsert on unique constraints
- **Event-driven architecture** — Pub/sub event bus for real-time reactivity
- **Trading strategy hooks** — Abstract interfaces (Signal, TradingStrategy, PortfolioManager) ready for future implementation
- **Docker deployment** — Dockerfile + docker-compose with separate dashboard and scheduler services

---

## Quick Start

### 1. Create virtual environment

```bash
cd Financial_Insight
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys (all optional for basic usage)
```

### 4. Run demo (one-shot self-test)

```bash
python app.py --demo
```

### 5. Run the dashboard

```bash
streamlit run dashboard/app_ui.py
```

### 6. Run the scheduler (persistent background refresh)

```bash
python app.py --schedule
```

---

## Docker Deployment

### Run with Docker Compose (recommended)

```bash
cp .env.example .env
# Edit .env with your API keys

docker compose up -d
```

This starts two services:

- **dashboard** — Streamlit UI on `http://localhost:8501`
- **scheduler** — Background price/news/insight refresh

Both services share persistent volumes for the SQLite database and logs.

### Run individual containers

```bash
# Build the image
docker build -t financial-insight .

# Dashboard only
docker run -p 8501:8501 --env-file .env financial-insight

# Scheduler only
docker run --env-file .env financial-insight python app.py --schedule

# Demo mode
docker run --env-file .env financial-insight python app.py --demo
```

---

## Configuration

All configuration is via `.env` file and `config/assets.yaml`.

### Environment Variables

| Variable              | Default                  | Description                         |
| --------------------- | ------------------------ | ----------------------------------- |
| `DATABASE_PATH`       | `data/prices.db`         | SQLite database location            |
| `ASSETS_CONFIG`       | `config/assets.yaml`     | Tracked assets configuration        |
| `LLM_MODE`            | `online`                 | `online` or `offline`               |
| `LLM_ONLINE_PROVIDER` | `openai`                 | `openai` or `anthropic`             |
| `LLM_ONLINE_MODEL`    | `gpt-4o-mini`            | Model name for online provider      |
| `LLM_API_KEY`         | —                        | API key for the chosen LLM provider |
| `LLM_OFFLINE_MODEL`   | `mistral`                | Ollama model name                   |
| `OLLAMA_HOST`         | `http://localhost:11434` | Ollama server URL                   |
| `FINNHUB_API_KEY`     | —                        | Optional: Finnhub news API key      |
| `NEWSAPI_KEY`         | —                        | Optional: NewsAPI key               |
| `MARKET_HOURS_ONLY`   | `true`                   | Skip refreshes outside market hours |

### Tracked Assets (`config/assets.yaml`)

```yaml
assets:
  commodities:
    - { ticker: "GC=F", name: "Gold Futures" }
  stocks:
    - { ticker: "AAPL", name: "Apple Inc." }
    - { ticker: "MSFT", name: "Microsoft Corp." }
  etfs:
    - { ticker: "SPY", name: "S&P 500 ETF" }
```

---

## Project Structure

```
Financial_Insight/
├── app.py                      # Entry point (--demo | --schedule)
├── Dockerfile                  # Container image definition
├── docker-compose.yaml         # Multi-service deployment
├── .dockerignore               # Docker build exclusions
├── config/assets.yaml          # Tracked assets + refresh config
├── tools/                      # MCP tools
│   ├── price/                  # Gold + stock price tools
│   ├── news/                   # Financial news tool
│   ├── data/                   # Data aggregator tool
│   └── llm/                    # LLM insight tool
├── services/                   # Core services
│   ├── data_store.py           # SQLite persistence
│   ├── llm_provider.py         # LLM abstraction (OpenAI/Anthropic/Ollama)
│   ├── scheduler.py            # APScheduler wrapper
│   ├── events.py               # Pub/sub event bus
│   ├── cache.py                # TTL cache for API responses
│   └── strategy.py             # Trading strategy interfaces
├── dashboard/                  # Streamlit UI
│   ├── app_ui.py               # Main dashboard
│   └── components/             # Reusable UI components
├── tests/                      # Test suite (88 tests)
│   ├── test_tools/             # Tool unit tests
│   ├── test_core/              # Service tests
│   ├── test_data_store.py      # Data store tests
│   └── test_integration/       # End-to-end tests
└── data/                       # SQLite database (auto-created)
```

---

## Running Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

88 tests covering: tool unit tests, service tests, data store CRUD, scheduler logic, event bus, cache, trading strategy interfaces, and end-to-end integration.

---

## Architecture

The platform is built on an MCP (Model Context Protocol) tool architecture:

1. **Tools Layer** — Each capability (price fetch, news fetch, LLM call) is a self-contained `BaseTool` subclass registered with `ToolLoader`
2. **Data Aggregator** — Orchestrates tools to combine price data, news, and technical indicators into structured LLM prompts
3. **LLM Insight Engine** — Sends aggregated data to LLM (online/offline), parses structured JSON response, persists to database
4. **Scheduler** — Periodically triggers refresh cycles with market-hours awareness
5. **Event Bus** — Pub/sub system emits `price_updated`, `news_updated`, `insight_generated` events
6. **Dashboard** — Streamlit UI consumes tools and data store to display real-time information

### Future Trading Platform Hooks

The `services/strategy.py` module defines abstract interfaces ready for implementation:

- `Action` enum — BUY / SELL / HOLD
- `Signal` dataclass — action + confidence + reasoning
- `TradingStrategy` ABC — `evaluate(insight) -> Signal`
- `PortfolioManager` ABC — position tracking + order execution

The LLM insight tool's `recommendation_hint` field maps directly to these interfaces.

---

## Contributing

Contributions are welcome! Whether it's bug fixes, new features, documentation improvements, or test coverage — all help is appreciated.

### How to contribute

1. **Fork** the repository
2. **Create a branch** for your feature or fix
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** — follow the existing code style and patterns
4. **Run the tests** to make sure nothing is broken
   ```bash
   python -m pytest tests/ -v
   ```
5. **Commit** with a clear message describing the change
6. **Open a Pull Request** against the `main` branch

### Guidelines

- Keep PRs focused — one feature or fix per PR
- Add tests for new functionality
- Update documentation if your change affects usage or configuration
- Use the existing tool/service patterns (extend `BaseTool`, register via `ToolLoader`, etc.)

### Areas where help is needed

- New asset tools (crypto, forex, commodities)
- Additional LLM provider integrations
- Dashboard improvements and new visualizations
- Trading strategy implementations (see `services/strategy.py` interfaces)
- Documentation and examples

---

## Support This Project

If you find Financial Insight useful, consider supporting its development. Your contributions help keep the project maintained, fund new features, and cover infrastructure costs.

[![Buy Me A Coffee](https://img.shields.io/badge/Buy_Me_A_Coffee-Support-FFDD00?style=for-the-badge&logo=buy-me-a-coffee&logoColor=black)](https://buymeacoffee.com/ashrafalnas)
[![Patreon](https://img.shields.io/badge/Patreon-Support-F96854?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/c/UnrealPatr?vanity=user)

| Platform            | Type                         | Link                                                                       |
| ------------------- | ---------------------------- | -------------------------------------------------------------------------- |
| **Buy Me a Coffee** | One-time or monthly support  | [buymeacoffee.com/ashrafalnas](https://buymeacoffee.com/ashrafalnas)       |
| **Patreon**         | Recurring monthly membership | [patreon.com/UnrealPatr](https://www.patreon.com/c/UnrealPatr?vanity=user) |

> Replace `YOUR_USERNAME` with your actual platform usernames before publishing.

---

## Dependencies

- **mcp_server** (v1.0.0) — Core tool system (included in `Dependency/`)
- **yfinance** — Price data (no API key required)
- **feedparser** — RSS news feeds
- **openai / anthropic / ollama** — LLM providers
- **streamlit + plotly** — Dashboard UI
- **apscheduler** — Periodic scheduling
- **aiosqlite** — Async SQLite
- **pandas** — Data processing
