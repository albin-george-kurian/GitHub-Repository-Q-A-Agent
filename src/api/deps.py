import re

from fastapi import Header, HTTPException

_USER_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def get_user_id(x_user_id: str | None = Header(default=None)) -> str:
    """Anonymous per-browser identity. There are no accounts yet: anyone holding an ID can read
    its chats, so this scopes data per browser but is not authentication."""
    if not x_user_id or not _USER_ID.match(x_user_id):
        raise HTTPException(status_code=400, detail="Missing or invalid X-User-Id header")
    return x_user_id
