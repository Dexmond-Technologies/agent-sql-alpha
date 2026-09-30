PRAGMA foreign_keys = ON;

CREATE TABLE branches (
    branch_id INTEGER PRIMARY KEY,
    branch_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    country_code TEXT NOT NULL CHECK (length(country_code) = 2),
    opened_on TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
) STRICT;

CREATE TABLE currencies (
    currency_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    minor_unit INTEGER NOT NULL CHECK (minor_unit BETWEEN 0 AND 4),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
) STRICT, WITHOUT ROWID;

CREATE TABLE customers (
    customer_id TEXT PRIMARY KEY,
    customer_type TEXT NOT NULL CHECK (customer_type IN ('INDIVIDUAL', 'BUSINESS')),
    given_name TEXT,
    family_name TEXT,
    legal_name TEXT,
    display_name TEXT GENERATED ALWAYS AS (
        CASE WHEN customer_type = 'BUSINESS' THEN legal_name
             ELSE trim(coalesce(given_name, '') || ' ' || coalesce(family_name, '')) END
    ) STORED,
    email TEXT NOT NULL UNIQUE,
    phone TEXT,
    risk_rating TEXT NOT NULL CHECK (risk_rating IN ('LOW', 'MEDIUM', 'HIGH')),
    tax_residency_country TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'REVIEW', 'CLOSED')),
    created_at TEXT NOT NULL,
    CHECK (
        (customer_type = 'BUSINESS' AND legal_name IS NOT NULL) OR
        (customer_type = 'INDIVIDUAL' AND given_name IS NOT NULL AND family_name IS NOT NULL)
    )
) STRICT;

CREATE TABLE customer_addresses (
    address_id INTEGER PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    address_type TEXT NOT NULL CHECK (address_type IN ('HOME', 'BUSINESS', 'MAILING')),
    line_1 TEXT NOT NULL,
    line_2 TEXT,
    city TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    country_code TEXT NOT NULL CHECK (length(country_code) = 2),
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    is_primary INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1)),
    CHECK (valid_to IS NULL OR valid_to >= valid_from)
) STRICT;

CREATE TABLE kyc_cases (
    kyc_case_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    case_status TEXT NOT NULL CHECK (case_status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXPIRED')),
    risk_score INTEGER NOT NULL CHECK (risk_score BETWEEN 0 AND 100),
    verification_reference TEXT NOT NULL UNIQUE,
    opened_at TEXT NOT NULL,
    reviewed_at TEXT,
    reviewer TEXT,
    notes TEXT
) STRICT;

CREATE TABLE account_products (
    product_id INTEGER PRIMARY KEY,
    product_code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    product_type TEXT NOT NULL CHECK (product_type IN ('CURRENT', 'SAVINGS', 'CREDIT', 'ESCROW')),
    default_currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE RESTRICT,
    interest_rate_bps INTEGER NOT NULL DEFAULT 0,
    minimum_balance_minor INTEGER NOT NULL DEFAULT 0,
    monthly_fee_minor INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
) STRICT;

CREATE TABLE accounts (
    account_id TEXT PRIMARY KEY,
    account_reference TEXT NOT NULL UNIQUE,
    branch_id INTEGER NOT NULL REFERENCES branches(branch_id) ON DELETE RESTRICT,
    product_id INTEGER NOT NULL REFERENCES account_products(product_id) ON DELETE RESTRICT,
    currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE RESTRICT,
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'DORMANT', 'FROZEN', 'CLOSED')),
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    last_activity_at TEXT,
    overdraft_limit_minor INTEGER NOT NULL DEFAULT 0 CHECK (overdraft_limit_minor >= 0),
    external_reference TEXT,
    account_label TEXT GENERATED ALWAYS AS (substr(account_reference, 1, 8) || '…' || substr(account_reference, -4)) VIRTUAL,
    updated_at TEXT NOT NULL,
    CHECK ((status = 'CLOSED' AND closed_at IS NOT NULL) OR status <> 'CLOSED')
) STRICT;

