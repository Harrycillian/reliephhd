CREATE TABLE IF NOT EXISTS `fund_status_workflow` (
  `fund_id` int(11) NOT NULL,
  `current_status` varchar(40) NOT NULL DEFAULT 'Pending',
  `created_at` datetime NOT NULL DEFAULT current_timestamp(),
  `updated_at` datetime NOT NULL DEFAULT current_timestamp() ON UPDATE current_timestamp(),
  `updated_by` int(11) DEFAULT NULL,
  PRIMARY KEY (`fund_id`),
  KEY `idx_fund_workflow_status` (`current_status`),
  KEY `idx_fund_workflow_updated_at` (`updated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
