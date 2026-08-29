-- Schema migration for storing fundamental analysis and screening metrics

CREATE TABLE IF NOT EXISTS security_fundamentals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    security_id INTEGER NOT NULL,
    ticker TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    market_cap REAL,
    market_cap_cr REAL,
    debt_to_equity REAL,
    peg_ratio REAL,
    beta_nsei REAL,
    beta_yf REAL,
    avg_volume_252 REAL,
    roe REAL,
    institutional_ownership REAL,
    is_passing INTEGER NOT NULL DEFAULT 0,
    filter_details TEXT,
    FOREIGN KEY (security_id) REFERENCES securities(id),
    UNIQUE(security_id)
);

CREATE INDEX IF NOT EXISTS idx_fundamentals_ticker ON security_fundamentals(ticker);
CREATE INDEX IF NOT EXISTS idx_fundamentals_passing ON security_fundamentals(is_passing);
