# Medic Care

> **Healthcare appointments, made simpler.**
>
> Medic Care helps patients find services, book appointments, and manage their care. Clinic staff can review bookings and manage patient accounts from the admin portal.

## Features

### 🩺 For Patients

| | |
|---|---|
| **Find care** | Browse medical services and book through a guided appointment flow. |
| **Manage appointments** | View appointment history, and reschedule or cancel bookings. |
| **Stay informed** | Get in-app updates with a notification sound when an appointment is approved or denied. |
| **Appointment reminders** | See a reminder popup and hear `alert.mp3` during the 30 minutes before a confirmed appointment. Receive one reminder email when an appointment is due within an hour. |
| **Manage your account** | Update profile details, contact information, and a profile photo (JPG, PNG, or WebP; up to 2 MB). Change your password or request a reset email. |

### 🗂️ For Clinic Staff

- Review appointment requests and update their status.
- Provide a reason when denying an appointment; patients receive that reason in their notification.
- Manage patient accounts and appointment records in the admin portal.
- Receive a notification sound when a new appointment is waiting for review.

### ✨ Designed for Everyday Use

- Choose English or Filipino.
- Switch between light and dark themes.
- Use a responsive interface on desktop or mobile.

> **Reminder timing:** Appointment times use Philippine time (UTC+8). The in-app popup checks for upcoming appointments while the patient is using the site. Reminder emails are checked as the app receives patient notification requests, so delivery depends on the site receiving traffic near the reminder time. Configure the optional Render Cron Job in [Appointment Reminders](#appointment-reminders) for checks independent of site activity.

---

## Initial Setup (Windows)

Follow these steps to run the web app locally. The Flask server serves both the frontend and backend; do not open the HTML files directly.

### What You Need

Install these first:

1. **Python 3** – [Download Python](https://www.python.org/downloads/)
2. **MySQL Server 8.x** – [Download MySQL Community Server](https://dev.mysql.com/downloads/mysql/)
3. **MySQL Workbench** (recommended) – [Download Workbench](https://dev.mysql.com/downloads/workbench/)

> MySQL Workbench is a visual tool for managing the database. MySQL Server must be installed and running for the website to work.

### 1. Open the Project

1. Extract the project ZIP file.
2. Open the extracted `MedicCare` folder in VS Code.
3. In VS Code, open **Terminal → New Terminal**.
4. Make sure the terminal is in the project root (the folder containing `README.md`).

### 2. Create the MySQL Database

1. Start your local MySQL Server.
2. Open MySQL Workbench and connect to your local MySQL connection.
3. In VS Code, open `backend/schema.sql`.
4. Copy the SQL script and paste it into a new query tab in MySQL Workbench.
5. Execute the script.

This creates the `medic_care` database and the tables needed by the app, including user accounts, appointments, notifications, profile details, and profile photos.

New appointments remain pending until an administrator reviews them. When denying a request, the administrator must enter a reason, which is included in the patient's notification. Appointment status and notifications refresh while the page is open.

### 3. Set Up Python

In the VS Code terminal, run these commands from the project root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

This creates and activates a virtual environment, then installs the required packages.

**If PowerShell does not allow activation**, you can install the packages without activating the environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Use that same Python executable to start the app in Step 5 if you did not activate the environment.

### 4. Configure the Database Connection

1. In VS Code, find `backend/.env.example`.
2. Make a copy of that file inside the same `backend` folder.
3. Rename the copied file to `.env` (the final path should be `backend/.env`).
4. Open `backend/.env` and enter your own local MySQL details.

Example configuration:

```env
SECRET_KEY=replace-this-with-a-long-random-value
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=medic_care
LOGIN_EMAIL_VERIFICATION=0
```

Set these values to match your local setup:

- `DB_USER`: your MySQL username. `root` is common for a local installation.
- `DB_PASSWORD`: the password you set for that MySQL user. Leave it empty only if your MySQL account has no password.
- `DB_PORT`: usually `3306`. If your MySQL Server uses another port, enter that port instead.
- `SECRET_KEY`: use a long, random secret.

Keep `LOGIN_EMAIL_VERIFICATION=0` to test locally without email verification. Email verification and password-reset emails require an email service configured in `backend/.env` (Brevo or SMTP). See `backend/.env.example` for the supported email variable names.

> Do not share your `backend/.env` file or upload it to GitHub. It contains private configuration and credentials.

### 5. Start the Web App

If your virtual environment is activated, run:

```powershell
python backend\app.py
```

If you did not activate it, run:

```powershell
.\.venv\Scripts\python.exe backend\app.py
```

When the server starts, open this address in your browser:

**http://127.0.0.1:10000/**

Keep the terminal open while using the website. To stop the server, go back to the terminal and press **Ctrl + C**.

### Admin Access (Optional)

Admin access is provisioned for an existing account by an authorized database administrator. After creating the account, its `users.role` must be set to `admin`. Admin sign-in uses an emailed verification code, so configure an email service before using the admin portal at **http://127.0.0.1:10000/admin**.

---

## Project Structure

```text
MedicCare/
├── backend/
│   ├── app.py              # Flask server and application logic
│   ├── schema.sql          # MySQL database and tables
│   ├── .env.example        # Sample local configuration
│   └── .env                # Your private local settings (create this)
├── frontend/
│   ├── assets/             # Images and logos
│   ├── pages/              # Website pages
│   ├── script/             # JavaScript files
│   ├── styles/             # CSS files
│   └── index.html          # Homepage
├── requirements.txt        # Python dependencies
└── README.md               # Features and setup instructions
```

## Troubleshooting

**The website does not open**
- Check that the Flask server is still running in the terminal.
- Make sure you opened `http://127.0.0.1:10000/` and did not open an HTML file directly.

**MySQL connection error**
- Make sure MySQL Server is running.
- Check the host, port, username, and password in `backend/.env`.
- Confirm that you executed `backend/schema.sql` in MySQL Workbench.
- Make sure `DB_NAME` is set to `medic_care`.

**Python or package command is not recognized**
- Confirm that Python is installed.
- On Windows, try using `py` instead of `python`.
- Re-run the dependency installation command from Step 3.

**Email verification or password reset does not work**
- Email features need valid Brevo or SMTP settings in `backend/.env`.
- For local testing without email, set `LOGIN_EMAIL_VERIFICATION=0`.

---

## Notes for Deployment

The instructions above are for local development only. For deployment, configure the production environment variables, database connection, email service, and secure cookie settings on your hosting provider. Never use your local `.env` file or development credentials in production.

### Appointment Reminders

For confirmed appointments, the patient dashboard shows an in-app reminder and plays `frontend/assets/alert.mp3` during the 30 minutes before the appointment. The browser may require a user interaction before it allows audio playback.

The backend checks for appointments due within one hour when it receives a patient notification request and sends each patient one email reminder. This does not require a Cron Job, but it depends on the web app receiving requests near the reminder time. If the service is asleep or has no traffic, the email may be late or missed.

For checks independent of site activity, optionally configure a **Render Cron Job**:

1. Use the same repository and branch as the web service.
2. Set the build command to `pip install -r requirements.txt`.
3. Set the start command to `python -m backend.reminders`.
4. Set the schedule to `* * * * *` (once per minute).
5. Add the same production database and email environment variables used by the web service, including `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, and either Brevo (`BREVO_API_KEY`, `BREVO_SENDER_EMAIL`) or SMTP settings.

Each appointment reminder email is sent at most once for its scheduled booking. A valid Brevo API key and verified sender are required when using Brevo.
