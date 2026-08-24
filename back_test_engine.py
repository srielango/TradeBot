import numpy as np
import pandas as pd

class BacktestEngine:
    def __init__(self, initial_capital=100000.0):
        self.initial_capital = initial_capital

    def run(self, df: pd.DataFrame) -> dict:
        results = df.copy()

        results['Market_Returns'] = np.log(results['Close'] / results['Close'].shift(1))
        results['Strategy_Returns'] = results['Market_returns'] * results['Signal'].shift(1)

        total_return = np.exp(results['Strategy_Returns'].sum()) - 1
        sharpe = (results['Strategy_Returns'].mean() / results['Strategy_Returns'].std()) * np.sqrt(252) if results['Stragety_Returns'].std() != 0 else 0

        return {
            "Total_Return_Pct": total_return * 100,
            "Sharpe_Ratio": sharpe,
            "Equity_Curve": np.exp(results['Strategy_Returns'].cumsum()) * self.initial_capital
        }
    