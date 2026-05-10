-- reset_false_positive_tamper_flags.sql
-- Clears tamper flags that were set by the old trigger logic on normal blockchain writes.

UPDATE `donations`
SET `is_tampered` = 0
WHERE COALESCE(`is_tampered`, 0) = 1
  AND COALESCE(LOWER(`blockchain_tx_hash`), '') = COALESCE(LOWER(`original_tx_hash`), '');

UPDATE `blockchain_transactions`
SET `is_tampered` = 0
WHERE COALESCE(`is_tampered`, 0) = 1
  AND COALESCE(LOWER(`blockchain_tx_hash`), '') = COALESCE(LOWER(`original_tx_hash`), '');
