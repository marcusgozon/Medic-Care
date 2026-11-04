# Medic Care

Medic Care is a small healthcare website where patients can create an account,
book appointments, and manage their account details. The experience is designed
around a polished, trustworthy medical brand with a clean interface, consistent
visual identity, and patient-friendly layouts.

## Branding

Medic Care uses a healthcare-focused visual system that reinforces trust,
professionalism, and clarity. The branding is carried through the logo,
favicon, hero imagery, page styling, and overall layout so patients can quickly
recognize the application across screens and features.

Key branding elements include:

- A modern medical logo and favicon for a recognizable identity.
- A calm, professional color palette suited to healthcare services.
- Consistent typography and spacing for a more premium patient experience.
- Cohesive hero and page design that supports appointment booking and account
  management workflows.

## What you can do

- Browse the home page and available medical services.
- Create an account and sign in with an email address.
- Book an appointment by choosing a service, date, time, and entering patient
  details.
- View, reschedule, or cancel your appointments.
- Review appointment records in Medical History.
- Update your profile and phone number.
- Change your language between English and Filipino.
- Change your password or delete your account.
- Request a password-reset link by email.

Login email confirmation is optional. It can be enabled when an email server is
configured.

## Run the website on Windows

The website needs Python, MySQL Server, and (optionally) MySQL Workbench. Workbench
is a convenient way to set up the database, but the app itself connects to MySQL
Server.

### 1. Create the database

1. Start MySQL Server.
2. Open MySQL Workbench and connect to your local server.
3. Open `backend/schema.sql` and run the script. It creates the `medic_care`
   database and required tables.

### 2. Install the Python packages

Open PowerShell in the project folder and run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell does not allow activating the virtual environment, you can run
Python from it directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 3. Configure the app

Create `backend\.env` from the example if it does not already exist:

```powershell
if (-not (Test-Path backend\.env)) { Copy-Item backend\.env.example backend\.env }
```

Open `backend\.env` and set `DB_PASSWORD` to your MySQL password. Also replace
`SECRET_KEY` with a long, random value. The other database settings normally
work for a local MySQL installation:

```text
SECRET_KEY=replace-with-a-long-random-value
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your-mysql-root-password
DB_NAME=medic_care
LOGIN_EMAIL_VERIFICATION=0
```

Keep `LOGIN_EMAIL_VERIFICATION=0` for local development without an email
service. To require an email confirmation every time someone signs in, set it
to `1` and configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`,
`SMTP_PASSWORD`, and `RESET_EMAIL_FROM`. Email settings are also needed to send
password-reset links.

### 4. Start the website

From the project folder, run:

```powershell
python backend\app.py
```

Open **http://127.0.0.1:10000/** in your browser. Use the site through this
address rather than opening the HTML files directly. Leave the PowerShell
window running while you use the website; press `Ctrl+C` there to stop it.

The app uses port `10000` by default. To use another port, set the `PORT`
environment variable before starting the app.

## Project layout

| Path | What it contains |
| --- | --- |
| `backend/app.py` | Flask server, API, and local website server |
| `backend/schema.sql` | MySQL database and table definitions |
| `backend/.env.example` | Example local configuration |
| `frontend/index.html` | Home page |
| `frontend/assets/` | Branding assets including the logo, favicon, and hero image |
| `frontend/pages/` | Signup, login, booking, appointments, profile, history, and settings |
| `frontend/script/` | Shared account and language functionality |
| `frontend/styles/medic-care.css` | Shared, page-scoped styles, responsive layouts, and motion |

## Troubleshooting

- **The page cannot reach the server:** Make sure `python backend\app.py` is
  still running, and open the local address above.
- **Database connection error:** Confirm MySQL Server is running and that
  `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` in
  `backend\.env` match your MySQL setup. Make sure you ran `backend/schema.sql`.
- **Email confirmation or password reset does not arrive:** Check your SMTP
  settings and spam folder. For local sign-in without email, use
  `LOGIN_EMAIL_VERIFICATION=0`.

## Deployment note

Run the production server with:

```powershell
gunicorn --chdir backend app:app
```

Configure `SECRET_KEY`, the `DB_*` settings, email settings as needed,
`SESSION_COOKIE_SECURE=1`, `TRUST_PROXY=1` (when behind a trusted proxy), and
`PUBLIC_URL`. Do not commit `backend/.env` or use development server settings in
production.
