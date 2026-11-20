"""Six multi-family 5-minute research signals. All values known at completed signal bar."""
import numpy as np
import pandas as pd

def ema(s,n): return s.ewm(span=n,adjust=False,min_periods=n).mean()
def cross_up(a,b): return (a>b)&(a.shift(1)<=b.shift(1))
def cross_dn(a,b): return (a<b)&(a.shift(1)>=b.shift(1))

def advanced_signals(df):
    c,h,l,o,v=[df[k].astype(float) for k in ('close','high','low','open','volume')]
    day=pd.Series(df.index.date,index=df.index)
    slot=df.groupby(day).cumcount()
    e9,e21,e50,e200=[ema(c,n) for n in (9,21,50,200)]
    delta=c.diff(); gain=delta.clip(lower=0).ewm(alpha=1/14,adjust=False,min_periods=14).mean(); loss=(-delta.clip(upper=0)).ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    rsi=(100-100/(1+gain/loss.replace(0,np.nan))).where(loss.ne(0),100).where(~((gain==0)&(loss==0)),50)
    macd=ema(c,12)-ema(c,26); macds=ema(macd,9)
    prev=c.shift(1); tr=pd.concat([h-l,(h-prev).abs(),(l-prev).abs()],axis=1).max(axis=1)
    atr=tr.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    plus=h.diff().clip(lower=0); minus=(-l.diff()).clip(lower=0)
    plus=plus.where(plus>minus,0); minus=minus.where(minus>plus,0)
    plusdi=100*plus.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr.replace(0,np.nan)
    minusdi=100*minus.ewm(alpha=1/14,adjust=False,min_periods=14).mean()/atr.replace(0,np.nan)
    dx=100*(plusdi-minusdi).abs()/(plusdi+minusdi).replace(0,np.nan)
    adx=dx.ewm(alpha=1/14,adjust=False,min_periods=14).mean()
    relvol=v/v.shift(1).rolling(20,min_periods=20).mean().replace(0,np.nan)
    vwap=((h+l+c)/3*v).groupby(day).cumsum()/v.groupby(day).cumsum().replace(0,np.nan)
    d=df.groupby(day).agg({'high':'max','low':'min','close':'last'})
    prevday=d.shift(1)
    ph=day.map(prevday.high); pl=day.map(prevday.low); pc=day.map(prevday.close)
    pivot=(ph+pl+pc)/3; bc=(ph+pl)/2; tc=2*pivot-bc
    top=pd.concat([bc,tc],axis=1).max(axis=1); bottom=pd.concat([bc,tc],axis=1).min(axis=1)
    # Opening range values only referenced once three completed bars exist
    orbhi=h.where(slot<3).groupby(day).transform('max'); orblo=l.where(slot<3).groupby(day).transform('min')
    chhi=h.shift(1).rolling(20,min_periods=20).max(); chlo=l.shift(1).rolling(20,min_periods=20).min()
    mid=c.rolling(20,min_periods=20).mean(); std=c.rolling(20,min_periods=20).std(); bu=mid+2*std; bl=mid-2*std
    up=(e9>e21)&(e21>e50)&(c>e200)&(c>vwap)&(plusdi>minusdi)
    dn=(e9<e21)&(e21<e50)&(c<e200)&(c<vwap)&(minusdi>plusdi)
    strength=adx>20; participation=relvol>1.2
    # Each combination uses trend, strength, momentum, volume, location, volatility and trigger.
    ready=(slot>=3)&(atr/c>0.001)&(atr/c<0.04)&strength&participation
    setups={
      'A1_Trend_Channel_7Filters':(ready&up&(rsi>55)&(rsi<75)&cross_up(c,chhi),ready&dn&(rsi<45)&(rsi>25)&cross_dn(c,chlo)),
      'A2_ORB_7Filters':(ready&up&(rsi>55)&cross_up(c,orbhi),ready&dn&(rsi<45)&cross_dn(c,orblo)),
      'A3_PDH_CPR_7Filters':(ready&up&(rsi>55)&(c>top)&cross_up(c,ph),ready&dn&(rsi<45)&(c<bottom)&cross_dn(c,pl)),
      'A4_VWAP_Retest_7Filters':(ready&(e9>e21)&(c>e50)&(plusdi>minusdi)&(rsi>52)&(macd>macds)&cross_up(c,vwap),ready&(e9<e21)&(c<e50)&(minusdi>plusdi)&(rsi<48)&(macd<macds)&cross_dn(c,vwap)),
      'A5_Momentum_7Filters':(ready&up&(rsi>58)&(rsi<75)&(macd>macds)&cross_up(c,h.shift(1).rolling(10).max()),ready&dn&(rsi<42)&(rsi>25)&(macd<macds)&cross_dn(c,l.shift(1).rolling(10).min())),
      # Reversion uses opposite regime filters intentionally; do not mix with trend setups.
      'A6_Range_Reversion_7Filters':((slot>=3)&(adx<20)&(relvol>0.8)&(atr/c>0.001)&(atr/c<0.04)&(rsi<42)&(c<vwap)&(prev<bl.shift(1))&cross_up(c,bl),
                                     (slot>=3)&(adx<20)&(relvol>0.8)&(atr/c>0.001)&(atr/c<0.04)&(rsi>58)&(c>vwap)&(prev>bu.shift(1))&cross_dn(c,bu))
    }
    return {k:(a.fillna(False).astype(bool),b.fillna(False).astype(bool)) for k,(a,b) in setups.items()}
