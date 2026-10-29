# ModernIQ: AI Legacy Modernization & Transformation Platform

> AI-Assisted Legacy Application Modernization and Transformation Platform powered by **NVIDIA Nemotron** via **Nebius Token Factory**

---

## Overview

ModernIQ is a full-stack web application that helps developers, architects, and engineering teams understand, assess, and modernize legacy codebases using AI assistance from NVIDIA Nemotron, accessed through the Nebius Token Factory OpenAI-compatible inference API.

**The complete workflow:**

```
Import Legacy Code → Analyze → Understand Architecture → Assess Technical Debt →
Get Recommendations → Generate Migration Plan → Transform Code → Validate → Report
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        ModernIQ Platform                            │
├──────────────────────────┬──────────────────────────────────────────┤
│   React + TypeScript     │         FastAPI + Python 3.11            │
│   Frontend (Vite)        │         Backend                          │
│                          │                                          │
│  ┌─────────────────┐     │  ┌─────────────────────────────────┐    │
│  │ Project Manager  │────────│ Project / File Services          │    │
│  │ File Explorer   │     │  │ Analysis Orchestration           │    │
│  │ Analysis View   │     │  │ Transformation Service           │    │
│  │ Architecture    │     │  │ Validation Service               │    │
│  │ Issues/Debt     │────────│ AI Service (Nebius/Nemotron)     │    │
│  │ Recommendations │     │  │ Chat Service                     │    │
│  │ Moderniz. Plan  │     │  └────────────────┬────────────────┘    │
│  │ Transform WS    │     │                   │                       │
│  │ Validation      │     │  ┌────────────────▼────────────────┐    │
│  │ Reports         │     │  │         DuckDB Database          │    │
│  │ AI Chat Panel   │     │  │  (projects, files, analyses,     │    │
│  └─────────────────┘     │  │   issues, plans, transforms)     │    │
│                          │  └─────────────────────────────────┘    │
└──────────────────────────┴──────────────────────────────────────────┘
                                        │
                          ┌─────────────▼────────────┐
                          │   Nebius Token Factory    │
                          │   NVIDIA Nemotron-3_5     │
                          │   (OpenAI-compatible API) │
                          └──────────────────────────┘
```

### Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Frontend | React 18 + TypeScript + Vite | Fast iteration, type safety |
| Routing | React Router v6 | SPA navigation |
| Styling | Custom CSS (dark theme) | No runtime overhead |
| Charts | Recharts | Radar and bar charts |
| Backend | FastAPI + Python 3.11 | Async API, auto-generated docs |
| Database | DuckDB | Zero-config embedded SQL database |
| AI | NVIDIA Nemotron via Nebius Token Factory | OpenAI-compatible chat completions |
| HTTP client | httpx | Async-friendly with configurable timeouts |
| File Upload | python-multipart + react-dropzone | Multi-file, ZIP support |
| Testing | pytest + FastAPI TestClient | 79 backend tests |

---

## Features

### 🔍 Analysis Engine
- Detects programming languages, frameworks, libraries, build tools
- Identifies architecture pattern (Monolith, MVC, Layered, SOA, etc.)
- Discovers external dependencies with version/status assessment
- Finds technical debt: deprecated dependencies, security vulnerabilities, coupling issues, missing tests
- AI-assisted heuristic scoring across 10 modernization dimensions (clearly labeled as heuristic)

### 🏛️ Architecture Visualization
- SVG-based interactive architecture diagram (current legacy system)
- AI-generated recommended modern architecture diagram
- Color-coded node types (controllers, services, models, databases, etc.)
- Hover tooltips with component descriptions

