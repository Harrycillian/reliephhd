-- donation_hash_only_triggers.sql
-- MySQL-only: updates only hashes and writes payload_history

ALTER TABLE `donations`
  ADD COLUMN IF NOT EXISTS `donation_row_hash` CHAR(64) NULL;

DELIMITER $$

DROP TRIGGER IF EXISTS `track_payload_on_insert`;
DROP TRIGGER IF EXISTS `track_payload_on_update`;
DROP TRIGGER IF EXISTS `trg_donation_rowhash_bi`;
DROP TRIGGER IF EXISTS `trg_donation_rowhash_bu`;
DROP TRIGGER IF EXISTS `trg_donation_payload_hash_ai`;
DROP TRIGGER IF EXISTS `trg_donation_payload_hash_au`;
DROP FUNCTION IF EXISTS `fn_donation_row_hash_v1`;

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
    'don_amount=', REPLACE(FORMAT(COALESCE(p_don_amount,0),2), ',', ''),
    'don_refnum=', COALESCE(p_don_refnum, ''),
    'don_status=', COALESCE(p_don_status, ''),
    'don_date=', COALESCE(DATE_FORMAT(p_don_date, '%Y-%m-%d %H:%i:%s'), ''),
    'don_notes=', COALESCE(p_don_notes, ''),
    'blockchain_tx_hash=', COALESCE(p_blockchain_tx_hash, ''),
    'block_number=', COALESCE(p_block_number, -1),
    'gas_used=', COALESCE(p_gas_used, -1),
    'verification_status=', COALESCE(p_verification_status, ''),
    'verification_date=', COALESCE(DATE_FORMAT(p_verification_date, '%Y-%m-%d %H:%i:%s'), ''),
    'donor_wallet_address=', LOWER(COALESCE(p_donor_wallet_address, '')),
    'recorded_by_admin=', COALESCE(p_recorded_by_admin, 0)
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
    `previous_hash`, `change_type`, `changed_by`, `created_at`
  )
  VALUES (
    NEW.`don_id`,
    NEW.`don_refnum`,
    COALESCE(NEW.`donation_row_hash`, fn_donation_row_hash_v1(
      NEW.`don_id`, NEW.`fund_id`, NEW.`don_donorid`, NEW.`don_donorname`, NEW.`don_receiver`,
      NEW.`don_paymethod`, NEW.`don_amount`, NEW.`don_refnum`, NEW.`don_status`,
      NEW.`don_date`, NEW.`don_notes`, NEW.`blockchain_tx_hash`, NEW.`block_number`,
      NEW.`gas_used`, NEW.`verification_status`, NEW.`verification_date`, NEW.`donor_wallet_address`, NEW.`recorded_by_admin`
    )),
    NEW.`don_notes`,
    NULL,
    'created',
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
      `previous_hash`, `change_type`, `changed_by`, `created_at`, `change_reason`
    )
    VALUES (
      NEW.`don_id`,
      NEW.`don_refnum`,
      NEW.`donation_row_hash`,
      NEW.`don_notes`,
      OLD.`donation_row_hash`,
      'updated',
      CASE
        WHEN NEW.`don_donorid` > 0 AND EXISTS (SELECT 1 FROM `users` WHERE `id` = NEW.`don_donorid`)
        THEN NEW.`don_donorid`
        ELSE NULL
      END,
      NOW(),
      'Hash changed due to donation row update'
    );
  END IF;
END$$

DELIMITER ;
