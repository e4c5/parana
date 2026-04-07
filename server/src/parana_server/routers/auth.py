"""Authentication routes for user registration and login."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from .. import auth_utils, queries
from ..db import get_conn
from ..models import Token, User, UserCreate

router = APIRouter()


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register(user_in: UserCreate, conn=Depends(get_conn)):
    """Register a new user."""
    existing_user = await queries.get_user_by_username(conn, user_in.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    hashed_password = auth_utils.get_password_hash(user_in.password)
    user_row = await queries.create_user(conn, user_in.username, hashed_password)
    return User(**user_row)


@router.post("/token", response_model=Token)
async def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(),
    conn=Depends(get_conn),
):
    """OAuth2 compatible token login, get an access token for future requests."""
    user_row = await queries.get_user_by_username(conn, form_data.username)
    if not user_row or not auth_utils.verify_password(form_data.password, user_row["hashed_password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = auth_utils.create_access_token(data={"sub": user_row["username"]})
    return Token(access_token=access_token, token_type="bearer")
