import unittest
import numpy as np
import pandas as pd
from combined import composite_signals
from lab import signals, backtest

class SmokeTest(unittest.TestCase):
    def test_signals_and_execution(self):
        rng=np.random.default_rng(11)
        dates=pd.bdate_range('2026-10-05',periods=8)
        idx=pd.DatetimeIndex([pd.Timestamp(d.date(),tz='Asia/Kolkata')+pd.Timedelta(hours=9,minutes=15)+pd.Timedelta(minutes=5*i) for d in dates for i in range(75)])
        close=100+np.cumsum(rng.normal(.015,.3,len(idx)))
        op=np.r_[close[0],close[:-1]]
        df=pd.DataFrame({'open':op,'high':np.maximum(op,close)+.1,'low':np.minimum(op,close)-.1,'close':close,'volume':rng.integers(1000,10000,len(idx))},index=idx)
        combos=composite_signals(df)
        self.assertEqual(len(combos),6)
        all_s=signals(df)
        self.assertEqual(len(all_s),27)
        for name,(bull,bear) in combos.items():
            self.assertTrue(bull.index.equals(df.index))
            self.assertFalse(bull.isna().any())
            self.assertFalse(bear.isna().any())
            self.assertFalse((bull&bear).any())
            cfg={'per_trade_capital':25000,'stop_pct':.0075,'target_pct':.015,'max_bars':24,'round_trip_cost_bps':12}
            for direction,mask in [('LONG',bull),('SHORT',bear)]:
                for t in backtest(df,name,direction,mask,cfg,'TEST'):
                    self.assertEqual(t['entry_time'][:10],t['exit_time'][:10])
                    self.assertLessEqual(t['entry_time'],t['exit_time'])
if __name__=='__main__': unittest.main()
