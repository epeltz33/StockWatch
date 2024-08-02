"""Add cascade delete for user data

Revision ID: f328e9b4f413
Revises: dce9ad99638a
Create Date: 2024-08-02 18:03:32.781112

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'f328e9b4f413'
down_revision = 'dce9ad99638a'
branch_labels = None
depends_on = None


def upgrade():
    # Clean up any existing temporary tables
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_watchlist")
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_user")
    op.execute("DROP TABLE IF EXISTS user_new")
    op.execute("DROP TABLE IF EXISTS watchlist_new")

    # Delete watchlists without a user_id or name
    op.execute(
        "DELETE FROM watchlist WHERE user_id IS NULL OR name IS NULL OR name = ''")

    # Modify watchlist table
    op.execute("PRAGMA foreign_keys=off")

    # Add NOT NULL constraint to name and user_id
    op.execute("ALTER TABLE watchlist RENAME TO watchlist_old")
    op.execute("""
        CREATE TABLE watchlist (
            id INTEGER NOT NULL,
            name VARCHAR(64) NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE
        )
    """)
    op.execute("INSERT INTO watchlist SELECT * FROM watchlist_old")
    op.execute("DROP TABLE watchlist_old")

    # Modify watchlist_stocks table
    op.execute("ALTER TABLE watchlist_stocks RENAME TO watchlist_stocks_old")
    op.execute("""
        CREATE TABLE watchlist_stocks (
            watchlist_id INTEGER NOT NULL,
            stock_id INTEGER NOT NULL,
            PRIMARY KEY (watchlist_id, stock_id),
            FOREIGN KEY(watchlist_id) REFERENCES watchlist (id) ON DELETE CASCADE,
            FOREIGN KEY(stock_id) REFERENCES stock (id) ON DELETE CASCADE
        )
    """)
    op.execute("INSERT INTO watchlist_stocks SELECT * FROM watchlist_stocks_old")
    op.execute("DROP TABLE watchlist_stocks_old")

    op.execute("PRAGMA foreign_keys=on")


def downgrade():
    op.execute("PRAGMA foreign_keys=off")

    # Revert watchlist table changes
    op.execute("ALTER TABLE watchlist RENAME TO watchlist_old")
    op.execute("""
        CREATE TABLE watchlist (
            id INTEGER NOT NULL,
            name VARCHAR(64),
            user_id INTEGER,
            PRIMARY KEY (id),
            FOREIGN KEY(user_id) REFERENCES user (id)
        )
    """)
    op.execute("INSERT INTO watchlist SELECT * FROM watchlist_old")
    op.execute("DROP TABLE watchlist_old")

    # Revert watchlist_stocks table changes
    op.execute("ALTER TABLE watchlist_stocks RENAME TO watchlist_stocks_old")
    op.execute("""
        CREATE TABLE watchlist_stocks (
            watchlist_id INTEGER NOT NULL,
            stock_id INTEGER NOT NULL,
            PRIMARY KEY (watchlist_id, stock_id),
            FOREIGN KEY(watchlist_id) REFERENCES watchlist (id),
            FOREIGN KEY(stock_id) REFERENCES stock (id)
        )
    """)
    op.execute("INSERT INTO watchlist_stocks SELECT * FROM watchlist_stocks_old")
    op.execute("DROP TABLE watchlist_stocks_old")

    op.execute("PRAGMA foreign_keys=on")
