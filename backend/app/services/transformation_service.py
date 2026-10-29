"""
Transformation and validation service.
"""
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List
from ..db.database import get_db
from ..services.file_service import get_file_by_path, get_project_files
from ..services.project_service import get_project
from . import ai_service


def create_transformation(
    project_id: str,
    file_path: str,
    task_id: Optional[str],
    instruction: Optional[str],
    target_tech: Optional[str]
) -> Dict[str, Any]:
    """Generate a transformation proposal for a file."""
    project = get_project(project_id)
    if not project:
        raise ValueError("Project not found")

    file_data = get_file_by_path(project_id, file_path)
    if not file_data:
        raise ValueError(f"File not found: {file_path}")

    original_code = file_data.get("content", "")
    language = file_data.get("language", "unknown")
    effective_target = target_tech or project.get("target_tech") or "modern best practices"

    # Build project context summary
    ctx = f"""Project: {project['name']}
Legacy Tech: {project.get('legacy_tech', 'Unknown')}
Target Tech: {effective_target}
Objective: {project.get('objective', 'Modernize the application')}"""

    result = ai_service.transform_file(
        file_path=file_path,
        original_code=original_code,
        language=language,
        target_tech=effective_target,
        instruction=instruction,
        project_context=ctx
    )

    now = datetime.utcnow()
    transformation_id = str(uuid.uuid4())
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO transformations
            (id, project_id, file_id, task_id, file_path, original_code, transformed_code,
             explanation, risks, review_items, status, validation_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'proposed', 'pending', ?, ?)
        """, [
            transformation_id, project_id,
            file_data.get("id"), task_id, file_path,
            original_code,
            result.get("transformed_code", ""),
            result.get("explanation", ""),
            result.get("risks", "") + "\n\nAssumptions: " + result.get("assumptions", ""),
            result.get("review_items", "") + "\n\nValidation Notes: " + result.get("validation_notes", ""),
            now, now
        ])
        conn.commit()
        return get_transformation(transformation_id)
    finally:
        conn.close()


def get_transformation(transformation_id: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    try:
        result = conn.execute(
            "SELECT * FROM transformations WHERE id = ?", [transformation_id]
        ).fetchone()
        if not result:
            return None
        cols = [d[0] for d in conn.description]
        return dict(zip(cols, result))
    finally:
        conn.close()


def get_project_transformations(project_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    try:
        results = conn.execute(
            "SELECT * FROM transformations WHERE project_id = ? ORDER BY created_at DESC",
            [project_id]
        ).fetchall()
        cols = [d[0] for d in conn.description]
        return [dict(zip(cols, r)) for r in results]
    finally:
        conn.close()


def update_transformation_status(transformation_id: str, status: str) -> Optional[Dict[str, Any]]:
    conn = get_db()
    try:
        conn.execute(
            "UPDATE transformations SET status = ?, updated_at = ? WHERE id = ?",
            [status, datetime.utcnow(), transformation_id]
        )
        conn.commit()
        return get_transformation(transformation_id)
    finally:
        conn.close()


def run_validation(project_id: str, transformation_id: str) -> Dict[str, Any]:
    """
    Run AI-assisted validation on a transformation.

    Uses ai_service.validate_transformation() which calls the Nebius Token Factory
    inference endpoint with both the original and transformed code.  Since arbitrary
    code execution is not available in this environment, all validation is AI-based
    review and is clearly labelled as such.
    """
    conn = get_db()
    try:
        trans = get_transformation(transformation_id)
        if not trans:
            raise ValueError("Transformation not found")

        ai_unavailable = False
        try:
            review_data = ai_service.validate_transformation(
                file_path=trans["file_path"],
                original_code=(trans.get("original_code") or ""),
                transformed_code=(trans.get("transformed_code") or ""),
            )
        except Exception as e:
            ai_unavailable = True
            review_data = {
                "errors": [],
                "warnings": ["Automated AI validation could not complete — manual review required"],
                "manual_review_items": ["Full manual code review required before applying this transformation"],
                "static_analysis": [],
                "overall_assessment": "ai_unavailable",
                "notes": f"AI validation service error: {str(e)}"
            }

        val_id = str(uuid.uuid4())
        now = datetime.utcnow()
        if ai_unavailable:
            # AI was unavailable — do NOT claim issues were detected or that review
            # completed; use a distinct status so the frontend can label it correctly.
            overall = "ai_unavailable"
        elif review_data.get("errors"):
            overall = "issues_detected"
        else:
            overall = "ready_for_review"

        conn.execute("""
            INSERT INTO validation_results
            (id, project_id, transformation_id, build_status, test_status,
             static_analysis, errors, warnings, manual_review_items, overall_status, notes, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            val_id, project_id, transformation_id,
            "not_applicable",  # we don't execute code
            "not_applicable",
            json.dumps(review_data.get("static_analysis", [])),
            json.dumps(review_data.get("errors", [])),
            json.dumps(review_data.get("warnings", [])),
            json.dumps(review_data.get("manual_review_items", [])),
            overall,
            review_data.get("notes", ""),
            now
        ])

        conn.execute("""
            UPDATE transformations SET validation_status = ?, validation_output = ?, updated_at = ?
            WHERE id = ?
        """, [overall, json.dumps(review_data), now, transformation_id])
        conn.commit()

        result = conn.execute(
            "SELECT * FROM validation_results WHERE id = ?", [val_id]
        ).fetchone()
        cols = [d[0] for d in conn.description]
        row = dict(zip(cols, result))
        for f in ["static_analysis", "errors", "warnings", "manual_review_items"]:
            if isinstance(row.get(f), str):
                try:
                    row[f] = json.loads(row[f])
                except Exception:
                    row[f] = []
        return row
    finally:
        conn.close()


def get_project_validations(project_id: str) -> List[Dict[str, Any]]:
    conn = get_db()
    try:
        results = conn.execute(
            "SELECT * FROM validation_results WHERE project_id = ? ORDER BY created_at DESC",
            [project_id]
        ).fetchall()
        cols = [d[0] for d in conn.description]
        rows = []
        for r in results:
            row = dict(zip(cols, r))
            for f in ["static_analysis", "errors", "warnings", "manual_review_items"]:
                if isinstance(row.get(f), str):
                    try:
                        row[f] = json.loads(row[f])
                    except Exception:
                        row[f] = []
            rows.append(row)
        return rows
    finally:
        conn.close()
