from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class ProjectCreate(BaseModel):
    title: str
    student_name: str

@app.post("/projects/submit")
async def submit_project(project: ProjectCreate):
    notification_payload = {
        "event": "new_project_submission",
        "message": f"New project '{project.title}' posted by {project.student_name}!",
        "student": project.student_name,
        "project_title": project.title
    }
    await manager.broadcast_to_role(role="faculty", message=notification_payload)
    return {"status": "success", "message": "Project submitted and faculty notified."}
