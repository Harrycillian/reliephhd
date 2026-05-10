-- Payload History Tracking System for ReliePH
-- Tracks all changes to donation payload hashes for tamper detection

-- Create payload_history table to track all payload hash changes
CREATE TABLE IF NOT EXISTS `payload_history` (
  `id` INT(11) NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `donation_id` INT(11) NOT NULL,
  `don_refnum` VARCHAR(50) NOT NULL,
  `payload_hash` VARCHAR(64) NOT NULL,
  `payload_data` JSON NOT NULL,
  `previous_hash` VARCHAR(64) DEFAULT NULL,
  `change_reason` VARCHAR(255) DEFAULT NULL,
  `changed_by` INT(11) DEFAULT NULL,
  `change_type` ENUM('created', 'updated', 'verified', 'manual') DEFAULT 'updated',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `ip_address` VARCHAR(45) DEFAULT NULL,
  FOREIGN KEY (`donation_id`) REFERENCES `donations`(`don_id`) ON DELETE CASCADE,
  FOREIGN KEY (`changed_by`) REFERENCES `users`(`id`) ON DELETE SET NULL,
  INDEX idx_donation_id (`donation_id`),
  INDEX idx_don_refnum (`don_refnum`),
  INDEX idx_payload_hash (`payload_hash`),
  INDEX idx_created_at (`created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Function to automatically track payload hash creation
DELIMITER //
CREATE TRIGGER track_payload_on_insert
AFTER INSERT ON donations
FOR EACH ROW
BEGIN
    IF NEW.don_notes IS NOT NULL THEN
        INSERT INTO payload_history (
            donation_id, don_refnum, payload_hash, payload_data,
            previous_hash, change_type, changed_by
        )
        SELECT 
            NEW.don_id,
            NEW.don_refnum,
            JSON_UNQUOTE(JSON_EXTRACT(NEW.don_notes, '$.plaintext_sha256')),
            NEW.don_notes,
            NULL,
            'created',
            CASE 
                WHEN NEW.don_donorid > 0 AND EXISTS(SELECT 1 FROM users WHERE id = NEW.don_donorid) 
                THEN NEW.don_donorid 
                ELSE NULL 
            END
        WHERE JSON_EXTRACT(NEW.don_notes, '$.plaintext_sha256') IS NOT NULL;
    END IF;
END//
DELIMITER ;

-- Function to track payload hash changes on updates
DELIMITER //
CREATE TRIGGER track_payload_on_update
AFTER UPDATE ON donations
FOR EACH ROW
BEGIN
    -- Only track if payload hash has changed
    IF OLD.don_notes != NEW.don_notes THEN
        INSERT INTO payload_history (
            donation_id, don_refnum, payload_hash, payload_data,
            previous_hash, change_type, changed_by
        )
        SELECT 
            NEW.don_id,
            NEW.don_refnum,
            JSON_UNQUOTE(JSON_EXTRACT(NEW.don_notes, '$.plaintext_sha256')),
            NEW.don_notes,
            JSON_UNQUOTE(JSON_EXTRACT(OLD.don_notes, '$.plaintext_sha256')),
            'updated',
            CASE 
                WHEN NEW.don_donorid > 0 AND EXISTS(SELECT 1 FROM users WHERE id = NEW.don_donorid) 
                THEN NEW.don_donorid 
                ELSE NULL 
            END
        WHERE JSON_EXTRACT(NEW.don_notes, '$.plaintext_sha256') IS NOT NULL;
    END IF;
END//
DELIMITER ;
