-- Representative reads for manual and integration testing.

-- Account balances and their primary owners.
SELECT c.display_name, a.account_reference, b.currency_code, b.balance_minor
FROM v_account_balances b
JOIN accounts a ON a.account_id = b.account_id
JOIN account_holders ah ON ah.account_id = a.account_id AND ah.holder_role = 'PRIMARY'
JOIN customers c ON c.customer_id = ah.customer_id
ORDER BY abs(b.balance_minor) DESC
LIMIT 25;

-- Month-over-month movement using the windowed reporting view.
SELECT account_id, posting_month, net_flow_minor, previous_month_net_minor
FROM v_monthly_cash_flow
WHERE previous_month_net_minor IS NOT NULL
ORDER BY abs(net_flow_minor - previous_month_net_minor) DESC
LIMIT 25;

-- High-risk AML work queue with linked transaction totals.
SELECT alert_id, display_name, severity, alert_type, matched_transaction_count, matched_amount_minor
FROM v_open_aml_alerts
WHERE severity IN ('HIGH', 'CRITICAL')
ORDER BY score DESC, opened_at;

-- Delinquent lending exposure by branch.
SELECT branch_id, currency_code, count(*) AS delinquent_loans, sum(arrears_minor) AS arrears_minor
FROM v_loan_arrears
WHERE arrears_minor > 0
GROUP BY branch_id, currency_code
ORDER BY arrears_minor DESC;

-- Reversals and their original transactions.
SELECT r.transaction_reference AS reversal_reference,
       o.transaction_reference AS original_reference,
       r.amount_minor,
       r.booked_at
FROM ledger_transactions r
JOIN ledger_transactions o ON o.transaction_id = r.reversal_of_id
ORDER BY r.booked_at DESC
LIMIT 50;

-- Deliberately exceeds agentSQL's 10,000-row result cap.
SELECT * FROM ledger_entries ORDER BY entry_id;
