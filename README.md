# College Lost & Found Management Website

A modern, full-stack campus **Lost & Found Management System**, built using **Python Flask**, **SQLite**, **Tailwind CSS (Stitch Blush Collegiate UI/UX)**, and **pytest**.

This project features both a responsive Web User Interface and RESTful API endpoints structured for academic clarity, ease of explanation during technical vivas/presentations, and adherence to software engineering standards.

---

## 🎨 Frontend UI/UX Design System (Blush Collegiate)

The user interface follows the **Blush Collegiate** design language designed via Stitch AI:
- **Color Palette**:
  - Primary: `#974259` (Deep Berry / Rose)
  - Secondary Container: `#f8dce2` (Blush Accent)
  - Tertiary / Success: `#35675a` (Sage / Verified Emerald)
  - Background: `#fbf8ff` (Warm Ivory Canvas)
  - Surfaces: `#ffffff` & `#f5f2f9`
- **Typography**: Plus Jakarta Sans (`headline-xl`, `headline-lg`, `body-md`, `label-sm`)
- **Icons**: Google Material Symbols Outlined
- **Framework**: Tailwind CSS (via CDN with custom theme extensions)

### Web Pages:
- **`GET /` (Homepage)**: Hero banner, campus registry live stats, quick action center, recently reported live feed, 4-step safe handover protocol, campus custody desks.
- **`GET /browse` or `GET /board` (Campus Board)**: Real-time search, segmented tabs (`All`, `Lost`, `Found`), category filters, sorting, dynamic item cards, full details modal, and interactive "Claim Item" workflow.
- **`GET /report` (Report Item)**: Lost/Found toggle, category dropdown, campus location & date picker, description character counter, drag-and-drop photo upload with instant preview.
- **`GET /claims` (My Claims)**: Track submitted ownership claims, view verification notes, and see status badges (`Pending`, `Approved`, `Rejected`).
- **`GET /admin` (Admin Control Panel)**: Real-time system stats, pending ownership claims review (one-click Approve / Reject), and item report status management (`open`, `claimed`, `returned`, `resolved`).

---

## 📁 Project Architecture & Directory Structure

```text
college-lost-and-found/
├── .env.example          # Template for environment configuration & secrets
├── .env                  # Local environment file (git-ignored)
├── .gitignore            # Excludes databases, virtual environments, and secrets
├── requirements.txt      # Minimal project dependencies (Flask, pytest, python-dotenv)
├── README.md             # Project documentation and API specifications
├── app.py                # Application factory (create_app), error handlers, entry point
├── database.py           # SQLite connection lifecycle (get_db, close_db, init_db)
├── models.py             # DDL schemas, domain constants, and serialization helpers
├── routes/               # Modular Flask Blueprints (API & Web endpoints)
│   ├── __init__.py       # Blueprint registry
│   ├── admin_routes.py   # Admin management endpoints (/api/admin/users, /api/admin/stats, review)
│   ├── auth_routes.py    # Authentication (register, login, logout, me, notifications) & RBAC
│   ├── claim_routes.py   # Ownership claims endpoints (/api/items/<id>/claims, /api/claims/my)
│   ├── health.py         # Health check endpoint (/api/health) & DB ping
│   ├── item_routes.py    # Lost & found item reporting, listing, filters, and image serving
│   └── web_routes.py     # Frontend web routes (/, /browse, /report, /claims, /admin)
├── services/             # Business logic layer
│   ├── __init__.py
│   ├── auth_service.py   # Password hashing (Werkzeug), user creation, authentication
│   ├── claim_service.py  # Claim submission, admin review, and item lifecycle transitions
│   ├── item_service.py   # Validation, search, and image processing for items
│   └── seed_service.py   # Auto-seeds realistic demo items matching the Stitch UI design
├── templates/            # Jinja2 HTML Templates (Blush Collegiate UI/UX)
│   ├── base.html         # Base layout with navbar, auth modal, notifications & footer
│   ├── index.html        # Homepage with hero, metrics, live feed, custody desks
│   ├── board.html        # Interactive Lost & Found catalog board with search & claim modal
│   ├── report.html       # Report Lost/Found form with drag-and-drop image upload
│   ├── claims.html       # Student claims verification & tracking page
│   └── admin.html        # Administrator moderation & claim approval panel
├── tests/                # Automated pytest suite (61 test cases)
│   ├── __init__.py
│   ├── conftest.py       # Isolated test client and temporary DB fixtures
│   ├── test_audit.py     # Edge cases, date validation, 404s, case-insensitivity, stale sessions
│   ├── test_auth.py      # Registration, login, duplicate check, and RBAC tests
│   ├── test_claims.py    # Claim submission, approval/rejection cascades, status transitions
│   ├── test_database.py  # Schema initialization, tables, foreign keys & cascade tests
│   ├── test_errors.py    # Custom JSON error handler tests (404, 405)
│   ├── test_health.py    # Health check endpoint tests
│   ├── test_items.py     # Reporting, search, filters, image uploads, edit/delete auth
│   ├── test_services.py  # Password hashing, validation, & item tests
│   └── test_web.py       # Frontend web page rendering and template verification tests
└── uploads/              # Storage directory for uploaded item photos (.gitkeep)
```

