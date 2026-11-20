import argparse, json, os, time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).parent
DATA=ROOT/'data'; OUT=ROOT/'reports'
DATA.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)

def resolve_dhan_instruments(instruments):
    """Resolve missing Dhan security IDs from the official public scrip master."""
    needed={'security_id','exchange_segment','instrument'}
    if needed.issubset(instruments.columns) and instruments['security_id'].notna().all():
        return instruments
    url='https://images.dhan.co/api-data/api-scrip-master.csv'
    try:
        master=pd.read_csv(url,low_memory=False,dtype=str)
    except Exception as exc:
        raise RuntimeError(f'Cannot download Dhan instrument master: {exc}') from exc
    required={'SEM_EXM_EXCH_ID','SEM_SEGMENT','SEM_SMST_SECURITY_ID','SEM_TRADING_SYMBOL','SEM_INSTRUMENT_NAME'}
    missing=required-set(master.columns)
    if missing:
        raise RuntimeError(f'Dhan instrument master format changed: missing {sorted(missing)}')
    master=master[(master['SEM_EXM_EXCH_ID']=='NSE') & (master['SEM_SEGMENT']=='E')].copy()
    master['match_symbol']=master['SEM_TRADING_SYMBOL'].astype(str).str.strip().str.upper()
    master=master.drop_duplicates('match_symbol').set_index('match_symbol')
    for symbol in instruments.index:
        if symbol not in master.index:
            print(f'WARNING: {symbol} missing from current Dhan NSE equity instrument master',flush=True)
            continue
        item=master.loc[symbol]
        instruments.loc[symbol,'security_id']=str(item['SEM_SMST_SECURITY_ID']).strip()
        instruments.loc[symbol,'exchange_segment']='NSE_EQ'
        instruments.loc[symbol,'instrument']='EQUITY'
    return instruments

def fetch_dhan(row, start, end):
    token=os.environ.get('DHAN_ACCESS_TOKEN')
    if not token: raise RuntimeError('Set DHAN_ACCESS_TOKEN in GitHub Secrets or environment')
    url='https://api.dhan.co/v2/charts/intraday'
    parts=[]
    # API supports maximum 90 days per call; use 85-day windows
    for a in pd.date_range(start, end, freq='85D'):
        b=min(a+pd.Timedelta(days=85), pd.Timestamp(end)+pd.Timedelta(days=1))
        payload={'securityId':str(row.security_id),'exchangeSegment':row.exchange_segment,
                 'instrument':row.instrument,'interval':'5','oi':False,
                 'fromDate':a.strftime('%Y-%m-%d 00:00:00'),
                 'toDate':b.strftime('%Y-%m-%d 00:00:00')}
        for attempt in range(5):
            r=requests.post(url,headers={'access-token':token,'Content-Type':'application/json','Accept':'application/json'},json=payload,timeout=50)
            if r.ok: break
            if r.status_code in (429,500,502,503,504): time.sleep(2**attempt); continue
            raise RuntimeError(f'Dhan error {r.status_code}: {r.text[:250]}')
        r.raise_for_status(); x=r.json()
        if 'timestamp' not in x: raise RuntimeError(f'Unexpected Dhan response: {str(x)[:250]}')
        if x['timestamp']:
            z=pd.DataFrame({k:x[k] for k in ('timestamp','open','high','low','close','volume')})
            z['datetime']=pd.to_datetime(z.pop('timestamp'),unit='s',utc=True).dt.tz_convert('Asia/Kolkata')
            parts.append(z)
        time.sleep(.35)
    if not parts: return pd.DataFrame()
    return pd.concat(parts).drop_duplicates('datetime').set_index('datetime').sort_index()

def fetch_yahoo(row):
    import yfinance as yf
    x=yf.download(row.yahoo_symbol,period='59d',interval='5m',progress=False,auto_adjust=False)
    if isinstance(x.columns,pd.MultiIndex): x.columns=x.columns.get_level_values(0)
    x=x.rename(columns=str.lower)
    if x.index.tz is None: x.index=x.index.tz_localize('UTC')
    x.index=x.index.tz_convert('Asia/Kolkata')
    return x[['open','high','low','close','volume']]

def ema(s,n): return s.ewm(span=n,adjust=False,min_periods=n).mean()
def sma(s,n): return s.rolling(n,min_periods=n).mean()
def crossup(a,b): return (a>b)&(a.shift(1)<=b.shift(1))
def crossdn(a,b): return (a<b)&(a.shift(1)>=b.shift(1))

