"""Tradebot Management Studio - Desktop analytical dashboard entry point."""

import sys

# pylint: disable=no-name-in-module
# PyQt6 modules are compiled C/C++ extensions (.pyd), which static analyzers
# like Pylint cannot inspect without dynamic loading.
from PyQt6.QtWidgets import QApplication

from ui import TradingApp


def example_trading_dashboard():
    """Showcase and launch Tradebot Management Studio graphical interface."""
    app = QApplication(sys.argv)
    window = TradingApp()
    window.show()
    sys.exit(app.exec())


def main():
    """Initialize and showcase the primary application functionality."""
    example_trading_dashboard()


if __name__ == '__main__':
    main()
