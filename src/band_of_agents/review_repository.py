from __future__ import annotations

from typing import Any

from psycopg.types.json import Jsonb

from band_of_agents.db import connect


class ReviewRepository:
    def get_review_by_session_uid(self, session_uid: str) -> dict[str, Any] | None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        id::text,
                        session_uid::text,
                        band_chat_id,
                        evidence,
                        summarizer_output,
                        status
                    FROM review
                    WHERE session_uid = %s
                    """,
                    (session_uid,),
                )
                return cursor.fetchone()

    def mark_review_agents_running(self, review_id: str, band_chat_id: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE review
                    SET band_chat_id = %s,
                        status = 'agents_running',
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (band_chat_id, review_id),
                )

    def ensure_review_status_rows(self, review_id: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO review_status (review_id, agent_id, status)
                    SELECT
                        %s,
                        id,
                        'pending'
                    FROM agent
                    WHERE is_active = TRUE
                      AND participates_in_review_status = TRUE
                    ON CONFLICT (review_id, agent_id) DO NOTHING
                    """,
                    (review_id,),
                )

    def mark_agent_processing(self, review_id: str, agent_key: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE review_status
                    SET status = 'processing',
                        started_at = COALESCE(started_at, now()),
                        updated_at = now()
                    WHERE review_id = %s
                      AND agent_id = (
                          SELECT id FROM agent WHERE agent_key = %s
                      )
                    """,
                    (review_id, agent_key),
                )

    def mark_agent_completed(
        self,
        review_id: str,
        agent_key: str,
        analysis: dict[str, Any],
    ) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE review_status
                    SET status = 'completed',
                        analysis = %s,
                        error_message = NULL,
                        completed_at = now(),
                        updated_at = now()
                    WHERE review_id = %s
                      AND agent_id = (
                          SELECT id FROM agent WHERE agent_key = %s
                      )
                    """,
                    (Jsonb(analysis), review_id, agent_key),
                )

    def mark_agent_failed(
        self,
        review_id: str,
        agent_key: str,
        error_message: str,
    ) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE review_status
                    SET status = 'failed',
                        error_message = %s,
                        completed_at = now(),
                        updated_at = now()
                    WHERE review_id = %s
                      AND agent_id = (
                          SELECT id FROM agent WHERE agent_key = %s
                      )
                    """,
                    (error_message, review_id, agent_key),
                )

    def save_review_summarizer_output(
        self,
        review_id: str,
        summarizer_output: dict[str, Any],
    ) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE review
                    SET summarizer_output = %s,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (Jsonb(summarizer_output), review_id),
                )

    def mark_review_summarized(self, review_id: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE review
                    SET status = 'summarized',
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (review_id,),
                )

    def mark_review_failed(self, review_id: str) -> None:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE review
                    SET status = 'failed',
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (review_id,),
                )
