# Celery application setup
from celery import Celery

# It's recommended to use a configuration object for settings
# For now, we'll use a basic setup
celery_app = Celery(
    "worker",
    broker="redis://localhost:6379/0",  # Example broker, replace with your choice
    backend="redis://localhost:6379/0"  # Example backend, replace with your choice
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
