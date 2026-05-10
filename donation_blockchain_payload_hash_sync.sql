-- donation_blockchain_payload_hash_sync.sql
-- MySQL/MariaDB trigger-only implementation:
-- 1) donation row changed -> recompute donation hash, append payload history
-- 2) blockchain transaction row changed -> recompute tx hash, append payload history
-- 3) no application code changes required

-- Add hash columns
ALTER TABLE `donations`
  ADD COLUMN IF NOT EXISTS `donation_row_hash` CHAR(64) NULL,
  ADD INDEX IF NOT EXISTS `idx_donations_row_hash` (`donation_row_hash`);

ALTER TABLE `blockchain_transactions`
  ADD COLUMN IF NOT EXISTS `tx_row_hash` CHAR(64) NULL,
  ADD INDEX IF NOT EXISTS `idx_blockchain_tx_row_hash` (`tx_row_hash`);

-- Remove existing versions to keep re-runs idempotent
DROP TRIGGER IF EXISTS `track_payload_on_insert`;
DROP TRIGGER IF EXISTS `track_payload_on_update`;
DROP TRIGGER IF EXISTS `trg_donation_rowhash_bi`;
DROP TRIGGER IF EXISTS `trg_donation_rowhash_bu`;
DROP TRIGGER IF EXISTS `trg_donation_payload_hash_ai`;
DROP TRIGGER IF EXISTS `trg_donation_payload_hash_au`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_hash_bi`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_hash_bu`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_payload_ai`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_payload_au`;

-- 1) Recompute donation row hash on INSERT
CREATE TRIGGER `trg_donation_rowhash_bi`
BEFORE INSERT ON `donations`
FOR EACH ROW
SET NEW.`donation_row_hash` = LOWER(SHA2(
  CONCAT_WS('|',
    'don_id=', COALESCE(NEW.`don_id`, -1),
    'fund_id=', COALESCE(NEW.`fund_id`, -1),
    'don_donorid=', COALESCE(NEW.`don_donorid`, -1),
    'don_donorname=', COALESCE(NEW.`don_donorname`, ''),
    'don_receiver=', COALESCE(NEW.`don_receiver`, ''),
    'don_paymethod=', COALESCE(NEW.`don_paymethod`, ''),
    'don_amount=', REPLACE(FORMAT(COALESCE(NEW.`don_amount`, 0), 2), ',', ''),
    'don_refnum=', COALESCE(NEW.`don_refnum`, ''),
    'don_status=', COALESCE(NEW.`don_status`, ''),
    'don_date=', COALESCE(DATE_FORMAT(NEW.`don_date`, '%Y-%m-%d %H:%i:%s'), ''),
    'don_notes=', COALESCE(NEW.`don_notes`, ''),
    'blockchain_tx_hash=', COALESCE(NEW.`blockchain_tx_hash`, ''),
    'block_number=', COALESCE(NEW.`block_number`, -1),
    'gas_used=', COALESCE(NEW.`gas_used`, -1),
    'verification_status=', COALESCE(NEW.`verification_status`, ''),
    'verification_date=', COALESCE(DATE_FORMAT(NEW.`verification_date`, '%Y-%m-%d %H:%i:%s'), ''),
    'donor_wallet_address=', LOWER(COALESCE(NEW.`donor_wallet_address`, '')),
    'recorded_by_admin=', COALESCE(NEW.`recorded_by_admin`, 0)
  ), 256));

