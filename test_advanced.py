import unittest
import numpy as np
import pandas as pd
from advanced import advanced_signals
class AdvancedTests(unittest.TestCase):
    def test_signals_are_boolean_and_aligned(self):
        idx=pd.date_range('2026-01-05 09:15',periods=75*12,freq='5min',tz='Asia/Kolkata')
        idx=idx[idx.time<=pd.Timestamp('15:25').time()]
        n=len(idx); rng=np.random.default_rng(4); c=100+np.cumsum(rng.normal(0,.25,n))
        df=pd.DataFrame({'open':c,'high':c+.2,'low':c-.2,'close':c,'volume':rng.integers(1000,9000,n)},index=idx)
        result=advanced_signals(df)
        self.assertEqual(len(result),6)
        for long,short in result.values():
            self.assertTrue(long.index.equals(df.index)); self.assertTrue(short.index.equals(df.index))
            self.assertFalse(long.isna().any()); self.assertFalse(short.isna().any())
            self.assertFalse((long&short).any())
if __name__=='__main__': unittest.main()
