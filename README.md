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
