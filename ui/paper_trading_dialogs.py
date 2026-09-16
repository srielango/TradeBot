"""Modal dialogs for paper trading position management.

Provides:
1. ModifyPositionDialog: Adjust Stop Loss and Profit Target levels on active open trades.
2. PartialSellDialog: Sell a partial quantity of an active position with live PnL preview.
"""

from typing import Any

# pylint: disable=no-name-in-module
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from paper_trading_engine import PaperTradingEngine


class ModifyPositionDialog(QDialog):
    """Modal dialog allowing traders to edit Stop Loss and Profit Target of an open trade."""

    def __init__(
        self,
        parent: QWidget | None,
        trade: dict[str, Any],
        engine: PaperTradingEngine,
    ):
        """Initialize modification dialog.

        Args:
            parent (QWidget | None): Parent UI widget.
            trade (dict[str, Any]): Active trade data dictionary.
            engine (PaperTradingEngine): Backend engine instance.
        """
        super().__init__(parent)
        self.trade = trade
        self.engine = engine
        self.updated_result: dict[str, Any] | None = None

        self.setWindowTitle(
            f"Modify Position - Trade #{trade['trade_id']} ({trade['ticker']})"
        )
        self.setMinimumWidth(440)
        self.setStyleSheet(
            "QDialog { background-color: #21252b; color: #abb2bf; } "
            "QLabel { color: #abb2bf; font-size: 12px; } "
            "QGroupBox { color: #abb2bf; font-weight: bold; border: 1px solid #3b4048; "
            "border-radius: 6px; margin-top: 8px; padding-top: 14px; "
            "background-color: #1e2227; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; } "
            "QDoubleSpinBox { background-color: #282c34; color: #ffffff; "
            "border: 1px solid #3b4048; border-radius: 4px; padding: 4px; font-size: 12px; } "
            "QDoubleSpinBox:focus { border: 1px solid #61afef; } "
            "QCheckBox { color: #abb2bf; font-weight: bold; spacing: 6px; }"
        )

        self._init_ui()
        self._recalculate_preview()

    def _init_ui(self) -> None:
        """Construct the dialog layout and widgets."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # 1. Position Overview Card
        info_group = QGroupBox("Position Overview")
        info_layout = QGridLayout(info_group)
        info_layout.setSpacing(6)

        info_layout.addWidget(QLabel("Ticker / Security:"), 0, 0)
        lbl_ticker = QLabel(f"<b>{self.trade['ticker']}</b> ({self.trade['side']})")
        lbl_ticker.setStyleSheet("color: #61afef; font-size: 13px;")
        info_layout.addWidget(lbl_ticker, 0, 1)

        info_layout.addWidget(QLabel("Holding Quantity:"), 1, 0)
        lbl_qty = QLabel(f"{self.trade['quantity']} Shares")
        lbl_qty.setStyleSheet("color: #ffffff; font-weight: bold;")
        info_layout.addWidget(lbl_qty, 1, 1)

        info_layout.addWidget(QLabel("Original Entry Price:"), 2, 0)
        lbl_entry = QLabel(f"₹{self.trade['entry_price']:,.2f}")
        lbl_entry.setStyleSheet("color: #abb2bf;")
        info_layout.addWidget(lbl_entry, 2, 1)

        info_layout.addWidget(QLabel("Current Market Price:"), 3, 0)
        curr_price = self.trade.get("current_price", self.trade["entry_price"])
        lbl_cmp = QLabel(f"₹{curr_price:,.2f}")
        lbl_cmp.setStyleSheet("color: #e5c07b; font-weight: bold;")
        info_layout.addWidget(lbl_cmp, 3, 1)

        layout.addWidget(info_group)

        # 2. Editable Parameters Group
        params_group = QGroupBox("Order Management Parameters")
        params_layout = QVBoxLayout(params_group)
        params_layout.setSpacing(8)

        # Stop Loss Input
        params_layout.addWidget(QLabel("<b>Adjust Stop Loss (₹):</b>"))
        self.spin_sl = QDoubleSpinBox()
        self.spin_sl.setRange(0.01, 1_000_000.00)
        self.spin_sl.setDecimals(2)
        self.spin_sl.setValue(float(self.trade["stop_loss"]))
        self.spin_sl.valueChanged.connect(self._recalculate_preview)
        params_layout.addWidget(self.spin_sl)

        # Profit Target Input with Checkbox
        target_val = self.trade.get("sell_target")
        has_target = target_val is not None and float(target_val) > 0

        self.chk_target = QCheckBox("Enable Sell Target (₹) [Optional]")
        self.chk_target.setChecked(has_target)
        self.chk_target.toggled.connect(self._on_target_toggled)
        params_layout.addWidget(self.chk_target)

        self.spin_target = QDoubleSpinBox()
        self.spin_target.setRange(0.01, 1_000_000.00)
        self.spin_target.setDecimals(2)
        initial_target = float(target_val) if has_target else round(curr_price * 1.05, 2)
        self.spin_target.setValue(initial_target)
        self.spin_target.setEnabled(has_target)
        self.spin_target.valueChanged.connect(self._recalculate_preview)
        params_layout.addWidget(self.spin_target)

        layout.addWidget(params_group)

        # 3. Dynamic Calculation Preview Box
        self.preview_box = QFrame()
        self.preview_box.setStyleSheet(
            "QFrame { background-color: #1a1d23; border: 1px solid #2d3139; "
            "border-radius: 4px; padding: 6px; }"
        )
        prev_layout = QGridLayout(self.preview_box)
        prev_layout.setSpacing(4)

        prev_layout.addWidget(QLabel("Max Loss at SL:"), 0, 0)
        self.lbl_prev_loss = QLabel("-₹0.00")
        self.lbl_prev_loss.setStyleSheet("color: #e06c75; font-weight: bold;")
        prev_layout.addWidget(self.lbl_prev_loss, 0, 1)

        prev_layout.addWidget(QLabel("Max Gain at Target:"), 1, 0)
        self.lbl_prev_gain = QLabel("+₹0.00")
        self.lbl_prev_gain.setStyleSheet("color: #98c379; font-weight: bold;")
        prev_layout.addWidget(self.lbl_prev_gain, 1, 1)

        prev_layout.addWidget(QLabel("Risk : Reward Ratio:"), 2, 0)
        self.lbl_prev_rrr = QLabel("1 : 0.00")
        self.lbl_prev_rrr.setStyleSheet("color: #e5c07b; font-weight: bold;")
        prev_layout.addWidget(self.lbl_prev_rrr, 2, 1)

        layout.addWidget(self.preview_box)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #3b4048; color: #abb2bf; padding: 6px 14px; "
            "border-radius: 4px; font-weight: bold; border: none; } "
            "QPushButton:hover { background-color: #4b5263; color: white; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("💾 Update Position")
        self.btn_save.setStyleSheet(
            "QPushButton { background-color: #27ae60; color: #ffffff; padding: 6px 16px; "
            "border-radius: 4px; font-weight: bold; border: none; } "
            "QPushButton:hover { background-color: #2ecc71; } "
            "QPushButton:disabled { background-color: #3b4048; color: #7f848e; }"
        )
        self.btn_save.clicked.connect(self._save_changes)
        btn_layout.addWidget(self.btn_save)

        layout.addLayout(btn_layout)

    def _on_target_toggled(self, checked: bool) -> None:
        """Enable or disable target spin box."""
        self.spin_target.setEnabled(checked)
        self._recalculate_preview()

    def _recalculate_preview(self) -> None:
        """Update live preview metrics for the updated Stop Loss and Target."""
        qty = int(self.trade["quantity"])
        entry = float(self.trade["entry_price"])
        curr = float(self.trade.get("current_price", entry))
        new_sl = self.spin_sl.value()
        has_target = self.chk_target.isChecked()
        new_target = self.spin_target.value() if has_target else None

        # Validate SL against current market price
        if new_sl >= curr:
            self.lbl_prev_loss.setText("Invalid SL (must be < CMP)")
            self.lbl_prev_loss.setStyleSheet("color: #e06c75; font-weight: bold;")
            self.btn_save.setEnabled(False)
            return

        # PnL at Stop Loss relative to entry
        pnl_sl = qty * (new_sl - entry)
        pct_sl = ((new_sl - entry) / entry * 100.0) if entry > 0 else 0.0
        sign_sl = "+" if pnl_sl >= 0 else ""
        color_sl = "#98c379" if pnl_sl >= 0 else "#e06c75"
        self.lbl_prev_loss.setText(f"{sign_sl}₹{pnl_sl:,.2f} ({sign_sl}{pct_sl:.2f}%)")
        self.lbl_prev_loss.setStyleSheet(f"color: {color_sl}; font-weight: bold;")

        # Target calculations
        if has_target and new_target is not None:
            if new_target <= curr:
                self.lbl_prev_gain.setText("Invalid Target (must be > CMP)")
                self.lbl_prev_gain.setStyleSheet("color: #e06c75; font-weight: bold;")
                self.btn_save.setEnabled(False)
                return

            if new_target <= new_sl:
                self.lbl_prev_gain.setText("Invalid Target (must be > SL)")
                self.lbl_prev_gain.setStyleSheet("color: #e06c75; font-weight: bold;")
                self.btn_save.setEnabled(False)
                return

            pnl_target = qty * (new_target - entry)
            pct_target = ((new_target - entry) / entry * 100.0) if entry > 0 else 0.0
            self.lbl_prev_gain.setText(f"+₹{pnl_target:,.2f} (+{pct_target:.2f}%)")
            self.lbl_prev_gain.setStyleSheet("color: #98c379; font-weight: bold;")

            risk_span = curr - new_sl
            reward_span = new_target - curr
            rrr = (reward_span / risk_span) if risk_span > 0 else 0.0
            self.lbl_prev_rrr.setText(f"1 : {rrr:.2f}")
        else:
            self.lbl_prev_gain.setText("Target Disabled (Open Exit)")
            self.lbl_prev_gain.setStyleSheet("color: #abb2bf;")
            self.lbl_prev_rrr.setText("Trailing / Manual Exit")

        self.btn_save.setEnabled(True)

    def _save_changes(self) -> None:
        """Persist updated stop loss and target via engine."""
        trade_id = self.trade["trade_id"]
        new_sl = self.spin_sl.value()
        new_target = self.spin_target.value() if self.chk_target.isChecked() else None

        try:
            res = self.engine.update_trade_sl_and_target(
                trade_id=trade_id,
                stop_loss=new_sl,
                sell_target=new_target,
            )
            self.updated_result = res
            self.accept()
        except ValueError as err:
            QMessageBox.critical(self, "Modification Failed", str(err))


class PartialSellDialog(QDialog):
    """Modal dialog allowing traders to sell a partial quantity of an active position."""

    def __init__(
        self,
        parent: QWidget | None,
        trade: dict[str, Any],
        engine: PaperTradingEngine,
    ):
        """Initialize partial sell dialog.

        Args:
            parent (QWidget | None): Parent UI widget.
            trade (dict[str, Any]): Active trade data dictionary.
            engine (PaperTradingEngine): Backend engine instance.
        """
        super().__init__(parent)
        self.trade = trade
        self.engine = engine
        self.partial_result: dict[str, Any] | None = None

        self.setWindowTitle(
            f"Sell Partial Quantity - Trade #{trade['trade_id']} ({trade['ticker']})"
        )
        self.setMinimumWidth(450)
        self.setStyleSheet(
            "QDialog { background-color: #21252b; color: #abb2bf; } "
            "QLabel { color: #abb2bf; font-size: 12px; } "
            "QGroupBox { color: #abb2bf; font-weight: bold; border: 1px solid #3b4048; "
            "border-radius: 6px; margin-top: 8px; padding-top: 14px; background-color: #1e2227; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; } "
            "QSpinBox { background-color: #282c34; color: #ffffff; border: 1px solid #3b4048; "
            "border-radius: 4px; padding: 4px; font-size: 13px; font-weight: bold; } "
            "QSpinBox:focus { border: 1px solid #e5c07b; }"
        )

        self._init_ui()
        self._recalculate_preview()

    def _init_ui(self) -> None:
        """Construct the partial sell interface."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # 1. Position Overview Card
        info_group = QGroupBox("Active Position Details")
        info_layout = QGridLayout(info_group)
        info_layout.setSpacing(6)

        info_layout.addWidget(QLabel("Ticker / Security:"), 0, 0)
        lbl_ticker = QLabel(f"<b>{self.trade['ticker']}</b>")
        lbl_ticker.setStyleSheet("color: #61afef; font-size: 13px;")
        info_layout.addWidget(lbl_ticker, 0, 1)

        info_layout.addWidget(QLabel("Current Open Quantity:"), 1, 0)
        self.total_qty = int(self.trade["quantity"])
        lbl_open_qty = QLabel(f"<b>{self.total_qty} Shares</b>")
        lbl_open_qty.setStyleSheet("color: #ffffff; font-size: 13px;")
        info_layout.addWidget(lbl_open_qty, 1, 1)

        info_layout.addWidget(QLabel("Original Entry Price:"), 2, 0)
        self.entry_price = float(self.trade["entry_price"])
        info_layout.addWidget(QLabel(f"₹{self.entry_price:,.2f}"), 2, 1)

        info_layout.addWidget(QLabel("Current Market Price (CMP):"), 3, 0)
        self.curr_price = float(self.trade.get("current_price", self.entry_price))
        lbl_cmp = QLabel(f"₹{self.curr_price:,.2f}")
        lbl_cmp.setStyleSheet("color: #e5c07b; font-weight: bold;")
        info_layout.addWidget(lbl_cmp, 3, 1)

        info_layout.addWidget(QLabel("Total Unrealized PnL:"), 4, 0)
        total_pnl = self.total_qty * (self.curr_price - self.entry_price)
        total_pct = (
            ((self.curr_price - self.entry_price) / self.entry_price * 100.0)
            if self.entry_price > 0
            else 0.0
        )
        pnl_color = "#98c379" if total_pnl >= 0 else "#e06c75"
        sign = "+" if total_pnl >= 0 else ""
        lbl_total_pnl = QLabel(f"{sign}₹{total_pnl:,.2f} ({sign}{total_pct:.2f}%)")
        lbl_total_pnl.setStyleSheet(f"color: {pnl_color}; font-weight: bold;")
        info_layout.addWidget(lbl_total_pnl, 4, 1)

        layout.addWidget(info_group)

        # 2. Sell Quantity Selector Group
        sell_group = QGroupBox("Partial Sell Order")
        sell_layout = QVBoxLayout(sell_group)
        sell_layout.setSpacing(8)

        sell_layout.addWidget(QLabel("<b>Quantity to Sell (Shares):</b>"))
        self.spin_qty = QSpinBox()
        self.spin_qty.setRange(1, self.total_qty)
        default_val = max(1, self.total_qty // 2)
        self.spin_qty.setValue(default_val)
        self.spin_qty.valueChanged.connect(self._recalculate_preview)
        sell_layout.addWidget(self.spin_qty)

        # Quick percentage buttons
        pct_layout = QHBoxLayout()
        pct_layout.setSpacing(6)

        percentages = [
            ("25%", 0.25),
            ("50%", 0.50),
            ("75%", 0.75),
            ("100% (All)", 1.00),
        ]
        for label, frac in percentages:
            btn = QPushButton(label)
            btn.setStyleSheet(
                "QPushButton { background-color: #2c313a; color: #abb2bf; font-size: 11px; "
                "padding: 4px 8px; border: 1px solid #3b4048; border-radius: 3px; } "
                "QPushButton:hover { background-color: #3e4451; color: #ffffff; }"
            )
            calc_val = max(1, round(self.total_qty * frac))
            btn.clicked.connect(lambda _checked=False, val=calc_val: self.spin_qty.setValue(val))
            pct_layout.addWidget(btn)

        sell_layout.addLayout(pct_layout)
        layout.addWidget(sell_group)

        # 3. Dynamic Execution Preview Box
        self.preview_box = QFrame()
        self.preview_box.setStyleSheet(
            "QFrame { background-color: #1a1d23; border: 1px solid #2d3139; "
            "border-radius: 4px; padding: 6px; }"
        )
        prev_layout = QGridLayout(self.preview_box)
        prev_layout.setSpacing(4)

        prev_layout.addWidget(QLabel("Shares Sold:"), 0, 0)
        self.lbl_prev_sold = QLabel("0 Shares")
        self.lbl_prev_sold.setStyleSheet("color: #e5c07b; font-weight: bold;")
        prev_layout.addWidget(self.lbl_prev_sold, 0, 1)

        prev_layout.addWidget(QLabel("Remaining Shares:"), 1, 0)
        self.lbl_prev_remain = QLabel("0 Shares")
        self.lbl_prev_remain.setStyleSheet("color: #abb2bf;")
        prev_layout.addWidget(self.lbl_prev_remain, 1, 1)

        prev_layout.addWidget(QLabel("Realized PnL from Sale:"), 2, 0)
        self.lbl_prev_realized_pnl = QLabel("₹0.00")
        self.lbl_prev_realized_pnl.setStyleSheet("color: #98c379; font-weight: bold;")
        prev_layout.addWidget(self.lbl_prev_realized_pnl, 2, 1)

        prev_layout.addWidget(QLabel("Cash Returned to Portfolio:"), 3, 0)
        self.lbl_prev_cash = QLabel("₹0.00")
        self.lbl_prev_cash.setStyleSheet("color: #61afef; font-weight: bold;")
        prev_layout.addWidget(self.lbl_prev_cash, 3, 1)

        layout.addWidget(self.preview_box)

        # 4. Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setStyleSheet(
            "QPushButton { background-color: #3b4048; color: #abb2bf; padding: 6px 14px; "
            "border-radius: 4px; font-weight: bold; border: none; } "
            "QPushButton:hover { background-color: #4b5263; color: white; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_confirm = QPushButton("✂ Confirm Partial Sell")
        self.btn_confirm.setStyleSheet(
            "QPushButton { background-color: #d19a66; color: #1e1e1e; padding: 6px 16px; "
            "border-radius: 4px; font-weight: bold; border: none; } "
            "QPushButton:hover { background-color: #e5c07b; } "
            "QPushButton:disabled { background-color: #3b4048; color: #7f848e; }"
        )
        self.btn_confirm.clicked.connect(self._confirm_sell)
        btn_layout.addWidget(self.btn_confirm)

        layout.addLayout(btn_layout)

    def _recalculate_preview(self) -> None:
        """Update live execution preview values."""
        sold = self.spin_qty.value()
        remain = self.total_qty - sold

        self.lbl_prev_sold.setText(f"{sold} Shares")
        self.lbl_prev_remain.setText(
            f"{remain} Shares" if remain > 0 else "0 Shares (Full Position Close)"
        )

        realized_pnl = sold * (self.curr_price - self.entry_price)
        ret_pct = (
            ((self.curr_price - self.entry_price) / self.entry_price * 100.0)
            if self.entry_price > 0
            else 0.0
        )
        cash_return = sold * self.curr_price

        sign = "+" if realized_pnl >= 0 else ""
        color = "#98c379" if realized_pnl >= 0 else "#e06c75"
        self.lbl_prev_realized_pnl.setText(f"{sign}₹{realized_pnl:,.2f} ({sign}{ret_pct:.2f}%)")
        self.lbl_prev_realized_pnl.setStyleSheet(f"color: {color}; font-weight: bold;")

        self.lbl_prev_cash.setText(f"₹{cash_return:,.2f}")

    def _confirm_sell(self) -> None:
        """Execute partial position sale via engine."""
        sold = self.spin_qty.value()
        trade_id = self.trade["trade_id"]

        try:
            res = self.engine.partial_close_trade(
                trade_id=trade_id,
                sell_quantity=sold,
                exit_price=self.curr_price,
                exit_reason="PARTIAL_EXIT",
            )
            self.partial_result = res
            self.accept()
        except ValueError as err:
            QMessageBox.critical(self, "Partial Sell Failed", str(err))
