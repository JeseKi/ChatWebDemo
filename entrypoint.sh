#!/bin/sh
set -e

DB_PATH="$(python - <<'PY'
from pathlib import Path

from src.server.config import global_config

path = Path(global_config.database_path)
if not path.is_absolute():
    path = Path.cwd() / path
print(path)
PY
)"
BACKUP_PATH="${DB_PATH}.bak"

backup_database() {
    if [ ! -f "$DB_PATH" ]; then
        echo "未找到现有数据库，跳过备份"
        return 0
    fi

    echo "开始备份数据库..."
    rm -f "${BACKUP_PATH}.3"

    if [ -f "${BACKUP_PATH}.2" ]; then
        mv "${BACKUP_PATH}.2" "${BACKUP_PATH}.3"
    fi

    if [ -f "${BACKUP_PATH}.1" ]; then
        mv "${BACKUP_PATH}.1" "${BACKUP_PATH}.2"
    fi

    if [ -f "$BACKUP_PATH" ]; then
        mv "$BACKUP_PATH" "${BACKUP_PATH}.1"
    fi

    cp "$DB_PATH" "$BACKUP_PATH"
    echo "数据库备份完成: ${BACKUP_PATH}"
}

# 确保数据库目录存在（volume 挂载时可能为空）
mkdir -p "$(dirname "$DB_PATH")"

backup_database

# 运行数据库迁移。空库也必须执行，以便写入 alembic_version。
echo "正在运行数据库迁移..."
alembic upgrade head
echo "数据库迁移完成"

# 启动应用
exec python run.py