CREATE TABLE account_holders (
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    holder_role TEXT NOT NULL CHECK (holder_role IN ('PRIMARY', 'JOINT', 'AUTHORIZED')),
    ownership_percent INTEGER NOT NULL CHECK (ownership_percent BETWEEN 0 AND 100),
    added_at TEXT NOT NULL,
    PRIMARY KEY (account_id, customer_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE beneficiaries (
    beneficiary_id TEXT PRIMARY KEY,
    owner_customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE CASCADE,
    nickname TEXT NOT NULL,
    beneficiary_name TEXT NOT NULL,
    destination_reference TEXT NOT NULL,
    destination_country TEXT NOT NULL,
    currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE RESTRICT,
    created_at TEXT NOT NULL,
    verified_at TEXT,
    is_trusted INTEGER NOT NULL DEFAULT 0 CHECK (is_trusted IN (0, 1)),
    UNIQUE (owner_customer_id, destination_reference)
) STRICT;

CREATE TABLE journal_batches (
    batch_id INTEGER PRIMARY KEY,
    batch_reference TEXT NOT NULL UNIQUE,
    business_date TEXT NOT NULL,
    source_system TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'POSTED', 'REVERSED')),
    posted_at TEXT,
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE merchants (
    merchant_id TEXT PRIMARY KEY,
    merchant_name TEXT NOT NULL,
    merchant_category_code TEXT NOT NULL CHECK (length(merchant_category_code) = 4),
    country_code TEXT NOT NULL,
    risk_tier INTEGER NOT NULL CHECK (risk_tier BETWEEN 1 AND 5),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE ledger_transactions (
    transaction_id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES journal_batches(batch_id) ON DELETE RESTRICT,
    transaction_reference TEXT NOT NULL UNIQUE,
    transaction_type TEXT NOT NULL CHECK (transaction_type IN ('TRANSFER', 'CARD', 'FEE', 'INTEREST', 'LOAN', 'REVERSAL')),
    currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE RESTRICT,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    booked_at TEXT NOT NULL,
    value_date TEXT NOT NULL,
    description TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'POSTED', 'REVERSED', 'DECLINED')),
    channel TEXT NOT NULL CHECK (channel IN ('MOBILE', 'WEB', 'BRANCH', 'CARD', 'BATCH')),
    is_cross_border INTEGER NOT NULL DEFAULT 0 CHECK (is_cross_border IN (0, 1)),
    reversal_of_id INTEGER REFERENCES ledger_transactions(transaction_id) ON DELETE SET NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}'
) STRICT;

CREATE TABLE ledger_entries (
    entry_id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES ledger_transactions(transaction_id) ON DELETE RESTRICT,
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    amount_minor INTEGER NOT NULL CHECK (amount_minor <> 0),
    entry_side TEXT GENERATED ALWAYS AS (CASE WHEN amount_minor < 0 THEN 'DEBIT' ELSE 'CREDIT' END) STORED,
    running_sequence INTEGER NOT NULL CHECK (running_sequence > 0),
    posted_at TEXT NOT NULL,
    integrity_hash BLOB NOT NULL,
    UNIQUE (transaction_id, running_sequence)
) STRICT;

CREATE TABLE payment_instructions (
    payment_id TEXT PRIMARY KEY,
    source_account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    beneficiary_id TEXT REFERENCES beneficiaries(beneficiary_id) ON DELETE SET NULL,
    transaction_id INTEGER UNIQUE REFERENCES ledger_transactions(transaction_id) ON DELETE SET NULL,
    requested_amount_minor INTEGER NOT NULL CHECK (requested_amount_minor > 0),
    requested_currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE RESTRICT,
    payment_method TEXT NOT NULL CHECK (payment_method IN ('FASTER_PAYMENT', 'SEPA', 'SWIFT', 'INTERNAL')),
    payment_status TEXT NOT NULL CHECK (payment_status IN ('SCHEDULED', 'PROCESSING', 'SETTLED', 'FAILED', 'CANCELLED')),
    requested_at TEXT NOT NULL,
    settled_at TEXT,
    failure_reason TEXT
) STRICT;

