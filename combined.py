"""Six independent, 5-minute-only composite research strategies.
Signal at completed candle t; lab.py enters at next candle open.
These are experimental adaptations, not proven profitable rules.
"""
import numpy as np
import pandas as pd

def ema(x,n): return x.ewm(span=n,adjust=False,min_periods=n).mean()
def cross_up(a,b): return (a>b)&(a.shift(1)<=b.shift(1))
def cross_dn(a,b): return (a<b)&(a.shift(1)>=b.shift(1))

def composite_signals(df):
    c,h,l,v=[df[k].astype(float) for k in ('close','high','low','volume')]
    o=df['open'].astype(float)
    dates=pd.Series(df.index.date,index=df.index)
    slot=df.groupby(dates).cumcount()
    e9,e21,e50,e20=ema(c,9),ema(c,21),ema(c,50),ema(c,20)
    d=c.diff(); gain=d.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    loss=(-d.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rs=gain/loss.replace(0,np.nan)
    rsi=100-100/(1+rs)
    rsi=rsi.where(loss.ne(0),100).where(~((loss==0)&(gain==0)),50)
    macd=ema(c,12)-ema(c,26); macsig=ema(macd,9)
    volume_ref=v.shift(1).rolling(20,min_periods=20).mean()
    vol_ok=v>1.5*volume_ref
    pv=(h+l+c)/3*v
    vw=pv.groupby(dates).cumsum()/v.groupby(dates).cumsum().replace(0,np.nan)
    hi20=h.shift(1).rolling(20,min_periods=20).max()
    lo20=l.shift(1).rolling(20,min_periods=20).min()
    # Opening range only available after the third 5-minute bar completes.
    orb_hi=h.where(slot<3).groupby(dates).transform('max')
    orb_lo=l.where(slot<3).groupby(dates).transform('min')
    daily=df.groupby(dates).agg({'high':'max','low':'min'})
    pdh=dates.map(daily.high.shift(1)); pdl=dates.map(daily.low.shift(1))
    mid=c.rolling(20,min_periods=20).mean(); sd=c.rolling(20,min_periods=20).std()
    upper=mid+2*sd; lower=mid-2*sd
    # Standard 10,3 supertrend (persistent bands, no artificial daily reset).
    tr=pd.concat([h-l,(h-c.shift(1)).abs(),(l-c.shift(1)).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/10,adjust=False,min_periods=10).mean()
    ub=(h+l)/2+3*atr; lb=(h+l)/2-3*atr
    st_dir=np.zeros(len(c),dtype=np.int8)
    fu=fl=np.nan; direction=1
    for i in range(len(c)):
        if not np.isfinite(ub.iat[i]): continue
        if not np.isfinite(fu): fu=ub.iat[i]; fl=lb.iat[i]
        else:
            pc=c.iat[i-1]
            prev_fu,prev_fl=fu,fl
            fu=ub.iat[i] if ub.iat[i]<prev_fu or pc>prev_fu else prev_fu
            fl=lb.iat[i] if lb.iat[i]>prev_fl or pc<prev_fl else prev_fl
            if direction==1 and c.iat[i]<prev_fl: direction=-1
            elif direction==-1 and c.iat[i]>prev_fu: direction=1
        st_dir[i]=direction
    st=pd.Series(st_dir,index=c.index)
    uptrend=(e9>e21)&(e21>e50)
    downtrend=(e9<e21)&(e21<e50)
    results={
        'C1_Trend_Donchian':(uptrend&(rsi>55)&cross_up(c,hi20)&vol_ok,
                              downtrend&(rsi<45)&cross_dn(c,lo20)&vol_ok),
        'C2_ST_Momentum':((st==1)&(rsi>55)&(macd>macsig)&cross_up(c,vw),
                          (st==-1)&(rsi<45)&(macd<macsig)&cross_dn(c,vw)),
        'C3_ORB_Volume':((slot>=3)&(e9>e21)&(rsi>55)&vol_ok&cross_up(c,orb_hi),
                         (slot>=3)&(e9<e21)&(rsi<45)&vol_ok&cross_dn(c,orb_lo)),
        'C4_PDH_MACD':(uptrend&(macd>macsig)&vol_ok&cross_up(c,pdh),
                       downtrend&(macd<macsig)&vol_ok&cross_dn(c,pdl)),
        'C5_VWAP_Pullback':(uptrend&(rsi>50)&cross_up(c,vw)&(c>o),
                            downtrend&(rsi<50)&cross_dn(c,vw)&(c<o)),
        'C6_BB_Reversion':((c.shift(1)<lower.shift(1))&cross_up(c,lower)&(rsi<45)&(c<e20),
                           (c.shift(1)>upper.shift(1))&cross_dn(c,upper)&(rsi>55)&(c>e20))
    }
    return {k:(a.fillna(False),b.fillna(False)) for k,(a,b) in results.items()}
