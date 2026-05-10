-- blockchain_cross_table_hash_enforce.sql
-- Enforce cross-table hash behavior for donation + blockchain_transactions verification.
-- Requirements:
-- 1) donations changes generate donation_row_hash + payload_history entries
-- 2) blockchain_transactions changes generate tx_row_hash + payload_history entries
-- 3) blockchain tx and donation hash values are compared directly/originally without snapshots

ALTER TABLE `donations`
  ADD COLUMN IF NOT EXISTS `donation_row_hash` CHAR(64) NULL;

ALTER TABLE `blockchain_transactions`
  ADD COLUMN IF NOT EXISTS `tx_row_hash` CHAR(64) NULL;

DROP FUNCTION IF EXISTS `fn_donation_row_hash_v1`;
DROP FUNCTION IF EXISTS `fn_blockchain_tx_row_hash_v1`;

DROP TRIGGER IF EXISTS `trg_donation_rowhash_bi`;
DROP TRIGGER IF EXISTS `trg_donation_rowhash_bu`;
DROP TRIGGER IF EXISTS `trg_donation_payload_hash_ai`;
DROP TRIGGER IF EXISTS `trg_donation_payload_hash_au`;

DROP TRIGGER IF EXISTS `trg_blockchain_tx_rowhash_bi`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_rowhash_bu`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_payload_ai`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_payload_au`;

DELIMITER $$

CREATE FUNCTION `fn_donation_row_hash_v1`(
  p_don_id INT(11),
  p_fund_id INT(11),
  p_don_donorid INT(11),
  p_don_donorname VARCHAR(80),
  p_don_receiver VARCHAR(80),
  p_don_paymethod VARCHAR(50),
  p_don_amount DECIMAL(12,2),
  p_don_refnum VARCHAR(80),
  p_don_status VARCHAR(50),
  p_don_date DATETIME,
  p_don_notes LONGTEXT,
  p_blockchain_tx_hash VARCHAR(255),
  p_block_number BIGINT(20),
  p_gas_used BIGINT(20),
  p_verification_status VARCHAR(20),
  p_verification_date DATETIME,
  p_donor_wallet_address VARCHAR(42),
  p_recorded_by_admin TINYINT(1)
) RETURNS CHAR(64)
DETERMINISTIC
BEGIN
  DECLARE payload LONGTEXT;

  SET payload = CONCAT_WS('|',
    'don_id=', COALESCE(p_don_id, -1),
    'fund_id=', COALESCE(p_fund_id, -1),
    'don_donorid=', COALESCE(p_don_donorid, -1),
    'don_donorname=', COALESCE(p_don_donorname, ''),
    'don_receiver=', COALESCE(p_don_receiver, ''),
    'don_paymethod=', COALESCE(p_don_paymethod, ''),
    'don_amount=', REPLACE(FORMAT(COALESCE(p_don_amount,0), 2), ',', ''),
    'don_refnum=', COALESCE(p_don_refnum, ''),
    'don_status=', COALESCE(p_don_status, ''),
    'don_date=', COALESCE(DATE_FORMAT(p_don_date, '%Y-%m-%d %H:%i:%s'), ''),
    'don_notes=', COALESCE(p_don_notes, ''),
    'block_number=', COALESCE(p_block_number, -1),
    'gas_used=', COALESCE(p_gas_used, -1),
    'verification_status=', COALESCE(p_verification_status, ''),
    'verification_date=', COALESCE(DATE_FORMAT(p_verification_date, '%Y-%m-%d %H:%i:%s'), ''),
    'blockchain_tx_hash=', COALESCE(p_blockchain_tx_hash, ''),
    'donor_wallet_address=', LOWER(COALESCE(p_donor_wallet_address, '')),
    'recorded_by_admin=', COALESCE(p_recorded_by_admin, 0)
  );

  RETURN LOWER(SHA2(payload, 256));
END$$

CREATE FUNCTION `fn_blockchain_tx_row_hash_v1`(
  p_id INT(11),
  p_transaction_type VARCHAR(32),
  p_related_id INT(11),
  p_blockchain_tx_hash VARCHAR(255),
  p_block_number BIGINT(20),
  p_gas_used BIGINT(20),
  p_gas_price BIGINT(20),
  p_status VARCHAR(20),
  p_confirmation_blocks INT(11),
  p_created_at DATETIME,
  p_confirmed_at DATETIME,
  p_error_message TEXT
) RETURNS CHAR(64)
DETERMINISTIC
BEGIN
  DECLARE payload LONGTEXT;

  SET payload = CONCAT_WS('|',
    'id=', COALESCE(p_id, -1),
    'transaction_type=', COALESCE(p_transaction_type, ''),
    'related_id=', COALESCE(p_related_id, -1),
    'blockchain_tx_hash=', COALESCE(p_blockchain_tx_hash, ''),
    'block_number=', COALESCE(p_block_number, -1),
    'gas_used=', COALESCE(p_gas_used, -1),
    'gas_price=', COALESCE(p_gas_price, -1),
    'status=', COALESCE(p_status, ''),
    'confirmation_blocks=', COALESCE(p_confirmation_blocks, 0),
    'created_at=', COALESCE(DATE_FORMAT(p_created_at, '%Y-%m-%d %H:%i:%s'), ''),
    'confirmed_at=', COALESCE(DATE_FORMAT(p_confirmed_at, '%Y-%m-%d %H:%i:%s'), ''),
    'error_message=', COALESCE(p_error_message, '')
  );

  RETURN LOWER(SHA2(payload, 256));
END$$

CREATE TRIGGER `trg_donation_rowhash_bi`
BEFORE INSERT ON `donations`
FOR EACH ROW
BEGIN
  SET NEW.donation_row_hash = fn_donation_row_hash_v1(
    NEW.don_id,
    NEW.fund_id,
    NEW.don_donorid,
    NEW.don_donorname,
    NEW.don_receiver,
    NEW.don_paymethod,
    NEW.don_amount,
    NEW.don_refnum,
    NEW.don_status,
    NEW.don_date,
    NEW.don_notes,
    NEW.blockchain_tx_hash,
    NEW.block_number,
    NEW.gas_used,
    NEW.verification_status,
    NEW.verification_date,
    NEW.donor_wallet_address,
    NEW.recorded_by_admin
  );
END$$

CREATE TRIGGER `trg_donation_rowhash_bu`
BEFORE UPDATE ON `donations`
FOR EACH ROW
BEGIN
  SET NEW.donation_row_hash = fn_donation_row_hash_v1(
    NEW.don_id,
    NEW.fund_id,
    NEW.don_donorid,
    NEW.don_donorname,
    NEW.don_receiver,
    NEW.don_paymethod,
    NEW.don_amount,
    NEW.don_refnum,
    NEW.don_status,
    NEW.don_date,
    NEW.don_notes,
    NEW.blockchain_tx_hash,
    NEW.block_number,
    NEW.gas_used,
    NEW.verification_status,
    NEW.verification_date,
    NEW.donor_wallet_address,
    NEW.recorded_by_admin
  );
END$$

CREATE TRIGGER `trg_donation_payload_hash_ai`
AFTER INSERT ON `donations`
FOR EACH ROW
BEGIN
  INSERT INTO `payload_history` (
    `donation_id`, `don_refnum`, `payload_hash`, `payload_data`,
    `previous_hash`, `change_type`, `change_reason`, `changed_by`, `created_at`
  )
  VALUES (
    NEW.`don_id`,
    NEW.`don_refnum`,
    NEW.`donation_row_hash`,
    IF(
      NEW.`don_notes` IS NULL
      OR NEW.`don_notes` = ''
      OR JSON_VALID(NEW.`don_notes`) = 0,
      JSON_OBJECT(),
      NEW.`don_notes`
    ),
    NULL,
    'created',
    'Initial row hash capture',
    CASE
      WHEN NEW.`don_donorid` > 0 AND EXISTS (SELECT 1 FROM `users` WHERE `id` = NEW.`don_donorid`)
      THEN NEW.`don_donorid`
      ELSE NULL
    END,
    NOW()
  );
END$$

CREATE TRIGGER `trg_donation_payload_hash_au`
AFTER UPDATE ON `donations`
FOR EACH ROW
BEGIN
  IF NOT (OLD.`donation_row_hash` <=> NEW.`donation_row_hash`) THEN
    INSERT INTO `payload_history` (
      `donation_id`, `don_refnum`, `payload_hash`, `payload_data`,
    `previous_hash`, `change_type`, `change_reason`, `changed_by`, `created_at`
  )
  VALUES (
      NEW.`don_id`,
      NEW.`don_refnum`,
      NEW.`donation_row_hash`,
      IF(
        NEW.`don_notes` IS NULL
        OR NEW.`don_notes` = ''
        OR JSON_VALID(NEW.`don_notes`) = 0,
        JSON_OBJECT(),
        NEW.`don_notes`
      ),
      OLD.`donation_row_hash`,
      'updated',
      'Donation row hash changed',
      CASE
        WHEN NEW.`don_donorid` > 0 AND EXISTS (SELECT 1 FROM `users` WHERE `id` = NEW.`don_donorid`)
        THEN NEW.`don_donorid`
        ELSE NULL
      END,
      NOW()
    );
  END IF;
END$$

CREATE TRIGGER `trg_blockchain_tx_rowhash_bi`
BEFORE INSERT ON `blockchain_transactions`
FOR EACH ROW
BEGIN
  SET NEW.tx_row_hash = fn_blockchain_tx_row_hash_v1(
    NEW.id,
    NEW.transaction_type,
    NEW.related_id,
    NEW.blockchain_tx_hash,
    NEW.block_number,
    NEW.gas_used,
    NEW.gas_price,
    NEW.status,
    NEW.confirmation_blocks,
    NEW.created_at,
    NEW.confirmed_at,
    NEW.error_message
  );
END$$

CREATE TRIGGER `trg_blockchain_tx_rowhash_bu`
BEFORE UPDATE ON `blockchain_transactions`
FOR EACH ROW
BEGIN
  SET NEW.tx_row_hash = fn_blockchain_tx_row_hash_v1(
    NEW.id,
    NEW.transaction_type,
    NEW.related_id,
    NEW.blockchain_tx_hash,
    NEW.block_number,
    NEW.gas_used,
    NEW.gas_price,
    NEW.status,
    NEW.confirmation_blocks,
    NEW.created_at,
    NEW.confirmed_at,
    NEW.error_message
  );
END$$

CREATE TRIGGER `trg_blockchain_tx_payload_ai`
AFTER INSERT ON `blockchain_transactions`
FOR EACH ROW
INSERT INTO `payload_history` (
  `donation_id`, `don_refnum`, `payload_hash`, `payload_data`,
  `previous_hash`, `change_type`, `change_reason`, `changed_by`, `created_at`
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
  CASE
    WHEN NEW.`transaction_type` = 'donation' THEN 'created'
    ELSE 'created'
  END,
  'blockchain tx row created',
  CASE
    WHEN d.`don_donorid` > 0
      AND EXISTS (SELECT 1 FROM `users` WHERE `id` = d.`don_donorid`)
    THEN d.`don_donorid`
    ELSE NULL
  END,
  NOW()
FROM `donations` d
WHERE NEW.`transaction_type` = 'donation'
  AND d.`don_id` = NEW.`related_id`$$

CREATE TRIGGER `trg_blockchain_tx_payload_au`
AFTER UPDATE ON `blockchain_transactions`
FOR EACH ROW
INSERT INTO `payload_history` (
  `donation_id`, `don_refnum`, `payload_hash`, `payload_data`,
  `previous_hash`, `change_type`, `change_reason`, `changed_by`, `created_at`
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
  'updated',
  'blockchain tx row hash changed',
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
  AND d.`don_id` = NEW.`related_id`$$

DELIMITER ;

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
  d.`recorded_by_admin`
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
WHERE bt.`tx_row_hash` IS NULL
  AND bt.`id` IS NOT NULL;
