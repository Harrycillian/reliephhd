CREATE TABLE IF NOT EXISTS `fund_completion_proofs` (
  `proof_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `fund_id` int(11) NOT NULL,
  `audit_id` bigint(20) DEFAULT NULL,
  `uploaded_by` int(11) DEFAULT NULL,
  `proof_filename` varchar(255) NOT NULL,
  `original_filename` varchar(255) DEFAULT NULL,
  `proof_mime_type` varchar(120) DEFAULT NULL,
  `proof_note` varchar(500) DEFAULT NULL,
  `uploaded_at` datetime NOT NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`proof_id`),
  KEY `idx_completion_proof_fund` (`fund_id`),
  KEY `idx_completion_proof_uploaded_at` (`uploaded_at`),
  KEY `idx_completion_proof_audit` (`audit_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
