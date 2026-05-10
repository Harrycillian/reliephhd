-- remove_snapshot_artifacts.sql
-- Removes snapshot-based blockchain verification artifacts.

DROP TRIGGER IF EXISTS `trg_blockchain_tx_snapshot_bi`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_snapshot_bu`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_rowhash_snapshot_bi`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_rowhash_snapshot_bu`;

ALTER TABLE `blockchain_transactions`
  DROP COLUMN IF EXISTS `donation_row_hash_snapshot`,
  DROP COLUMN IF EXISTS `tx_row_hash_snapshot`;
