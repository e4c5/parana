"""Authentication and authorization dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from . import auth_utils, queries
from .db import get_conn
from .models import TokenData, User

# tokenUrl must match the route where we get the token
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    conn=Depends(get_conn),
) -> User:
    """FastAPI dependency to get the currently authenticated user from a JWT."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = auth_utils.decode_token(token)
    if payload is None:
        raise credentials_exception
    
    username: str | None = payload.get("sub")
    if username is None:
        raise credentials_exception
    
    token_data = TokenData(username=username)
    user_row = await queries.get_user_by_username(conn, token_data.username)
    
    if user_row is None:
        raise credentials_exception
    
    return User(**user_row)


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Dependency to ensure the authenticated user is also active."""
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user
