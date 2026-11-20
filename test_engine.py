import unittest
import numpy as np
import pandas as pd
from engine import MODELS,backtest,portfolio_replay

class EngineTests(unittest.TestCase):
    def setUp(self):
        ix=pd.date_range('2026-11-19 09:15',periods=76,freq='5min',tz='Asia/Kolkata')
        close=np.linspace(100,105,len(ix))
        self.df=pd.DataFrame({'open':close,'high':close+.2,'low':close-.2,'close':close,'volume':1000},index=ix)
        self.cfg={'capital':100000,'per_trade_capital':25000,'stop_pct':.0075,'target_pct':.015,'max_bars':24,'round_trip_cost_bps':12,'cooldown_bars':3,'max_trades_per_symbol_day':3}
    def test_all_models(self):
        sig=pd.Series(False,index=self.df.index);sig.iloc[12]=True
        for model in MODELS:
            with self.subTest(model=model):
                trades=backtest(self.df,'TEST','LONG',sig,self.cfg,'TEST',model)
                self.assertLessEqual(len(trades),1)
                if trades: self.assertGreater(trades[0]['estimated_cost'],0)
    def test_no_repeated_signal(self):
        sig=pd.Series(True,index=self.df.index)
        trades=backtest(self.df,'TEST','LONG',sig,self.cfg,'TEST','E1_FIXED')
        self.assertEqual(len(trades),0) # first candle before 09:30; no fresh later trigger
    def test_portfolio_limits(self):
        rows=[dict(strategy='S',exit_model='E1_FIXED',symbol=s,direction='LONG',entry_time='2026-11-19 10:00:00+05:30',exit_time='2026-11-19 11:00:00+05:30',entry=100,qty=250,net=1,estimated_cost=1) for s in ['A','B','C','D','E']]
        p=portfolio_replay(pd.DataFrame(rows),self.cfg)
        self.assertEqual(len(p),4)

if __name__=='__main__':unittest.main()