-- 1b) Recompute donation row hash on UPDATE
CREATE TRIGGER `trg_donation_rowhash_bu`
BEFORE UPDATE ON `donations`
FOR EACH ROW
SET NEW.`donation_row_hash` = LOWER(SHA2(
  CONCAT_WS('|',
    'don_id=', COALESCE(NEW.`don_id`, -1),
    'fund_id=', COALESCE(NEW.`fund_id`, -1),
    'don_donorid=', COALESCE(NEW.`don_donorid`, -1),
    'don_donorname=', COALESCE(NEW.`don_donorname`, ''),
    'don_receiver=', COALESCE(NEW.`don_receiver`, ''),
    'don_paymethod=', COALESCE(NEW.`don_paymethod`, ''),
    'don_amount=', REPLACE(FORMAT(COALESCE(NEW.`don_amount`, 0), 2), ',', ''),
    'don_refnum=', COALESCE(NEW.`don_refnum`, ''),
    'don_status=', COALESCE(NEW.`don_status`, ''),
    'don_date=', COALESCE(DATE_FORMAT(NEW.`don_date`, '%Y-%m-%d %H:%i:%s'), ''),
    'don_notes=', COALESCE(NEW.`don_notes`, ''),
    'blockchain_tx_hash=', COALESCE(NEW.`blockchain_tx_hash`, ''),
    'block_number=', COALESCE(NEW.`block_number`, -1),
    'gas_used=', COALESCE(NEW.`gas_used`, -1),
    'verification_status=', COALESCE(NEW.`verification_status`, ''),
    'verification_date=', COALESCE(DATE_FORMAT(NEW.`verification_date`, '%Y-%m-%d %H:%i:%s'), ''),
    'donor_wallet_address=', LOWER(COALESCE(NEW.`donor_wallet_address`, '')),
    'recorded_by_admin=', COALESCE(NEW.`recorded_by_admin`, 0)
  ), 256));

-- 2) Write payload history for donation insert
CREATE TRIGGER `trg_donation_payload_hash_ai`
AFTER INSERT ON `donations`
FOR EACH ROW
INSERT INTO `payload_history` (
  `donation_id`, `don_refnum`, `payload_hash`, `payload_data`,
  `previous_hash`, `change_reason`, `change_type`, `changed_by`, `created_at`
)
SELECT
  NEW.`don_id`,
  NEW.`don_refnum`,
  NEW.`donation_row_hash`,
  JSON_OBJECT(
    'source', 'donations',
    'don_id', NEW.`don_id`,
    'fund_id', NEW.`fund_id`,
    'don_donorid', NEW.`don_donorid`,
    'don_donorname', NEW.`don_donorname`,
    'don_receiver', NEW.`don_receiver`,
    'don_paymethod', NEW.`don_paymethod`,
    'don_amount', NEW.`don_amount`,
    'don_status', NEW.`don_status`,
    'don_date', DATE_FORMAT(NEW.`don_date`, '%Y-%m-%d %H:%i:%s'),
    'don_notes', NEW.`don_notes`,
    'blockchain_tx_hash', NEW.`blockchain_tx_hash`,
    'block_number', NEW.`block_number`,
    'gas_used', NEW.`gas_used`,
    'verification_status', NEW.`verification_status`,
    'verification_date', DATE_FORMAT(NEW.`verification_date`, '%Y-%m-%d %H:%i:%s'),
    'donor_wallet_address', NEW.`donor_wallet_address`,
    'recorded_by_admin', NEW.`recorded_by_admin`
  ),
  NULL,
  'initial creation',
  'created',
  CASE
    WHEN NEW.`don_donorid` > 0
      AND EXISTS (SELECT 1 FROM `users` WHERE `id` = NEW.`don_donorid`)
    THEN NEW.`don_donorid`
    ELSE NULL
  END,
  NOW();

