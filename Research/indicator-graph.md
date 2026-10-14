# Pre-Signal System — README

A **Pre-Signal System** for trading charts that warns traders **before** a real signal appears, helping them prepare for strong market movements, breakouts, and volatility spikes around **BE (Break Even)** and **OP (Opening Price)** levels.

---

## Table of Contents

1. [Overview](#overview)
2. [Core Concept](#core-concept)
3. [Signal Layers](#signal-layers)
4. [Pre-Signal Types](#pre-signal-types)
5. [System Architecture](#system-architecture)
6. [Warning Levels](#warning-levels)
7. [Signal Flow](#signal-flow)
8. [UI / Button Design Principles](#ui--button-design-principles)
9. [Alert Pipeline](#alert-pipeline)
10. [False Signal Prevention](#false-signal-prevention)
11. [Design Principles](#design-principles)
12. [Testing Workflow](#testing-workflow)
13. [Roadmap](#roadmap)

---

## Overview

Most traders face three problems:

- 🐢 Entering **too late** — price already moved
- ⚡ Entering **too early** — false signals
- 🌀 Not knowing **when** the market will explode

The **Pre-Signal System** solves this by:

- ⚠️ Warning **before** the real signal
- 🎯 Giving the trader time to **prepare**
- 🧭 Showing the **direction** the market is heading

---

## Core Concept

The system focuses on **BE** and **OP** levels as psychological price zones:

| Level | Meaning | Role |
|-------|---------|------|
| **OP** | Opening Price | Session reference — above = bullish, below = bearish |
| **BE** | Break Even | Traders defend it → strong reactions near it |

**Rule of thumb:** As price approaches BE or OP, the market becomes more volatile — that's when Pre-Signals matter most.

---

## Signal Layers

The system uses **3 progressive layers** — like a staircase:

```mermaid
flowchart LR
    A["👁️ LAYER 1<br/>WATCH<br/>Price approaching BE/OP"] --> B["🧠 LAYER 2<br/>PREPARE<br/>Near breakout zone"]
    B --> C["🎯 LAYER 3<br/>ACTION<br/>Real signal fires"]
    
    style A fill:#FFF9C4,stroke:#FBC02D,stroke-width:2px
    style B fill:#FFE0B2,stroke:#FB8C00,stroke-width:2px
    style C fill:#FFCDD2,stroke:#E53935,stroke-width:2px
```

**Key principle:** A signal should **never pop instantly** — it must progress through stages.

---

## Pre-Signal Types

```mermaid
mindmap
  root((Pre-Signal))
    Price-based
      Near BE
      Near OP
      Near Support/Resistance
      Pattern forming
    Movement-based
      Momentum buildup
      Price spike
      Consolidation
    Volatility-based
      Volatility spike
      Volatility squeeze
      Tight range
    Time-based
      Candle close
      Session open/close
      News release
```

---

## System Architecture

```mermaid
flowchart TB
    subgraph DATA["📡 Data Layer"]
        A1[Market Feed / API]
        A2[Historical Data]
    end
    
    subgraph ENGINE["⚙️ Signal Engine"]
        B1[Pre-Signal Detector]
        B2[Real Signal Generator]
        B3[Signal Validator]
        B4[False Signal Filter]
    end
    
    subgraph UI["🖥️ Frontend"]
        C1[Price Chart]
        C2[OP / BE Lines]
        C3[⚠️ Warning Buttons]
        C4[🟢🔴 Buy/Sell Arrows]
        C5[Alert Panel]
    end
    
    subgraph ALERT["🔔 Alert Layer"]
        D1[Sound]
        D2[Telegram / LINE]
        D3[Email]
        D4[Push Notification]
    end
    
    A1 --> B1
    A2 --> B1
    B1 --> B2 --> B3 --> B4
    B4 --> C1
    B4 --> C3
    B4 --> C4
    B4 --> C5
    B4 --> D1
    B4 --> D2
    B4 --> D3
    B4 --> D4
    
    style DATA fill:#E3F2FD,stroke:#1976D2
    style ENGINE fill:#FFF3E0,stroke:#F57C00
    style UI fill:#E8F5E9,stroke:#388E3C
    style ALERT fill:#FCE4EC,stroke:#C2185B
```

---

## Warning Levels

The system uses a **traffic-light** model with 4 levels:

```mermaid
flowchart LR
    L1["🟡 LEVEL 1<br/>WATCH<br/>Far from level<br/>No action needed"]
    L2["🟠 LEVEL 2<br/>PREPARE<br/>Approaching level<br/>Review chart"]
    L3["🔴 LEVEL 3<br/>READY<br/>Very close<br/>Set orders"]
    L4["🟢 LEVEL 4<br/>ACTION<br/>Crossed level<br/>Enter trade"]
    
    L1 --> L2 --> L3 --> L4
    
    style L1 fill:#FFF9C4,stroke:#FBC02D,stroke-width:2px
    style L2 fill:#FFE0B2,stroke:#FB8C00,stroke-width:2px
    style L3 fill:#FFCDD2,stroke:#E53935,stroke-width:2px
    style L4 fill:#C8E6C9,stroke:#2E7D32,stroke-width:2px
```

| Level | Trigger | User Action |
|-------|---------|-------------|
| 🟡 1 | Price far from BE/OP | Just watch |
| 🟠 2 | Price approaching BE/OP | Review chart, plan |
| 🔴 3 | Price very near BE/OP | Set pending orders |
| 🟢 4 | Price crosses BE/OP | Enter trade |

---

## Signal Flow

```mermaid
sequenceDiagram
    participant M as Market
    participant D as Detector
    participant V as Validator
    participant U as User
    
    M->>D: Price approaches BE
    D->>D: Compute proximity
    D->>U: ⚠️ Warning (Level 1-2)
    
    M->>D: Volatility increases
    D->>D: Confirm momentum
    D->>U: 🟠 Prepare (Level 3)
    
    M->>D: Price crosses BE
    D->>V: Send candidate signal
    V->>V: Check confirmation rules
    V-->>D: Valid? 
    D->>U: 🟢 Action (Level 4)
    
    M->>D: Trend continues
    D->>U: ✅ Confirmation
```

---

## UI / Button Design Principles

```mermaid
flowchart TB
    subgraph PRINCIPLES["Button Design Principles"]
        P1[Avoid Clutter]
        P2[Use Color Coding]
        P3[Scale by Severity]
        P4[Anchor to Price]
        P5[Connect with Line]
        P6[Don't Obscure Chart]
    end
    
    subgraph COLORS["Color System"]
        C1["🟡 Watch"]
        C2["🟠 Prepare"]
        C3["🔴 Ready"]
        C4["🟢 Action"]
    end
    
    PRINCIPLES --> COLORS
```

### Rules

- 🚫 **Don't overcrowd** — too many buttons hide the chart
- 🎨 **Color = severity** — consistent palette across the app
- 📏 **Size matters** — bigger button = higher urgency
- 📌 **Anchor to price** — show where the signal occurred
- 🔗 **Connect with line** — link button to price point
- 👁️ **Never hide candles** — keep chart readable

---

## Alert Pipeline

```mermaid
flowchart LR
    S[Signal Detected] --> L1{Level?}
    L1 -->|Level 1| A1[Chart dot only]
    L1 -->|Level 2| A2[Chart button + panel]
    L1 -->|Level 3| A3[+ sound]
    L1 -->|Level 4| A4[+ Telegram + Email + Push]
    
    style A1 fill:#FFF9C4
    style A2 fill:#FFE0B2
    style A3 fill:#FFCDD2
    style A4 fill:#C8E6C9
```

**Principle:** Higher level = louder alert. This prevents notification fatigue.

---

## False Signal Prevention

```mermaid
flowchart TB
    RAW[Raw Signal] --> C1{Confirmation?}
    C1 -->|No| REJECT[Reject]
    C1 -->|Yes| C2{Time filter?}
    C2 -->|No| WAIT[ Wait 1-2 candles]
    C2 -->|Yes| C3{Context OK?}
    C3 -->|No| REJECT
    C3 -->|Yes| C4{Timeframe aligned?}
    C4 -->|No| REJECT
    C4 -->|Yes| ACCEPT[Valid Signal]
    
    style REJECT fill:#FFCDD2,stroke:#C62828
    style ACCEPT fill:#C8E6C9,stroke:#2E7D32
```

### Four Filters

1. **Confirmation** — require 2-3 indicators to agree
2. **Time** — wait 1-2 candles before acting
3. **Context** — check session, news, market regime
4. **Timeframe** — align with higher timeframe trend

---

## Design Principles

| # | Principle | Description |
|---|-----------|-------------|
| 1 | **Progressive signals** | Never pop instantly — stage by stage |
| 2 | **Color-coded severity** | 🟡 → 🟠 → 🔴 → 🟢 |
| 3 | **Confirmation required** | Multiple indicators agree |
| 4 | **Context-aware** | Session, news, timeframe |
| 5 | **BE/OP as psychology** | Not just lines — behavioral zones |
| 6 | **Focus on pre-explosion** | Catch the calm before the storm |
| 7 | **Multi-layer alerts** | Chart → Panel → Sound → External |
| 8 | **User-configurable** | Let traders tune sensitivity |
| 9 | **Test before live** | Backtest → Forward → Demo → Live |
| 10 | **Iterate constantly** | Adjust based on performance |

---

## Testing Workflow

```mermaid
flowchart LR
    BT[Backtest<br/>Historical data] --> FT[Forward Test<br/>Live data, no trade]
    FT --> DM[Demo Account<br/>Fake money]
    DM --> LV[Live Account<br/>Small size]
    LV --> IT[Iterate<br/>Adjust & repeat]
    IT --> BT
    
    style BT fill:#E3F2FD,stroke:#1976D2
    style FT fill:#FFF3E0,stroke:#F57C00
    style DM fill:#FFF9C4,stroke:#FBC02D
    style LV fill:#C8E6C9,stroke:#2E7D32
    style IT fill:#F3E5F5,stroke:#8E24AA
```

| Stage | Purpose | Risk |
|-------|---------|------|
| Backtest | Validate logic on history | None |
| Forward Test | Observe live behavior | None |
| Demo | Practice execution | None |
| Live | Real trading | Real money |
| Iterate | Improve system | — |

---

## Roadmap

```mermaid
gantt
    title Pre-Signal System — Build Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1 — Core
    Define signal rules        :a1, 2026-10-01, 7d
    Build detector engine      :a2, after a1, 14d
    section Phase 2 — UI
    Design warning buttons     :b1, after a2, 7d
    Build chart frontend       :b2, after b1, 14d
    section Phase 3 — Alerts
    Sound + panel alerts       :c1, after b2, 7d
    Telegram / Email / Push    :c2, after c1, 7d
    section Phase 4 — Testing
    Backtest                   :d1, after c2, 14d
    Forward test               :d2, after d1, 14d
    Demo + Live                :d3, after d2, 30d
```

---

## Summary

The **Pre-Signal System** is not about predicting the future — it's about **preparing for it**.

- Warn early
- Confirm carefully
- Act decisively

> "The best trade is the one you were ready for before it happened."

---

## License

MIT — free to use, modify, and distribute.

## Contributing

Pull requests welcome. For major changes, please open an issue first.