---

## 🛡️ Security Best Practices

1. **No Plain-Text Passwords**: Passwords are cryptographically hashed using Werkzeug (`generate_password_hash` with secure salting). Plain text passwords are never stored in the database.
2. **Data Sanitization**: Internal model serializers (`user_to_dict`) explicitly exclude sensitive fields like `password_hash` from API payloads.
3. **Session Security & Fixation Protection**:
   - `SESSION_COOKIE_HTTPONLY = True`: Blocks JavaScript from reading the cookie, mitigating XSS attacks.
   - `SESSION_COOKIE_SAMESITE = 'Lax'`: Mitigates Cross-Site Request Forgery (CSRF).
   - `session.clear()` is called on login to prevent session fixation attacks.
4. **Role-Based Access Control (RBAC)**: Custom decorators `@login_required` (HTTP 401) and `@admin_required` (HTTP 403) protect sensitive resources.
5. **No Secrets in Source Control**: Secrets and environment configurations are loaded from `.env` (via `.env.example`). `.env` and SQLite database files (`*.db`) are ignored in `.gitignore`.
6. **SQL Injection Prevention**: All queries use parameterized placeholders (`?`), preventing SQL injection attacks.
7. **Upload Protection**: File upload size limits are enforced via `MAX_CONTENT_LENGTH` (16MB default).

---

## 🗄️ Database Design (SQLite)

- **`users`**:
  - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `name` (TEXT NOT NULL)
  - `email` (TEXT UNIQUE NOT NULL)
  - `password_hash` (TEXT NOT NULL)
  - `role` (TEXT NOT NULL CHECK(role IN ('student', 'faculty', 'staff', 'admin')))
  - `phone` (TEXT)
  - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

- **`items`**:
  - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `title` (TEXT NOT NULL)
  - `description` (TEXT NOT NULL)
  - `category` (TEXT NOT NULL)
  - `type` (TEXT NOT NULL CHECK(type IN ('lost', 'found')))
  - `location` (TEXT NOT NULL)
  - `date_event` (DATE NOT NULL)
  - `status` (TEXT NOT NULL CHECK(status IN ('open', 'claimed', 'resolved', 'returned')))
  - `image_filename` (TEXT)
  - `user_id` (INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE)
  - `contact_email` (TEXT)
  - `contact_phone` (TEXT)
  - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

- **`claims`**:
  - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `item_id` (INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE)
  - `claimant_id` (INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE)
  - `proof_details` (TEXT NOT NULL)
  - `status` (TEXT NOT NULL CHECK(status IN ('pending', 'approved', 'rejected')))
  - `admin_notes` (TEXT)
  - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

