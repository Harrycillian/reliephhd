CREATE TABLE IF NOT EXISTS `donation_fund_status` (
  `reference_number` varchar(80) NOT NULL,
  `donation_id` int(11) DEFAULT NULL,
  `current_status` varchar(40) NOT NULL DEFAULT 'Donation Received',
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`reference_number`),
  KEY `idx_donation_fund_ref` (`reference_number`),
  KEY `idx_donation_fund_donation` (`donation_id`),
  KEY `idx_donation_fund_status` (`current_status`),
  KEY `idx_donation_fund_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `donation_fund_status_history` (
  `history_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `reference_number` varchar(80) NOT NULL,
  `donation_id` int(11) DEFAULT NULL,
  `status` varchar(40) NOT NULL,
  `previous_status` varchar(40) DEFAULT NULL,
  `updated_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  `audit_id` bigint(20) DEFAULT NULL,
  `note` varchar(255) DEFAULT NULL,
  PRIMARY KEY (`history_id`),
  KEY `idx_donation_fund_history_ref` (`reference_number`),
  KEY `idx_donation_fund_history_donation` (`donation_id`),
  KEY `idx_donation_fund_history_status` (`status`),
  KEY `idx_donation_fund_history_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS `donation_completion_proofs` (
  `proof_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `donation_id` int(11) NOT NULL,
  `fund_id` int(11) DEFAULT NULL,
  `audit_id` bigint(20) DEFAULT NULL,
  `uploaded_by` int(11) DEFAULT NULL,
  `proof_filename` varchar(255) NOT NULL,
  `original_filename` varchar(255) DEFAULT NULL,
  `proof_mime_type` varchar(120) DEFAULT NULL,
  `proof_note` varchar(500) DEFAULT NULL,
  `uploaded_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`proof_id`),
  KEY `idx_donation_proof_donation` (`donation_id`),
  KEY `idx_donation_proof_fund` (`fund_id`),
  KEY `idx_donation_proof_uploaded_at` (`uploaded_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