-- 2b) Write payload history for donation updates only when hash changed
CREATE TRIGGER `trg_donation_payload_hash_au`
AFTER UPDATE ON `donations`
FOR EACH ROW
INSERT INTO `payload_history` (
  `donation_id`, `don_refnum`, `payload_hash`, `payload_data`,
  `previous_hash`, `change_reason`, `change_type`, `changed_by`, `created_at`
)
SELECT
  NEW.`don_id`,
  NEW.`don_refnum`,
  NEW.`donation_row_hash`,
  JSON_OBJECT(
    'source', 'donations',
    'don_id', NEW.`don_id`,
    'fund_id', NEW.`fund_id`,
    'don_donorid', NEW.`don_donorid`,
    'don_donorname', NEW.`don_donorname`,
    'don_receiver', NEW.`don_receiver`,
    'don_paymethod', NEW.`don_paymethod`,
    'don_amount', NEW.`don_amount`,
    'don_status', NEW.`don_status`,
    'don_date', DATE_FORMAT(NEW.`don_date`, '%Y-%m-%d %H:%i:%s'),
    'don_notes', NEW.`don_notes`,
    'blockchain_tx_hash', NEW.`blockchain_tx_hash`,
    'block_number', NEW.`block_number`,
    'gas_used', NEW.`gas_used`,
    'verification_status', NEW.`verification_status`,
    'verification_date', DATE_FORMAT(NEW.`verification_date`, '%Y-%m-%d %H:%i:%s'),
    'donor_wallet_address', NEW.`donor_wallet_address`,
    'recorded_by_admin', NEW.`recorded_by_admin`
  ),
  OLD.`donation_row_hash`,
  'donation row hash changed',
  'updated',
  CASE
    WHEN NEW.`don_donorid` > 0
      AND EXISTS (SELECT 1 FROM `users` WHERE `id` = NEW.`don_donorid`)
    THEN NEW.`don_donorid`
    ELSE NULL
  END,
  NOW()
FROM DUAL
WHERE NOT (OLD.`donation_row_hash` <=> NEW.`donation_row_hash`);

-- 3) Recompute blockchain tx hash on INSERT
CREATE TRIGGER `trg_blockchain_tx_hash_bi`
BEFORE INSERT ON `blockchain_transactions`
FOR EACH ROW
SET NEW.`tx_row_hash` = LOWER(SHA2(
  CONCAT_WS('|',
    'id=', COALESCE(NEW.`id`, -1),
    'transaction_type=', COALESCE(NEW.`transaction_type`, ''),
    'related_id=', COALESCE(NEW.`related_id`, -1),
    'blockchain_tx_hash=', COALESCE(NEW.`blockchain_tx_hash`, ''),
    'block_number=', COALESCE(NEW.`block_number`, -1),
    'gas_used=', COALESCE(NEW.`gas_used`, -1),
    'gas_price=', COALESCE(NEW.`gas_price`, -1),
    'status=', COALESCE(NEW.`status`, ''),
    'confirmation_blocks=', COALESCE(NEW.`confirmation_blocks`, 0),
    'created_at=', COALESCE(DATE_FORMAT(NEW.`created_at`, '%Y-%m-%d %H:%i:%s'), ''),
    'confirmed_at=', COALESCE(DATE_FORMAT(NEW.`confirmed_at`, '%Y-%m-%d %H:%i:%s'), ''),
    'error_message=', COALESCE(NEW.`error_message`, '')
  ), 256));

-- 3b) Recompute blockchain tx hash on UPDATE
CREATE TRIGGER `trg_blockchain_tx_hash_bu`
BEFORE UPDATE ON `blockchain_transactions`
FOR EACH ROW
SET NEW.`tx_row_hash` = LOWER(SHA2(
  CONCAT_WS('|',
    'id=', COALESCE(NEW.`id`, -1),
    'transaction_type=', COALESCE(NEW.`transaction_type`, ''),
    'related_id=', COALESCE(NEW.`related_id`, -1),
    'blockchain_tx_hash=', COALESCE(NEW.`blockchain_tx_hash`, ''),
    'block_number=', COALESCE(NEW.`block_number`, -1),
    'gas_used=', COALESCE(NEW.`gas_used`, -1),
    'gas_price=', COALESCE(NEW.`gas_price`, -1),
    'status=', COALESCE(NEW.`status`, ''),
    'confirmation_blocks=', COALESCE(NEW.`confirmation_blocks`, 0),
    'created_at=', COALESCE(DATE_FORMAT(NEW.`created_at`, '%Y-%m-%d %H:%i:%s'), ''),
    'confirmed_at=', COALESCE(DATE_FORMAT(NEW.`confirmed_at`, '%Y-%m-%d %H:%i:%s'), ''),
    'error_message=', COALESCE(NEW.`error_message`, '')
  ), 256));

