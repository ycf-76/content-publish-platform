"""add_profile_six_dimensions

Revision ID: e4e5d130d25f
Revises: 012
Create Date: 2026-09-19 22:54:49.807526

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e4e5d130d25f'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('user_profiles', sa.Column('identity', sa.String(length=200), nullable=True))
    op.add_column('user_profiles', sa.Column('differentiation', sa.String(length=200), nullable=True))
    op.add_column('user_profiles', sa.Column('content_direction', sa.String(length=200), nullable=True))
    op.add_column('user_profiles', sa.Column('target_audience', sa.String(length=200), nullable=True))
    op.add_column('user_profiles', sa.Column('audience_pain_points', sa.String(length=200), nullable=True))
    op.add_column('user_profiles', sa.Column('opening_style', sa.String(length=100), nullable=True))
    op.add_column('user_profiles', sa.Column('content_rhythm', sa.String(length=100), nullable=True))
    op.add_column('user_profiles', sa.Column('signature_elements', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('user_profiles', 'signature_elements')
    op.drop_column('user_profiles', 'content_rhythm')
    op.drop_column('user_profiles', 'opening_style')
    op.drop_column('user_profiles', 'audience_pain_points')
    op.drop_column('user_profiles', 'target_audience')
    op.drop_column('user_profiles', 'content_direction')
    op.drop_column('user_profiles', 'differentiation')
    op.drop_column('user_profiles', 'identity')