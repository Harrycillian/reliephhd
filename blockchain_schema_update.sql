-- Blockchain Integration Schema Updates for ReliePH
-- This file contains the database schema updates needed for blockchain integration

-- Add blockchain-related columns to donations table
ALTER TABLE `donations` 
ADD COLUMN `blockchain_tx_hash` VARCHAR(66) DEFAULT NULL COMMENT 'Blockchain transaction hash',
ADD COLUMN `block_number` BIGINT DEFAULT NULL COMMENT 'Block number where transaction was recorded',
ADD COLUMN `gas_used` BIGINT DEFAULT NULL COMMENT 'Gas used for the transaction',
ADD COLUMN `verification_status` ENUM('pending', 'verified', 'failed') DEFAULT 'pending' COMMENT 'Blockchain verification status',
ADD COLUMN `verification_date` DATETIME DEFAULT NULL COMMENT 'When the transaction was verified on blockchain',
ADD COLUMN `donor_wallet_address` VARCHAR(42) DEFAULT NULL COMMENT 'Donor wallet address for blockchain transactions',
ADD INDEX `idx_blockchain_tx_hash` (`blockchain_tx_hash`),
ADD INDEX `idx_verification_status` (`verification_status`),
ADD INDEX `idx_donor_wallet` (`donor_wallet_address`);

-- Add blockchain-related columns to fundraisers table
ALTER TABLE `fundraisers`
ADD COLUMN `blockchain_fund_id` INT DEFAULT NULL COMMENT 'Blockchain fundraiser ID',
ADD COLUMN `blockchain_tx_hash` VARCHAR(66) DEFAULT NULL COMMENT 'Blockchain transaction hash for fundraiser creation',
ADD COLUMN `blockchain_verified` BOOLEAN DEFAULT FALSE COMMENT 'Whether fundraiser is verified on blockchain',
ADD COLUMN `creator_wallet_address` VARCHAR(42) DEFAULT NULL COMMENT 'Creator wallet address',
ADD INDEX `idx_blockchain_fund_id` (`blockchain_fund_id`),
ADD INDEX `idx_blockchain_verified` (`blockchain_verified`);

-- Create blockchain_transactions table for tracking all blockchain operations
CREATE TABLE `blockchain_transactions` (
  `id` INT(11) NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `transaction_type` ENUM('donation', 'fundraiser_creation', 'fundraiser_update') NOT NULL,
  `related_id` INT(11) NOT NULL COMMENT 'ID of the related record (donation_id or fund_id)',
  `blockchain_tx_hash` VARCHAR(66) NOT NULL UNIQUE,
  `block_number` BIGINT DEFAULT NULL,
  `gas_used` BIGINT DEFAULT NULL,
  `gas_price` BIGINT DEFAULT NULL,
  `status` ENUM('pending', 'confirmed', 'failed') DEFAULT 'pending',
  `confirmation_blocks` INT DEFAULT 0,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `confirmed_at` DATETIME DEFAULT NULL,
  `error_message` TEXT DEFAULT NULL,
  INDEX `idx_tx_type` (`transaction_type`),
  INDEX `idx_related_id` (`related_id`),
  INDEX `idx_status` (`status`),
  INDEX `idx_created_at` (`created_at`)
);

-- Create wallet_addresses table for managing user wallet addresses
CREATE TABLE `wallet_addresses` (
  `id` INT(11) NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `user_id` INT(11) NOT NULL,
  `wallet_address` VARCHAR(42) NOT NULL UNIQUE,
  `wallet_type` ENUM('ethereum', 'polygon', 'binance_smart_chain') DEFAULT 'ethereum',
  `is_verified` BOOLEAN DEFAULT FALSE,
  `verification_date` DATETIME DEFAULT NULL,
  `is_primary` BOOLEAN DEFAULT FALSE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (`user_id`) REFERENCES `users`(`id`) ON DELETE CASCADE,
  INDEX `idx_user_id` (`user_id`),
  INDEX `idx_wallet_address` (`wallet_address`),
  INDEX `idx_is_primary` (`is_primary`)
);