CREATE TABLE cards (
    card_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE CASCADE,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    card_token TEXT NOT NULL UNIQUE,
    last_four TEXT NOT NULL CHECK (length(last_four) = 4),
    card_type TEXT NOT NULL CHECK (card_type IN ('DEBIT', 'CREDIT', 'VIRTUAL')),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'BLOCKED', 'EXPIRED', 'CANCELLED')),
    issued_at TEXT NOT NULL,
    expires_on TEXT NOT NULL,
    spending_limit_minor INTEGER NOT NULL CHECK (spending_limit_minor > 0)
) STRICT;

CREATE TABLE card_authorizations (
    authorization_id TEXT PRIMARY KEY,
    card_id TEXT NOT NULL REFERENCES cards(card_id) ON DELETE CASCADE,
    merchant_id TEXT NOT NULL REFERENCES merchants(merchant_id) ON DELETE RESTRICT,
    transaction_id INTEGER REFERENCES ledger_transactions(transaction_id) ON DELETE SET NULL,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE RESTRICT,
    decision TEXT NOT NULL CHECK (decision IN ('APPROVED', 'DECLINED', 'REFERRED')),
    response_code TEXT NOT NULL,
    authorized_at TEXT NOT NULL,
    device_fingerprint BLOB,
    is_card_present INTEGER NOT NULL CHECK (is_card_present IN (0, 1))
) STRICT;

CREATE TABLE fx_rates (
    base_currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE CASCADE,
    quote_currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE CASCADE,
    rate_date TEXT NOT NULL,
    rate_micros INTEGER NOT NULL CHECK (rate_micros > 0),
    source TEXT NOT NULL,
    PRIMARY KEY (base_currency_code, quote_currency_code, rate_date),
    CHECK (base_currency_code <> quote_currency_code)
) STRICT, WITHOUT ROWID;

CREATE TABLE loans (
    loan_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id) ON DELETE RESTRICT,
    disbursement_account_id TEXT NOT NULL REFERENCES accounts(account_id) ON DELETE RESTRICT,
    principal_minor INTEGER NOT NULL CHECK (principal_minor > 0),
    currency_code TEXT NOT NULL REFERENCES currencies(currency_code) ON DELETE RESTRICT,
    annual_rate_bps INTEGER NOT NULL CHECK (annual_rate_bps BETWEEN 0 AND 10000),
    term_months INTEGER NOT NULL CHECK (term_months BETWEEN 1 AND 360),
    originated_on TEXT NOT NULL,
    maturity_on TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('CURRENT', 'DELINQUENT', 'PAID', 'CHARGED_OFF')),
    collateral_json TEXT
) STRICT;

CREATE TABLE loan_installments (
    loan_id TEXT NOT NULL REFERENCES loans(loan_id) ON DELETE CASCADE,
    installment_number INTEGER NOT NULL CHECK (installment_number > 0),
    due_on TEXT NOT NULL,
    principal_due_minor INTEGER NOT NULL CHECK (principal_due_minor >= 0),
    interest_due_minor INTEGER NOT NULL CHECK (interest_due_minor >= 0),
    paid_minor INTEGER NOT NULL DEFAULT 0 CHECK (paid_minor >= 0),
    paid_at TEXT,
    installment_status TEXT NOT NULL CHECK (installment_status IN ('DUE', 'PAID', 'LATE', 'WAIVED')),
    PRIMARY KEY (loan_id, installment_number)
) STRICT, WITHOUT ROWID;

