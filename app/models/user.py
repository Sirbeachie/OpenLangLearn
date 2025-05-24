# User model using SQLModel and FastAPI-Users
from typing import Optional
from sqlmodel import SQLModel, Field
from fastapi_users.db import SQLModelBaseUserTable # Correct base for SQLModel
from fastapi_users import schemas # For UserRead, UserCreate, UserUpdate

class User(SQLModelBaseUserTable[int], table=True):
    """
    Database model for User, compatible with SQLModel and FastAPI-Users.
    Fields like email, hashed_password, is_active, is_superuser, is_verified
    are inherited from SQLModelBaseUserTable.
    """
    id: Optional[int] = Field(default=None, primary_key=True, index=True)
    # Add any additional custom fields here, for example:
    # username: str = Field(unique=True, index=True)
    # profile_picture_url: Optional[str] = None

    # FastAPI-Users expects certain fields. SQLModelBaseUserTable provides:
    # email: str
    # hashed_password: str
    # is_active: bool
    # is_superuser: bool
    # is_verified: bool
    # You can add more fields or override them if necessary, following SQLModel syntax.


# Pydantic models (schemas) for FastAPI-Users
class UserRead(schemas.BaseUser[int]):
    """Schema for reading user data."""
    # Inherits id, email, is_active, is_superuser, is_verified
    # Add any custom fields from User model that should be readable
    # username: Optional[str] = None 
    pass

class UserCreate(schemas.BaseUserCreate):
    """Schema for creating a new user."""
    # Inherits email, password
    # Add any custom fields that are required or optional during creation
    # username: Optional[str] = None
    pass

class UserUpdate(schemas.BaseUserUpdate):
    """Schema for updating an existing user."""
    # Inherits password (optional), email (optional), is_active (optional), etc.
    # Add any custom fields that can be updated
    # username: Optional[str] = None
    pass
