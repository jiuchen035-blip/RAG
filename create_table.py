# create_table.py
from db import get_conn
from sqlalchemy import text

create_sql = text("""
CREATE TABLE IF NOT EXISTS qa_history (
    id BIGSERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    model VARCHAR(32) NOT NULL,
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    cost NUMERIC(10,6) NOT NULL DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
""")
with get_conn() as conn:
    conn.execute(create_sql)
    conn.commit()
print("qa_history 表创建完成")