CREATE TABLE aml_alerts (
    alert_id TEXT PRIMARY KEY,
    customer_id TEXT REFERENCES customers(customer_id) ON DELETE SET NULL,
    account_id TEXT REFERENCES accounts(account_id) ON DELETE SET NULL,
    alert_type TEXT NOT NULL CHECK (alert_type IN ('STRUCTURING', 'RAPID_MOVEMENT', 'SANCTIONS', 'UNUSUAL_VALUE', 'NEW_BENEFICIARY')),
    severity TEXT NOT NULL CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    alert_status TEXT NOT NULL CHECK (alert_status IN ('OPEN', 'INVESTIGATING', 'CLOSED', 'ESCALATED')),
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    disposition TEXT,
    rule_version TEXT NOT NULL
) STRICT;

CREATE TABLE aml_alert_transactions (
    alert_id TEXT NOT NULL REFERENCES aml_alerts(alert_id) ON DELETE CASCADE,
    transaction_id INTEGER NOT NULL REFERENCES ledger_transactions(transaction_id) ON DELETE CASCADE,
    match_reason TEXT NOT NULL,
    contribution_score INTEGER NOT NULL CHECK (contribution_score BETWEEN 0 AND 100),
    PRIMARY KEY (alert_id, transaction_id)
) STRICT, WITHOUT ROWID;

CREATE TABLE audit_events (
    audit_event_id INTEGER PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    actor TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    correlation_id TEXT,
    source_ip TEXT
) STRICT;

CREATE UNIQUE INDEX ux_customer_primary_address
    ON customer_addresses(customer_id) WHERE is_primary = 1 AND valid_to IS NULL;
CREATE INDEX ix_customers_risk_status ON customers(risk_rating, status, created_at);
CREATE INDEX ix_accounts_branch_status ON accounts(branch_id, status, currency_code);
CREATE INDEX ix_account_holders_customer ON account_holders(customer_id, holder_role);
CREATE INDEX ix_beneficiaries_owner_created ON beneficiaries(owner_customer_id, created_at DESC);
CREATE INDEX ix_transactions_booked_type ON ledger_transactions(booked_at DESC, transaction_type, status);
CREATE INDEX ix_transactions_reversal ON ledger_transactions(reversal_of_id) WHERE reversal_of_id IS NOT NULL;
CREATE INDEX ix_ledger_entries_account_posted ON ledger_entries(account_id, posted_at DESC, entry_id);
CREATE INDEX ix_ledger_entries_transaction ON ledger_entries(transaction_id, running_sequence);
CREATE INDEX ix_payments_status_requested ON payment_instructions(payment_status, requested_at DESC);
CREATE INDEX ix_cards_account_status ON cards(account_id, status);
CREATE INDEX ix_authorizations_card_time ON card_authorizations(card_id, authorized_at DESC);
CREATE INDEX ix_loans_customer_status ON loans(customer_id, status);
CREATE INDEX ix_installments_status_due ON loan_installments(installment_status, due_on);
CREATE INDEX ix_aml_alerts_work_queue ON aml_alerts(severity DESC, opened_at) WHERE alert_status IN ('OPEN', 'INVESTIGATING', 'ESCALATED');
CREATE INDEX ix_audit_entity_time ON audit_events(entity_type, entity_id, occurred_at DESC);
CREATE INDEX ix_customer_email_domain ON customers(substr(email, instr(email, '@') + 1));

CREATE VIEW v_account_balances AS
SELECT a.account_id,
       a.account_reference,
       a.currency_code,
       a.status,
       coalesce(sum(le.amount_minor), 0) AS balance_minor,
       max(le.posted_at) AS last_posted_at
FROM accounts a
LEFT JOIN ledger_entries le ON le.account_id = a.account_id
GROUP BY a.account_id, a.account_reference, a.currency_code, a.status;

CREATE VIEW v_customer_account_summary AS
SELECT c.customer_id,
       c.display_name,
       c.risk_rating,
       count(DISTINCT ah.account_id) AS account_count,
       coalesce(sum(CASE WHEN ah.holder_role = 'PRIMARY' THEN b.balance_minor ELSE 0 END), 0) AS primary_balance_minor,
       max(b.last_posted_at) AS last_activity_at
