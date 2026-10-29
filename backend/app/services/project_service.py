"""
Project management service.
"""
import logging
import os
import json
import uuid
import shutil
from datetime import datetime
from typing import Optional, List, Dict, Any
from ..db.database import get_db
from ..core.config import settings

logger = logging.getLogger(__name__)


def create_project(data: Dict[str, Any]) -> Dict[str, Any]:
    project_id = str(uuid.uuid4())
    now = datetime.utcnow()
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO projects (id, name, description, legacy_tech, target_tech, objective, status, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, 'created', ?, ?, ?)
        """, [
            project_id,
            data["name"],
            data.get("description"),
            data.get("legacy_tech"),
            data.get("target_tech"),
            data.get("objective"),
            now,
            now,
            json.dumps(data.get("metadata") or {})
        ])
        conn.commit()
        return get_project(project_id)
    finally:
        conn.close()


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    try:
        result = conn.execute(
            "SELECT * FROM projects WHERE id = ?", [project_id]
        ).fetchone()
        if not result:
            return None
        cols = [d[0] for d in conn.description]
        row = dict(zip(cols, result))
        if isinstance(row.get("metadata"), str):
            try:
                row["metadata"] = json.loads(row["metadata"])
            except Exception:
                row["metadata"] = {}
        return row
    finally:
        conn.close()


def list_projects() -> List[Dict[str, Any]]:
    conn = get_db()
    try:
        results = conn.execute(
            "SELECT * FROM projects ORDER BY updated_at DESC"
        ).fetchall()
        cols = [d[0] for d in conn.description]
        rows = []
        for r in results:
            row = dict(zip(cols, r))
            if isinstance(row.get("metadata"), str):
                try:
                    row["metadata"] = json.loads(row["metadata"])
                except Exception:
                    row["metadata"] = {}
            rows.append(row)
        return rows
    finally:
        conn.close()


# Safe whitelist of mutable columns — no external input ever reaches the SQL template.
_MUTABLE_PROJECT_COLS = ["name", "description", "legacy_tech", "target_tech", "objective", "status"]


def update_project(project_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Update a project record using only fully-parameterized UPDATE statements.
    Each allowed column is updated in a dedicated statement so no user-supplied
    key is ever interpolated into the SQL string.
    """
    now = datetime.utcnow()
    conn = get_db()
    try:
        for key in _MUTABLE_PROJECT_COLS:
            if key in data and data[key] is not None:
                conn.execute(
                    f"UPDATE projects SET {key} = ?, updated_at = ? WHERE id = ?",
                    [data[key], now, project_id],
                )
        if "metadata" in data:
            conn.execute(
                "UPDATE projects SET metadata = ?, updated_at = ? WHERE id = ?",
                [json.dumps(data["metadata"] or {}), now, project_id],
            )
        conn.commit()
        return get_project(project_id)
    finally:
        conn.close()


_CASCADE_DELETE_TABLES = [
    "validation_results",
    "transformations",
    "plan_tasks",
    "modernization_plans",
    "architecture_models",
    "recommendations",
    "issues",
    "analyses",
    "project_files",
    "chat_messages",
    "projects",
]


def delete_project(project_id: str) -> bool:
    """
    Delete a project and all related rows atomically.
    All DELETEs run inside a single transaction so a mid-way failure
    cannot leave orphaned rows.
    """
    conn = get_db()
    try:
        for table in _CASCADE_DELETE_TABLES:
            if table == "projects":
                conn.execute("DELETE FROM projects WHERE id = ?", [project_id])
            else:
                conn.execute(f"DELETE FROM {table} WHERE project_id = ?", [project_id])
        conn.commit()
        # Remove upload directory only after the DB transaction commits
        upload_dir = os.path.join(settings.uploads_dir, project_id)
        if os.path.exists(upload_dir):
            shutil.rmtree(upload_dir)
        return True
    except Exception:
        logger.exception("Failed to delete project %s — rolling back", project_id)
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.close()


def get_dashboard_stats(project_id: str) -> Dict[str, Any]:
    conn = get_db()
    try:
        total_files = conn.execute(
            "SELECT COUNT(*) FROM project_files WHERE project_id = ?", [project_id]
        ).fetchone()[0]

        total_issues = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE project_id = ?", [project_id]
        ).fetchone()[0]

        high_issues = conn.execute(
            "SELECT COUNT(*) FROM issues WHERE project_id = ? AND severity IN ('critical', 'high')",
            [project_id]
        ).fetchone()[0]

        total_recs = conn.execute(
            "SELECT COUNT(*) FROM recommendations WHERE project_id = ?", [project_id]
        ).fetchone()[0]

        total_tasks = conn.execute(
            "SELECT COUNT(*) FROM plan_tasks WHERE project_id = ?", [project_id]
        ).fetchone()[0]

        completed_tasks = conn.execute(
            "SELECT COUNT(*) FROM plan_tasks WHERE project_id = ? AND status = 'completed'",
            [project_id]
        ).fetchone()[0]

        total_transforms = conn.execute(
            "SELECT COUNT(*) FROM transformations WHERE project_id = ?", [project_id]
        ).fetchone()[0]

        # Get latest analysis status
        analysis_row = conn.execute(
            "SELECT status FROM analyses WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
            [project_id]
        ).fetchone()
        analysis_status = analysis_row[0] if analysis_row else "not_started"

        # Count files that were actually included in an analysis
        analyzed_files = conn.execute(
            """
            SELECT COUNT(DISTINCT pf.id)
            FROM project_files pf
            JOIN analyses a ON a.project_id = pf.project_id
            WHERE pf.project_id = ? AND a.status = 'completed'
            """,
            [project_id]
        ).fetchone()[0]

        # Derive an honest validation_status from the latest completed validation
        val_row = conn.execute(
            """
            SELECT overall_status FROM validation_results
            WHERE project_id = ?
            ORDER BY created_at DESC LIMIT 1
            """,
            [project_id]
        ).fetchone()
        validation_status = val_row[0] if val_row else "not_validated"

        return {
            "total_files": total_files,
            "analyzed_files": analyzed_files,
            "total_issues": total_issues,
            "high_priority_issues": high_issues,
            "total_recommendations": total_recs,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "transformations_performed": total_transforms,
            "validation_status": validation_status,
            "remaining_risks": high_issues,
            "analysis_status": analysis_status,
        }
    finally:
        conn.close()
