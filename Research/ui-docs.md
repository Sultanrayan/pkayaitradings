## 1. Dashboard (Home Page)

**Key Features:**

- **Market Overview Panel** — Real-time XAUUSD and BTCUSD prices with % Change
- **Agent Status Panel** — Status of the 4 agents (Active/Idle/Error) with Last Heartbeat
- **Today's Signals** — Signals generated today with Confidence Score
- **Recent Alerts** — Latest notifications (News events, Risk warnings)
- **Signal Summary Cards** — Total Signals, Bullish/Bearish count, Avg Confidence
- **Mini Charts** — Sparkline charts for XAUUSD and BTCUSD
- **News Ticker** — Scrolling news feed

---

## 2. Charts & Analysis

**Key Features:**

- **Multi-Timeframe Chart** — M1, M5, M15, H1, H4, D1, W1
- **Candlestick Chart** with Overlays:
- EMA/SMA lines
- Bollinger Bands
- Support/Resistance lines
- Fibonacci retracement
- Signal markers (points where AI issued a signal)
- **Indicator Sub-charts:**
- RSI
- MACD
- Volume
- ATR
- Stochastic
- **Drawing Tools** — Trend lines, Horizontal lines, Rectangles, Text notes
- **Symbol Switcher** — Instant switching between XAUUSD and BTCUSD
- **Timeframe Sync** — Synchronize multiple charts
- **Fullscreen Mode** — Expand chart to full screen
- **Screenshot/Export** — Download chart as PNG
- **Indicator Toggle Panel** — Toggle individual indicators on/off

---

## 3. AI Agent Control Panel

**Key Features:**

- **Agent List View** — List of all 4 agents with status icons
- **Individual Agent Page** for each agent:

**Technical Analyst:**
- Latest signal (direction, confidence)
- Signal history table
- Indicator snapshot
- Model accuracy metrics
- Feature importance chart
- Chart with signal markers

**News Monitor:**
- Live news feed
- Sentiment score gauge
- Upcoming events calendar
- Impact classification
- Historical event reactions
- Source credibility list

**Risk Manager:**
- Current risk metrics (VaR, Volatility, Exposure)
- Risk assessment of each signal
- Risk limits configuration
- Correlation matrix
- Veto history log
- Warning alerts

**Decision Maker:**
- Final decision stream
- Voting breakdown chart
- Reasoning log (LLM output)
- Confidence timeline
- Consensus visualization

- **Agent Enable/Disable Toggle** — Temporarily activate/deactivate agents
- **Agent Performance Metrics** — Accuracy, win rate, reaction time
- **Agent Logs Viewer** — View logs for each agent
- **Agent Communication Flow** — Visualize agent-to-agent communication

---

## 4. Signals & Analysis Feed

**Key Features:**

- **Signal Feed** — List of all signals with filters:
- By Symbol (XAUUSD/BTCUSD)
- By Agent (Technical/News/Risk/Decision)
- By Time range
- By Confidence level
- By Direction (Bullish/Bearish/Neutral)
- **Signal Detail Modal:**
- Agent source
- Timestamp
- Confidence score
- Supporting evidence
- Related news (if any)
- Risk assessment
- Historical accuracy of similar signals
- **Consensus View** — Aggregated signals from the 3 agents
- **Signal Timeline** — Chronological display of signals
- **Signal Strength Meter** — Display confidence level
- **Signal Comparison** — Compare multiple signals simultaneously
- **Export Signals** — Download as CSV/JSON
- **Signal Notifications** — Get notified of new signals

---

## 5. News & Events

**Recommended Features:**

- **Live News Feed** — Real-time news stream including source, time, and impact
- **Economic Calendar** — Displayed in table or calendar view:
- Date/Time
- Country
- Event
- Impact level
- Actual/Forecast/Previous
- **Countdown Timer** — Countdown for high-impact events
- **News Filter** — Filter by symbol relevance, impact, or category
- **Sentiment Gauge** — Bullish/Bearish meter for each currency
- **Custom Alerts** — Set alerts based on keywords or event types
- **Historical Event Analysis** — Show market reactions to past events
- **News Search** — Search for news by keyword
- **Saved Articles** — Save important articles

---

## 6. Risk Analysis Panel

**Recommended Features:**

- **Risk Dashboard:**
- Current volatility indicators
- VaR (95%, 99%) for reference
- Market regime detection (Trending/Ranging/Volatile)
- Correlation between XAUUSD and BTCUSD
- **Risk Assessment of Signals** — Risk level for each signal
- **Risk Limits Configuration:**
- Volatility threshold
- Correlation threshold
- Event proximity warning
- **Risk Alerts Log** — List of warnings from the Risk Manager
- **Scenario Analysis** — "What-if" simulator showing various scenarios
- **Correlation Matrix** — Show relationships between XAUUSD, BTCUSD, and other assets
- **Volatility Chart** — Display ATR/Historical Volatility
- **Market Regime Chart** — Display market conditions

---

## 7. Performance & Analytics

**Key Features:**

- **Signal Accuracy Chart** — Displays signal accuracy over time
- **Win Rate Analysis** — Percentage of signals that align with market movements
- **Per-Symbol Performance** — Breakdown for XAUUSD and BTCUSD
- **Per-Agent Attribution** — Identifies the most accurate agent
- **Time-based Analysis** — Shows accuracy by hour/day
- **Model Accuracy Chart** — Displays ML model accuracy
- **Confidence vs. Accuracy** — Compares confidence levels against actual accuracy
- **Signal Distribution** — Shows Bullish/Bearish signal distribution
- **Export Reports** — Download reports in PDF/Excel formats