FROM customers c
LEFT JOIN account_holders ah ON ah.customer_id = c.customer_id
LEFT JOIN v_account_balances b ON b.account_id = ah.account_id
GROUP BY c.customer_id, c.display_name, c.risk_rating;

CREATE VIEW v_monthly_cash_flow AS
WITH monthly AS (
    SELECT account_id,
           substr(posted_at, 1, 7) AS posting_month,
           sum(CASE WHEN amount_minor > 0 THEN amount_minor ELSE 0 END) AS inflow_minor,
           -sum(CASE WHEN amount_minor < 0 THEN amount_minor ELSE 0 END) AS outflow_minor
    FROM ledger_entries
    GROUP BY account_id, substr(posted_at, 1, 7)
)
SELECT account_id,
       posting_month,
       inflow_minor,
       outflow_minor,
       inflow_minor - outflow_minor AS net_flow_minor,
       lag(inflow_minor - outflow_minor) OVER (PARTITION BY account_id ORDER BY posting_month) AS previous_month_net_minor
FROM monthly;

CREATE VIEW v_open_aml_alerts AS
SELECT aa.alert_id,
       aa.severity,
       aa.alert_status,
       aa.alert_type,
       aa.customer_id,
       c.display_name,
       aa.account_id,
       aa.score,
       aa.opened_at,
       count(aat.transaction_id) AS matched_transaction_count,
       coalesce(sum(lt.amount_minor), 0) AS matched_amount_minor
FROM aml_alerts aa
LEFT JOIN customers c ON c.customer_id = aa.customer_id
LEFT JOIN aml_alert_transactions aat ON aat.alert_id = aa.alert_id
LEFT JOIN ledger_transactions lt ON lt.transaction_id = aat.transaction_id
WHERE aa.alert_status IN ('OPEN', 'INVESTIGATING', 'ESCALATED')
GROUP BY aa.alert_id, aa.severity, aa.alert_status, aa.alert_type,
         aa.customer_id, c.display_name, aa.account_id, aa.score, aa.opened_at;

CREATE VIEW v_loan_arrears AS
SELECT l.loan_id,
       l.customer_id,
       c.display_name,
       l.disbursement_account_id,
       a.branch_id,
       l.currency_code,
       count(*) FILTER (WHERE li.installment_status = 'LATE') AS late_installment_count,
       coalesce(sum(CASE WHEN li.installment_status = 'LATE'
                         THEN li.principal_due_minor + li.interest_due_minor - li.paid_minor
                         ELSE 0 END), 0) AS arrears_minor,
       min(CASE WHEN li.installment_status = 'LATE' THEN li.due_on END) AS oldest_late_due_on
FROM loans l
JOIN customers c ON c.customer_id = l.customer_id
JOIN accounts a ON a.account_id = l.disbursement_account_id
JOIN loan_installments li ON li.loan_id = l.loan_id
GROUP BY l.loan_id, l.customer_id, c.display_name,
         l.disbursement_account_id, a.branch_id, l.currency_code;

CREATE TRIGGER trg_accounts_touch_updated_at
AFTER UPDATE OF status, branch_id, product_id ON accounts
BEGIN
    UPDATE accounts SET updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
    WHERE account_id = NEW.account_id;
END;

CREATE TRIGGER trg_accounts_status_audit
AFTER UPDATE OF status ON accounts
WHEN OLD.status <> NEW.status
BEGIN
    INSERT INTO audit_events(entity_type, entity_id, action, actor, occurred_at, changes_json, correlation_id, source_ip)
    VALUES ('ACCOUNT', NEW.account_id, 'STATUS_CHANGED', 'fixture-trigger',
            strftime('%Y-%m-%dT%H:%M:%SZ', 'now'),
            json_object('old', OLD.status, 'new', NEW.status), NULL, NULL);
END;

CREATE TRIGGER trg_ledger_entries_immutable_update
BEFORE UPDATE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'posted ledger entries are immutable');
END;

CREATE TRIGGER trg_ledger_entries_immutable_delete
BEFORE DELETE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'posted ledger entries are immutable');
END;
