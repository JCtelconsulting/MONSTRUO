from fastapi import FastAPI
from starlette.staticfiles import StaticFiles
from starlette.responses import HTMLResponse
from app.api.routers import calendar, task_manager, justificaciones

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="MONSTRUO/static"), name="static")

# Include API routers
app.include_router(calendar.router, prefix="/api/calendar", tags=["Calendar"])
app.include_router(task_manager.router, prefix="/api/tasks", tags=["Task Manager"])
app.include_router(justificaciones.router, prefix="/api/justificaciones", tags=["Justificaciones"])

@app.get("/", tags=["Root"])
async def read_root():
    return HTMLResponse(content="<h1>Welcome to Monstruo ERP API. Access /static/modulos/calendar/calendar.html, /static/modulos/task-manager/task-manager.html, or /static/modulos/justificaciones/justificaciones.html for modules.</h1>", status_code=200)
