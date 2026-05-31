CREATE TABLE IF NOT EXISTS v05_commerce_source_generation_run (
  run_id VARCHAR(80) PRIMARY KEY,
  profile_id VARCHAR(80) NOT NULL,
  event_date DATE NOT NULL,
  scenario_name VARCHAR(120) NOT NULL,
  journey_count INT NOT NULL DEFAULT 0,
  behavior_count INT NOT NULL DEFAULT 0,
  transaction_count INT NOT NULL DEFAULT 0,
  state_count INT NOT NULL DEFAULT 0,
  manifest_path VARCHAR(1024) NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_v05_src_run_profile_dt (profile_id, event_date, scenario_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS v05_commerce_source_file_manifest (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id VARCHAR(80) NOT NULL,
  profile_id VARCHAR(80) NOT NULL,
  event_date DATE NOT NULL,
  scenario_name VARCHAR(120) NOT NULL,
  file_role VARCHAR(80) NOT NULL,
  file_path VARCHAR(1024) NOT NULL,
  record_count INT NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_v05_src_file_run (run_id),
  KEY idx_v05_src_file_profile_dt (profile_id, event_date, scenario_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
