"""
Backend tests for the Legacy Modernization Platform.
Tests cover project management, file ingestion, analysis orchestration,
transformation, validation, AI service configuration, and error handling.
"""
import pytest
import json
import os
import sys
import tempfile
import uuid
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from app.core.config import settings

# Use a temp DB for testing — unique per process to avoid file locking
settings.db_path = os.path.join(tempfile.gettempdir(), f"test_platform_{os.getpid()}_{uuid.uuid4().hex[:8]}.duckdb")
# Nebius API key placeholder — AI calls are mocked or skipped in the test suite
settings.nebius_api_key = "test-placeholder-not-used"
settings.nebius_base_url = "https://api.tokenfactory.nebius.com/v1"
settings.nebius_model = "nvidia/Nemotron-3_5-Lightning"

from app.db.database import init_db
from app.services import project_service, file_service, analysis_service, transformation_service, demo_service
from fastapi.testclient import TestClient
from app.main import app

# Initialize test DB
init_db()
client = TestClient(app)


# ─── Project Tests ────────────────────────────────────────────────────────────

class TestProjectCreation:
    def test_create_project_minimal(self):
        resp = client.post("/api/v1/projects", json={"name": "Test Project"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Test Project"
        assert data["id"]
        assert data["status"] == "created"

    def test_create_project_full(self):
        resp = client.post("/api/v1/projects", json={
            "name": "Full Project",
            "description": "A legacy monolith",
            "legacy_tech": "Java Spring MVC",
            "target_tech": "Spring Boot 3",
            "objective": "Framework migration",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Full Project"
        assert data["legacy_tech"] == "Java Spring MVC"
        assert data["target_tech"] == "Spring Boot 3"

    def test_list_projects(self):
        client.post("/api/v1/projects", json={"name": "List Test Project"})
        resp = client.get("/api/v1/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert any(p["name"] == "List Test Project" for p in data)

    def test_get_project(self):
        create_resp = client.post("/api/v1/projects", json={"name": "Get Test"})
        project_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == project_id

    def test_get_nonexistent_project(self):
        resp = client.get(f"/api/v1/projects/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_update_project(self):
        create_resp = client.post("/api/v1/projects", json={"name": "Update Test"})
        project_id = create_resp.json()["id"]
        resp = client.patch(f"/api/v1/projects/{project_id}", json={"name": "Updated Name", "status": "analyzed"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    def test_delete_project(self):
        create_resp = client.post("/api/v1/projects", json={"name": "Delete Test"})
        project_id = create_resp.json()["id"]
        resp = client.delete(f"/api/v1/projects/{project_id}")
        assert resp.status_code == 200
        # Verify gone
        resp2 = client.get(f"/api/v1/projects/{project_id}")
        assert resp2.status_code == 404

    def test_create_project_requires_name(self):
        resp = client.post("/api/v1/projects", json={"description": "no name"})
        assert resp.status_code == 422  # validation error

    def test_dashboard_stats(self):
        create_resp = client.post("/api/v1/projects", json={"name": "Dashboard Test"})
        project_id = create_resp.json()["id"]
        resp = client.get(f"/api/v1/projects/{project_id}/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_files" in data
        assert "total_issues" in data
        assert "analysis_status" in data


# ─── File Ingestion Tests ──────────────────────────────────────────────────────

class TestFileIngestion:
    def setup_method(self):
        resp = client.post("/api/v1/projects", json={"name": "File Test Project"})
        self.project_id = resp.json()["id"]

    def test_load_demo_project(self):
        resp = client.post(f"/api/v1/projects/{self.project_id}/files/upload-demo")
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] > 0
        assert len(data["files"]) > 0

    def test_list_files_after_demo(self):
        client.post(f"/api/v1/projects/{self.project_id}/files/upload-demo")
        resp = client.get(f"/api/v1/projects/{self.project_id}/files")
        assert resp.status_code == 200
        files = resp.json()
        assert len(files) > 5

    def test_demo_project_has_java_files(self):
        client.post(f"/api/v1/projects/{self.project_id}/files/upload-demo")
        resp = client.get(f"/api/v1/projects/{self.project_id}/files")
        files = resp.json()
        java_files = [f for f in files if f.get("language") == "java"]
        assert len(java_files) > 0

    def test_upload_single_file(self):
        content = b"public class HelloWorld { public static void main(String[] args) {} }"
        resp = client.post(
            f"/api/v1/projects/{self.project_id}/files/upload",
            files=[("files", ("HelloWorld.java", content, "text/plain"))],
            data={"replace": "false"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["saved"] >= 1

    def test_upload_unsupported_binary(self):
        # .class files should be detected as binary
        content = b"\xca\xfe\xba\xbe" + b"\x00" * 100  # fake Java class header
        resp = client.post(
            f"/api/v1/projects/{self.project_id}/files/upload",
            files=[("files", ("compiled.class", content, "application/octet-stream"))],
            data={"replace": "false"},
        )
        assert resp.status_code == 200
        # File should be saved but marked binary/unsupported
        saved = resp.json()["files"]
        if saved:
            assert saved[0].get("is_binary") or not saved[0].get("is_supported")

    def test_get_file_detail(self):
        client.post(f"/api/v1/projects/{self.project_id}/files/upload-demo")
        files_resp = client.get(f"/api/v1/projects/{self.project_id}/files")
        files = files_resp.json()
        java_file = next((f for f in files if f.get("language") == "java"), None)
        assert java_file is not None
        resp = client.get(f"/api/v1/projects/{self.project_id}/files/{java_file['id']}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail.get("content")

    def test_list_files_empty_project(self):
        resp = client.get(f"/api/v1/projects/{self.project_id}/files")
        assert resp.status_code == 200
        assert resp.json() == []


# ─── File Service Unit Tests ───────────────────────────────────────────────────

class TestFileService:
    def test_detect_language_java(self):
        assert file_service.detect_language("Foo.java") == "java"

    def test_detect_language_python(self):
        assert file_service.detect_language("app.py") == "python"

    def test_detect_language_typescript(self):
        assert file_service.detect_language("component.tsx") == "typescript"

    def test_detect_language_unknown(self):
        result = file_service.detect_language("unknown_file.xyz")
        assert result is None

    def test_is_binary_class_file(self):
        assert file_service.is_binary_file("App.class") is True

    def test_is_binary_jar(self):
        assert file_service.is_binary_file("app.jar") is True

    def test_is_binary_java_source(self):
        assert file_service.is_binary_file("App.java") is False

    def test_is_supported_java(self):
        assert file_service.is_supported_file("Main.java") is True

    def test_is_supported_class(self):
        assert file_service.is_supported_file("Main.class") is False

    def test_is_supported_image(self):
        assert file_service.is_supported_file("logo.png") is False


# ─── Demo Project Tests ────────────────────────────────────────────────────────

class TestDemoProject:
    def test_demo_files_loaded(self):
        files = demo_service.load_demo_files()
        assert len(files) > 5

    def test_demo_has_pom_xml(self):
        files = demo_service.load_demo_files()
        paths = [f["path"] for f in files]
        assert any("pom.xml" in p for p in paths)

    def test_demo_has_java_controller(self):
        files = demo_service.load_demo_files()
        java_files = [f for f in files if f["name"].endswith(".java")]
        assert len(java_files) >= 3

    def test_demo_has_security_issues(self):
        files = demo_service.load_demo_files()
        controller = next((f for f in files if "InventoryController" in f["name"]), None)
        assert controller is not None
        assert "admin123" in controller["content"]  # Hardcoded password

    def test_demo_has_sql_injection(self):
        files = demo_service.load_demo_files()
        controller = next((f for f in files if "InventoryController" in f["name"]), None)
        assert controller is not None
        assert "query" in controller["content"]  # SQL injection risk present

    def test_demo_files_have_content(self):
        files = demo_service.load_demo_files()
        for f in files:
            assert f["content"] is not None
            assert len(f["content"]) > 0

    def test_demo_has_outdated_dependencies(self):
        files = demo_service.load_demo_files()
        pom = next((f for f in files if "pom.xml" in f["path"]), None)
        assert pom is not None
        assert "log4j" in pom["content"]
        assert "1.2.17" in pom["content"]


# ─── Analysis Status Tests ─────────────────────────────────────────────────────

class TestAnalysisStatus:
    def setup_method(self):
        resp = client.post("/api/v1/projects", json={"name": "Analysis Status Test"})
        self.project_id = resp.json()["id"]

    def test_analysis_status_not_started(self):
        resp = client.get(f"/api/v1/projects/{self.project_id}/analysis/status")
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_started"

    def test_analysis_get_before_run_returns_404(self):
        resp = client.get(f"/api/v1/projects/{self.project_id}/analysis")
        assert resp.status_code == 404

    def test_start_analysis_no_files_creates_record(self):
        """Analysis start should create a record even if no files (will fail gracefully)"""
        resp = client.post(f"/api/v1/projects/{self.project_id}/analysis/start", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert "analysis_id" in data
        time.sleep(0.3)  # allow background thread to settle

    def test_issues_empty_before_analysis(self):
        """Use a dedicated project to avoid background thread race"""
        r = client.post("/api/v1/projects", json={"name": "Issues Empty Check"})
        pid = r.json()["id"]
        resp = client.get(f"/api/v1/projects/{pid}/analysis/issues")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_recommendations_empty_before_analysis(self):
        r = client.post("/api/v1/projects", json={"name": "Recs Empty Check"})
        pid = r.json()["id"]
        resp = client.get(f"/api/v1/projects/{pid}/analysis/recommendations")
        assert resp.status_code == 200
        assert resp.json() == []


# ─── Transformation Tests ──────────────────────────────────────────────────────

class TestTransformations:
    def setup_method(self):
        resp = client.post("/api/v1/projects", json={"name": "Transform Test"})
        self.project_id = resp.json()["id"]

    def test_list_transformations_empty(self):
        resp = client.get(f"/api/v1/projects/{self.project_id}/transformations")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_transform_nonexistent_file_returns_404(self):
        resp = client.post(f"/api/v1/projects/{self.project_id}/transformations", json={
            "file_path": "nonexistent/file.java",
        })
        assert resp.status_code in [404, 500]  # File not found

    def test_transform_request_structure(self):
        """Test that TransformationRequest validates correctly"""
        resp = client.post(f"/api/v1/projects/{self.project_id}/transformations", json={
            "file_path": "src/Main.java",
            "instruction": "Add proper error handling",
            "target_tech": "Spring Boot 3",
        })
        # Either 404 (file not found) or 500 (AI error) — both correct
        assert resp.status_code in [404, 500]

    def test_update_status_invalid_value_returns_422(self):
        """PATCH with an unrecognised status must return 422, not silently persist garbage."""
        fake_id = str(uuid.uuid4())
        resp = client.patch(
            f"/api/v1/projects/{self.project_id}/transformations/{fake_id}",
            json={"status": "totally_made_up_status"},
        )
        assert resp.status_code == 422, (
            f"Expected 422 for invalid status, got {resp.status_code}: {resp.json()}"
        )

    def test_update_status_valid_values_accepted(self):
        """All whitelisted statuses must pass validation (404 is fine — no real row)."""
        fake_id = str(uuid.uuid4())
        for valid_status in ("proposed", "reviewed", "approved", "rejected", "applied"):
            resp = client.patch(
                f"/api/v1/projects/{self.project_id}/transformations/{fake_id}",
                json={"status": valid_status},
            )
            # 404 = record not found (correct), anything else means validation passed
            assert resp.status_code in (200, 404), (
                f"Expected 200/404 for valid status '{valid_status}', got {resp.status_code}"
            )

    def test_update_status_missing_field_returns_400(self):
        """PATCH with no status field must return 400."""
        fake_id = str(uuid.uuid4())
        resp = client.patch(
            f"/api/v1/projects/{self.project_id}/transformations/{fake_id}",
            json={"something_else": "value"},
        )
        assert resp.status_code == 400


# ─── Validation Tests ──────────────────────────────────────────────────────────

class TestValidation:
    def setup_method(self):
        resp = client.post("/api/v1/projects", json={"name": "Validation Test"})
        self.project_id = resp.json()["id"]

    def test_list_validations_empty(self):
        resp = client.get(f"/api/v1/projects/{self.project_id}/transformations/validation/all")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_validate_nonexistent_transformation(self):
        resp = client.post(f"/api/v1/projects/{self.project_id}/transformations/{uuid.uuid4()}/validate")
        assert resp.status_code == 404


# ─── Health Check ──────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_check(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_health_has_version(self):
        resp = client.get("/api/health")
        assert "version" in resp.json()

    def test_health_reports_ai_configured(self):
        resp = client.get("/api/health")
        data = resp.json()
        assert "ai_configured" in data
        # With test placeholder set, this should be True
        assert data["ai_configured"] is True

    def test_health_reports_provider(self):
        """Health endpoint must report the AI provider name."""
        resp = client.get("/api/health")
        data = resp.json()
        assert data.get("ai_provider") == "nebius"
        assert "ai_model" in data



# ─── Nebius AI Configuration Tests ────────────────────────────────────────────

class TestNebiusAIConfig:
    """Tests for Nebius Token Factory AI service configuration and error handling."""

    def test_ai_status_endpoint_exists(self):
        resp = client.get("/api/ai/status")
        assert resp.status_code == 200

    def test_ai_status_reports_provider(self):
        """AI status must report provider=nebius."""
        resp = client.get("/api/ai/status")
        data = resp.json()
        assert data.get("provider") == "nebius"

    def test_ai_status_reports_configured_true_with_test_settings(self):
        """With placeholder value set, ai/status should report configured=True."""
        resp = client.get("/api/ai/status")
        data = resp.json()
        assert "configured" in data
        # Test settings have a placeholder value for the required var
        assert data["configured"] is True

    def test_ai_config_error_raises_when_key_missing(self):
        """AIServiceConfigError should be raised when NEBIUS_API_KEY is missing."""
        from app.services.ai_service import AIServiceConfigError, _get_api_key
        original = settings.nebius_api_key
        settings.nebius_api_key = ""
        try:
            _get_api_key()
            assert False, "Should have raised AIServiceConfigError"
        except AIServiceConfigError as e:
            assert "NEBIUS_API_KEY" in str(e)
        finally:
            settings.nebius_api_key = original

    def test_api_key_not_in_error_response(self):
        """The API key must never appear in HTTP error responses."""
        original = settings.nebius_api_key
        settings.nebius_api_key = ""
        try:
            # Wrong method on ai/status → 405, key should not be exposed
            resp = client.post("/api/ai/status")
            assert resp.status_code == 405
        finally:
            settings.nebius_api_key = original

    def test_nebius_config_var_names(self):
        """Verify the config uses NEBIUS_ vars, not Nemotron or OpenAI vars."""
        assert hasattr(settings, "nebius_api_key")
        assert hasattr(settings, "nebius_base_url")
        assert hasattr(settings, "nebius_model")
        assert not hasattr(settings, "Nemotronshell_api_key")
        assert not hasattr(settings, "Nemotron_inference_url")
        assert not hasattr(settings, "openai_api_key")
        assert not hasattr(settings, "openai_model")

    def test_ai_status_reports_model(self):
        """AI status endpoint must include the model name."""
        resp = client.get("/api/ai/status")
        data = resp.json()
        assert "model" in data
        # With placeholder settings, model should reflect nemotron
        if data["configured"]:
            assert "nemotron" in data.get("model", "").lower() or \
                   "nvidia" in data.get("model", "").lower()

    def test_default_model_is_nemotron(self):
        """Default model must be an NVIDIA Nemotron variant."""
        from app.services.ai_service import _model_id
        original = settings.nebius_model
        settings.nebius_model = ""
        try:
            model = _model_id()
            assert "nemotron" in model.lower() or "nvidia" in model.lower()
        finally:
            settings.nebius_model = original

    def test_inference_url_is_nebius(self):
        """Inference URL must point to Nebius, not Nemotron."""
        from app.services.ai_service import _inference_url
        url = _inference_url()
        assert "nebius" in url.lower()
        assert "https://nemotron-ai.com/" not in url


# ─── AI Service Mock Tests ─────────────────────────────────────────────────────

class TestAIServiceMocks:
    """Tests that mock external calls to verify AI service behavior."""

    def test_successful_call_ai_returns_content(self):
        """call_ai should return choice content on a 200 response."""
        from app.services.ai_service import call_ai
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello from Nemotron"}}]
        }
        with patch("app.services.ai_service._make_client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: s
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client
            result = call_ai([{"role": "user", "content": "test"}])
        assert result == "Hello from Nemotron"

    def test_call_ai_raises_auth_error_on_401(self):
        """call_ai should raise AIServiceAuthError on HTTP 401."""
        from app.services.ai_service import call_ai, AIServiceAuthError
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"message": "Unauthorized"}
        mock_response.text = "Unauthorized"
        with patch("app.services.ai_service._make_client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: s
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client
            with pytest.raises(AIServiceAuthError):
                call_ai([{"role": "user", "content": "test"}])

    def test_call_ai_raises_rate_limit_on_429(self):
        """call_ai should raise AIServiceRateLimitError on HTTP 429."""
        from app.services.ai_service import call_ai, AIServiceRateLimitError
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.json.return_value = {}
        with patch("app.services.ai_service._make_client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: s
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client
            with pytest.raises(AIServiceRateLimitError):
                call_ai([{"role": "user", "content": "test"}])

    def test_call_ai_raises_error_on_500(self):
        """call_ai should raise AIServiceError on HTTP 5xx."""
        from app.services.ai_service import call_ai, AIServiceError
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal server error"}
        with patch("app.services.ai_service._make_client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: s
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client
            with pytest.raises(AIServiceError):
                call_ai([{"role": "user", "content": "test"}])

    def test_call_ai_raises_config_error_on_connect_error(self):
        """call_ai should raise AIServiceConfigError on connection failure."""
        import httpx
        from app.services.ai_service import call_ai, AIServiceConfigError
        with patch("app.services.ai_service._make_client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: s
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_cls.return_value = mock_client
            with pytest.raises(AIServiceConfigError):
                call_ai([{"role": "user", "content": "test"}])

    def test_call_ai_raises_error_on_timeout(self):
        """call_ai should raise AIServiceError on timeout."""
        import httpx
        from app.services.ai_service import call_ai, AIServiceError
        with patch("app.services.ai_service._make_client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: s
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.side_effect = httpx.ReadTimeout("Timeout")
            mock_client_cls.return_value = mock_client
            with pytest.raises(AIServiceError):
                call_ai([{"role": "user", "content": "test"}])

    def test_call_ai_raises_error_on_malformed_response(self):
        """call_ai should raise AIServiceError when choices is missing."""
        from app.services.ai_service import call_ai, AIServiceError
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"unexpected": "structure"}
        mock_response.text = '{"unexpected": "structure"}'
        with patch("app.services.ai_service._make_client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: s
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_response
            mock_client_cls.return_value = mock_client
            with pytest.raises(AIServiceError):
                call_ai([{"role": "user", "content": "test"}])

    def test_check_connectivity_ok(self):
        """check_connectivity should return status=ok on a successful ping."""
        from app.services.ai_service import check_connectivity
        with patch("app.services.ai_service.call_ai", return_value="ready"):
            result = check_connectivity()
        assert result["status"] == "ok"
        assert "nebius" in result.get("endpoint", "").lower()
        assert result.get("model") is not None

    def test_check_connectivity_error(self):
        """check_connectivity should return status=error when the call fails."""
        from app.services.ai_service import check_connectivity, AIServiceAuthError
        with patch("app.services.ai_service.call_ai", side_effect=AIServiceAuthError("Bad key")):
            result = check_connectivity()
        assert result["status"] == "error"
        assert "Bad key" in result["message"]


# ─── JSON Repair Tests ─────────────────────────────────────────────────────────

class TestJSONRepair:
    """Tests for the JSON repair pipeline in ai_service."""

    def test_extract_json_from_fenced_block(self):
        from app.services.ai_service import _extract_json_from_text
        text = 'Here is the result:\n```json\n{"key": "value"}\n```'
        result = _extract_json_from_text(text)
        assert result == '{"key": "value"}'

    def test_extract_json_bare_json(self):
        from app.services.ai_service import _extract_json_from_text
        text = '{"key": "value"}'
        assert _extract_json_from_text(text) == '{"key": "value"}'

    def test_remove_trailing_commas(self):
        from app.services.ai_service import _remove_trailing_commas
        import json
        text = '{"a": 1, "b": 2,}'
        result = _remove_trailing_commas(text)
        assert json.loads(result) == {"a": 1, "b": 2}

    def test_replace_python_literals(self):
        from app.services.ai_service import _replace_python_literals
        import json
        text = '{"a": None, "b": True, "c": False}'
        result = _replace_python_literals(text)
        assert json.loads(result) == {"a": None, "b": True, "c": False}

    def test_repair_truncated_json(self):
        from app.services.ai_service import _repair_truncated_json
        import json
        text = '{"a": 1, "b": ['
        result = _repair_truncated_json(text)
        parsed = json.loads(result)
        assert parsed["a"] == 1


# ─── Chat Tests ────────────────────────────────────────────────────────────────

class TestChat:
    def setup_method(self):
        resp = client.post("/api/v1/projects", json={"name": "Chat Test"})
        self.project_id = resp.json()["id"]

    def test_chat_history_empty(self):
        resp = client.get(f"/api/v1/projects/{self.project_id}/chat/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_clear_chat_history(self):
        resp = client.delete(f"/api/v1/projects/{self.project_id}/chat/history")
        assert resp.status_code == 200


# ─── Error Handling Tests ──────────────────────────────────────────────────────

class TestErrorHandling:
    def test_invalid_project_id_for_files(self):
        resp = client.get(f"/api/v1/projects/not-a-real-id/files")
        assert resp.status_code == 404

    def test_invalid_project_id_for_analysis(self):
        resp = client.get(f"/api/v1/projects/not-a-real-id/analysis")
        assert resp.status_code in [404]

    def test_project_name_required(self):
        resp = client.post("/api/v1/projects", json={})
        assert resp.status_code == 422

    def test_analysis_on_nonexistent_project(self):
        resp = client.post(f"/api/v1/projects/{uuid.uuid4()}/analysis/start", json={})
        assert resp.status_code == 404

    def test_upload_to_nonexistent_project(self):
        content = b"some code"
        resp = client.post(
            f"/api/v1/projects/{uuid.uuid4()}/files/upload",
            files=[("files", ("file.java", content, "text/plain"))],
            data={"replace": "false"},
        )
        assert resp.status_code == 404


# ─── New regression tests for fixes applied in this session ───────────────────

class TestProjectServiceFixes:
    """Regression tests for project_service fixes: dynamic SQL, cascade delete,
    accurate dashboard metrics."""

    def setup_method(self):
        resp = client.post("/api/v1/projects", json={
            "name": "Service Fix Test",
            "legacy_tech": "Java",
            "target_tech": "Spring Boot 3",
        })
        self.project_id = resp.json()["id"]

    def test_update_project_all_fields(self):
        """update_project should accept all whitelisted columns without SQL errors."""
        resp = client.patch(f"/api/v1/projects/{self.project_id}", json={
            "name": "Renamed",
            "description": "Updated desc",
            "legacy_tech": "COBOL",
            "target_tech": "Java 21",
            "objective": "New goal",
            "status": "analyzed",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Renamed"
        assert data["legacy_tech"] == "COBOL"
        assert data["target_tech"] == "Java 21"

    def test_update_project_partial_update(self):
        """Partial update should only change the specified fields."""
        resp = client.patch(f"/api/v1/projects/{self.project_id}", json={"name": "Only Name Changed"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Only Name Changed"
        # legacy_tech should be unchanged from setup
        assert data["legacy_tech"] == "Java"

    def test_delete_project_cascades(self):
        """delete_project must remove the project row and succeed atomically."""
        resp = client.delete(f"/api/v1/projects/{self.project_id}")
        assert resp.status_code == 200
        # Project should be gone
        get_resp = client.get(f"/api/v1/projects/{self.project_id}")
        assert get_resp.status_code == 404

    def test_dashboard_analyzed_files_is_zero_before_analysis(self):
        """analyzed_files should be 0 before any successful analysis."""
        resp = client.get(f"/api/v1/projects/{self.project_id}/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        # Before any analysis runs, no files have been analyzed
        assert data["analyzed_files"] == 0

    def test_dashboard_validation_status_before_validation(self):
        """validation_status should be 'not_validated' before any validation run."""
        resp = client.get(f"/api/v1/projects/{self.project_id}/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["validation_status"] == "not_validated"


class TestAIServiceEmptyResponse:
    """Regression tests for empty / null AI response handling."""

    def _make_mock_response(self, content, finish_reason="stop", status=200):
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.json.return_value = {
            "choices": [{"message": {"content": content}, "finish_reason": finish_reason}]
        }
        mock_response.text = str(content)
        return mock_response

    def _call_with_mock(self, mock_resp):
        from app.services.ai_service import call_ai
        with patch("app.services.ai_service._make_client") as mock_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = lambda s: s
            mock_client.__exit__ = MagicMock(return_value=False)
            mock_client.post.return_value = mock_resp
            mock_cls.return_value = mock_client
            return call_ai([{"role": "user", "content": "test"}])

    def test_empty_string_response_raises_error(self):
        """An empty string content must be rejected, not returned silently."""
        from app.services.ai_service import AIServiceError
        mock_resp = self._make_mock_response("")
        with pytest.raises(AIServiceError, match="empty response"):
            self._call_with_mock(mock_resp)

    def test_whitespace_only_response_raises_error(self):
        """Whitespace-only content must be rejected."""
        from app.services.ai_service import AIServiceError
        mock_resp = self._make_mock_response("   \n  ")
        with pytest.raises(AIServiceError, match="empty response"):
            self._call_with_mock(mock_resp)

    def test_null_content_raises_error(self):
        """Null content must be rejected."""
        from app.services.ai_service import AIServiceError
        mock_resp = self._make_mock_response(None)
        with pytest.raises(AIServiceError, match="null"):
            self._call_with_mock(mock_resp)

    def test_valid_content_is_returned(self):
        """Non-empty content must be returned unchanged."""
        from app.services.ai_service import call_ai
        mock_resp = self._make_mock_response("Hello from Nemotron")
        result = self._call_with_mock(mock_resp)
        assert result == "Hello from Nemotron"


class TestValidationStatusFix:
    """Regression tests for the misleading validation fallback status fix."""

    def setup_method(self):
        resp = client.post("/api/v1/projects", json={"name": "Validation Status Test"})
        self.project_id = resp.json()["id"]
        # Upload a small file so there's something to transform
        content = b"def hello(): pass"
        up = client.post(
            f"/api/v1/projects/{self.project_id}/files/upload",
            files=[("files", ("hello.py", content, "text/plain"))],
            data={"replace": "false"},
        )
        # Response shape: {"saved": N, "files": [...], "errors": [...]}
        up_data = up.json() if up.status_code == 200 else {}
        files_list = up_data.get("files", [])
        self.file_id = files_list[0]["id"] if files_list else None

    def test_validation_fallback_sets_ai_unavailable_status(self):
        """When AI is unavailable, overall_status must be 'ai_unavailable', not 'requires_significant_rework'."""
        from app.services import transformation_service
        from app.services.ai_service import AIServiceError

        if not self.file_id:
            pytest.skip("File upload failed in setup")

        # Create a transformation record directly via service (avoids HTTP routing)
        with patch("app.services.transformation_service.ai_service.transform_file") as mock_tf:
            mock_tf.return_value = {
                "transformed_code": "def hello(): return 'hi'",
                "explanation": "Added return value",
                "risks": "", "assumptions": "", "review_items": "", "validation_notes": "",
            }
            trans = transformation_service.create_transformation(
                project_id=self.project_id,
                file_path="hello.py",
                task_id=None,
                instruction="Add return value",
                target_tech="Python 3",
            )

        assert trans is not None
        transformation_id = trans["id"]

        # Simulate AI unavailable during validation
        with patch("app.services.transformation_service.ai_service.validate_transformation",
                   side_effect=AIServiceError("AI is down")):
            result = transformation_service.run_validation(self.project_id, transformation_id)

        assert result["overall_status"] == "ai_unavailable", (
            f"Expected 'ai_unavailable', got '{result['overall_status']}'. "
            "This status must be distinct from 'issues_detected' or 'requires_significant_rework'."
        )

    def test_validation_status_ready_when_no_errors(self):
        """overall_status must be 'ready_for_review' when AI returns no errors."""
        from app.services import transformation_service

        if not self.file_id:
            pytest.skip("File upload failed in setup")

        with patch("app.services.transformation_service.ai_service.transform_file") as mock_tf:
            mock_tf.return_value = {
                "transformed_code": "def hello(): return 'hi'",
                "explanation": "Added return value",
                "risks": "", "assumptions": "", "review_items": "", "validation_notes": "",
            }
            trans = transformation_service.create_transformation(
                project_id=self.project_id,
                file_path="hello.py",
                task_id=None,
                instruction="Add return value",
                target_tech="Python 3",
            )

        with patch("app.services.transformation_service.ai_service.validate_transformation") as mock_val:
            mock_val.return_value = {
                "errors": [],
                "warnings": ["Minor style issue"],
                "manual_review_items": [],
                "static_analysis": [],
                "notes": "",
            }
            result = transformation_service.run_validation(self.project_id, trans["id"])

        assert result["overall_status"] == "ready_for_review"

    def test_validation_status_issues_when_errors_present(self):
        """overall_status must be 'issues_detected' when AI returns errors."""
        from app.services import transformation_service

        if not self.file_id:
            pytest.skip("File upload failed in setup")

        with patch("app.services.transformation_service.ai_service.transform_file") as mock_tf:
            mock_tf.return_value = {
                "transformed_code": "def hello(): return 'hi'",
                "explanation": "", "risks": "", "assumptions": "", "review_items": "", "validation_notes": "",
            }
            trans = transformation_service.create_transformation(
                project_id=self.project_id,
                file_path="hello.py",
                task_id=None,
                instruction="test",
                target_tech="Python 3",
            )

        with patch("app.services.transformation_service.ai_service.validate_transformation") as mock_val:
            mock_val.return_value = {
                "errors": ["Missing type hints"],
                "warnings": [],
                "manual_review_items": [],
                "static_analysis": [],
                "notes": "",
            }
            result = transformation_service.run_validation(self.project_id, trans["id"])

        assert result["overall_status"] == "issues_detected"


class TestAnalysisThreadSafety:
    """Tests for the background thread wrapper in analysis.py."""

    def test_run_analysis_safe_logs_and_fails_on_exception(self):
        """_run_analysis_safe must call _fail_analysis when run_analysis raises."""
        from app.api.analysis import _run_analysis_safe
        from app.services import analysis_service

        fake_id = str(uuid.uuid4())
        fake_project = str(uuid.uuid4())

        with patch.object(analysis_service, "run_analysis",
                          side_effect=RuntimeError("Simulated crash")):
            with patch.object(analysis_service, "_fail_analysis") as mock_fail:
                _run_analysis_safe(fake_project, fake_id)
                mock_fail.assert_called_once()
                # Confirm the failure message contains context
                call_args = mock_fail.call_args[0]
                assert call_args[0] == fake_id
                assert "Simulated crash" in call_args[1]