- **`notifications`**:
  - `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
  - `user_id` (INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE)
  - `title` (TEXT NOT NULL)
  - `message` (TEXT NOT NULL)
  - `is_read` (INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0, 1)))
  - `created_at` (TIMESTAMP DEFAULT CURRENT_TIMESTAMP)

---

## 🔌 API Endpoints Specification

### 1. Health & Discovery
- `GET /api/health`: Health status & SQLite connectivity test.
- `GET /`: API metadata and registered endpoints directory.

### 2. Authentication (`/api/auth`)
- `POST /api/auth/register`: Register new user.
  - Body: `{"name": "...", "email": "...", "password": "...", "role": "student|faculty|staff|admin", "phone": "..."}`
  - Status codes: `201 Created`, `400 Bad Request` (validation error), `409 Conflict` (duplicate email).
- `POST /api/auth/login`: Authenticate and start session.
  - Body: `{"email": "...", "password": "..."}`
  - Status codes: `200 OK`, `400 Bad Request`, `401 Unauthorized`.
- `POST /api/auth/logout`: Invalidate and clear current session.
  - Status codes: `200 OK`.
- `GET /api/auth/me`: Get profile of authenticated user.
  - Protected: `@login_required`.
  - Status codes: `200 OK`, `401 Unauthorized`.
- `GET /api/auth/notifications`: List notifications for current user.
  - Protected: `@login_required`.
  - Status codes: `200 OK`, `401 Unauthorized`.
- `PATCH /api/auth/notifications/<id>/read`: Mark a notification as read.
  - Protected: `@login_required`.
  - Status codes: `200 OK`, `401 Unauthorized`, `404 Not Found`.

### 3. Admin Management & Claim Review (`/api/admin`)
- `GET /api/admin/users`: List all registered accounts (passwords sanitized).
  - Protected: `@admin_required`.
  - Status codes: `200 OK`, `401 Unauthorized`, `403 Forbidden`.
- `GET /api/admin/stats`: Total counts of users, items, claims, and notifications.
  - Protected: `@admin_required`.
  - Status codes: `200 OK`, `401 Unauthorized`, `403 Forbidden`.
- `GET /api/admin/reports`: List all submitted reports with optional filters.
  - Protected: `@admin_required`.
  - Status codes: `200 OK`, `401 Unauthorized`, `403 Forbidden`.
- `GET /api/admin/claims`: List all ownership claims across items.
  - Protected: `@admin_required`.
  - Query parameters: `status=pending|approved|rejected`, `item_id`.
  - Status codes: `200 OK`, `401 Unauthorized`, `403 Forbidden`.
- `POST /api/admin/claims/<id>/approve`: Approve a pending ownership claim.
  - Protected: `@admin_required`.
  - Effect: Transitions claim to `approved`, item status to `claimed`, auto-rejects other pending claims, notifies claimant.
  - Status codes: `200 OK`, `400 Bad Request` (invalid transition), `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.
- `POST /api/admin/claims/<id>/reject`: Reject a pending ownership claim.
  - Protected: `@admin_required`.
  - Body: `{"admin_notes": "..."}` (optional).
  - Effect: Transitions claim to `rejected`, notifies claimant.
  - Status codes: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.
- `PUT /api/admin/claims/<id>` / `PATCH /api/admin/claims/<id>`: Unified review endpoint.
  - Protected: `@admin_required`.
  - Body: `{"status": "approved|rejected", "admin_notes": "..."}`.
  - Status codes: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.
- `PUT /api/admin/items/<id>/status` / `PATCH /api/admin/items/<id>/status`: Update item lifecycle status.
  - Protected: `@admin_required`.
  - Body: `{"status": "returned|resolved|open|claimed", "admin_notes": "..."}`.
  - Enforces invalid transition prevention: closed/returned/resolved items cannot be reverted to `open`.
  - Status codes: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.

### 4. Items & Uploads (`/api/items`)
- `POST /api/items`: Report a lost or found item.
  - Protected: `@login_required`.
  - Content-Type: `multipart/form-data` (with image) or `application/json` (text-only).
  - Fields: `title`, `description`, `category`, `type` (`lost`|`found`), `location`, `date_event`, `image` (file, optional), `contact_email`, `contact_phone`.
  - Status codes: `201 Created`, `400 Bad Request` (validation / file-type / file-size failure), `401 Unauthorized`.
