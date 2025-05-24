# Celery application setup
from celery import Celery
from app.core.config import settings # Import centralized settings

# Initialize Celery app with settings from the config module
celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Optional: Autodiscover tasks from a 'tasks.py' file in installed apps (if using Django structure)
# Or explicitly include task modules:
celery_app.conf.update(
    imports=('workers.tasks',)
)
# If your tasks are in workers.tasks, ensure it's discoverable.
# For a simple structure like this, you might need to explicitly import or define tasks here
# or ensure the module containing tasks is imported when the worker starts.

if __name__ == "__main__":
    celery_app.start()
