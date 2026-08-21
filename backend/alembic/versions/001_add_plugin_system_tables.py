"""add plugin system tables

Revision ID: 001_plugin_system
Revises: 
Create Date: 2026-01-15 12:00:00.000000

This migration adds 6 tables for the plugin system:
1. plugins - Plugin registry and metadata
2. plugin_versions - Version history
3. plugin_configs - Per-user configuration
4. plugin_reviews - User ratings and reviews
5. audit_logs - Security audit trail
6. plugin_stats - Runtime statistics
"""

from alembic import op
import sqlalchemy as sa
from datetime import datetime


# revision identifiers
revision = '001_plugin_system'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ===== Table 1: plugins =====
    op.create_table(
        'plugins',
        sa.Column('id', sa.String(64), primary_key=True, comment='Plugin ID'),
        sa.Column('name', sa.String(128), nullable=False, comment='Display name'),
        sa.Column('version', sa.String(20), nullable=False, server_default='0.0.1'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'category',
            sa.Enum(
                'platform', 'datasource', 'workflow_node',
                'ai_model', 'ui_theme', 'integration',
                name='plugincategory'
            ),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum(
                'pending_review', 'approved', 'rejected', 'active',
                'inactive', 'suspended', 'deprecated',
                name='pluginstatus'
            ),
            nullable=False,
            server_default='active',
        ),
        sa.Column('author_name', sa.String(128), nullable=False, server_default=''),
        sa.Column('author_email', sa.String(255), nullable=True),
        sa.Column('entry_point', sa.String(128), nullable=False, server_default='main.py'),
        sa.Column('manifest_json', sa.JSON(), nullable=True),
        sa.Column('capabilities', sa.JSON(), nullable=True),
        sa.Column('permissions', sa.JSON(), nullable=True),
        sa.Column('config_schema', sa.JSON(), nullable=True),
        sa.Column('display_icon', sa.String(10), nullable=False, server_default='📦'),
        sa.Column('display_color', sa.String(7), nullable=False, server_default='#6366f1'),
        sa.Column(
            'pricing_model',
            sa.Enum('free', 'freemium', 'paid', name='pricingmodel'),
            nullable=False,
            server_default='free',
        ),
        sa.Column('price_monthly', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('events_publishes', sa.JSON(), nullable=True),
        sa.Column('events_subscribes', sa.JSON(), nullable=True),
        sa.Column('dependencies', sa.JSON(), nullable=True),
        sa.Column('is_builtin', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('source_url', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('install_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('average_rating', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('review_count', sa.Integer(), nullable=False, server_default='0'),
        
        # Indexes
        sa.Index('ix_plugins_category', 'category'),
        sa.Index('ix_plugins_status', 'status'),
        sa.Index('ix_plugins_author_name', 'author_name'),
        sa.Index('ix_plugins_category_status', 'category', 'status'),
        sa.Index('ix_plugins_name_search', 'name', mysql_length=100),
    )
    
    # ===== Table 2: plugin_versions =====
    op.create_table(
        'plugin_versions',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'plugin_id',
            sa.String(64),
            sa.ForeignKey('plugins.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('changelog', sa.Text(), nullable=True),
        sa.Column('release_notes', sa.Text(), nullable=True),
        sa.Column('package_checksum', sa.String(64), nullable=True),
        sa.Column('package_size_bytes', sa.Integer(), nullable=True),
        sa.Column('download_url', sa.String(512), nullable=True),
        sa.Column('min_platform_version', sa.String(20), nullable=True),
        sa.Column('max_platform_version', sa.String(20), nullable=True),
        sa.Column('is_latest', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('released_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        # Indexes
        sa.Index('ix_plugin_versions_plugin_id', 'plugin_id'),
        sa.Index('ix_plugin_versions_version', 'plugin_id', 'version', unique=True),
    )
    
    # ===== Table 3: plugin_configs =====
    op.create_table(
        'plugin_configs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.String(26),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'plugin_id',
            sa.String(64),
            sa.ForeignKey('plugins.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('config_json', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('encrypted_fields', sa.JSON(), nullable=True),
        sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        # Indexes
        sa.Index('ix_plugin_configs_user_id', 'user_id'),
        sa.Index('ix_plugin_configs_plugin_user', 'user_id', 'plugin_id', unique=True),
    )
    
    # ===== Table 4: plugin_reviews =====
    op.create_table(
        'plugin_reviews',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'plugin_id',
            sa.String(64),
            sa.ForeignKey('plugins.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column(
            'user_id',
            sa.String(26),
            sa.ForeignKey('users.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('rating', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(256), nullable=True),
        sa.Column('content', sa.Text(), nullable=True),
        sa.Column('is_verified_purchase', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('is_featured', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('moderation_status', sa.String(20), nullable=False, server_default='approved'),
        sa.Column('helpful_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        # Indexes
        sa.Index('ix_plugin_reviews_plugin_id', 'plugin_id'),
        sa.Index('ix_plugin_reviews_user_id', 'user_id'),
        sa.Index('ix_plugin_reviews_plugin_user', 'plugin_id', 'user_id', unique=True),
        sa.Index('ix_plugin_reviews_rating', 'plugin_id', 'rating'),
    )
    
    # ===== Table 5: audit_logs =====
    op.create_table(
        'audit_logs',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'user_id',
            sa.String(26),
            sa.ForeignKey('users.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'plugin_id',
            sa.String(64),
            sa.ForeignKey('plugins.id', ondelete='SET NULL'),
            nullable=True,
        ),
        sa.Column(
            'action',
            sa.Enum(
                'plugin_install', 'plugin_uninstall', 'plugin_enable', 'plugin_disable',
                'plugin_update', 'config_change', 'permission_grant', 'permission_revoke',
                'security_violation', 'api_access',
                name='auditaction'
            ),
            nullable=False,
        ),
        sa.Column(
            'severity',
            sa.Enum('info', 'warning', 'error', 'critical', name='auditseverity'),
            nullable=False,
            server_default='info',
        ),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('context_json', sa.JSON(), nullable=True),
        sa.Column('success', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        # Indexes
        sa.Index('ix_audit_logs_plugin_id', 'plugin_id'),
        sa.Index('ix_audit_logs_user_id', 'user_id'),
        sa.Index('ix_audit_logs_action', 'action'),
        sa.Index('ix_audit_logs_severity', 'severity'),
        sa.Index('ix_audit_logs_timestamp', 'created_at'),
        sa.Index('ix_audit_logs_action_time', 'action', 'created_at'),
    )
    
    # ===== Table 6: plugin_stats =====
    op.create_table(
        'plugin_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            'plugin_id',
            sa.String(64),
            sa.ForeignKey('plugins.id', ondelete='CASCADE'),
            nullable=False,
            unique=True,
        ),
        sa.Column('total_executions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('successful_executions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_executions', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_execution_time_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('max_execution_time_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('total_execution_time_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('consecutive_failures', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_execution_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('peak_concurrent_usages', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('memory_usage_mb', sa.Float(), nullable=True),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        
        # Indexes
        sa.Index('ix_plugin_stats_plugin_id', 'plugin_id', unique=True),
    )
    
    print("✅ Plugin system tables created successfully!")


def downgrade() -> None:
    # Drop in reverse order (respect foreign keys)
    op.drop_table('plugin_stats')
    op.drop_table('audit_logs')
    op.drop_table('plugin_reviews')
    op.drop_table('plugin_configs')
    op.drop_table('plugin_versions')
    op.drop_table('plugins')
    
    # Drop enums (PostgreSQL specific)
    op.execute("DROP TYPE IF EXISTS plugincategory")
    op.execute("DROP TYPE IF EXISTS pluginstatus")
    op.execute("DROP TYPE IF EXISTS pricingmodel")
    op.execute("DROP TYPE IF EXISTS auditaction")
    op.execute("DROP TYPE IF EXISTS auditseverity")
    
    print("⏪ Plugin system tables dropped successfully!")