def signals(df):
    c,h,l,v=(df[k].astype(float) for k in ('close','high','low','volume'))
    e9,e21,e50=ema(c,9),ema(c,21),ema(c,50)
    m3,m10,m20,m21=sma(c,3),sma(c,10),sma(c,20),sma(c,21)
    d=c.diff(); up=d.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    down=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=100-100/(1+up/down.replace(0,np.nan))
    date=pd.Series(df.index.date,index=df.index)
    daily=df.groupby(date).agg({'high':'max','low':'min','close':'last'})
    prev=daily.shift(1); ph=date.map(prev['high']); pl=date.map(prev['low']); pc=date.map(prev['close'])
    pivot=(ph+pl+pc)/3
    # First three 5-minute candles, levels only become available from 09:30
    slots=df.groupby(date).cumcount()
    opening_hi=h.where(slots<3).groupby(date).transform('max')
    opening_lo=l.where(slots<3).groupby(date).transform('min')
    upper=h.shift(1).rolling(20).max(); lower=l.shift(1).rolling(20).min()
    mid=sma(c,20); std=c.rolling(20).std(); bu=mid+2*std; bl=mid-2*std
    typical=(h+l+c)/3
    vwap=(typical*v).groupby(date).cumsum()/v.groupby(date).cumsum().replace(0,np.nan)
    macd=ema(c,12)-ema(c,26); macsig=ema(macd,9)
    tr=pd.concat([h-l,(h-c.shift()).abs(),(l-c.shift()).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/10,adjust=False,min_periods=10).mean()
    hl2=(h+l)/2; basic_up=hl2+3*atr; basic_dn=hl2-3*atr
    # Stateful supertrend bands, reset per session to avoid cross-session gap distortion
    st=pd.Series(np.nan,index=df.index); trend=pd.Series(0,index=df.index,dtype=int)
    last_day=None; fu=fl=previous_close=np.nan; direction=1
    for i,(ts,hi,lo,cl,bu0,bd0) in enumerate(zip(df.index,h,l,c,basic_up,basic_dn)):
        if not np.isfinite(bu0): continue
        if ts.date()!=last_day:
            fu,fl,direction=bu0,bd0,1; last_day=ts.date()
        else:
            fu=bu0 if (bu0<fu or previous_close>fu) else fu
            fl=bd0 if (bd0>fl or previous_close<fl) else fl
            if direction==1 and cl<fl: direction=-1
            elif direction==-1 and cl>fu: direction=1
        st.iloc[i]=fl if direction==1 else fu; trend.iloc[i]=direction
        previous_close=cl
    prevtrend=trend.shift(1)
    setups={
      '01_EMA_9_21':(crossup(e9,e21)&(c>e50),crossdn(e9,e21)&(c<e50)),
      '02_Triple_SMA':((m3>m10)&(m10>m21)&~((m3.shift(1)>m10.shift(1))&(m10.shift(1)>m21.shift(1))),
                       (m3<m10)&(m10<m21)&~((m3.shift(1)<m10.shift(1))&(m10.shift(1)<m21.shift(1)))),
      '03_SMA20_Cross':(crossup(c,m20),crossdn(c,m20)),
      '04_Daily_Pivot':(crossup(c,pivot),crossdn(c,pivot)),
      '05_Prev_Day_Break':(crossup(c,ph),crossdn(c,pl)),
      '06_ORB_15min':(crossup(c,opening_hi)&(slots>=3),crossdn(c,opening_lo)&(slots>=3)),
      '07_Donchian_Break':((c>upper)&(c.shift(1)<=upper.shift(1)),(c<lower)&(c.shift(1)>=lower.shift(1))),
      '08_Donchian_Reversal':((l<=lower)&(c>df.open), (h>=upper)&(c<df.open)),
      '09_RSI_Reversion':(crossup(rsi,pd.Series(30.,index=c.index)),crossdn(rsi,pd.Series(70.,index=c.index))),
      '10_BB_Reentry':((c.shift(1)<bl.shift(1))&crossup(c,bl),(c.shift(1)>bu.shift(1))&crossdn(c,bu)),
      '11_Supertrend':((trend==1)&(prevtrend==-1),(trend==-1)&(prevtrend==1)),
      '12_EMA_RSI':((e9>e21)&crossup(rsi,pd.Series(55.,index=c.index)),(e9<e21)&crossdn(rsi,pd.Series(45.,index=c.index))),
      '13_VWAP_RSI':(crossup(c,vwap)&(rsi>50),crossdn(c,vwap)&(rsi<50)),
      '14_MACD_EMA':(crossup(macd,macsig)&(c>e50),crossdn(macd,macsig)&(c<e50)),
      '15_Volume_PDH':(crossup(c,ph)&(v>1.5*sma(v,20)),crossdn(c,pl)&(v>1.5*sma(v,20)))
    }
    return setups

def backtest(df, strategy, direction, mask, cfg, symbol):
    # Signal at close of bar i, entry at OPEN of bar i+1. No overnight positions.
    # Stops/targets tested against high/low; if both hit same bar assume stop first.
    trades=[]; idx=df.index; mask=mask.fillna(False).to_numpy(); n=len(df)
    i=0
    while i<n-1:
        if not mask[i] or idx[i].strftime('%H:%M')<'09:30' or idx[i].strftime('%H:%M')>'14:40': i+=1; continue
        j=i+1
        if idx[j].date()!=idx[i].date() or idx[j].strftime('%H:%M')>'14:45': i+=1; continue
        entry=float(df.open.iloc[j]); sign=1 if direction=='LONG' else -1
        if not np.isfinite(entry) or entry<=0: i+=1; continue
        qty=int(float(cfg['per_trade_capital'])//entry)
        if qty<1: i+=1; continue
        stop=entry*(1-sign*cfg['stop_pct']); target=entry*(1+sign*cfg['target_pct'])
        last=j; reason='TIME'; exit_price=float(df.close.iloc[j])
        for k in range(j,min(j+int(cfg['max_bars']),n)):
            if idx[k].date()!=idx[j].date(): break
            hi=float(df.high.iloc[k]); lo=float(df.low.iloc[k]); close=float(df.close.iloc[k]); last=k
            stop_hit=(lo<=stop if sign==1 else hi>=stop)
            target_hit=(hi>=target if sign==1 else lo<=target)
            if stop_hit:
                exit_price=stop; reason='STOP'; break
            if target_hit:
                exit_price=target; reason='TARGET'; break
            exit_price=close
            if idx[k].strftime('%H:%M')>='15:15': reason='EOD'; break
        gross=sign*(exit_price-entry)*qty
        cost=(entry+exit_price)*qty*cfg['round_trip_cost_bps']/10000
        trades.append(dict(symbol=symbol,strategy=strategy,direction=direction,entry_time=str(idx[j]),exit_time=str(idx[last]),entry=entry,exit=exit_price,qty=qty,gross=round(gross,2),estimated_cost=round(cost,2),net=round(gross-cost,2),exit_reason=reason))
        i=last+1
    return trades

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--provider',choices=['dhan','yahoo']); ap.add_argument('--start'); ap.add_argument('--end'); ap.add_argument('--symbols'); args=ap.parse_args()
    cfg=json.loads((ROOT/'config.json').read_text()); provider=args.provider or cfg['provider']; start=args.start or cfg['start']; end=args.end or cfg['end']
    instruments=pd.read_csv(ROOT/'instruments.csv',dtype=str).set_index('symbol')
    if provider=='dhan':
        instruments=resolve_dhan_instruments(instruments)
    if provider=='yahoo' and 'yahoo_symbol' not in instruments.columns:
        instruments['yahoo_symbol']=instruments.index.astype(str)+'.NS'
    symbols=args.symbols.split(',') if args.symbols else cfg['symbols']
    trades=[]; coverage=[]
    for sym in symbols:
        if sym not in instruments.index:
            coverage.append(dict(symbol=sym,status='NOT_MAPPED')); continue
        row=instruments.loc[sym]
        try:
            if provider=='dhan' and (pd.isna(row.get('security_id')) or not str(row.get('security_id')).strip()):
                raise ValueError('Security ID unavailable in Dhan instrument master')
            cache=DATA/f'{sym}_{provider}.csv'
            if cache.exists():
                old=pd.read_csv(cache,index_col=0,parse_dates=True)
            else: old=pd.DataFrame()
            new=fetch_dhan(row,start,end) if provider=='dhan' else fetch_yahoo(row)
            df=pd.concat([old,new]).loc[lambda d:~d.index.duplicated(keep='last')].sort_index()
            df=df.loc[(df.index>=pd.Timestamp(start,tz='Asia/Kolkata'))&(df.index<pd.Timestamp(end,tz='Asia/Kolkata')+pd.Timedelta(days=1))]
            if df.empty: raise ValueError('No candles returned')
            df.to_csv(cache)
            coverage.append(dict(symbol=sym,status='OK',first=str(df.index.min()),last=str(df.index.max()),bars=len(df)))
            for strategy,(bull,bear) in signals(df).items():
                for direction,mask in [('LONG',bull),('SHORT',bear)]:
                    trades+=backtest(df,strategy,direction,mask,cfg,sym)
            print(sym,len(df),'candles',flush=True)
        except Exception as ex:
            coverage.append(dict(symbol=sym,status='ERROR',message=str(ex)[:250])); print(sym,'ERROR',ex,flush=True)
    pd.DataFrame(coverage).to_csv(OUT/'coverage.csv',index=False)
    if not trades:
        print('No trades generated. Inspect coverage.csv.'); return
    t=pd.DataFrame(trades); t.to_csv(OUT/'trades.csv',index=False)
    rows=[]
    for (strategy,direction),g in t.groupby(['strategy','direction']):
        win=g[g.net>0].net.sum(); loss=-g[g.net<0].net.sum()
        eq=g.net.cumsum(); dd=(eq-eq.cummax()).min()
        rows.append(dict(strategy=strategy,direction=direction,trades=len(g),win_rate_pct=round(100*(g.net>0).mean(),2),net_profit=round(g.net.sum(),2),profit_factor=round(win/loss,3) if loss else None,max_drawdown_rupees=round(dd,2),estimated_cost=round(g.estimated_cost.sum(),2)))
    pd.DataFrame(rows).sort_values('net_profit',ascending=False).to_csv(OUT/'ranking.csv',index=False)
    t.assign(month=t.entry_time.str[:7]).groupby(['strategy','direction','month'],as_index=False).net.sum().to_csv(OUT/'monthly.csv',index=False)
    print('Reports saved under reports/. This is underlying-price research, NOT option premium P&L.')
if __name__=='__main__': main()
