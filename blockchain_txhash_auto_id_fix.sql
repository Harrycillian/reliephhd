-- Recompute tx_row_hash values for existing blockchain transaction rows.
UPDATE `blockchain_transactions` b
SET `tx_row_hash` = fn_blockchain_tx_row_hash_v1(
  b.`id`,
  b.`transaction_type`,
  b.`related_id`,
  b.`blockchain_tx_hash`,
  b.`block_number`,
  b.`gas_used`,
  b.`gas_price`,
  b.`status`,
  b.`confirmation_blocks`,
  b.`created_at`,
  b.`confirmed_at`,
  b.`error_message`
)
WHERE `tx_row_hash` IS NULL
   OR `tx_row_hash` <> fn_blockchain_tx_row_hash_v1(
      b.`id`,
      b.`transaction_type`,
      b.`related_id`,
      b.`blockchain_tx_hash`,
      b.`block_number`,
      b.`gas_used`,
      b.`gas_price`,
      b.`status`,
      b.`confirmation_blocks`,
      b.`created_at`,
      b.`confirmed_at`,
      b.`error_message`
   );
