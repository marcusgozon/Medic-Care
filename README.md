# Medic Care

Medic Care is a healthcare appointment web app for patients to discover services, request appointments, and manage their account. Staff can review appointment requests and manage users through a separate admin portal.

## Features

- Browse the public landing page and available medical services
- Create an account, sign in, and optionally verify the email address
- Book appointments through a guided, multi-step flow
- View appointment history, and reschedule or cancel appointments
- Receive in-app notifications with sound when an appointment is approved or denied
- Get a 30-minute reminder popup and alert sound for confirmed appointments while using the patient dashboard
- Receive one appointment reminder email 30 minutes before a confirmed appointment when the Render reminder Cron Job is configured
- Review and manage appointment requests in the admin portal, including denial reasons
- Manage user accounts and appointment records as an administrator
- Keep profile details, contact information, and a profile photo (JPG, PNG, or WebP; up to 2 MB) in the database
- Change a password or request a password-reset email
- Choose English or Filipino and switch between light and dark themes
- Use responsive layouts on desktop and mobile devices

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

### Appointment Reminders on Render

The patient dashboard checks confirmed appointments and shows a popup with `frontend/assets/alert.mp3` during the 30 minutes before the appointment. The sound plays after the user interacts with the page, as required by browser autoplay policies. Appointment dates and times are interpreted as Philippine time (UTC+8).

To send one reminder email to the patient's account email address even when they are not using the site, create a **Cron Job** in Render:

- Use the same repository and branch as the web service.
- Build command: `pip install -r requirements.txt`
- Start command: `python -m backend.reminders`
- Schedule: `* * * * *` (once per minute)
- Add the production database and email environment variables to the Cron Job, including `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `BREVO_API_KEY`, and `BREVO_SENDER_EMAIL` (or the SMTP variables).

The reminder email is sent only for confirmed appointments. The scheduled job also creates an in-app notification and avoids sending the same appointment reminder more than once. Brevo must have a valid API key and verified sender configured on the Cron Job; SMTP can be used instead.
