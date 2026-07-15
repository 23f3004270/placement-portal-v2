# EZPlace - Placement Portal

## Project Purpose

EZPlace is a web application created to manage campus placement drives. It connects college admins, corporate recruiters, and students in one place. The system uses a background task queue to handle time-consuming jobs like generating CSV reports and sending email notifications, keeping the website fast and responsive.

---

# User Types and Permissions

The app uses Role-Based Access Control (RBAC) to restrict features based on who logs in. User validation is handled via JSON Web Tokens (JWT) passed in the request headers.

## Admin
The campus placement cell manager.

**Responsibilities:**
- View overall portal statistics.
- Verify and approve new company registrations.
- Activate or deactivate user accounts.
- Approve or reject placement drives before they go live.

## Company (Recruiter)
Corporate talent acquisition teams.

**Responsibilities:**
- Post new job drives.
- Manage posted positions.
- View applicants for specific jobs.
- Change candidate application statuses.
- Add review remarks.
- Book interview slots by defining a date, time, and meeting link.

## Student
The job applicants.

**Responsibilities:**
- Build personal profiles.
- Add and manage technical skills.
- Compute skill matching percentage against live jobs.
- Apply to active placement drives.
- Track application history.
- Accept official job offers.

---

# Technical Inventory and Functions

## Frontend Engine (Vue.js)

The frontend uses Vue.js with custom square bracket delimiters `[[ ]]` to prevent conflicts with Flask's Jinja template syntax.

### `calculateAffinity(jobSkillsStr)`
Compares a job's required skills against a student's profile tags and displays the matching percentage.

### `addSkillTag()`
Adds a skill tag when the user presses **Enter**.

### `removeSkillTag(idx)`
Removes a selected skill tag.

### `triggerExport()`
Initiates asynchronous CSV generation.

### `pollExportStatus()`
Continuously checks the export status until the download becomes available.

### `lockInterviewSlot(applicant)`
Sends the selected interview date, time, and meeting link to the backend to schedule an interview.

---

## Backend Routing (Flask & Celery)

### `company_page()`
Serves the recruiter dashboard.

### `POST /api/export/trigger`
Starts asynchronous CSV generation using Celery.

### `GET /api/export/status`
Returns the current status of the export task.

### Celery Tasks

Background workers perform tasks such as:

- Generating CSV reports.
- Processing long-running data operations.
- Dispatching email notifications through the local SMTP server.

---

# How to Setup and Run the Project

## Prerequisites

- Python 3.x
- Redis Server (installed and running)
- MailHog Server (installed and running)

---

## Step 1: Initialize the Environment

Open a terminal inside the project directory and execute:

```
python -m venv venv

# Linux/macOS
source venv/bin/activate

# Windows
venv\Scripts\activate

pip install -r requirements.txt
```

---

## Step 2: Start Background Services

Ensure the following services are running:

- Redis Server
- MailHog Server

---

## Step 3: Run the Application

Open **three separate terminals**, activate the virtual environment in each terminal, and execute the following commands.

### Terminal 1 — Flask Web Server

```
python app.py
```

### Terminal 2 — Celery Worker

```
celery -A app.celery worker --loglevel=info
```

### Terminal 3 — Celery Beat Scheduler

```
celery -A app.celery beat --loglevel=info
```

---

## Access the Application

Open browser and navigate to:

```text
http://127.0.0.1:5000/
```

---

# Logged Issues and Resolutions

## Database Connection Errors

**Issue**

The application could not connect to the database or background services.

**Resolution**

Verified the installation and ensured all required services were started in the correct order.

---

## Template Syntax Conflicts

**Issue**

Flask attempted to interpret Vue.js template expressions.

**Resolution**

Configured Vue.js to use square bracket delimiters (`[[ ]]`) instead of the default curly braces.

---

## Inconsistent UI Styling

**Issue**

Stylesheets loaded inconsistently across different devices.

**Resolution**

Centralized theme variables and localized CSS imports.

---

## Table UI Stretching During Interview Scheduling

**Issue**

Interview scheduling forms disrupted the table layout.

**Resolution**

Moved the scheduling form into a dedicated row spanning the full table width.

---

## Duplicate Email Notifications

**Issue**

Emails were sent multiple times due to duplicate event listeners.

**Resolution**

Separated status update logic from form submission to ensure a single notification trigger.

---

## Environment Path Errors

**Issue**

Celery workers failed to locate project files.

**Resolution**

Activated the virtual environment before starting every service terminal.

---

## Export Download Reliability

**Issue**

Generated CSV files occasionally failed to download automatically.

**Resolution**

Updated the polling mechanism to trigger a browser download once the export status changed to **Completed**.