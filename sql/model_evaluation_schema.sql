USE CL_Data_Collection;

CREATE TABLE IF NOT EXISTS evaluation_sessions (
    id BIGINT NOT NULL AUTO_INCREMENT,
    participant_id VARCHAR(50) NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    video_id VARCHAR(50) NOT NULL,
    consented_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_evaluation_participant (participant_id),
    UNIQUE KEY uq_evaluation_session (session_id),
    INDEX idx_evaluation_session_video_created (video_id, created_at)
);

CREATE TABLE IF NOT EXISTS evaluation_records (
    id BIGINT NOT NULL AUTO_INCREMENT,
    evaluation_id CHAR(36) NOT NULL,
    participant_id VARCHAR(50) NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    video_id VARCHAR(50) NOT NULL,
    segment_index INT NOT NULL,
    segment_start_time DATETIME NOT NULL,
    segment_end_time DATETIME NOT NULL,
    pause_frequency INT NOT NULL,
    navigation_count_video INT NOT NULL,
    rewatch_segments INT NOT NULL,
    playback_rate_change INT NOT NULL,
    idle_duration_video INT NOT NULL,
    time_on_content INT NOT NULL,
    model_prediction_value VARCHAR(50) NOT NULL,
    model_prediction_label VARCHAR(50) NOT NULL,
    model_confidence DECIMAL(9, 6) NOT NULL,
    participant_rating TINYINT DEFAULT NULL,
    participant_rating_label VARCHAR(50) DEFAULT NULL,
    agreement BOOLEAN DEFAULT NULL,
    prediction_at DATETIME NOT NULL,
    submitted_at DATETIME DEFAULT NULL,
    model_version VARCHAR(100) NOT NULL,
    model_file_hash CHAR(64) NOT NULL,
    mapping_version VARCHAR(100) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_evaluation_id (evaluation_id),
    UNIQUE KEY uq_evaluation_segment (session_id, video_id, segment_index),
    INDEX idx_evaluation_participant_session (participant_id, session_id),
    INDEX idx_evaluation_video_segment (video_id, segment_index),
    INDEX idx_evaluation_created (created_at),
    CONSTRAINT fk_evaluation_record_session
        FOREIGN KEY (session_id) REFERENCES evaluation_sessions(session_id)
        ON DELETE CASCADE,
    CONSTRAINT chk_evaluation_rating CHECK (
        participant_rating IS NULL OR participant_rating BETWEEN 1 AND 5
    )
);
