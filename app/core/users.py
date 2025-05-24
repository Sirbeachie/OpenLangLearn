# FastAPI-Users setup for authentication and user management
from fastapi import Depends
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, BearerTransport, JWTStrategy
from fastapi_users.db import SQLModelUserDatabase # Correct adapter for SQLModel
from sqlmodel import Session # Standard SQLModel session

from app.models.user import User, UserCreate, UserRead, UserUpdate # User models/schemas
from app.core.config import settings # For SECRET key
from app.main import get_db_session # Re-use existing DB session logic if compatible

# Define UserDatabase dependency
# FastAPI-Users expects an async session usually, but SQLModelUserDatabase
# can work with a synchronous session generator if adapted or if it handles it internally.
# Let's try with the existing get_db_session first.
async def get_user_db(session: Session = Depends(get_db_session)):
    yield SQLModelUserDatabase(session, User) # Pass User model here

# JWT Strategy
def get_jwt_strategy() -> JWTStrategy:
    return JWTStrategy(secret=settings.FASTAPI_USERS_SECRET, lifetime_seconds=3600) # 1 hour

# Authentication Backends
# Bearer transport for API calls
bearer_transport = BearerTransport(tokenUrl="/api/v1/auth/jwt/login") # Matches the router prefix

# Setup authentication backends
# Note: CookieAuth is not included as per instructions focusing on JWT for API
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)

# FastAPIUsers instance
# The generic type should be <User, User.id type>
fastapi_users_instance = FastAPIUsers[User, int](
    get_user_db,
    [auth_backend], # List of authentication methods
    UserRead,       # Schema for reading a user
    UserCreate,     # Schema for creating a user
    UserUpdate,     # Schema for updating a user
)

# Dependency to get the current active and verified user (or just active)
# current_active_user = fastapi_users_instance.current_user(active=True, verified=True)
# For this task, let's use active=True only, as email verification is not set up.
current_active_user = fastapi_users_instance.current_user(active=True)

# Routers provided by FastAPI-Users
# /auth router (login, logout, etc.)
# /register router
# /verify router (if email verification is enabled)
# /reset router (if password reset is enabled)
# /users router (get/patch current user, get/delete/patch specific user by ID for superusers)

# Auth routes (e.g., /login, /logout)
# The get_auth_router requires the backend instance.
auth_router = fastapi_users_instance.get_auth_router(auth_backend)

# Register routes (e.g., /register)
# The get_register_router requires UserRead and UserCreate schemas.
register_router = fastapi_users_instance.get_register_router(UserRead, UserCreate)

# Users routes (e.g., /users/me, /users/{id})
# The get_users_router requires UserRead and UserUpdate schemas.
users_router = fastapi_users_instance.get_users_router(UserRead, UserUpdate)

# If you need reset password functionality:
# reset_password_router = fastapi_users_instance.get_reset_password_router()

# If you need email verification functionality:
# verify_router = fastapi_users_instance.get_verify_router(UserRead)
