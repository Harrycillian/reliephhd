-- add_tamper_flags.sql
-- Adds explicit tamper flags that turn on when tracked row values change.

ALTER TABLE `donations`
  ADD COLUMN IF NOT EXISTS `is_tampered` TINYINT(1) NOT NULL DEFAULT 0;

ALTER TABLE `blockchain_transactions`
  ADD COLUMN IF NOT EXISTS `is_tampered` TINYINT(1) NOT NULL DEFAULT 0;

DROP TRIGGER IF EXISTS `trg_donation_tamper_bi`;
DROP TRIGGER IF EXISTS `trg_donation_tamper_bu`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_tamper_bi`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_tamper_bu`;

DELIMITER $$

CREATE TRIGGER `trg_donation_tamper_bi`
BEFORE INSERT ON `donations`
FOR EACH ROW
BEGIN
  SET NEW.`is_tampered` = 0;
END$$

CREATE TRIGGER `trg_donation_tamper_bu`
BEFORE UPDATE ON `donations`
FOR EACH ROW
BEGIN
  DECLARE changed_core TINYINT(1) DEFAULT 0;
  DECLARE initial_blockchain_write TINYINT(1) DEFAULT 0;

  SET changed_core = (
    NOT (OLD.`fund_id` <=> NEW.`fund_id`) OR
    NOT (OLD.`don_donorid` <=> NEW.`don_donorid`) OR
    NOT (OLD.`don_donorname` <=> NEW.`don_donorname`) OR
    NOT (OLD.`don_paymethod` <=> NEW.`don_paymethod`) OR
    NOT (OLD.`don_amount` <=> NEW.`don_amount`) OR
    NOT (OLD.`don_refnum` <=> NEW.`don_refnum`) OR
    NOT (OLD.`don_date` <=> NEW.`don_date`) OR
    NOT (OLD.`donor_wallet_address` <=> NEW.`donor_wallet_address`) OR
    NOT (OLD.`recorded_by_admin` <=> NEW.`recorded_by_admin`)
  );

  SET initial_blockchain_write = (
    COALESCE(OLD.`original_tx_hash`, '') = ''
    AND changed_core = 0
    AND (
      NOT (OLD.`blockchain_tx_hash` <=> NEW.`blockchain_tx_hash`) OR
      NOT (OLD.`block_number` <=> NEW.`block_number`) OR
      NOT (OLD.`gas_used` <=> NEW.`gas_used`) OR
      NOT (OLD.`verification_status` <=> NEW.`verification_status`) OR
      NOT (OLD.`verification_date` <=> NEW.`verification_date`) OR
      NOT (OLD.`original_tx_hash` <=> NEW.`original_tx_hash`)
    )
  );

  IF COALESCE(OLD.`is_tampered`, 0) = 1 THEN
    SET NEW.`is_tampered` = 1;
  ELSEIF initial_blockchain_write = 1 THEN
    SET NEW.`is_tampered` = 0;
  ELSEIF changed_core = 1 THEN
    SET NEW.`is_tampered` = 1;
  ELSE
    SET NEW.`is_tampered` = COALESCE(OLD.`is_tampered`, 0);
  END IF;
END$$

CREATE TRIGGER `trg_blockchain_tx_tamper_bi`
BEFORE INSERT ON `blockchain_transactions`
FOR EACH ROW
BEGIN
  SET NEW.`is_tampered` = 0;
END$$

CREATE TRIGGER `trg_blockchain_tx_tamper_bu`
BEFORE UPDATE ON `blockchain_transactions`
FOR EACH ROW
BEGIN
  DECLARE changed_core TINYINT(1) DEFAULT 0;
  DECLARE initial_blockchain_write TINYINT(1) DEFAULT 0;

  SET changed_core = (
    NOT (OLD.`transaction_type` <=> NEW.`transaction_type`) OR
    NOT (OLD.`related_id` <=> NEW.`related_id`)
  );

  SET initial_blockchain_write = (
    COALESCE(OLD.`original_tx_hash`, '') = ''
    AND changed_core = 0
    AND (
      NOT (OLD.`blockchain_tx_hash` <=> NEW.`blockchain_tx_hash`) OR
      NOT (OLD.`block_number` <=> NEW.`block_number`) OR
      NOT (OLD.`gas_used` <=> NEW.`gas_used`) OR
      NOT (OLD.`gas_price` <=> NEW.`gas_price`) OR
      NOT (OLD.`status` <=> NEW.`status`) OR
      NOT (OLD.`confirmation_blocks` <=> NEW.`confirmation_blocks`) OR
      NOT (OLD.`confirmed_at` <=> NEW.`confirmed_at`) OR
      NOT (OLD.`error_message` <=> NEW.`error_message`) OR
      NOT (OLD.`original_tx_hash` <=> NEW.`original_tx_hash`)
    )
  );

  IF COALESCE(OLD.`is_tampered`, 0) = 1 THEN
    SET NEW.`is_tampered` = 1;
  ELSEIF initial_blockchain_write = 1 THEN
    SET NEW.`is_tampered` = 0;
  ELSEIF changed_core = 1 THEN
    SET NEW.`is_tampered` = 1;
  ELSE
    SET NEW.`is_tampered` = COALESCE(OLD.`is_tampered`, 0);
  END IF;
END$$

-- Backfill existing rows as clean by default after trigger install.
UPDATE `donations` SET `is_tampered` = 0 WHERE `is_tampered` IS NULL;
UPDATE `blockchain_transactions` SET `is_tampered` = 0 WHERE `is_tampered` IS NULL;

DELIMITER ;
