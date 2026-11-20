"""Conservative 5-minute OHLC execution research; no broker order placement."""
import numpy as np
import pandas as pd

MODELS=('E1_FIXED','E2_ATR','E3_ST7_2','E4_ATR_TRAIL','E5_STRUCTURE')

def atr14(df):
    h,l,c=(df[k].astype(float) for k in ('high','low','close'))
    prev=c.shift()
    tr=pd.concat((h-l,(h-prev).abs(),(l-prev).abs()),axis=1).max(axis=1)
    return tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()

def supertrend72(df):
    h,l,c=(df[k].astype(float).to_numpy() for k in ('high','low','close'))
    a=atr14(df).to_numpy(); n=len(df); out=np.zeros(n,dtype=np.int8)
    upper=lower=np.nan; trend=0
    for i in range(n):
        if not np.isfinite(a[i]): continue
        u=(h[i]+l[i])/2+2*a[i]; d=(h[i]+l[i])/2-2*a[i]
        if not np.isfinite(upper): upper,lower,trend=u,d,1
        else:
            old_upper,old_lower=upper,lower
            upper=u if (u<old_upper or c[i-1]>old_upper) else old_upper
            lower=d if (d>old_lower or c[i-1]<old_lower) else old_lower
            if trend==1 and c[i]<old_lower: trend=-1
            elif trend==-1 and c[i]>old_upper: trend=1
        out[i]=trend
    return out

def costs(entry,exit_price,qty,cfg):
    """Explicit research cost approximation, not an exchange-verified tax calculator."""
    turnover=(entry+exit_price)*qty
    if cfg.get('cost_model','bps')=='bps':
        return turnover*float(cfg.get('round_trip_cost_bps',12))/10000
    # Equity intraday approximation: capped brokerage per order + turnover charges + GST.
    buy=entry*qty; sell=exit_price*qty
    brokerage=min(20.,0.0003*buy)+min(20.,0.0003*sell)
    exchange=turnover*float(cfg.get('exchange_fee_rate',0.0000297))
    sebi=turnover*0.000001
    gst=0.18*(brokerage+exchange+sebi)
    stt=sell*float(cfg.get('stt_sell_rate',0.00025))
    stamp=buy*float(cfg.get('stamp_buy_rate',0.00003))
    slippage=turnover*float(cfg.get('slippage_bps',2))/10000
    return brokerage+exchange+sebi+gst+stt+stamp+slippage

