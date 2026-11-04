
-- ============================================================
-- MEDIC CARE DATABASE
-- Fresh Local Setup
-- MySQL Community Server 8.4.11
-- ============================================================

CREATE DATABASE IF NOT EXISTS medic_care
CHARACTER SET utf8mb4
COLLATE utf8mb4_unicode_ci;

USE medic_care;


-- ============================================================
-- 1. USERS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS users (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    login_id VARCHAR(254) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(254) NOT NULL DEFAULT '',
    phone VARCHAR(30) NOT NULL DEFAULT '',
    code VARCHAR(8) NOT NULL DEFAULT '+63',
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    UNIQUE KEY uq_users_login_id (login_id)

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 1A. USER PROFILE PHOTOS
-- ============================================================

CREATE TABLE IF NOT EXISTS profile_photos (
    user_id INT UNSIGNED NOT NULL,
    image_data MEDIUMBLOB NOT NULL,
    mime_type VARCHAR(32) NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id),

    CONSTRAINT fk_profile_photos_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 1B. USER PROFILE DETAILS
-- ============================================================

CREATE TABLE IF NOT EXISTS user_profile_details (
    user_id INT UNSIGNED NOT NULL,
    alt_phone VARCHAR(30) NOT NULL DEFAULT '',
    address VARCHAR(500) NOT NULL DEFAULT '',
    gender VARCHAR(30) NOT NULL DEFAULT '',
    bday_month TINYINT UNSIGNED NULL,
    bday_day TINYINT UNSIGNED NULL,
    bday_year SMALLINT UNSIGNED NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (user_id),

    CONSTRAINT fk_user_profile_details_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 2. APPOINTMENTS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS appointments (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id INT UNSIGNED NOT NULL,
    client_id INT NOT NULL DEFAULT 0,

    doctor VARCHAR(100) NOT NULL DEFAULT '',
    doctor_name VARCHAR(200) NOT NULL DEFAULT '',
    spec VARCHAR(200) NOT NULL DEFAULT '',
    service VARCHAR(300) NOT NULL DEFAULT '',
    specific_service VARCHAR(300) NOT NULL DEFAULT '',

    status VARCHAR(20) NOT NULL DEFAULT 'Pending',

    appt_date DATE NULL,
    appt_time VARCHAR(40) NOT NULL DEFAULT '',

    patient_first VARCHAR(100) NOT NULL DEFAULT '',
    patient_middle VARCHAR(100) NOT NULL DEFAULT '',
    patient_last VARCHAR(100) NOT NULL DEFAULT '',
    patient_suffix VARCHAR(20) NOT NULL DEFAULT '',

    patient_dob DATE NULL,
    patient_sex VARCHAR(20) NOT NULL DEFAULT '',

    patient_phone VARCHAR(30) NOT NULL DEFAULT '',
    patient_email VARCHAR(254) NOT NULL DEFAULT '',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_appointments_user (user_id),

    CONSTRAINT fk_appointments_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;

-- ============================================================
-- 3. USER NOTIFICATIONS
-- ============================================================

CREATE TABLE IF NOT EXISTS notifications (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    user_id INT UNSIGNED NOT NULL,
    appointment_id INT UNSIGNED NULL,
    type VARCHAR(50) NOT NULL,
    doctor_name VARCHAR(200) NOT NULL DEFAULT '',
    appointment_date DATE NULL,
    appointment_time VARCHAR(40) NOT NULL DEFAULT '',
    reason VARCHAR(500) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at DATETIME NULL,

    PRIMARY KEY (id),
    KEY idx_notifications_user_read_created (user_id, read_at, created_at),

    CONSTRAINT fk_notifications_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 4. PASSWORD RESETS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS password_resets (
    token_hash CHAR(64) NOT NULL,
    user_id INT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (token_hash),

    KEY idx_password_resets_user (user_id),

    CONSTRAINT fk_password_resets_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 5. LOGIN CHALLENGES TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS login_challenges (
    token_hash CHAR(64) NOT NULL,
    user_id INT UNSIGNED NOT NULL,
    expires_at DATETIME NOT NULL,
    confirmed TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (token_hash),

    KEY idx_login_challenges_user (user_id),

    CONSTRAINT fk_login_challenges_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 6. APPOINTMENT SLOTS TABLE
-- ============================================================

CREATE TABLE IF NOT EXISTS appointment_slots (
    slot_key CHAR(64) NOT NULL,
    user_id INT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (slot_key),

    KEY idx_appointment_slots_user (user_id),

    CONSTRAINT fk_appointment_slots_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE

) ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 7. ADMIN ACCOUNT
-- ============================================================

INSERT INTO users (
    login_id,
    password_hash,
    name,
    email,
    role,
    status
)
VALUES (
    'thisismydatabase666@gmail.com',

    'scrypt:32768:8:1$4RAKR6N2Bj1blcvw$8589258f21d85db33eb0c8a6d3197a0eaa1da28cca85502f91fd6c7ca40df475807a6a667c02286129e91bd0293bb1c1cd84cccc9212f1ce0b39c37126f0cf46',

    'System Admin',

    'thisismydatabase666@gmail.com',

    'admin',

    'active'
)

ON DUPLICATE KEY UPDATE
    login_id = VALUES(login_id);


-- ============================================================
-- 7. VERIFY DATABASE
-- ============================================================

SHOW TABLES;

DESCRIBE users;

SELECT
    id,
    login_id,
    name,
    email,
    role,
    status,
    created_at
FROM users
WHERE login_id = 'thisismydatabase666@gmail.com';


-- ============================================================
-- END OF MEDIC CARE DATABASE
-- ============================================================