-- Create blockchain_verification_logs table for audit trail
CREATE TABLE `blockchain_verification_logs` (
  `id` INT(11) NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `transaction_hash` VARCHAR(66) NOT NULL,
  `verification_type` ENUM('donation', 'fundraiser', 'general') NOT NULL,
  `verification_status` ENUM('success', 'failed', 'pending') NOT NULL,
  `verification_method` ENUM('smart_contract', 'api', 'manual') NOT NULL,
  `verification_data` JSON DEFAULT NULL,
  `error_message` TEXT DEFAULT NULL,
  `verified_by` INT(11) DEFAULT NULL COMMENT 'User ID who performed verification',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (`verified_by`) REFERENCES `users`(`id`) ON DELETE SET NULL,
  INDEX `idx_transaction_hash` (`transaction_hash`),
  INDEX `idx_verification_type` (`verification_type`),
  INDEX `idx_verification_status` (`verification_status`),
  INDEX `idx_created_at` (`created_at`)
);

-- Create smart_contract_events table for tracking contract events
CREATE TABLE `smart_contract_events` (
  `id` INT(11) NOT NULL PRIMARY KEY AUTO_INCREMENT,
  `event_type` VARCHAR(100) NOT NULL,
  `transaction_hash` VARCHAR(66) NOT NULL,
  `block_number` BIGINT NOT NULL,
  `log_index` INT NOT NULL,
  `contract_address` VARCHAR(42) NOT NULL,
  `event_data` JSON NOT NULL,
  `processed` BOOLEAN DEFAULT FALSE,
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX `idx_event_type` (`event_type`),
  INDEX `idx_transaction_hash` (`transaction_hash`),
  INDEX `idx_block_number` (`block_number`),
  INDEX `idx_processed` (`processed`)
);

-- Add blockchain settings to platform_settings table
INSERT INTO `platform_settings` (`setting_key`, `setting_value`, `setting_type`, `description`) VALUES
('blockchain_enabled', 'true', 'boolean', 'Enable blockchain integration for transactions'),
('ethereum_rpc_url', 'https://sepolia.infura.io/v3/YOUR_INFURA_KEY', 'string', 'Ethereum RPC endpoint URL'),
('donation_contract_address', '', 'string', 'Address of the donation smart contract'),
('fundraiser_contract_address', '', 'string', 'Address of the fundraiser smart contract'),
('blockchain_network', 'sepolia', 'string', 'Blockchain network (mainnet, sepolia, polygon, etc.)'),
('min_confirmation_blocks', '3', 'number', 'Minimum number of confirmations required'),
('gas_price_multiplier', '1.1', 'number', 'Multiplier for gas price estimation'),
('auto_verify_transactions', 'true', 'boolean', 'Automatically verify transactions on blockchain'),
('blockchain_verification_interval', '300', 'number', 'Interval in seconds for checking transaction confirmations');

-- Create indexes for better performance
CREATE INDEX `idx_donations_blockchain` ON `donations`(`blockchain_tx_hash`, `verification_status`);
CREATE INDEX `idx_fundraisers_blockchain` ON `fundraisers`(`blockchain_fund_id`, `blockchain_verified`);
CREATE INDEX `idx_blockchain_tx_status` ON `blockchain_transactions`(`status`, `created_at`);

-- Add foreign key constraints
ALTER TABLE `blockchain_transactions`
ADD CONSTRAINT `fk_blockchain_tx_donation` 
FOREIGN KEY (`related_id`) REFERENCES `donations`(`don_id`) ON DELETE CASCADE;

-- Note: We'll need to handle the fundraiser foreign key separately since it references fundraisers table
-- This will be added after ensuring the fundraisers table structure is compatible

-- Create a view for blockchain transaction summary
CREATE VIEW `blockchain_transaction_summary` AS
SELECT 
    bt.transaction_type,
    bt.status,
    COUNT(*) as transaction_count,
    SUM(bt.gas_used) as total_gas_used,
    AVG(bt.gas_used) as avg_gas_used,
    MIN(bt.created_at) as earliest_transaction,
    MAX(bt.created_at) as latest_transaction
FROM blockchain_transactions bt
GROUP BY bt.transaction_type, bt.status;

-- Create a view for donation verification status
CREATE VIEW `donation_verification_status` AS
SELECT 
    d.don_id,
    d.don_refnum,
    d.don_amount,
    d.don_status,
    d.verification_status,
    d.blockchain_tx_hash,
    d.block_number,
    f.fund_title,
    u.name as donor_name,
    wa.wallet_address as donor_wallet
FROM donations d
LEFT JOIN fundraisers f ON d.fund_id = f.fund_id
LEFT JOIN users u ON d.don_donorid = u.id
LEFT JOIN wallet_addresses wa ON u.id = wa.user_id AND wa.is_primary = TRUE;

COMMIT;
