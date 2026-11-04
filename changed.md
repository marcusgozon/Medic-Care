# Medicare System Major Update

## Overview

This update represents a major improvement to the Medicare Appointment Management System. The project was upgraded with a cleaner user interface, improved project structure, enhanced security, a complete administrator portal, and migration from Firebase to MySQL.

---

# UI Improvements & Branding

The application's overall appearance was redesigned to provide a more modern, professional, and user-friendly healthcare experience.

## Improvements Made

- Redesigned the overall user interface.
- Improved layout consistency throughout the application.
- Enhanced spacing, typography, forms, buttons, and cards.
- Created a cleaner and more modern healthcare-themed design.
- Improved page organization and readability.
- Enhanced responsiveness and visual presentation.
- Added Medicare branding across the system.
- Added a custom Medicare favicon.
- Added a Medicare logo for a stronger visual identity.

## CSS Improvements

### Updated File
```
frontend/styles/medic-care.css
```

### Changes

- Refined color palette and theme styling.
- Improved form element designs.
- Enhanced button styles and interactions.
- Updated card layouts and page containers.
- Improved visual hierarchy.
- Optimized spacing and typography.
- Created a cleaner and more professional user experience.

---

# Frontend Structure Refactor

The frontend was reorganized into a more professional and scalable structure.

## New Project Structure

```text
frontend/
│
├── assets/
│   ├── herobg.png
│   ├── medic-care-logo.png
│   └── medic-care-favicon.png
│
├── pages/
│   ├── appointment.html
│   ├── booking.html
│   ├── login.html
│   ├── medical_history.html
│   ├── profile.html
│   ├── reset_password.html
│   ├── settings.html
│   └── signup.html
│
├── script/
│   ├── auth.js
│   └── languages.js
│
├── styles/
│   └── medic-care.css
│
└── index.html
```

## Benefits

- Better separation of concerns.
- More professional file organization.
- Easier project navigation.
- Improved maintainability.
- Better scalability for future development.
- Industry-standard frontend structure.
- Cleaner development workflow.

---

# Database Migration

## Previous Database

```
Firebase
```

## New Database

```
MySQL
```

## Benefits

- Better relational data management.
- Full SQL query support.
- Improved scalability.
- More control over database operations.
- Better support for appointments and user management.

---

# Admin Portal Implementation

A complete Admin Portal was created to allow administrators to manage users and appointments securely.

---

## Process 1: Admin Login & Two-Factor Authentication (2FA)

### Goal

Securely verify administrators using both a password and a one-time verification code sent via email.

### Flow

#### Step 1
Admin enters email and password on:

```text
admin.html
```

#### Step 2
Frontend sends:

```http
POST /api/admin/login
```

#### Step 3
Backend performs:

- Email lookup.
- Password verification using `check_password_hash()`.
- Admin role verification.
- Generates a random 6-digit OTP code.
- Stores OTP with a 10-minute expiration.
- Sends OTP via Brevo Email API.

#### Step 4
Admin enters received OTP.

#### Step 5
Frontend sends:

```http
POST /api/admin/verify
```

#### Step 6
Backend:

- Validates OTP.
- Checks expiration.
- Creates secure session.

```python
session["is_admin"] = True
```

#### Step 7
Admin dashboard loads system data.

---

## Process 2: Appointment Synchronization

### Goal

Ensure Admin and Patient portals display identical appointment statuses.

### Flow

#### Fetch Appointments

Frontend requests:

```http
GET /api/admin/appointments
```

Backend:

- Performs SQL JOIN between users and appointments.
- Returns complete appointment list.

#### Update Appointment

Frontend sends:

```http
PUT /api/admin/appointments/<id>
```

```json
{
  "status": "Confirmed"
}
```

Backend executes:

```sql
UPDATE appointments
SET status='Confirmed'
WHERE id=<id>;
```

### Cancellation Handling

When status becomes:

```text
Cancelled
```

The backend removes the entry from:

```text
appointment_slots
```

This frees the slot for new bookings.

### Patient View

Patients automatically see updated statuses because all appointment information is loaded directly from the database.

### Supported Statuses

- Pending
- Confirmed
- Completed
- Cancelled

---

## Process 3: User Ban & Unban System

### Goal

Block problematic users without removing their records.

### Ban User

Frontend sends:

```http
PUT /api/admin/users/<id>/status
```

