#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""datetime columns keep microseconds on MySQL

The initial schema created plain DATETIME columns, which drop the
fraction of a second that the Django schema's datetime(6) columns kept.
Records changed in the same second then tie when ordered by time.

Revision ID: 5b2e9c4a1f37
Revises: 40d50e265707
Create Date: 2026-11-11 16:00:00.000000

"""

from alembic import op
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = '5b2e9c4a1f37'
down_revision = '40d50e265707'
branch_labels = None
depends_on = None

COLUMNS = (
    ('allocation_request', 'submit_date'),
    ('allocation_request', 'modified_time'),
    ('usage_type', 'created_at'),
)


def _alter(type_, existing_type):
    # Other databases (SQLite in the tests) keep the fraction already.
    if op.get_context().dialect.name != 'mysql':
        return
    for table, column in COLUMNS:
        op.alter_column(
            table,
            column,
            type_=type_,
            existing_type=existing_type,
            existing_nullable=False,
        )


def upgrade():
    _alter(mysql.DATETIME(fsp=6), mysql.DATETIME())


def downgrade():
    _alter(mysql.DATETIME(), mysql.DATETIME(fsp=6))
