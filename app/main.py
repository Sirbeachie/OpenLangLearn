# FastAPI main application
from fastapi import FastAPI, Depends
from sqlmodel import SQLModel, create_engine, Session
from app.api import endpoints as api_endpoints # Renamed to avoid conflict
from app.core.config import settings # Using the settings from config.py
# Ensure all models are imported for table creation
from app.models import user, media # user.py now contains FastAPI-Users compatible User model
from app.models.subtitle import SubtitleCue, Word 
from app.core import users as core_users # Import the users module for routers

# Database setup
# Using the DATABASE_URL from settings
engine = create_engine(settings.DATABASE_URL, echo=True) # echo=True for logging SQL queries

def create_db_and_tables():
    # This will create tables for all imported models that inherit from SQLModel
    # Ensure all your models (user.py, media.py, etc.) are imported somewhere
    # before this function is called if they are in separate files.
    # We have imported them above.
    SQLModel.metadata.create_all(engine)

# Dependency to get DB session
def get_db_session() -> Session:
    with Session(engine) as session:
        yield session

app = FastAPI(title=settings.APP_NAME)

# Include the API router for existing endpoints
app.include_router(api_endpoints.router, prefix="/api/v1", tags=["media"])

# Include FastAPI-Users routers
# Ensure User model is correctly defined and tables are created via on_startup
app.include_router(
    core_users.auth_router, 
    prefix="/api/v1/auth/jwt", # Standard prefix for JWT auth
    tags=["auth"]
)
app.include_router(
    core_users.register_router, 
    prefix="/api/v1/auth", # Standard prefix for registration
    tags=["auth"]
)
app.include_router(
    core_users.users_router, 
    prefix="/api/v1/users", 
    tags=["users"]
)
# If using reset password or verify routers, include them here as well.
# app.include_router(core_users.reset_password_router, prefix="/auth", tags=["auth"])
# app.include_router(core_users.verify_router, prefix="/auth", tags=["auth"])


@app.on_event("startup")
def on_startup():
    create_db_and_tables()
    # You can also override the get_db_session in endpoints.py for FastAPI's dependency injection
    # This makes the actual session available to the endpoints
    api_endpoints.get_db_session = get_db_session


@app.get("/")
async def root():
    return {"message": f"Welcome to {settings.APP_NAME}"}

# If you want to test the endpoint directly via main for some reason (not typical for FastAPI)
# if __name__ == "__main__":
#     import uvicorn
#     # This will run the app using Uvicorn when the script is executed directly.
#     # Ensure that create_db_and_tables() is called, e.g., via on_startup event.
#     uvicorn.run(app, host="0.0.0.0", port=8000)