def backtest(df,strategy,direction,mask,cfg,symbol,model='E1_FIXED'):
    idx=df.index; n=len(df); sig=mask.fillna(False).to_numpy(dtype=bool)
    opens=df.open.to_numpy(dtype=float); highs=df.high.to_numpy(dtype=float)
    lows=df.low.to_numpy(dtype=float); closes=df.close.to_numpy(dtype=float)
    if '_engine_atr' not in df.attrs: df.attrs['_engine_atr']=atr14(df).to_numpy()
    atr=df.attrs['_engine_atr']
    if model=='E3_ST7_2' and '_engine_st' not in df.attrs: df.attrs['_engine_st']=supertrend72(df)
    st=df.attrs.get('_engine_st') if model=='E3_ST7_2' else None
    sign=1 if direction=='LONG' else -1
    cooldown=int(cfg.get('cooldown_bars',3)); daily_limit=int(cfg.get('max_trades_per_symbol_day',3))
    min_time=str(cfg.get('first_signal_time','09:30')); max_time=str(cfg.get('last_signal_time','14:40'))
    trades=[]; i=0; day_count={}
    while i<n-1:
        # Only a fresh False -> True event is eligible; no repeated level-state entries.
        if not sig[i] or (i>0 and sig[i-1]): i+=1; continue
        day=idx[i].date(); t=idx[i].strftime('%H:%M')
        if t<min_time or t>max_time or day_count.get(day,0)>=daily_limit: i+=1; continue
        j=i+1
        if idx[j].date()!=day or idx[j].strftime('%H:%M')>'14:45': i+=1; continue
        entry=opens[j]; a=atr[i]
        if not np.isfinite(entry) or entry<=0 or not np.isfinite(a) or a<=0: i+=1; continue
        qty=min(int(float(cfg['per_trade_capital'])//entry),int(float(cfg.get('capital',cfg['per_trade_capital']))//entry))
        if qty<1: i+=1; continue
        if model=='E1_FIXED': risk=entry*float(cfg['stop_pct']); reward=entry*float(cfg['target_pct'])
        elif model in ('E2_ATR','E3_ST7_2','E4_ATR_TRAIL'):
            risk=1.5*a; reward=2.5*a if model=='E2_ATR' else float('inf')
        elif model=='E5_STRUCTURE':
            lookback=int(cfg.get('structure_lookback',10))
            prior=lows[max(0,i-lookback+1):i+1] if sign==1 else highs[max(0,i-lookback+1):i+1]
            level=np.nanmin(prior) if sign==1 else np.nanmax(prior)
            risk=entry-level if sign==1 else level-entry
            if risk<=0 or risk>3*a: i+=1; continue
            reward=2*risk
        else: raise ValueError(model)
        if risk<=0: i+=1; continue
        stop=entry-sign*risk; target=entry+sign*reward
        last=j; exit_price=closes[j]; reason='TIME'; max_bars=int(cfg.get('max_bars',24))
        for k in range(j,min(j+max_bars,n)):
            if idx[k].date()!=day: break
            last=k; o=opens[k]; hi=highs[k]; lo=lows[k]; close=closes[k]
            # Gap-through protection: do not fill stops at a better price than the open.
            if (o<=stop if sign==1 else o>=stop): exit_price=o; reason='STOP_GAP'; break
            if (o>=target if sign==1 else o<=target): exit_price=o; reason='TARGET_GAP'; break
            if (lo<=stop if sign==1 else hi>=stop): exit_price=stop; reason='STOP'; break
            if (hi>=target if sign==1 else lo<=target): exit_price=target; reason='TARGET'; break
            exit_price=close
            # Signal from the completed candle can only execute at NEXT candle's open.
            if model=='E3_ST7_2' and st[k]==-sign and k+1<n and idx[k+1].date()==day:
                last=k+1; exit_price=opens[k+1]; reason='ST_REVERSAL'; break
            if model=='E4_ATR_TRAIL' and np.isfinite(atr[k]):
                # Update after close, never use current candle's high to retroactively tighten.
                candidate=close-sign*1.5*atr[k]
                stop=max(stop,candidate) if sign==1 else min(stop,candidate)
            if idx[k].strftime('%H:%M')>='15:15': reason='EOD'; break
        gross=sign*(exit_price-entry)*qty; cost=costs(entry,exit_price,qty,cfg)
        trades.append(dict(symbol=symbol,strategy=strategy,direction=direction,exit_model=model,
            signal_time=str(idx[i]),entry_time=str(idx[j]),exit_time=str(idx[last]),
            entry=round(entry,4),exit=round(exit_price,4),qty=qty,
            gross=round(gross,2),estimated_cost=round(cost,2),net=round(gross-cost,2),exit_reason=reason))
        day_count[day]=day_count.get(day,0)+1
        i=last+cooldown+1
    return trades

def portfolio_replay(t,cfg):
    """Independent portfolio per (strategy,exit_model), shared across stocks and directions."""
    if t.empty: return t.copy()
    selected=[]; capital=float(cfg.get('capital',cfg['per_trade_capital'])); slots=int(cfg.get('max_concurrent_positions',4))
    for _,group in t.groupby(['strategy','exit_model'],sort=False):
        active=[]
        for r in group.sort_values(['entry_time','symbol','direction']).itertuples(index=False):
            # Release capital for trades completed strictly BEFORE new entry.
            active=[a for a in active if a[0]>=r.entry_time]
            required=r.entry*r.qty
            if len(active)>=slots or sum(a[1] for a in active)+required>capital+1e-8: continue
            active.append((r.exit_time,required)); selected.append(r._asdict())
    return pd.DataFrame(selected,columns=t.columns)
