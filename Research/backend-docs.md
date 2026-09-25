# Pkay TDAI
A multi-agent AI system that analyzes Gold (XAUUSD) and Bitcoin (BTCUSD) markets in real-time using technical analysis, news sentiment, risk management, and intelligent decision-making.

![Status](https://img.shields.io/badge/status-development-yellow)
![Python](https://img.shields.io/badge/python-3.11+-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Agents](#agents)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Data Flow](#data-flow)
- [Workflow](#workflow)
- [Trading Strategies](#trading-strategies)
- [Risk Management](#risk-management)
- [Deployment](#deployment)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

This system implements a **multi-agent architecture** where four specialized AI agents collaborate to make trading decisions:

| Agent | Role | Responsibility |
|-------|------|----------------|
| **Technical Analyst** | Market Analysis | Price action, indicators, ML models |
| **News Monitor** | Sentiment Analysis | Macro news, on-chain, social sentiment |
| **Risk Manager** | Risk Control | Position sizing, VaR, drawdown limits |
| **Decision Maker** | Final Judgment | Consensus voting, trade execution |

The **Risk Manager** holds **veto power** — no trade executes without its approval.

---

## Architecture

```mermaid
graph TB
    subgraph ORCH["ORCHESTRATOR LAYER"]
        API[FastAPI Gateway]
        BUS[Redis Pub/Sub Message Bus]
        SCHED[Celery Beat Scheduler]
    end

    subgraph AGENTS["AI AGENT LAYER"]
        A1[Technical Analyst]
        A2[News Monitor]
        A3[Risk Manager]
        A4[Decision Maker]
    end

    subgraph DATA["DATA LAYER"]
        DB[(PostgreSQL + TimescaleDB)]
        VDB[(Qdrant Vector DB)]
        CACHE[(Redis Cache)]
    end

    subgraph EXT["EXTERNAL SOURCES"]
        TV[tvkit WebSocket]
        LSE[lse-data API]
        NEWS[News APIs]
        ONCHAIN[On-Chain Data]
    end

    subgraph EXEC["EXECUTION LAYER"]
        BROKER[Broker API]
        MT5[MT5 / Binance]
    end

    TV --> A1
    LSE --> A1
    NEWS --> A2
    ONCHAIN --> A2

    A1 --> BUS
    A2 --> BUS
    A3 --> BUS
    A4 --> BUS

    BUS --> DB
    BUS --> VDB
    BUS --> CACHE

    A4 --> EXEC
    EXEC --> BROKER
    BROKER --> MT5

    API --> BUS
    SCHED --> BUS

    style A1 fill:#4A90E2,color:#fff
    style A2 fill:#E67E22,color:#fff
    style A3 fill:#E74C3C,color:#fff
    style A4 fill:#27AE60,color:#fff
```

---

## Agents

### Agent 1 — Technical Analyst

Analyzes price action and technical indicators for XAUUSD & BTCUSD.

```mermaid
flowchart LR
    IN[OHLCV Data] --> FE[Feature Engineering]
    FE --> M1[LSTM Model]
    FE --> M2[XGBoost Model]
    FE --> M3[Indicator Engine]

    M1 --> ENS[Ensemble]
    M2 --> ENS
    M3 --> ENS

    ENS --> SIG[Signal Output]

    style SIG fill:#27AE60,color:#fff
```

**Output Schema:**
```json
{
  "agent": "technical_analyst",
  "symbol": "XAUUSD",
  "signal": "BULLISH",
  "confidence": 0.78,
  "timeframe": "H1",
  "key_levels": {"support": 2640.50, "resistance": 2678.20},
  "indicators": {
    "rsi": 58.3,
    "macd": "bullish_cross",
    "ema_50_200": "golden_cross"
  },
  "reasoning": "Breakout above 2650 with volume confirmation"
}
```

---

### Agent 2 — News Monitor

Tracks macro news, on-chain metrics, and social sentiment.

```mermaid
flowchart TB
    subgraph SOURCES["Data Sources"]
        S1[Fed / ECB News]
        S2[CPI / NFP / FOMC]
        S3[SEC / ETF Flows]
        S4[Whale Alerts]
        S5[Twitter / Reddit]
    end

    S1 --> ING[Ingestion Pipeline]
    S2 --> ING
    S3 --> ING
    S4 --> ING
    S5 --> ING

    ING --> LLM[LLM Sentiment Classifier]
    LLM --> EMB[Embedding Generator]
    EMB --> VDB[(Vector Store)]

    LLM --> OUT[Event Alert]

    style OUT fill:#E67E22,color:#fff
```

**Output Schema:**
```json
{
  "agent": "news_monitor",
  "event": "FOMC_RATE_DECISION",
  "impact": "HIGH",
  "affected_symbols": ["XAUUSD", "BTCUSD"],
  "sentiment": "HAWKISH",
  "time_until_event": "2h 15m",
  "historical_reaction": {"XAUUSD": "-1.2%", "BTCUSD": "-2.8%"},
  "alert": "REDUCE_POSITION_SIZE"
}
```

---

## Agent 3 — Risk Manager

Enforces portfolio risk limits and holds **veto power**.

```mermaid
flowchart TD
    IN[Trade Proposal] --> CHK{Check Limits}

    CHK --> D1[Max Drawdown < 5%]
    CHK --> D2[Position Size Kelly×0.25]
    CHK --> D3[VaR 95% < 2%]
    CHK --> D4[Correlation < 0.7]
    CHK --> D5[ATR Volatility]

    D1 --> AGG[Aggregate Checks]
    D2 --> AGG
    D3 --> AGG
    D4 --> AGG
    D5 --> AGG

    AGG --> DEC{All Passed?}
    DEC -->|Yes| APPROVE[APPROVE]
    DEC -->|No| VETO[VETO]

    style APPROVE fill:#27AE60,color:#fff
    style VETO fill:#E74C3C,color:#fff
```

**Risk Rules:**

| Metric | Threshold | Action |
|--------|-----------|--------|
| Max Drawdown | 5% daily | Block new trades |
| Position Size | Kelly × 0.25 | Auto-adjust |
| VaR (95%) | 2% portfolio | Reduce leverage |
| Correlation | > 0.7 | Warn |
| Volatility (ATR) | Spike detected | Widen SL |

---

### Agent 4 — Decision Maker

Aggregates signals and produces the final trade decision.

```mermaid
flowchart LR
    T[Technical Signal<br/>Weight 0.45] --> V{Voting Engine}
    N[News Signal<br/>Weight 0.25] --> V
    R[Risk Approval<br/>Weight 0.30] --> V

    V --> SC{Final Score}
    SC -->|> 0.65| BUY[EXECUTE]
    SC -->|< 0.35| SKIP[STAY OUT]
    SC -->|0.35 - 0.65| WAIT[WAIT]

    BUY --> EX[Execution Layer]
    WAIT --> MON[Monitor]
    SKIP --> MON

    style BUY fill:#27AE60,color:#fff
    style SKIP fill:#E74C3C,color:#fff
    style WAIT fill:#F39C12,color:#fff
```

**Decision Formula:**
```
Final Score = (Technical × 0.45) + (News × 0.25) + (Risk × 0.30)
```

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | FastAPI, Uvicorn | High-performance API |
| **Async** | asyncio, aiohttp | Non-blocking I/O |
| **Task Queue** | Celery + Redis | Background jobs |
| **ML** | PyTorch, XGBoost | Prediction models |
| **Data** | Pandas, NumPy, TA-Lib | Feature engineering |
| **Database** | PostgreSQL + TimescaleDB | Time-series storage |
| **Vector DB** | Qdrant | News embeddings |
| **Cache** | Redis | Pub/Sub + cache |
| **LLM** | GPT-4o / Claude / Llama-3 | Reasoning & sentiment |
| **Container** | Docker + Compose | Deployment |
| **Monitoring** | Grafana + Prometheus | Observability |

---

## Project Structure

```mermaid
graph TD
    ROOT[ai_trading_system/]

    ROOT --> ORCH[orchestrator/]
    ROOT --> AG[agents/]
    ROOT --> SH[shared/]
    ROOT --> DP[data_pipeline/]
    ROOT --> EX[execution/]
    ROOT --> TST[tests/]
    ROOT --> DOC[docs/]

    ORCH --> O1[main.py]
    ORCH --> O2[message_bus.py]
    ORCH --> O3[scheduler.py]

    AG --> AG1[technical_analyst/]
    AG --> AG2[news_monitor/]
    AG --> AG3[risk_manager/]
    AG --> AG4[decision_maker/]
    AG --> AGB[base_agent.py]

    AG1 --> AG1a[models/]
    AG1 --> AG1b[indicators.py]
    AG1 --> AG1c[agent.py]

    AG2 --> AG2a[scrapers/]
    AG2 --> AG2b[llm_sentiment.py]
    AG2 --> AG2c[agent.py]

    AG3 --> AG3a[var_calculator.py]
    AG3 --> AG3b[position_sizer.py]
    AG3 --> AG3c[agent.py]

    AG4 --> AG4a[voting_logic.py]
    AG4 --> AG4b[llm_reasoner.py]
    AG4 --> AG4c[agent.py]

    SH --> SH1[database/]
    SH --> SH2[vector_store/]
    SH --> SH3[schemas/]
    SH --> SH4[utils/]

    DP --> DP1[tvkit_feed.py]
    DP --> DP2[lse_feed.py]
    DP --> DP3[onchain_feed.py]

    EX --> EX1[broker_api.py]
    EX --> EX2[order_manager.py]

    style ROOT fill:#2C3E50,color:#fff
    style AG fill:#4A90E2,color:#fff
    style SH fill:#27AE60,color:#fff
    style EX fill:#E74C3C,color:#fff
```

---

## Installation

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15+ (or use Docker)
- Redis 7+

### Quick Start

```bash
# 1. Clone repository
git clone https://github.com/your-org/ai-trading-system.git
cd ai-trading-system

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment variables
cp .env.example .env
# Edit .env with your API keys

# 5. Start infrastructure
docker-compose up -d postgres redis qdrant

# 6. Run database migrations
alembic upgrade head

# 7. Start orchestrator
uvicorn orchestrator.main:app --reload

# 8. Start Celery workers
celery -A orchestrator.scheduler worker -l info
celery -A orchestrator.scheduler beat -l info
```

---

## Configuration

`.env.example`:

```bash
# === Database ===
POSTGRES_URL=postgresql://user:pass@localhost:5432/trading
REDIS_URL=redis://localhost:6379/0
QDRANT_URL=http://localhost:6333

# === Data Providers ===
TVKIT_API_KEY=your_key_here
LSE_API_KEY=your_key_here
NEWS_API_KEY=your_key_here
FINNHUB_API_KEY=your_key_here
CRYPTOPANIC_API_KEY=your_key_here

# === LLM ===
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# === Broker ===
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=ICMarkets-Demo
BINANCE_API_KEY=...
BINANCE_API_SECRET=...

# === Risk Limits ===
MAX_DRAWDOWN_PCT=0.05
MAX_POSITION_SIZE=0.5
VAR_CONFIDENCE=0.95
```

---

## Usage

### Running a Single Analysis Cycle

```python
from orchestrator.main import run_analysis_cycle

result = await run_analysis_cycle(
    symbol="XAUUSD",
    timeframes=["M5", "H1", "H4"]
)
print(result)
```

### Subscribing to Agent Signals

```python
import redis.asyncio as redis
import json

r = redis.from_url("redis://localhost:6379")

async for msg in r.subscribe("signals.*"):
    data = json.loads(msg["data"])
    print(f"[{data['agent']}] {data['signal']} @ {data['confidence']}")
```

---

## Data Flow

```mermaid
sequenceDiagram
    participant DP as Data Pipeline
    participant TA as Technical Analyst
    participant NM as News Monitor
    participant RM as Risk Manager
    participant DM as Decision Maker
    participant EX as Execution
    participant BR as Broker

    DP->>TA: OHLCV + Indicators
    DP->>NM: News + On-chain
    activate TA
    TA->>TA: Analyze Patterns
    TA-->>DM: Signal (0.78 BULLISH)
    deactivate TA

    activate NM
    NM->>NM: LLM Sentiment
    NM-->>DM: Sentiment (0.50 NEUTRAL)
    deactivate NM

    activate DM
    DM->>RM: Trade Proposal
    deactivate DM

    activate RM
    RM->>RM: VaR + Position Size
    RM-->>DM: Approved / Veto
    deactivate RM

    activate DM
    DM->>DM: Weighted Vote
    DM->>EX: Execute BUY
    deactivate DM

    activate EX
    EX->>BR: Place Order
    BR-->>EX: Fill Confirmation
    EX-->>DM: Log Result
    deactivate EX
```

---

## Workflow

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> DataIngestion: Cron Trigger
    DataIngestion --> TechnicalAnalysis
    DataIngestion --> NewsScan

    TechnicalAnalysis --> SignalGenerated
    NewsScan --> SentimentGenerated

    SignalGenerated --> RiskEvaluation
    SentimentGenerated --> RiskEvaluation

    RiskEvaluation --> Approved: All checks pass
    RiskEvaluation --> Rejected: Limit breached

    Approved --> Decision
    Rejected --> Idle

    Decision --> Execute: Score > 0.65
    Decision --> Monitor: 0.35–0.65
    Decision --> Idle: Score < 0.35

    Execute --> LogResult
    Monitor --> Decision
    LogResult --> [*]
```

---

## Trading Strategies

### XAUUSD Strategies

```mermaid
mindmap
  root((XAUUSD))
    Liquidity Sweep
      Session High/Low Sweep
      Confirmed Reversal
      R:R 2:1
    RSI Divergence
      Bullish Divergence
      Bearish Divergence
      ATR-based Stops
    MACD-BB Breakout
      MACD + Bollinger
      EMA200 Filter
      RSI Confirmation
    Classic RSI+EMA
      Oversold < 30
      Overbought > 70
      Trend Filter
```

### BTCUSD Strategies

```mermaid
mindmap
  root((BTCUSD))
    On-Chain Composite
      MVRV Z-Score
      SOPR 28-day
      Puell Multiple
    Macro Liquidity
      Global M2
      ETF Net Flows
      Fed Policy
    MA + On-Chain
      MA Crossover
      Bottom Z-Score
      Realized Price
    RL Agents
      PPO + LSTM
      Sentiment-Enhanced
      ArchetypeTrader
```

---

## Risk Management

```mermaid
graph TD
    subgraph PRE["Pre-Trade Checks"]
        P1[Position Size]
        P2[VaR Calculation]
        P3[Correlation Check]
    end

    subgraph LIVE["Live Monitoring"]
        L1[Drawdown Tracker]
        L2[Exposure Monitor]
        L3[Volatility Guard]
    end

    subgraph POST["Post-Trade"]
        O1[PnL Attribution]
        O2[Strategy Performance]
        O3[Model Retrain Signal]
    end

    PRE --> LIVE
    LIVE --> POST
    POST -.feedback.-> PRE

    style PRE fill:#3498DB,color:#fff
    style LIVE fill:#F39C12,color:#fff
    style POST fill:#27AE60,color:#fff
```

---

## Deployment

```mermaid
graph TB
    subgraph DEV["Development"]
        D1[Local Docker Compose]
    end

    subgraph STG["Staging"]
        S1[K8s Cluster]
        S2[Paper Trading]
    end

    subgraph PROD["Production"]
        P1[K8s Multi-Region]
        P2[Live Trading]
        P3[Grafana Monitoring]
    end

    DEV -->|CI/CD| STG
    STG -->|3-6 months| PROD

    style PROD fill:#E74C3C,color:#fff
```

### Docker Compose Services

| Service | Port | Purpose |
|---------|------|---------|
| `api` | 8000 | FastAPI orchestrator |
| `worker` | — | Celery workers |
| `beat` | — | Scheduled tasks |
| `postgres` | 5432 | Primary database |
| `redis` | 6379 | Message bus + cache |
| `qdrant` | 6333 | Vector database |
| `grafana` | 3000 | Dashboards |
| `prometheus` | 9090 | Metrics |

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open a Pull Request

### Code Standards

- **Python:** PEP 8, type hints required
- **Testing:** pytest, minimum 80% coverage
- **Docs:** Docstrings for all public functions
- **Commits:** Conventional Commits format

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Disclaimer

**Trading financial instruments carries significant risk.** This software is for educational and research purposes. Past performance does not guarantee future results. Always test strategies in paper trading before deploying capital. The authors are not responsible for any financial losses.

