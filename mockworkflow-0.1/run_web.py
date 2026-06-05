
"""Run the Mockworkflow web server."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "mockworkflow.api.app:create_app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        factory=True,
        reload_dirs=["mockworkflow"],
        workers=1,
    )

