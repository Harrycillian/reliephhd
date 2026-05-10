-- add_original_hash_baseline.sql
-- Immutable baseline hashes:
-- - donations.donation_row_hash_original stores first-seen donation row hash
-- - donations.original_tx_hash stores first-seen blockchain tx hash for the donation
-- - blockchain_transactions.tx_row_hash_original stores first-seen tx row hash
-- - blockchain_transactions.original_tx_hash stores first-seen blockchain tx hash

ALTER TABLE `donations`
  ADD COLUMN IF NOT EXISTS `donation_row_hash_original` CHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS `original_tx_hash` VARCHAR(66) NULL;

CREATE INDEX IF NOT EXISTS `idx_donations_donation_row_hash_original`
  ON `donations` (`donation_row_hash_original`);

CREATE INDEX IF NOT EXISTS `idx_donations_original_tx_hash`
  ON `donations` (`original_tx_hash`);

ALTER TABLE `blockchain_transactions`
  ADD COLUMN IF NOT EXISTS `tx_row_hash_original` CHAR(64) NULL,
  ADD COLUMN IF NOT EXISTS `original_tx_hash` VARCHAR(66) NULL;

CREATE INDEX IF NOT EXISTS `idx_blockchain_tx_row_hash_original`
  ON `blockchain_transactions` (`tx_row_hash_original`);

CREATE INDEX IF NOT EXISTS `idx_blockchain_tx_original_tx_hash`
  ON `blockchain_transactions` (`original_tx_hash`);

DROP TRIGGER IF EXISTS `trg_donation_baseline_hash_bi`;
DROP TRIGGER IF EXISTS `trg_donation_baseline_hash_bu`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_baseline_hash_bi`;
DROP TRIGGER IF EXISTS `trg_blockchain_tx_baseline_hash_bu`;

DELIMITER $$

CREATE TRIGGER `trg_donation_baseline_hash_bi`
BEFORE INSERT ON `donations`
FOR EACH ROW
BEGIN
  SET NEW.`donation_row_hash_original` = NEW.`donation_row_hash`;
  SET NEW.`original_tx_hash` = NEW.`blockchain_tx_hash`;
END$$

CREATE TRIGGER `trg_donation_baseline_hash_bu`
BEFORE UPDATE ON `donations`
FOR EACH ROW
BEGIN
  SET NEW.`donation_row_hash_original` = COALESCE(
    OLD.`donation_row_hash_original`,
    NEW.`donation_row_hash`,
    OLD.`donation_row_hash`
  );

  SET NEW.`original_tx_hash` = COALESCE(
    OLD.`original_tx_hash`,
    OLD.`blockchain_tx_hash`,
    NEW.`blockchain_tx_hash`
  );
END$$

CREATE TRIGGER `trg_blockchain_tx_baseline_hash_bi`
BEFORE INSERT ON `blockchain_transactions`
FOR EACH ROW
BEGIN
  SET NEW.`tx_row_hash_original` = NEW.`tx_row_hash`;
  SET NEW.`original_tx_hash` = NEW.`blockchain_tx_hash`;
END$$

CREATE TRIGGER `trg_blockchain_tx_baseline_hash_bu`
BEFORE UPDATE ON `blockchain_transactions`
FOR EACH ROW
BEGIN
  SET NEW.`tx_row_hash_original` = COALESCE(
    OLD.`tx_row_hash_original`,
    NEW.`tx_row_hash`,
    OLD.`tx_row_hash`
  );

  SET NEW.`original_tx_hash` = COALESCE(
    OLD.`original_tx_hash`,
    OLD.`blockchain_tx_hash`,
    NEW.`blockchain_tx_hash`
  );
END$$

DELIMITER ;

UPDATE `donations`
SET
  `donation_row_hash_original` = COALESCE(`donation_row_hash_original`, `donation_row_hash`),
  `original_tx_hash` = COALESCE(`original_tx_hash`, `blockchain_tx_hash`)
WHERE `donation_row_hash_original` IS NULL
   OR `original_tx_hash` IS NULL;

UPDATE `blockchain_transactions`
SET
  `tx_row_hash_original` = COALESCE(`tx_row_hash_original`, `tx_row_hash`),
  `original_tx_hash` = COALESCE(`original_tx_hash`, `blockchain_tx_hash`)
WHERE `tx_row_hash_original` IS NULL
   OR `original_tx_hash` IS NULL;