- `GET /api/items`: Search and filter items.
  - Public.
  - Query parameters:
    - `q` or `search`: Keyword search across title, description, and location.
    - `type`: Filter by item type (`lost` or `found`).
    - `category`: Filter by category (e.g., `Electronics`, `Keys`, `Clothing`).
    - `location`: Substring filter on location.
    - `status`: Filter by status (`open`, `claimed`, `returned`, `resolved`).
  - Status codes: `200 OK`.
- `GET /api/items/<id>`: Retrieve specific item details.
  - Public.
  - Status codes: `200 OK`, `404 Not Found`.
- `PUT /api/items/<id>` / `PATCH /api/items/<id>`: Update an existing report.
  - Protected: `@login_required` (only the report owner or an admin can edit).
  - Status codes: `200 OK`, `400 Bad Request`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.
- `DELETE /api/items/<id>`: Delete an item report.
  - Protected: `@login_required` (only the report owner or an admin can delete).
  - Status codes: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.
- `GET /uploads/<filename>`: Fetch uploaded item images.
  - Public.
  - Status codes: `200 OK`, `404 Not Found`.

### 5. Ownership Claims (`/api/items/<id>/claims` & `/api/claims`)
- `POST /api/items/<id>/claims`: Submit an ownership claim for a found item with proof description.
  - Protected: `@login_required`.
  - Body: `{"proof_details": "..."}` (minimum 10 characters).
  - Rules: Only found items can be claimed; users cannot claim their own reports; duplicate pending claims are prevented.
  - Status codes: `201 Created`, `400 Bad Request`, `401 Unauthorized`, `404 Not Found`.
- `GET /api/claims/my`: Retrieve all claims submitted by the current user.
  - Protected: `@login_required`.
  - Status codes: `200 OK`, `401 Unauthorized`.
- `GET /api/items/<id>/claims`: Retrieve claims for a specific item (reporter or admin only).
  - Protected: `@login_required`.
  - Status codes: `200 OK`, `401 Unauthorized`, `403 Forbidden`, `404 Not Found`.

---

## 🚀 Local Setup & Installation

### 1. Navigate to the project directory
```bash
cd college-lost-and-found
```

### 2. Create and activate a Python virtual environment (Recommended)
```bash
python3 -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Create your local environment file
```bash
cp .env.example .env
```

### 5. Initialize the SQLite database (Optional)
The database auto-initializes upon first start, but you can also manually initialize or reset it anytime using the CLI command:
```bash
flask --app app init-db

# Or drop existing tables and recreate cleanly from scratch:
flask --app app init-db --reset
```

---

## 🏃 Running the Application

Start the local development server:
```bash
python3 app.py
```
*(Default URL: `http://127.0.0.1:5001`. Port 5001 avoids macOS AirPlay receiver conflicts on port 5000).*

Open `http://127.0.0.1:5001/` in your web browser to explore the full Stitch UI/UX experience!

### 🔑 Pre-Seeded Demo Accounts:
Upon first launch, realistic campus sample items and two demo accounts are automatically prepared:
- **Student User**: `student@campus.edu` | Password: `StudentPass123`
- **Administrator**: `admin@campus.edu` | Password: `AdminPass123`
*(You can also use the "Quick Demo" buttons inside the Sign In modal to log in with 1 click).*

---

## 🧪 Running Automated Tests

Run the full 61-test pytest suite:
```bash
pytest -v
```

Tests cover:
- Table creation and foreign key constraints (including cascade deletes on notifications)
- Successful user registration & input validations
- Duplicate email registration conflict (409)
- Successful login, session cookies, and logout
- Incorrect password & non-existent user handling (401)
- Role-based access control:
  - Unauthenticated access to admin routes (401)
  - Student access to admin routes (403 Forbidden)
  - Admin access to admin routes (200 OK)
- Health check & custom JSON error handlers (404, 405)
- Frontend Web Route rendering (`/`, `/browse`, `/report`, `/claims`, `/admin`)
