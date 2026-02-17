from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_access_token, get_current_user
from ..database import get_session
from ..models.db import User
from ..models.login import LoginRequest, LoginResponse
from ..models.users import UserCreate, UserPublic, hash_password, verify_password

router = APIRouter()

@router.get("/users/", response_model=list[UserPublic])
async def read_users(session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User))
    users = result.scalars().all()
    return [
        UserPublic(username=user.username, email=user.email, full_name=user.full_name)
        for user in users
    ]


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_in: UserCreate, session: AsyncSession = Depends(get_session)):
    user = User(
        username=user_in.username,
        email=user_in.email,
        full_name=user_in.full_name,
        password_hash=hash_password(user_in.password),
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username or email already exists",
        )
    await session.refresh(user)
    return UserPublic(username=user.username, email=user.email, full_name=user.full_name)

@router.put("/users/{username}", response_model=UserPublic)
async def update_user(
    username: str, 
    user_in: UserCreate, 
    session: AsyncSession = Depends(get_session),
    current_user: str = Depends(get_current_user)
):
    # Check if the logged-in user is trying to update their own profile
    if current_user != username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own user information"
        )
    
    result = await session.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.email = user_in.email
    user.full_name = user_in.full_name
    if user_in.password:
        user.password_hash = hash_password(user_in.password)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already exists",
        )
    await session.refresh(user)
    return UserPublic(username=user.username, email=user.email, full_name=user.full_name)


@router.post("/login", response_model=LoginResponse)
async def login_user(credentials: LoginRequest, session: AsyncSession = Depends(get_session)):
    result = await session.execute(select(User).where(User.username == credentials.username))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access_token = create_access_token(subject=user.username, user_id=user.id)
    return LoginResponse(access_token=access_token, token_type="bearer")