---

## 8. Backtesting

**Key Features:**

- **Strategy Selector** — Select the strategy to test
- **Parameter Configuration** — Configure all parameters
- **Date Range Picker** — Select the testing period
- **Symbol Selector** — XAUUSD, BTCUSD, or both
- **Run Backtest Button**
- **Results Dashboard:**
- Signal accuracy over time
- Win/loss ratio
- Confidence calibration
- Statistics (Sharpe, Sortino, Calmar)
- Monthly accuracy heatmap
- **Compare Mode** — Compare multiple backtests simultaneously
- **Save/Load Preset** — Save configurations
- **Export Results** — Download results

---

## 9. Model Management (AI/ML)

**Key Features:**

- **Model List** — List of available models (LSTM, Transformer, XGBoost)
- **Model Status** — Training/Ready/Deprecated
- **Model Metrics:**
- Accuracy
- Precision/Recall
- F1 Score
- Confusion matrix
- ROC curve
- **Training Panel:**
- Start training button
- Progress bar
- Hyperparameters input
- Dataset selector
- **Model Comparison** — Compare multiple models
- **Deploy/Undeploy Button** — Activate/deactivate model
- **Feature Importance Chart** — Display important features
- **Prediction History** — Prediction history and accuracy
- **Model Versioning** — Manage model versions

---

## 10. User Settings

**Recommended functions:**

- **Profile Management:**
  - Username, Email, Password
  - Two-Factor Authentication
  - Avatar upload
- **API Keys Management:**
  - Add/Edit/Delete API keys
  - Test connection
  - Permission scopes
- **Analysis Preferences:**
  - Default symbol
  - Default timeframe
  - Default indicators
  - Confidence threshold filter
- **Notification Settings:**
  - Email alerts
  - Telegram bot
  - Push notifications
  - Custom alert rules
- **Theme & Layout:**
  - Dark/Light mode
  - Language selector
  - Timezone
  - Number format
- **Security:**
  - Session management
  - Login history
  - IP whitelist

---

## 11. System Monitoring

**Recommended Features:**

- **System Health Panel:**
- CPU/RAM usage
- Network latency
- API response times
- Database connections
- **Agent Heartbeat Monitor** — Shows the active status of each agent
- **API Rate Limit Status** — Displays remaining quota
- **Error Log Viewer** — List of errors with filtering capabilities
- **Uptime Tracker** — System uptime and downtime history
- **Service Status Grid** — Displays the status of all services
- **Data Feed Status** — Shows the status of data sources
---

## 12. Reports

**Required Functions:**

- **Daily Report** — Signals, Accuracy, Events
- **Weekly Report** — Performance summary
- **Monthly Report** — Detailed analytics
- **Custom Report Builder** — Select desired metrics
- **Scheduled Reports** — Automatic email delivery
- **Export Formats** — PDF, Excel, CSV, JSON
- **Signal History Report** — Full signal history
- **Agent Performance Report** — Individual agent reports

---

## 13. Admin Panel (For Admins)

**Required Functions:**

- **User Management** — Add/Edit/Delete users
- **Roles & Permissions** — Admin, Analyst, Viewer
- **Audit Log** — Full activity history
- **System Configuration** — Global settings
- **Backup & Restore** — Database backup
- **Maintenance Mode** — System shutdown for maintenance
- **Feature Flags** — Enable/Disable features

---

## 14. Mobile Responsive Functions

**Recommended Functions:**

- **Mobile Dashboard** — Simplified view optimized for mobile
- **Push Notifications** — Instant notifications when a signal is generated
- **Quick View** — Rapid signal preview
- **Biometric Login** — Face ID / Fingerprint
- **Offline Mode** — Access cached data

---

## 15. Alerts & Notifications

**Recommended Functions:**

- **Alert Builder** — Create alerts based on specific conditions:
- Signal direction
- Confidence threshold
- Specific symbol
- Specific agent
- News event type
- Volatility threshold
- **Alert History** — Log of all past alerts
- **Multi-Channel Delivery:**
- In-app notifications
- Email
- Telegram
- Discord webhook
- SMS
- **Alert Priority Levels** — Low/Medium/High/Critical
- **Do Not Disturb Mode** — Temporarily disable alerts
- **Alert Sound Settings** — Configure alert notification sounds

---

## Summary — Priorities for the MVP

| Priority | Module | Rationale |
|----------|--------|--------|
| **P0** | Dashboard | Essential foundation |
| **P0** | Charts & Analysis | Market and signal visualization |
| **P0** | Signals & Analysis Feed | Core of the AI ​​system |
| **P0** | Agent Control Panel | Agent management |
| **P1** | News & Events | Context for analysis |
| **P1** | Risk Analysis | Risk assessment |
| **P1** | Alerts & Notifications | Signal notifications |
| **P1** | Performance Analytics | Accuracy assessment |
| **P2** | Backtesting | Strategy development |
| **P2** | Model Management | For the AI ​​team |
| **P2** | Reports | For analysis |
| **P3** | Admin Panel | Administration |
| **P3** | Mobile Functions | Convenience/Accessibility |

---

## User Flow Summary

```
1. Access Dashboard → View market status and Agents
↓
2. View Charts → Analyze prices and indicators
↓
3. Check Signals Feed → View latest signals
↓
4. Read News & Events → Understand context
↓
5. Check Risk Analysis → Assess risk
↓
6. View Agent Reasoning → Understand the rationale
↓
7. Make a decision (User decides)
```
