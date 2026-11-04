-- Medic Care - MySQL schema
-- How to run this in MySQL Workbench:
--   File > Open SQL Script... > pick this file, then click the lightning bolt
--   (or Query > Execute All). Run it once on a fresh server; it is safe to
--   run again because every object is created with IF NOT EXISTS.

CREATE DATABASE IF NOT EXISTS medic_care
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE medic_care;

-- One row per account. login_id is the e-mail address the patient signs in with.
CREATE TABLE IF NOT EXISTS users (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    login_id      VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name          VARCHAR(200) NOT NULL,
    email         VARCHAR(254) NOT NULL DEFAULT '',
    phone         VARCHAR(30)  NOT NULL DEFAULT '',
    code          VARCHAR(8)   NOT NULL DEFAULT '+63',
    created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_login_id (login_id)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- One row per booked appointment. client_id is the number the browser
-- assigned to the appointment (it shows up in the UI as the record id).
CREATE TABLE IF NOT EXISTS appointments (
    id             INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id        INT UNSIGNED NOT NULL,
    client_id      INT          NOT NULL DEFAULT 0,
    doctor         VARCHAR(100) NOT NULL DEFAULT '',
    doctor_name    VARCHAR(200) NOT NULL DEFAULT '',
    spec           VARCHAR(200) NOT NULL DEFAULT '',
    service        VARCHAR(300) NOT NULL DEFAULT '',
    specific_service VARCHAR(300) NOT NULL DEFAULT '',
    status         VARCHAR(20)  NOT NULL DEFAULT 'Confirmed',
    appt_date      DATE         NULL,
    appt_time      VARCHAR(40)  NOT NULL DEFAULT '',
    patient_first  VARCHAR(100) NOT NULL DEFAULT '',
    patient_middle VARCHAR(100) NOT NULL DEFAULT '',
    patient_last   VARCHAR(100) NOT NULL DEFAULT '',
    patient_suffix VARCHAR(20)  NOT NULL DEFAULT '',
    patient_dob    DATE         NULL,
    patient_sex    VARCHAR(20)  NOT NULL DEFAULT '',
    patient_phone  VARCHAR(30)  NOT NULL DEFAULT '',
    patient_email  VARCHAR(254) NOT NULL DEFAULT '',
    created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_appointments_user (user_id),
    CONSTRAINT fk_appointments_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- "Forgot password" links. token_hash is the SHA-256 of the token in the e-mail,
-- so the link itself is never stored.
CREATE TABLE IF NOT EXISTS password_resets (
    token_hash CHAR(64)     NOT NULL,
    user_id    INT UNSIGNED NOT NULL,
    expires_at DATETIME     NOT NULL,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (token_hash),
    KEY idx_password_resets_user (user_id),
    CONSTRAINT fk_password_resets_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- "Confirm your login" e-mailed links (only used when LOGIN_EMAIL_VERIFICATION=1).
CREATE TABLE IF NOT EXISTS login_challenges (
    token_hash CHAR(64)     NOT NULL,
    user_id    INT UNSIGNED NOT NULL,
    expires_at DATETIME     NOT NULL,
    confirmed  TINYINT(1)   NOT NULL DEFAULT 0,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (token_hash),
    KEY idx_login_challenges_user (user_id),
    CONSTRAINT fk_login_challenges_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;

-- One row per taken doctor/date/time slot. The primary key is what stops two
-- patients from booking the same slot at the same moment.
CREATE TABLE IF NOT EXISTS appointment_slots (
    slot_key   CHAR(64)     NOT NULL,
    user_id    INT UNSIGNED NOT NULL,
    created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (slot_key),
    KEY idx_appointment_slots_user (user_id),
    CONSTRAINT fk_appointment_slots_user FOREIGN KEY (user_id)
        REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci;