### ⚠️ Issues & Technical Debt
- Severity-based issue tracking (critical/high/medium/low)
- Category filtering (Security, Architecture, Dependencies, etc.)
- Per-issue: evidence, why-it-matters, recommended action, complexity, risk
- Issue status management (open/in-progress/resolved/won't-fix)

### 💡 Recommendations
- Prioritized modernization recommendations
- Grouped by category with visual filtering
- Per-recommendation: evidence, proposed solution, expected benefit, related files

### 📋 Modernization Plan
- AI-generated staged migration plan
- Task status tracking (Not Started/In Progress/Completed/Blocked)
- Per-task: complexity, risk, priority, related files, dependencies
- Progress visualization

### ⚡ Transformation Workspace
- File-by-file AI-assisted code modernization
- Before/After side-by-side code view
- Explanation of what changed and why
- Risk assessment and manual review items
- Transformation history
- **Never overwrites original code** — all transformations are proposals

### ✅ Validation Center
- AI-based code review of proposed transformations
- Errors, warnings, static analysis findings, manual review items
- Clearly labeled: "AI validation" not "compilation/test results"

### 📄 Report Generation
- Executive summary, technology inventory, architecture assessment
- Technical debt summary, recommendations, target architecture
- Migration plan summary, transformation summary
- Exportable as JSON and Markdown

### 💬 Contextual AI Chat
- Per-project AI assistant (NVIDIA Nemotron)
- Context-aware: knows the project's files, analysis, architecture
- File-specific context when opened from file/transform views
- Suggested questions per page
- Persistent chat history per project

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- A **Nebius Token Factory** API key (see configuration below)

### 1. Configure credentials

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` and fill in your Nebius API key:

```env
NEBIUS_API_KEY=your-nebius-token-factory-api-key-here
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1
NEBIUS_MODEL=nvidia/Nemotron-3_5-Lightning
```

**Where to get a Nebius Token Factory API key:**
1. Create an account at [nebius.com](https://nebius.com/)
2. Navigate to **Token Factory → API Keys**
3. Create a new API key
4. Copy the key value into your `.env` file

### 2. Start the backend

```bash
cd backend
pip install -r requirements.txt
python run.py
# Backend starts at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### 3. Start the frontend (development)

```bash
cd frontend
npm install
npm run dev
# Frontend at http://localhost:5173
```

### 4. Production (single server)

```bash
cd frontend
npm run build
# Frontend built to frontend/dist/
# Backend serves frontend at http://localhost:8000
```

---

## NVIDIA Nemotron Integration

ModernIQ uses NVIDIA Nemotron through the **Nebius Token Factory** OpenAI-compatible API.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `NEBIUS_API_KEY` | (required) | Your Nebius Token Factory API key |
| `NEBIUS_BASE_URL` | `https://api.tokenfactory.nebius.com/v1` | API base URL |
| `NEBIUS_MODEL` | `nvidia/Nemotron-3_5-Lightning` | Model identifier |

### Authentication

The service uses standard **Bearer token** authentication:
```
Authorization: Bearer <NEBIUS_API_KEY>
```

### API Compatibility

The Nebius Token Factory exposes an OpenAI-compatible `/chat/completions` endpoint. No proprietary headers or special authentication flows are required beyond the Bearer token.

### Error Handling

The AI service handles:
- `401` → `AIServiceAuthError` (invalid or expired API key)
- `403` → `AIServiceAuthError` (access denied)
- `429` → `AIServiceRateLimitError` (rate limit exceeded, with retry guidance)
- `5xx` → `AIServiceError` (provider error)
- Network errors → `AIServiceConfigError` (misconfigured endpoint)
- Timeouts → `AIServiceError` (240-second read timeout)
- Malformed JSON → multi-stage repair pipeline, error if unrecoverable

### Connectivity Check

Verify the configuration at runtime:
```
GET /api/ai/status
```

---

## Demo Workflow

The platform includes a built-in realistic legacy Java application (ACME Inventory Management System) with intentional modernization problems.

### Demo Steps

1. **Open the app** at `http://localhost:5173`
2. **Create a new project**: Click "New Project" → enter a name → click "Create Project"
3. **Load demo project**: In the File Explorer, click "Load Demo Legacy Project"
4. **Explore the code**: Browse the file tree, inspect the legacy Java code
5. **Run analysis**: Click "Analyze Project" → "Start Analysis" (wait ~60–120 seconds)
6. **View results**:
   - **Dashboard**: Overall modernization assessment scorecard + radar chart
   - **Architecture**: Current vs. Recommended architecture diagrams
   - **Issues & Technical Debt**: 10+ identified issues with severity classification
   - **Recommendations**: Prioritized modernization recommendations
   - **Modernization Plan**: Staged migration tasks
7. **Transform code**: Go to "Transformation Workspace", select a file, click "Generate Transformation"
8. **Compare Before/After**: Review legacy vs. modern code side-by-side
9. **Validate**: Click "Run AI Validation" to get AI code review
10. **Generate Report**: Go to "Report" → "Generate Report" → export as JSON or Markdown

### Demo Legacy Application Details

The ACME Inventory Management System intentionally contains:

| Issue | Location | Severity |
|-------|---------|---------|
| Hardcoded DB credentials | `InventoryController.java`, `InventoryDAO.java`, `applicationContext.xml` | Critical |
| SQL injection vulnerability | `InventoryController.java:searchInventory()` | Critical |
| Log4j 1.x (CVE-2019-17571) | `pom.xml` | Critical |
| Commons Collections 3.2.1 (CVE-2015-7501) | `pom.xml` | Critical |
| Spring 3.2.x (EOL 2016) | `pom.xml` | High |
| JDBC connection leaks | `InventoryDAO.java` | High |
| No connection pooling | `DatabaseUtil.java` | High |
| Business logic in controller | `InventoryController.java` | High |
| Double type for monetary values | `Product.java`, `Order.java` | Medium |
| No transaction management | `InventoryDAO.java` | High |
| Zero test coverage | `InventoryControllerTest.java` | High |
| Unencrypted SMTP (port 25) | `EmailSender.java` | Medium |
| `java.util.Date` (deprecated) | `Order.java` | Low |
| No pagination | `InventoryController.java` | Medium |

---

## Running Tests

```bash
cd backend
python -m pytest tests/ -v
```

**Test coverage (79 tests):**
- Project CRUD operations
- File ingestion and language detection
- Demo project content validation
- Analysis status workflow
- Transformation and validation error handling
- Nebius AI configuration and error handling
- AI service mock tests (401, 403, 429, 5xx, timeouts, malformed responses)
- JSON repair pipeline
- Health check and provider reporting
- Chat history management

### Live Inference Test

To test actual Nebius connectivity (requires a valid `NEBIUS_API_KEY`):

```bash
cd backend
python integration_check.py
```

This creates a test project, loads demo files, verifies demo content, then calls `check_connectivity()` against the real Nebius endpoint.

---

## API Reference

The backend auto-generates API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Key Endpoints

```
GET    /api/health                               Health check + AI provider status
GET    /api/ai/status                            Nebius connectivity check

POST   /api/v1/projects                          Create project
GET    /api/v1/projects                          List projects
GET    /api/v1/projects/{id}                     Get project
PATCH  /api/v1/projects/{id}                     Update project
DELETE /api/v1/projects/{id}                     Delete project
GET    /api/v1/projects/{id}/dashboard           Dashboard stats

POST   /api/v1/projects/{id}/files/upload        Upload files
POST   /api/v1/projects/{id}/files/upload-zip    Upload ZIP archive
POST   /api/v1/projects/{id}/files/upload-demo   Load demo project
GET    /api/v1/projects/{id}/files               List files

POST   /api/v1/projects/{id}/analysis/start      Start analysis
GET    /api/v1/projects/{id}/analysis/status     Analysis status
GET    /api/v1/projects/{id}/analysis            Full analysis results
GET    /api/v1/projects/{id}/analysis/issues     Issues
GET    /api/v1/projects/{id}/analysis/recommendations  Recommendations
GET    /api/v1/projects/{id}/analysis/architecture     Architecture models
GET    /api/v1/projects/{id}/analysis/plan        Modernization plan

POST   /api/v1/projects/{id}/transformations     Generate transformation
GET    /api/v1/projects/{id}/transformations     List transformations
POST   /api/v1/projects/{id}/transformations/{tid}/validate  AI validation

POST   /api/v1/projects/{id}/chat               Send chat message
GET    /api/v1/projects/{id}/chat/history        Chat history

POST   /api/v1/projects/{id}/report             Generate report
```

---

## AI Service Architecture

NVIDIA Nemotron (via Nebius Token Factory) is used for these operations:

### 1. Comprehensive Analysis (`analyze_project`)
Three concurrent Nemotron passes that produce:
- Technology inventory, code structure, dependency assessment
- Architecture pattern and components
- Technical debt items (with evidence, severity, recommended action)
- Modernization recommendations
- Architecture models (current + recommended) with nodes/edges
- Staged modernization plan with tasks
- Assessment scores (0–100 per dimension, clearly labeled as AI-assisted heuristics)
- Executive summary

### 2. Code Transformation (`transform_file`)
Given a file's original code, language, target tech, and project context:
- Produces modernized code
- Explains each change decision
- Lists risks and potential behavior changes
- Identifies manual review requirements

### 3. Transformation Validation (`run_validation`)
Given original and transformed code:
- AI code review (not compilation or execution)
- Identifies definite errors
- Warns about potential issues
- Lists static analysis findings
- Recommends manual review items

### 4. Report Generation (`generate_report`)
Synthesizes all analysis findings into a structured executive report.

### 5. Contextual Chat (`answer_project_question`)
Answers questions with project context (technology, architecture, files) and optional file-specific context.

### Transparency

The platform is explicit about AI limitations:
- Assessment scores are labeled "AI-assisted heuristic assessments — not objective measurements"
- Transformations are labeled "AI-generated proposals requiring developer review"
- Validation is labeled "AI validation" not "compilation/test results"
- Analysis findings that cannot be confirmed are labeled "Requires Further Investigation"

---

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── api/           # FastAPI route handlers
│   │   │   ├── projects.py
│   │   │   ├── files.py
│   │   │   ├── analysis.py
│   │   │   ├── transformations.py
│   │   │   ├── chat.py
│   │   │   └── reports.py
│   │   ├── core/
│   │   │   └── config.py  # NEBIUS_API_KEY, NEBIUS_BASE_URL, NEBIUS_MODEL
│   │   ├── db/
│   │   │   └── database.py
│   │   ├── models/
│   │   │   └── schemas.py
│   │   ├── services/
│   │   │   ├── ai_service.py          # Nebius/Nemotron integration
│   │   │   ├── project_service.py
│   │   │   ├── file_service.py
│   │   │   ├── analysis_service.py
│   │   │   ├── transformation_service.py
│   │   │   ├── chat_service.py
│   │   │   └── demo_service.py        # Built-in legacy demo project
│   │   └── main.py
│   ├── tests/
│   │   └── test_platform.py           # 79 tests
│   ├── requirements.txt
│   ├── run.py
│   ├── startup_check.py
│   ├── integration_check.py
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── api/client.ts              # API client
│   │   ├── components/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── AIChatPanel.tsx        # Contextual AI chat
│   │   │   ├── ArchDiagram.tsx        # SVG arch visualization
│   │   │   └── ScoreBar.tsx
│   │   ├── context/AppContext.tsx
│   │   ├── pages/
│   │   │   ├── LandingPage.tsx
│   │   │   ├── ProjectList.tsx
│   │   │   ├── NewProject.tsx
│   │   │   ├── Dashboard.tsx
│   │   │   ├── FileExplorer.tsx
│   │   │   ├── Analysis.tsx
│   │   │   ├── Architecture.tsx
│   │   │   ├── Issues.tsx
│   │   │   ├── Recommendations.tsx
│   │   │   ├── ModernizationPlan.tsx
│   │   │   ├── Transformation.tsx
│   │   │   ├── Validation.tsx
│   │   │   └── Report.tsx
│   │   ├── styles/global.css
│   │   ├── App.tsx
│   │   └── main.tsx
│   └── package.json
├── data/                              # Runtime data directory (auto-created)
└── README.md
```

---

## Data Model

| Entity | Purpose |
|--------|---------|
| `projects` | Modernization project metadata |
| `project_files` | Uploaded source files with content |
| `analyses` | Full analysis results (JSON blobs) |
| `issues` | Technical debt items |
| `recommendations` | Modernization recommendations |
| `architecture_models` | Current + recommended arch (nodes/edges) |
| `modernization_plans` | Plan metadata |
| `plan_tasks` | Individual plan tasks with status |
| `transformations` | Before/after code proposals |
| `validation_results` | AI validation findings |
| `chat_messages` | Per-project chat history |

---

## Security Considerations

This is a prototype — the following apply:

- **No authentication**: Multi-user auth not implemented. Deploy behind auth proxy for production.
- **API key security**: `NEBIUS_API_KEY` is read from environment variables only. Never stored in the database or logged. The `.env` file is excluded from version control via `.gitignore`.
- **Exposed credential**: A real API key was committed in `.env.example` and has been removed. If you have a copy of the original repository, rotate that key immediately.
- **File validation**: Uploaded files are checked for binary/supported status. Source code is never executed.
- **Path traversal prevention**: File paths are stored as-is in DB; no direct filesystem operations on uploaded content.
- **Source code privacy**: Uploaded code is stored locally in DuckDB. It is transmitted only to the configured Nebius endpoint for inference.
- **Content Security**: HTML content in JSP files is not rendered — stored and displayed as text only.

For production deployment:
- Add authentication (JWT/OAuth)
- Enable HTTPS
- Rate-limit AI endpoints
- Implement file scanning
- Restrict CORS origins
- Use `DEBUG=false`

---

## Known Limitations

1. **Analysis time**: Full AI analysis takes 60–120 seconds depending on codebase size and API latency.
2. **No code execution**: The platform cannot compile, run, or test code. All validation is AI-based review, clearly labeled as such. Build and test status fields are set to `"not_applicable"` to prevent false claims of successful builds/tests.
3. **Large codebases**: Files are truncated to ~1500–8000 chars for AI context. Very large files may lose context.
4. **Language support**: Best support for Java, Python, JavaScript/TypeScript. Other languages analyzed but transformation quality varies.
5. **Concurrent analysis**: Multiple simultaneous analyses share DB connections (DuckDB concurrent write limitations).
6. **Binary files**: Excluded from AI analysis. Structure is preserved in file tree.
7. **Live inference verification**: A live inference test with the actual Nebius credentials was not performed during this migration because no valid Nebius API key was available in this environment. The implementation follows the documented OpenAI-compatible API contract.

---

## Commands Reference

### Run the application

```bash
# Backend
cd backend
pip install -r requirements.txt
python run.py

# Frontend (development)
cd frontend
npm install
npm run dev

# Frontend (production build)
cd frontend
npm run build
# Then serve via backend at http://localhost:8000
```

### Run tests

```bash
cd backend
python -m pytest tests/ -v
```

### Startup verification

```bash
cd backend
python startup_check.py
```

### Integration check (requires valid NEBIUS_API_KEY)

```bash
cd backend
python integration_check.py
```

---

## Manual Configuration Required

After cloning, a developer must:

1. Copy `backend/.env.example` to `backend/.env`
2. Fill in `NEBIUS_API_KEY` with a valid Nebius Token Factory API key
3. Optionally override `NEBIUS_BASE_URL` or `NEBIUS_MODEL` if using a different endpoint or model

No other manual configuration is required for local development.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
