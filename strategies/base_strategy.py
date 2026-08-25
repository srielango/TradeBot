from abc import ABC, abstractmethod
import pandas as pd

class BaseStrategy(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Input: DataFrame with Open, High, Low, Close, Volume
        Output: DataFrame with added indicator and 'Signal' columns
        """
        pass

#Example strategy implementation
class MacdRsiSwing(BaseStrategy):
    @property
    def name(self) -> str:
        return "MACD_RSI_Swing"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()

        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewn(span=26. adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_line'] = df['MACD'].ewm(span = 9, adjust=False).mean()

        #Determine signals
        df['Signal'] = 0
        df.loc[(df['MACD'] > df['Signal_Line']), 'Signal'] = 1 # Buy
        df.loc[(df['MACD'] < df['Signal_Line']), 'Signal'] = -1 # Sell

        return df