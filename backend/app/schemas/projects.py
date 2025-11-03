from typing import Optional, Literal
from pydantic import BaseModel

TaskType = Literal["design", "printing", "logistics"]
TaskStatus = Literal["pending", "in_progress", "completed"]

class ProjectCreate(BaseModel):
    order_id: int
    manager_id: Optional[int] = None  # defaults to current PM

class TaskCreate(BaseModel):
    project_id: int
    type: TaskType
    assignee_id: Optional[int] = None
    payload: Optional[dict] = None

class TaskUpdateStatus(BaseModel):
    status: TaskStatus
