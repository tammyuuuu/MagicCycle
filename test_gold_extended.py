import unittest
import numpy as np
from test_asset_strategies import frame
from research_gold_extended import run, targets


class ExtendedReportTests(unittest.TestCase):
    def test_ledger_and_causal_execution(self):
        data=frame(np.r_[np.full(130,100.),130.,np.full(90,131.)])
        stats,curve,trades=run(data,targets(data.close)[1],120,1,100000.)
        cash=100000.;quantity=0
        for date,row in curve.iterrows():
            for trade in trades:
                if trade['date']!=str(date.date()): continue
                self.assertLess(trade['signal_date'],trade['date'])
                sign=1 if trade['action'] in ('买入','恢复买入') else -1
                quantity+=sign*trade['quantity']
                cash-=sign*trade['quantity']*trade['price']+trade['fee']
            self.assertAlmostEqual(row.cash,cash)
            self.assertEqual(row.quantity,quantity)
            self.assertAlmostEqual(row.equity,cash+quantity*data.loc[date,'close'])
        self.assertAlmostEqual(stats['return_pct'],round(curve.return_pct.iloc[-1],2))
        self.assertAlmostEqual(stats['max_drawdown_pct'],round(curve.drawdown_pct.min(),2))


if __name__=='__main__': unittest.main()
