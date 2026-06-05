"""FastAPI application for web interface."""
from mockworkflow.web.app import app


def create_app():
    """Create and return the FastAPI app."""
    return app
