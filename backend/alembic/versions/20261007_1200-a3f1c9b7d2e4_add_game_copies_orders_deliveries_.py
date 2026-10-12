"""add game_copies, orders, order_items, deliveries, damage_reports

Revision ID: a3f1c9b7d2e4
Revises: cce67ede9b9a
Create Date: 2026-10-07 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f1c9b7d2e4'
down_revision: Union[str, Sequence[str], None] = 'cce67ede9b9a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('game_copies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('game_id', sa.Integer(), nullable=False),
    sa.Column('current_point_id', sa.Integer(), nullable=True),
    sa.Column('inventory_number', sa.String(length=50), nullable=False),
    sa.Column('status', sa.String(length=30), server_default=sa.text("'AVAILABLE'"), nullable=False),
    sa.CheckConstraint("(status IN ('WITH_CLIENT','IN_TRANSIT') AND current_point_id IS NULL) OR (status IN ('AVAILABLE','DAMAGED') AND current_point_id IS NOT NULL)", name=op.f('ck_game_copies_location_matches_status')),
    sa.CheckConstraint("status IN ('AVAILABLE','WITH_CLIENT','IN_TRANSIT','DAMAGED')", name=op.f('ck_game_copies_status')),
    sa.ForeignKeyConstraint(['current_point_id'], ['pickup_points.id'], name=op.f('fk_game_copies_current_point_id_pickup_points'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['game_id'], ['board_games.id'], name=op.f('fk_game_copies_game_id_board_games'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_game_copies')),
    sa.UniqueConstraint('inventory_number', name=op.f('uq_game_copies_inventory_number'))
    )
    op.create_index(op.f('ix_game_copies_current_point_id'), 'game_copies', ['current_point_id'], unique=False)
    op.create_index(op.f('ix_game_copies_game_id'), 'game_copies', ['game_id'], unique=False)
    op.create_table('orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('client_id', sa.Integer(), nullable=False),
    sa.Column('pickup_point_id', sa.Integer(), nullable=False),
    sa.Column('start_date', sa.Date(), nullable=False),
    sa.Column('end_date', sa.Date(), nullable=False),
    sa.Column('total_price', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('deposit_paid', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.Column('status', sa.String(length=30), server_default=sa.text("'CREATED'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('deposit_paid >= 0', name=op.f('ck_orders_deposit_paid')),
    sa.CheckConstraint('end_date >= start_date', name=op.f('ck_orders_end_date')),
    sa.CheckConstraint("status IN ('CREATED','NEEDS_TRANSFER','IN_TRANSIT','READY_FOR_PICKUP','ACTIVE','COMPLETED','CANCELLED')", name=op.f('ck_orders_status')),
    sa.CheckConstraint('total_price >= 0', name=op.f('ck_orders_total_price')),
    sa.ForeignKeyConstraint(['client_id'], ['clients.id'], name=op.f('fk_orders_client_id_clients'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['pickup_point_id'], ['pickup_points.id'], name=op.f('fk_orders_pickup_point_id_pickup_points'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_orders'))
    )
    op.create_index(op.f('ix_orders_client_id'), 'orders', ['client_id'], unique=False)
    op.create_index(op.f('ix_orders_pickup_point_id'), 'orders', ['pickup_point_id'], unique=False)
    op.create_table('order_items',
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('game_copy_id', sa.Integer(), nullable=False),
    sa.Column('price_at_rental', sa.Numeric(precision=10, scale=2), nullable=False),
    sa.CheckConstraint('price_at_rental >= 0', name=op.f('ck_order_items_price_at_rental')),
    sa.ForeignKeyConstraint(['game_copy_id'], ['game_copies.id'], name=op.f('fk_order_items_game_copy_id_game_copies'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_items_order_id_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('order_id', 'game_copy_id', name=op.f('pk_order_items'))
    )
    op.create_index(op.f('ix_order_items_game_copy_id'), 'order_items', ['game_copy_id'], unique=False)
    op.create_table('deliveries',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('courier_id', sa.Integer(), nullable=True),
    sa.Column('from_point_id', sa.Integer(), nullable=False),
    sa.Column('to_point_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=30), server_default=sa.text("'CREATED'"), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('CREATED','ACCEPTED','IN_TRANSIT','DELIVERED')", name=op.f('ck_deliveries_status')),
    sa.CheckConstraint('to_point_id <> from_point_id', name=op.f('ck_deliveries_distinct_points')),
    sa.ForeignKeyConstraint(['courier_id'], ['employees.id'], name=op.f('fk_deliveries_courier_id_employees'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['from_point_id'], ['pickup_points.id'], name=op.f('fk_deliveries_from_point_id_pickup_points'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_deliveries_order_id_orders'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['to_point_id'], ['pickup_points.id'], name=op.f('fk_deliveries_to_point_id_pickup_points'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_deliveries')),
    sa.UniqueConstraint('order_id', name=op.f('uq_deliveries_order_id'))
    )
    op.create_index(op.f('ix_deliveries_courier_id'), 'deliveries', ['courier_id'], unique=False)
    op.create_table('damage_reports',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('game_copy_id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=True),
    sa.Column('reported_by', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('deposit_withheld', sa.Numeric(precision=10, scale=2), server_default=sa.text('0'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('deposit_withheld >= 0', name=op.f('ck_damage_reports_deposit_withheld')),
    sa.ForeignKeyConstraint(['game_copy_id'], ['game_copies.id'], name=op.f('fk_damage_reports_game_copy_id_game_copies'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_damage_reports_order_id_orders'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reported_by'], ['employees.id'], name=op.f('fk_damage_reports_reported_by_employees'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_damage_reports'))
    )
    op.create_index(op.f('ix_damage_reports_game_copy_id'), 'damage_reports', ['game_copy_id'], unique=False)
    op.create_index(op.f('ix_damage_reports_order_id'), 'damage_reports', ['order_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_damage_reports_order_id'), table_name='damage_reports')
    op.drop_index(op.f('ix_damage_reports_game_copy_id'), table_name='damage_reports')
    op.drop_table('damage_reports')
    op.drop_index(op.f('ix_deliveries_courier_id'), table_name='deliveries')
    op.drop_table('deliveries')
    op.drop_index(op.f('ix_order_items_game_copy_id'), table_name='order_items')
    op.drop_table('order_items')
    op.drop_index(op.f('ix_orders_pickup_point_id'), table_name='orders')
    op.drop_index(op.f('ix_orders_client_id'), table_name='orders')
    op.drop_table('orders')
    op.drop_index(op.f('ix_game_copies_game_id'), table_name='game_copies')
    op.drop_index(op.f('ix_game_copies_current_point_id'), table_name='game_copies')
    op.drop_table('game_copies')
