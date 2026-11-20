# Indian 15 Strategy Backtesting Lab

Research-only backtester: 15 independent signal sets, both directions, completed 5-minute bars, next-bar open entry, same-day exits, simulated fixed stops and targets. Generates `reports/coverage.csv`, `trades.csv`, `ranking.csv`, and `monthly.csv`.

## Run on GitHub
1. Create a **private** GitHub repository and upload the contents of this folder, including `.github/workflows/backtest.yml`.
2. In repository Settings > Secrets and variables > Actions, add `DHAN_ACCESS_TOKEN` (and `DHAN_CLIENT_ID` if needed by future extensions). Never put credentials in code or CSV.
3. Verify every `security_id` in `instruments.csv` against the current Dhan instrument master before using it. These are initial mappings, not guaranteed permanent IDs.
4. Edit `config.json` for symbols and dates. Dhan historical 5-minute access is limited to **up to 5 years**, in requests covering at most 90 days; the script uses 85-day windows. Historical instrument eligibility and gaps are **not reconstructed** in this starter.
5. Open Actions > 15 Strategy Backtest > Run workflow. Download `backtest-results` artifact.
6. For quick Yahoo testing, select `yahoo`; Yahoo intraday history is only about 60 days, NOT 10 years.

## Local execution
`pip install -r requirements.txt`
`python lab.py --provider yahoo`
`python lab.py --provider dhan --start 2024-01-01 --end 2026-11-20`

## Limitations you must understand
- **Not 10-year 5-minute history.** To study 2016–2026, obtain licensed archival intraday data. Never extrapolate five years to ten.
- This tests **underlying stock prices**, not option CE/PE premiums or actual futures positions. Index constituents need tradable futures/option mappings before actual trading P&L is possible.
- The 10 tickers are a liquid large-cap **starter basket**, not a verified current top-ten by traded volume.
- This is a basic research prototype: fixed stop 0.75%, target 1.5%, max 24 bars, next bar open. If stop and target are both touched in one candle, it assumes stop first. Gap-through-stop and intrabar fills are simplified and need a tick-level execution simulator for realistic results.
- Costs are an **assumed combined round-trip basis-point proxy** (12 bps by default), not a historical Zerodha/Dhan statutory fee engine.
- The 15 strategies are partly adaptations inspired by the paper, not all exact reproductions. Some indicator rules and Supertrend implementation need comparison with Streak/Dhan reference charts before use.
- Signals are calculated per stock; independent per-strategy tests do not enforce shared portfolio capital, maximum simultaneous positions or margin.
- There is no train/test split or walk-forward selection in this starter; rankings are exploratory and cannot prove future profitability.
- No automatic live orders are placed.
- This version uses 10 configured symbols; for all F&O stocks, first build and validate a historical dated universe and rate-limited data ingestion pipeline.


### Fix: instrument mapping
`instruments.csv` contains stock symbols. When running with `dhan`, the program now downloads Dhan's public scrip master and resolves current NSE equity security IDs automatically. When running with `yahoo`, it creates `.NS` symbols automatically. If the Dhan scrip master schema or URL changes, the run will report a mapping error instead of inventing IDs.

**Limits:** This is an underlying-equity research prototype. Historical membership, actual options premium P&L, verified fee schedules and full ten-year intraday data are not included. The configured cost is an illustrative estimate.

## NEW: Six 5-minute composite strategies

The original 15 strategies remain unchanged and are evaluated alongside six additional
composites in `combined.py` (21 strategy names, LONG and SHORT separately):

| ID | Long signal at completed 5-minute candle | Short signal |
|---|---|---|
| C1_Trend_Donchian | EMA9>EMA21>EMA50, RSI14>55, close crosses above prior 20-bar high, volume>1.5x prior 20-bar average | Mirror, RSI<45, prior 20-bar low |
| C2_ST_Momentum | Supertrend(10,3) bullish, RSI>55, MACD>signal, price crosses above session VWAP | Mirror bearish |
| C3_ORB_Volume | After first 3 five-minute bars, EMA9>EMA21, RSI>55, 1.5x volume, close crosses opening 15-minute high | Mirror opening low |
| C4_PDH_MACD | EMA9>EMA21>EMA50, MACD>signal, 1.5x volume, close crosses previous-day high | Mirror previous-day low |
| C5_VWAP_Pullback | EMA9>EMA21>EMA50, RSI>50, bullish candle crosses session VWAP | Mirror bearish |
| C6_BB_Reversion | Previous close below prior lower BB(20,2), close crosses back above lower band, RSI<45, below EMA20 | Mirror upper band, RSI>55, above EMA20 |

All signal bars use only information known by their close. Existing `lab.py` enters at
next bar's open and simulates 0.75% underlying stops, 1.5% underlying targets, 24-bar
maximum holding and 12 bps round-trip modeled costs as configured in `config.json`.
These are *experimental hypotheses*, not proven profit strategies. They do not model
real option premiums, actual bid-ask spreads, slippage or historical broker fee changes.

### How to run
Upload **all files** in this ZIP to the repository root, including `combined.py`,
`test_combinations.py`, `lab.py`, and `.github/workflows/backtest.yml`.
Keep your existing GitHub `DHAN_ACCESS_TOKEN` secret. Open Actions and run the workflow.
The workflow runs a local smoke test before requesting Dhan data, then exports the same
four reports (`ranking.csv`, `trades.csv`, `monthly.csv`, `coverage.csv`) with both
original and composite strategy names. A successful workflow does not prove profitability.

### Research cautions
- `ranking.csv` sums independent simulations; it is not a capital-constrained portfolio.
- The existing 15 strategies have their original definitions and may have methodological
  weaknesses; the six new strategies have not been independently verified against a
  reference implementation.
- Dhan intraday history and current instrument-master mapping can have coverage gaps.
- Use net profit **per trade**, profit factor, drawdown and out-of-sample periods,
  not simply total net profit, to compare low-frequency composite strategies.
- There is no automatic live order placement.


## NEW: Six seven-filter combinations (A1–A6)
All use **5-minute candles only**, with completed-bar signals and next-bar entry.
Filters: EMA trend, RSI/MACD momentum, ADX/+DI/-DI strength, prior-20-bar relative volume, ATR volatility, VWAP/CPR/previous-day location, and an entry trigger.

- A1: Trend + 20-bar channel breakout
- A2: Trend + first 15-minute opening range breakout (formed from three 5-minute bars)
- A3: Trend + previous-day high/low and CPR location
- A4: VWAP reclaim/rejection + EMA + RSI + MACD
- A5: Strong momentum + 10-bar breakout
- A6: Range regime (ADX <20) + Bollinger re-entry (intentionally different regime)

The original 15 strategies and previous six combined strategies remain. The output now contains 27 strategy IDs (54 direction combinations). Some combinations may produce zero trades. Do not loosen filters simply to manufacture signals. No historical profitability has been validated. The current engine models underlying share-equivalent trades, not options, and has simplified transaction costs and no shared portfolio capital allocation.
