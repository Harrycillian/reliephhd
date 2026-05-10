-- blockchain_integrity_reconcile.sql
-- Recompute hashes under the currently deployed SQL functions.

-- Normalize all existing hashes to the currently deployed hash formulas.
-- Run only when you are OK that current DB content is the trusted baseline.
UPDATE `donations` d
SET d.`donation_row_hash` = fn_donation_row_hash_v1(
  d.`don_id`,
  d.`fund_id`,
  d.`don_donorid`,
  d.`don_donorname`,
  d.`don_receiver`,
  d.`don_paymethod`,
  d.`don_amount`,
  d.`don_refnum`,
  d.`don_status`,
  d.`don_date`,
  d.`don_notes`,
  d.`blockchain_tx_hash`,
  d.`block_number`,
  d.`gas_used`,
  d.`verification_status`,
  d.`verification_date`,
  d.`donor_wallet_address`,
  COALESCE(d.`recorded_by_admin`, 0)
)
WHERE d.`donation_row_hash` IS NULL;

UPDATE `blockchain_transactions` bt
SET bt.`tx_row_hash` = fn_blockchain_tx_row_hash_v1(
  bt.`id`,
  bt.`transaction_type`,
  bt.`related_id`,
  bt.`blockchain_tx_hash`,
  bt.`block_number`,
  bt.`gas_used`,
  bt.`gas_price`,
  bt.`status`,
  bt.`confirmation_blocks`,
  bt.`created_at`,
  bt.`confirmed_at`,
  bt.`error_message`
)
WHERE bt.`tx_row_hash` IS NULL;