-- 4) Record blockchain tx history for donation-related tx create
CREATE TRIGGER `trg_blockchain_tx_payload_ai`
AFTER INSERT ON `blockchain_transactions`
FOR EACH ROW
INSERT INTO `payload_history` (
  `donation_id`, `don_refnum`, `payload_hash`, `payload_data`,
  `previous_hash`, `change_reason`, `change_type`, `changed_by`, `created_at`
)
SELECT
  NEW.`related_id`,
  d.`don_refnum`,
  NEW.`tx_row_hash`,
  JSON_OBJECT(
    'source', 'blockchain_transactions',
    'tx_id', NEW.`id`,
    'transaction_type', NEW.`transaction_type`,
    'related_id', NEW.`related_id`,
    'blockchain_tx_hash', NEW.`blockchain_tx_hash`,
    'block_number', NEW.`block_number`,
    'gas_used', NEW.`gas_used`,
    'gas_price', NEW.`gas_price`,
    'status', NEW.`status`,
    'confirmation_blocks', NEW.`confirmation_blocks`,
    'created_at', DATE_FORMAT(NEW.`created_at`, '%Y-%m-%d %H:%i:%s'),
    'confirmed_at', DATE_FORMAT(NEW.`confirmed_at`, '%Y-%m-%d %H:%i:%s'),
    'error_message', NEW.`error_message`
  ),
  NULL,
  'blockchain tx created',
  'created',
  CASE
    WHEN d.`don_donorid` > 0
      AND EXISTS (SELECT 1 FROM `users` WHERE `id` = d.`don_donorid`)
    THEN d.`don_donorid`
    ELSE NULL
  END,
  NOW()
FROM `donations` d
WHERE NEW.`transaction_type` = 'donation'
  AND d.`don_id` = NEW.`related_id`;

-- 4b) Record blockchain tx history for donation-related tx update when tx hash changes
CREATE TRIGGER `trg_blockchain_tx_payload_au`
AFTER UPDATE ON `blockchain_transactions`
FOR EACH ROW
INSERT INTO `payload_history` (
  `donation_id`, `don_refnum`, `payload_hash`, `payload_data`,
  `previous_hash`, `change_reason`, `change_type`, `changed_by`, `created_at`
)
SELECT
  NEW.`related_id`,
  d.`don_refnum`,
  NEW.`tx_row_hash`,
  JSON_OBJECT(
    'source', 'blockchain_transactions',
    'tx_id', NEW.`id`,
    'transaction_type', NEW.`transaction_type`,
    'related_id', NEW.`related_id`,
    'blockchain_tx_hash', NEW.`blockchain_tx_hash`,
    'block_number', NEW.`block_number`,
    'gas_used', NEW.`gas_used`,
    'gas_price', NEW.`gas_price`,
    'status', NEW.`status`,
    'confirmation_blocks', NEW.`confirmation_blocks`,
    'created_at', DATE_FORMAT(NEW.`created_at`, '%Y-%m-%d %H:%i:%s'),
    'confirmed_at', DATE_FORMAT(NEW.`confirmed_at`, '%Y-%m-%d %H:%i:%s'),
    'error_message', NEW.`error_message`
  ),
  OLD.`tx_row_hash`,
  'blockchain tx hash changed',
  'updated',
  CASE
    WHEN d.`don_donorid` > 0
      AND EXISTS (SELECT 1 FROM `users` WHERE `id` = d.`don_donorid`)
    THEN d.`don_donorid`
    ELSE NULL
  END,
  NOW()
FROM `donations` d
WHERE NEW.`transaction_type` = 'donation'
  AND NOT (OLD.`tx_row_hash` <=> NEW.`tx_row_hash`)
  AND d.`don_id` = NEW.`related_id`;
