USE kumi_db;

-- Таблица для пользователей
CREATE TABLE IF NOT EXISTS users (
    user_id BIGINT PRIMARY KEY,
    username VARCHAR(50),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    is_bot_owner BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для серверов
CREATE TABLE IF NOT EXISTS servers (
    server_id BIGINT PRIMARY KEY,
    server_name VARCHAR(100),
    purpose ENUM('COMMUNITY', 'BUSINESS', 'CHANNEL', 'OTHER') DEFAULT 'COMMUNITY',
    language_code ENUM('en', 'ru') DEFAULT 'en',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_server_name (server_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для администраторов сервера
CREATE TABLE IF NOT EXISTS server_admins (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    permissions JSON NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE KEY idx_server_admin (server_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для медиа-файлов
CREATE TABLE IF NOT EXISTS media_files (
    media_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    file_type ENUM('PHOTO', 'VIDEO', 'DOCUMENT', 'VOICE') NOT NULL,
    file_url VARCHAR(255) NOT NULL,
    file_id VARCHAR(100),
    uploaded_by BIGINT NOT NULL,
    is_voice BOOLEAN DEFAULT FALSE,
    transcription TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    FOREIGN KEY (uploaded_by) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для Telegram Stories
CREATE TABLE IF NOT EXISTS stories (
    story_id BIGINT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    media_id INT,
    content JSON,
    views INT DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME,
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (media_id) REFERENCES media_files(media_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для использования команд
CREATE TABLE IF NOT EXISTS command_usage (
    usage_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    server_id BIGINT NOT NULL,
    command_name VARCHAR(50) NOT NULL,
    used_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    limit_per_user INT DEFAULT 10,
    limit_window INT DEFAULT 60,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (server_id) REFERENCES servers(server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для модулей чата
CREATE TABLE IF NOT EXISTS chat_modules (
    module_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    module_name VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    config JSON,
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    UNIQUE KEY idx_server_module (server_id, module_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для Telegram Premium пользователей
CREATE TABLE IF NOT EXISTS premium_users (
    premium_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    server_id BIGINT,
    is_premium BOOLEAN DEFAULT FALSE,
    privileges JSON,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    UNIQUE KEY idx_premium_user (user_id, server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для Mini Apps
CREATE TABLE IF NOT EXISTS mini_apps (
    app_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    app_name VARCHAR(100) NOT NULL,
    app_url VARCHAR(255) NOT NULL,
    config JSON,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (server_id) REFERENCES servers(server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для вебхуков
CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT,
    url VARCHAR(255) NOT NULL,
    status ENUM('ACTIVE', 'INACTIVE', 'ERROR') DEFAULT 'ACTIVE',
    last_error TEXT,
    last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    UNIQUE KEY idx_webhook_url (server_id, url)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для команд BotFather
CREATE TABLE IF NOT EXISTS botfather_commands (
    command_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT,
    command_name VARCHAR(50) NOT NULL,
    description JSON NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (server_id) REFERENCES servers(server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для опросов и квизов
CREATE TABLE IF NOT EXISTS polls (
    poll_id BIGINT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    poll_type ENUM('POLL', 'QUIZ') NOT NULL,
    question JSON NOT NULL,
    options JSON NOT NULL,
    correct_option_id INT,
    results JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES servers(server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для OAuth2-токенов
CREATE TABLE IF NOT EXISTS oauth_tokens (
    token_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    provider ENUM('GOOGLE', 'DISCORD', 'OTHER') NOT NULL,
    access_token BLOB NOT NULL,
    refresh_token BLOB,
    expires_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE KEY idx_oauth_user (user_id, provider)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для профилей пользователей
CREATE TABLE IF NOT EXISTS user_profiles (
    profile_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    server_id BIGINT,
    nickname VARCHAR(100),
    bio JSON,
    preferences JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    UNIQUE KEY idx_profile_user (user_id, server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для запланированных сообщений
CREATE TABLE IF NOT EXISTS scheduled_messages (
    message_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    content JSON NOT NULL,
    media_id INT,
    send_at DATETIME NOT NULL,
    status ENUM('PENDING', 'SENT', 'FAILED') DEFAULT 'PENDING',
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    FOREIGN KEY (media_id) REFERENCES media_files(media_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для правил анти-спама
CREATE TABLE IF NOT EXISTS antispam_rules (
    rule_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    rule_type ENUM('MESSAGE_FREQUENCY', 'LINKS', 'MENTIONS', 'BOT_DETECTION') NOT NULL,
    conditions JSON NOT NULL,
    action JSON NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (server_id) REFERENCES servers(server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для метаданных резервных копий
CREATE TABLE IF NOT EXISTS backups (
    backup_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT,
    backup_type ENUM('SETTINGS', 'DATA', 'FULL') NOT NULL,
    storage_path VARCHAR(255) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES servers(server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для локализаций
CREATE TABLE IF NOT EXISTS localizations (
    localization_id INT AUTO_INCREMENT PRIMARY KEY,
    resource_key VARCHAR(100) NOT NULL,
    language_code ENUM('en', 'ru') NOT NULL,
    translation TEXT NOT NULL,
    context ENUM('COMMAND', 'MENU', 'MESSAGE', 'GUIDE', 'POST') NOT NULL DEFAULT 'MESSAGE',
    UNIQUE KEY idx_resource_language (resource_key, language_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для пользовательских настроек
CREATE TABLE IF NOT EXISTS user_settings (
    setting_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    setting_name VARCHAR(50) NOT NULL,
    setting_value VARCHAR(50) NOT NULL,
    is_encrypted BOOLEAN DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    UNIQUE KEY idx_user_setting (user_id, setting_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для многоязычных сообщений
CREATE TABLE IF NOT EXISTS multilingual_messages (
    message_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT,
    message_key VARCHAR(100) NOT NULL,
    translations JSON NOT NULL,
    FOREIGN KEY (server_id) REFERENCES servers(server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для аналитики
CREATE TABLE IF NOT EXISTS chat_analytics (
    analytics_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    analytics_type ENUM('POST_VIEWS', 'MESSAGES', 'ORDERS', 'SUBSCRIPTIONS', 'REACTIONS') NOT NULL,
    value INT NOT NULL,
    details JSON,
    recorded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES servers(server_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для логов аудита
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT,
    user_id BIGINT,
    action_type ENUM('COMMAND', 'MODERATION', 'CONFIG', 'PAYMENT') NOT NULL,
    log_level ENUM('INFO', 'WARNING', 'ERROR') DEFAULT 'INFO',
    details JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Таблица для транзакций платежных систем
CREATE TABLE IF NOT EXISTS payment_transactions (
    transaction_id INT AUTO_INCREMENT PRIMARY KEY,
    server_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    provider ENUM('STRIPE', 'PAYPAL', 'TELEGRAM_STARS') NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    currency ENUM('USD', 'EUR', 'RUB', 'STARS') NOT NULL,
    status ENUM('PENDING', 'COMPLETED', 'FAILED') DEFAULT 'PENDING',
    details JSON,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (server_id) REFERENCES servers(server_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Индексы для оптимизации
CREATE INDEX IF NOT EXISTS idx_server_admins ON server_admins(server_id, user_id);
CREATE INDEX IF NOT EXISTS idx_stories ON stories(server_id, created_at);
CREATE INDEX IF NOT EXISTS idx_command_usage ON command_usage(user_id, server_id, used_at);
CREATE INDEX IF NOT EXISTS idx_premium_users ON premium_users(user_id, server_id);
CREATE INDEX IF NOT EXISTS idx_polls ON polls(server_id, poll_type);
CREATE INDEX IF NOT EXISTS idx_scheduled_messages ON scheduled_messages(server_id, send_at);
CREATE INDEX IF NOT EXISTS idx_localizations ON localizations(resource_key, language_code);
CREATE INDEX IF NOT EXISTS idx_user_settings ON user_settings(user_id, setting_name);
CREATE INDEX IF NOT EXISTS idx_chat_analytics ON chat_analytics(server_id, analytics_type);
CREATE INDEX IF NOT EXISTS idx_audit_logs ON audit_logs(server_id, created_at);
CREATE INDEX IF NOT EXISTS idx_payment_transactions ON payment_transactions(server_id, provider);