```json
{
  "status": "banned"
}
```

Backend executes:

```sql
UPDATE users
SET status='banned'
WHERE id=<id>;
```

### Login Prevention

When a banned account attempts login:

Backend returns:

```http
403 account_banned
```

### Active Session Protection

If a user is already logged in:

- Heartbeat checks run every 15 seconds.
- Backend detects banned status.
- User is automatically logged out.
- User is redirected to login page.

---

## Process 4: Secure Logout

### Goal

Completely destroy sessions and prevent access through browser cache.

### Logout Flow

#### Frontend

Admin clicks:

```text
Log Out
```

Frontend:

- Hides the dashboard immediately.
- Sends logout request.

```http
POST /api/logout
```

#### Backend

Executes:

```python
session.clear()
```

Deletes session cookie.

#### Frontend

Redirects to:

```text
/admin?t=<timestamp>
```

#### Backend

Returns:

```http
Cache-Control: no-store
```

#### Result

Any future admin request without authentication returns:

```http
401 Unauthorized
```

---

# Database Architecture

## Users Table

Stores:

- id
- login_id
- password_hash
- role
- status

### Roles

- user
- admin

### Statuses

- active
- banned

---

## Appointments Table

Stores:

- id
- user_id
- doctor_name
- appt_date
- appt_time
- status

---

## Appointment Slots Table

Used as a booking-locking mechanism.

Stores a unique hash generated from:

- Doctor
- Date
- Time

### Benefits

- Prevents double booking.
- Releases slots when appointments are cancelled.
- Ensures booking integrity.

---

# New Files Added

## frontend/pages/admin.html

### Purpose

Complete Administrator Portal containing:

- Admin Login
- OTP Verification
- Dashboard Analytics
- User Management
- Appointment Management
- Edit User Modal
- Appointment Details Modal
- Sidebar Navigation

---

# Updated Files

## backend/app.py

### Changes

- Added `/api/admin/login`
- Added `/api/admin/verify`
- Added `/api/admin/users`
- Added `/api/admin/users/<id>`
- Added `/api/admin/users/<id>/status`
- Added `/api/admin/appointments`
- Added `/api/admin/appointments/<id>`
- Added OTP functionality using Brevo Email API.
- Added session management improvements.
- Added anti-cache protection.
- Fixed logout caching issues.
- Added secure cookie deletion.

---

## backend/schema.sql

### Changes

Added:

```sql
role VARCHAR(20) DEFAULT 'user'
```

Added:

```sql
status VARCHAR(20) DEFAULT 'active'
```

Added administrator account initialization.

---

## frontend/styles/medic-care.css

### Changes

- Redesigned overall UI appearance.
- Improved healthcare branding.
- Updated typography and spacing.
- Enhanced layouts and responsiveness.
- Improved buttons, forms, cards, and navigation.
- Added styling support for newly organized frontend structure.

---

## frontend/script/auth.js

### Changes

- Removed hardcoded appointment status overrides.
- Appointment statuses now come directly from the database.
- Added 15-second heartbeat checks.
- Automatically logs out banned users.

---

## frontend/pages/appointment.html

### Changes

Updated appointment rendering to accurately display:

- Pending
- Confirmed
- Completed
- Cancelled

statuses directly from database records.

---

## frontend/pages/login.html

### Changes

Added support for:

```text
account_banned
```

Users now receive the message:

> This account has been banned or disabled by an administrator.

---

## backend/.env

### Changes

Updated:

```env
DB_PORT=3307
```

Added:

```env
BREVO_API_KEY=
```

```env
BREVO_SENDER_EMAIL=
```

for administrator OTP email delivery.

---

# Files Not Modified

The following files remained functionally unchanged:

- booking.html
- profile.html
- settings.html
- medical_history.html
- signup.html
- reset_password.html
- languages.js

These files continue working with the improved styling, database architecture, and backend functionality.

---

# Final Result

The Medicare Appointment Management System now includes:

✅ Modern and professional UI design

✅ Improved CSS architecture

✅ Professional frontend folder structure

✅ MySQL database integration

✅ Secure Admin Portal

✅ Email OTP Authentication

✅ Appointment Management System

✅ User Ban & Unban System

✅ Real-time Appointment Status Synchronization

✅ Secure Session Handling

✅ Anti-cache Logout Protection

✅ Improved Scalability and Maintainability

✅ Stronger Medicare Branding