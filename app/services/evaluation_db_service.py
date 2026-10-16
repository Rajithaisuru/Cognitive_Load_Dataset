from datetime import timezone

from app.core.database import get_db_connection


_schema_ready = False


EVALUATION_TABLES_SQL = """
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
"""


def ensure_evaluation_tables(connection=None) -> bool:
    global _schema_ready
    if _schema_ready:
        return True

    owns_connection = connection is None
    connection = connection or get_db_connection()
    if connection is None:
        return False

    cursor = None
    try:
        cursor = connection.cursor()
        for statement in EVALUATION_TABLES_SQL.split(";"):
            if statement.strip():
                cursor.execute(statement)
        connection.commit()
        _schema_ready = True
        return True
    except Exception as exc:
        print(f"MySQL evaluation schema setup failed: {exc}")
        connection.rollback()
        return False
    finally:
        if cursor is not None:
            cursor.close()
        if owns_connection:
            connection.close()


def evaluation_participant_exists(participant_id: str) -> bool:
    connection = get_db_connection()
    if connection is None or not ensure_evaluation_tables(connection):
        if connection is not None:
            connection.close()
        return False

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT id FROM evaluation_sessions WHERE participant_id = %s LIMIT 1",
            (participant_id,),
        )
        return cursor.fetchone() is not None
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def save_evaluation_session(session_data: dict):
    connection = get_db_connection()
    if connection is None or not ensure_evaluation_tables(connection):
        if connection is not None:
            connection.close()
        return None

    cursor = None
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            INSERT INTO evaluation_sessions (
                participant_id, session_id, video_id, consented_at
            ) VALUES (%s, %s, %s, %s)
            """,
            (
                session_data["participant_id"],
                session_data["session_id"],
                session_data["video_id"],
                _to_mysql_datetime(session_data["consented_at"]),
            ),
        )
        connection.commit()
        return cursor.lastrowid
    except Exception as exc:
        print(f"MySQL evaluation session insert failed: {exc}")
        connection.rollback()
        return None
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def save_evaluation_prediction(record: dict):
    connection = get_db_connection()
    if connection is None or not ensure_evaluation_tables(connection):
        if connection is not None:
            connection.close()
        return None

    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT id FROM evaluation_sessions
            WHERE participant_id = %s AND session_id = %s AND video_id = %s
            LIMIT 1
            """,
            (record["participant_id"], record["session_id"], record["video_id"]),
        )
        if cursor.fetchone() is None:
            return {"invalid_session": True}

        cursor.execute(
            """
            SELECT evaluation_id, participant_rating
            FROM evaluation_records
            WHERE session_id = %s AND video_id = %s AND segment_index = %s
            LIMIT 1
            """,
            (record["session_id"], record["video_id"], record["segment_index"]),
        )
        existing = cursor.fetchone()
        if existing:
            return {
                "evaluation_id": existing["evaluation_id"],
                "already_exists": True,
                "already_submitted": existing["participant_rating"] is not None,
                "invalid_session": False,
            }

        cursor.execute(
            """
            INSERT INTO evaluation_records (
                evaluation_id, participant_id, session_id, video_id, segment_index,
                segment_start_time, segment_end_time, pause_frequency,
                navigation_count_video, rewatch_segments, playback_rate_change,
                idle_duration_video, time_on_content, model_prediction_value,
                model_prediction_label, model_confidence, prediction_at,
                model_version, model_file_hash, mapping_version
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            """,
            (
                record["evaluation_id"], record["participant_id"], record["session_id"],
                record["video_id"], record["segment_index"],
                _to_mysql_datetime(record["segment_start_time"]),
                _to_mysql_datetime(record["segment_end_time"]),
                record["pause_frequency"], record["navigation_count_video"],
                record["rewatch_segments"], record["playback_rate_change"],
                record["idle_duration_video"], record["time_on_content"],
                record["model_prediction_value"], record["model_prediction_label"],
                record["model_confidence"], _to_mysql_datetime(record["prediction_at"]),
                record["model_version"], record["model_file_hash"],
                record["mapping_version"],
            ),
        )
        connection.commit()
        return {
            "evaluation_id": record["evaluation_id"],
            "already_exists": False,
            "already_submitted": False,
            "invalid_session": False,
        }
    except Exception as exc:
        print(f"MySQL evaluation prediction insert failed: {exc}")
        connection.rollback()
        return None
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def submit_evaluation_rating(rating_data: dict):
    connection = get_db_connection()
    if connection is None or not ensure_evaluation_tables(connection):
        if connection is not None:
            connection.close()
        return None

    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        connection.start_transaction()
        cursor.execute(
            """
            SELECT * FROM evaluation_records
            WHERE evaluation_id = %s AND participant_id = %s AND session_id = %s
            FOR UPDATE
            """,
            (
                rating_data["evaluation_id"],
                rating_data["participant_id"],
                rating_data["session_id"],
            ),
        )
        record = cursor.fetchone()
        if record is None:
            connection.rollback()
            return {"status": "not_found"}

        if record["participant_rating"] is not None:
            connection.commit()
            return {"status": "already_submitted", "record": record}

        agreement = rating_data["comparison_model_label"] == record["model_prediction_label"]

        cursor.execute(
            """
            UPDATE evaluation_records
            SET participant_rating = %s,
                participant_rating_label = %s,
                agreement = %s,
                submitted_at = %s
            WHERE evaluation_id = %s AND participant_rating IS NULL
            """,
            (
                rating_data["participant_rating"],
                rating_data["participant_rating_label"],
                agreement,
                _to_mysql_datetime(rating_data["submitted_at"]),
                rating_data["evaluation_id"],
            ),
        )
        cursor.execute(
            "SELECT * FROM evaluation_records WHERE evaluation_id = %s",
            (rating_data["evaluation_id"],),
        )
        updated = cursor.fetchone()
        connection.commit()
        return {"status": "submitted", "record": updated}
    except Exception as exc:
        print(f"MySQL evaluation rating update failed: {exc}")
        connection.rollback()
        return None
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def get_evaluation_records():
    connection = get_db_connection()
    if connection is None or not ensure_evaluation_tables(connection):
        if connection is not None:
            connection.close()
        return []

    cursor = None
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT
                participant_id, session_id, video_id, segment_index,
                segment_start_time, segment_end_time, pause_frequency,
                navigation_count_video, rewatch_segments, playback_rate_change,
                idle_duration_video, time_on_content, model_prediction_value,
                model_prediction_label, model_confidence, participant_rating,
                participant_rating_label, agreement, prediction_at, submitted_at,
                model_version, model_file_hash, mapping_version
            FROM evaluation_records
            ORDER BY created_at, id
            """
        )
        return cursor.fetchall()
    except Exception as exc:
        print(f"MySQL evaluation export failed: {exc}")
        return []
    finally:
        if cursor is not None:
            cursor.close()
        connection.close()


def _to_mysql_datetime(value):
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
