#
# backend/models.py
#
from sqlalchemy.orm import declarative_base
from sqlalchemy import (
    Column, BigInteger, Integer, Boolean, DateTime, JSON, ForeignKey, String, Text,
    Enum, DECIMAL, Index
)
from datetime import datetime, timezone
from typing import Optional

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    user_id = Column(BigInteger, primary_key=True)
    username = Column(String(50))
    first_name = Column(String(100))
    last_name = Column(String(100))
    is_bot_owner = Column(Boolean, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_username', 'username'),)

class Server(Base):
    __tablename__ = 'servers'
    server_id = Column(BigInteger, primary_key=True)
    server_name = Column(String(100))
    purpose = Column(String(50), default='COMMUNITY')  # ENUM заменён на String для SQLite
    language_code = Column(String(10), default='en')   # ENUM заменён на String для SQLite
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_server_name', 'server_name'),)

class ServerAdmin(Base):
    __tablename__ = 'server_admins'
    admin_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    permissions = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_server_admin', 'server_id', 'user_id', unique=True),)

class MediaFile(Base):
    __tablename__ = 'media_files'
    media_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    file_type = Column(String(50), nullable=False)  # ENUM заменён на String
    file_url = Column(String(255), nullable=False)
    file_id = Column(String(100))
    uploaded_by = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    is_voice = Column(Boolean, default=False)
    transcription = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Story(Base):
    __tablename__ = 'stories'
    story_id = Column(BigInteger, primary_key=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    media_id = Column(Integer, ForeignKey('media_files.media_id'))
    content = Column(JSON)
    views = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime)
    __table_args__ = (Index('idx_stories', 'server_id', 'created_at'),)

class CommandUsage(Base):
    __tablename__ = 'command_usage'
    usage_id = Column(Integer, primary_key=True, autoincrement=True, nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    command_name = Column(String(50), nullable=False)
    used_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    limit_per_user = Column(Integer, default=10)
    limit_window = Column(Integer, default=60)
    __table_args__ = (Index('idx_command_usage', 'user_id', 'server_id', 'used_at'),)

class ChatModule(Base):
    __tablename__ = 'chat_modules'
    module_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    module_name = Column(String(50), nullable=False)
    is_enabled = Column(Boolean, default=True)
    config = Column(JSON)
    __table_args__ = (Index('idx_server_module', 'server_id', 'module_name', unique=True),)

class PremiumUser(Base):
    __tablename__ = 'premium_users'
    premium_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'))
    is_premium = Column(Boolean, default=False)
    privileges = Column(JSON)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_premium_user', 'user_id', 'server_id', unique=True),)

class MiniApp(Base):
    __tablename__ = 'mini_apps'
    app_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    app_name = Column(String(100), nullable=False)
    app_url = Column(String(255), nullable=False)
    config = Column(JSON)
    is_active = Column(Boolean, default=True)

class Webhook(Base):
    __tablename__ = 'webhooks'
    webhook_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'))
    url = Column(String(255), nullable=False)
    status = Column(String(20), default='ACTIVE')  # ENUM заменён на String
    last_error = Column(Text)
    last_updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_webhook_url', 'server_id', 'url', unique=True),)

class BotfatherCommand(Base):
    __tablename__ = 'botfather_commands'
    command_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'))
    command_name = Column(String(50), nullable=False)
    description = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)

class Poll(Base):
    __tablename__ = 'polls'
    poll_id = Column(BigInteger, primary_key=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    poll_type = Column(String(20), nullable=False)  # ENUM заменён на String
    question = Column(JSON, nullable=False)
    options = Column(JSON, nullable=False)
    correct_option_id = Column(Integer)
    results = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_polls', 'server_id', 'poll_type'),)

class OAuthToken(Base):
    __tablename__ = 'oauth_tokens'
    token_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    provider = Column(String(20), nullable=False)  # ENUM заменён на String
    access_token = Column(Text, nullable=False)  # BLOB заменён на Text
    refresh_token = Column(Text)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_oauth_user', 'user_id', 'provider', unique=True),)

class UserProfile(Base):
    __tablename__ = 'user_profiles'
    profile_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'))
    nickname = Column(String(100))
    bio = Column(JSON)
    preferences = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_profile_user', 'user_id', 'server_id', unique=True),)

class ScheduledMessage(Base):
    __tablename__ = 'scheduled_messages'
    message_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    chat_id = Column(BigInteger, nullable=False)
    content = Column(JSON, nullable=False)
    media_id = Column(Integer, ForeignKey('media_files.media_id'))
    send_at = Column(DateTime, nullable=False)
    status = Column(String(20), default='PENDING')  # ENUM заменён на String
    __table_args__ = (Index('idx_scheduled_messages', 'server_id', 'send_at'),)

class AntispamRule(Base):
    __tablename__ = 'antispam_rules'
    rule_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    rule_type = Column(String(50), nullable=False)  # ENUM заменён на String
    conditions = Column(JSON, nullable=False)
    action = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)

class Backup(Base):
    __tablename__ = 'backups'
    backup_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'))
    backup_type = Column(String(20), nullable=False)  # ENUM заменён на String
    storage_path = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class Localization(Base):
    __tablename__ = 'localizations'
    localization_id = Column(Integer, primary_key=True, autoincrement=True)
    resource_key = Column(String(100), nullable=False)
    language_code = Column(String(10), nullable=False)  # ENUM заменён на String
    translation = Column(Text, nullable=False)
    context = Column(String(50), nullable=False, default='MESSAGE')  # ENUM заменён на String
    __table_args__ = (Index('idx_resource_language', 'resource_key', 'language_code', unique=True),)

class UserSetting(Base):
    __tablename__ = 'user_settings'
    setting_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    setting_name = Column(String(50), nullable=False)
    setting_value = Column(String(50), nullable=False)
    is_encrypted = Column(Boolean, default=False)
    __table_args__ = (Index('idx_user_setting', 'user_id', 'setting_name', unique=True),)

class MultilingualMessage(Base):
    __tablename__ = 'multilingual_messages'
    message_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'))
    message_key = Column(String(100), nullable=False)
    translations = Column(JSON, nullable=False)

class ChatAnalytics(Base):
    __tablename__ = 'chat_analytics'
    analytics_id = Column(BigInteger, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    analytics_type = Column(String(50), nullable=False)  # ENUM заменён на String
    value = Column(Integer, nullable=False)
    details = Column(JSON)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_chat_analytics', 'server_id', 'analytics_type'),)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    log_id = Column(BigInteger, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'))
    user_id = Column(BigInteger, ForeignKey('users.user_id'))
    action_type = Column(String(50), nullable=False)  # ENUM заменён на String
    log_level = Column(String(20), default='INFO')  # ENUM заменён на String
    details = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_audit_logs', 'server_id', 'created_at'),)

class PaymentTransaction(Base):
    __tablename__ = 'payment_transactions'
    transaction_id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(BigInteger, ForeignKey('servers.server_id'), nullable=False)
    user_id = Column(BigInteger, ForeignKey('users.user_id'), nullable=False)
    provider = Column(String(50), nullable=False)  # ENUM заменён на String
    amount = Column(DECIMAL(10, 2), nullable=False)
    currency = Column(String(10), nullable=False)  # ENUM заменён на String
    status = Column(String(20), default='PENDING')  # ENUM заменён на String
    details = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (Index('idx_payment_transactions', 'server_id', 'provider'),)

