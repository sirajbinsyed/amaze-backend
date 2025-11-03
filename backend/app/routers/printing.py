from typing import List
from fastapi import APIRouter, Depends, HTTPException, status 
from ..schemas.projects import ProjectCreate, TaskCreate, TaskUpdateStatus
from ..core.security import require_roles, get_current_user
from ..db.pool import fetch_one, fetch_all, execute
import textwrap
from typing import Optional
import traceback
from datetime import datetime

router = APIRouter(prefix="/printing", tags=["printing"])

from pydantic import BaseModel


# For editing, a model with optional fields
class EditTask(BaseModel):
    completion_time: Optional[str] = None  # Or datetime if parsed
    task_description: Optional[str] = None
    status: Optional[str] = None

class StaffInfo(BaseModel):
    id: Optional[int]
    staff_name: Optional[str]
    role: Optional[str]

class Task(BaseModel):
    id: int
    order_id: Optional[int]
    task_description: Optional[str]
    status: Optional[str]
    assigned_on: Optional[datetime]
    completion_time: Optional[datetime]
    order_completion_date: Optional[datetime]
    completed_on: Optional[datetime]  # 👈 new column added here
    assigned_by: Optional[StaffInfo]
    assigned_to: Optional[StaffInfo]
    updated_by: Optional[StaffInfo]
    
@router.get("/tasks", response_model=List[Task])
async def get_my_tasks(current_user=Depends(require_roles(["printing"]))):
    query = """
        SELECT 
            t.id,
            t.order_id,
            t.task_description,
            t.status,
            t.assigned_on,
            t.completion_time,
            t.completed_on,  -- 👈 new column added

            -- Order details
            o.completion_date AS order_completion_date,
            
            -- Assigned By details via staff_credentials → staff_users
            ab_staff.id AS assigned_by_id,
            ab_staff.staff_name AS assigned_by_name,
            ab_staff.role AS assigned_by_role,
            
            -- Assigned To details directly from staff_users
            at.id AS assigned_to_id,
            at.staff_name AS assigned_to_name,
            at.role AS assigned_to_role,
            
            -- Updated By details via staff_credentials → staff_users
            ub_staff.id AS updated_by_id,
            ub_staff.staff_name AS updated_by_name,
            ub_staff.role AS updated_by_role

        FROM public.tasks t

        -- Join assigned_by via staff_credentials → staff_users
        LEFT JOIN public.staff_credentials ab_cred ON t.assigned_by = ab_cred.id
        LEFT JOIN public.staff_users ab_staff ON ab_cred.staff_id = ab_staff.id

        -- Assigned To join
        LEFT JOIN public.staff_users at ON t.assigned_to = at.id

        -- Join updated_by via staff_credentials → staff_users
        LEFT JOIN public.staff_credentials ub_cred ON t.updated_by = ub_cred.id
        LEFT JOIN public.staff_users ub_staff ON ub_cred.staff_id = ub_staff.id

        -- Join orders to get order completion_date
        LEFT JOIN public.orders o ON t.order_id = o.id

        WHERE t.assigned_to = (
            SELECT staff_id FROM public.staff_credentials
            WHERE id = %s
            LIMIT 1
        )

        ORDER BY t.assigned_on DESC;
    """
    
    try:
        rows = await fetch_all(query, [current_user.get("id")])
        
        tasks = []
        for row in rows:
            tasks.append({
                "id": row["id"],
                "order_id": row["order_id"],
                "task_description": row["task_description"],
                "status": row["status"],
                "assigned_on": row["assigned_on"],
                "completion_time": row["completion_time"],
                "completed_on": row["completed_on"],  # 👈 included here
                "order_completion_date": row["order_completion_date"],
                "assigned_by": {
                    "id": row["assigned_by_id"],
                    "staff_name": row["assigned_by_name"],
                    "role": row["assigned_by_role"]
                },
                "assigned_to": {
                    "id": row["assigned_to_id"],
                    "staff_name": row["assigned_to_name"],
                    "role": row["assigned_to_role"]
                },
                "updated_by": {
                    "id": row["updated_by_id"],
                    "staff_name": row["updated_by_name"],
                    "role": row["updated_by_role"]
                }
            })
        
        return tasks

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {str(e)}")

@router.patch("/tasks/{task_id}", response_model=dict)
async def edit_task(
    task_id: int,
    payload: EditTask,
    current_user=Depends(require_roles(["printing"]))
):
    print(f"Current user full dict: {current_user}")
    print("Task ID:", task_id)
    print("Incoming payload:", payload.dict())

    role = current_user.get("role") or (
        current_user.get("roles")[0]
        if isinstance(current_user.get("roles"), list)
        else current_user.get("roles", "unknown")
    )
    print(f"Current user role: {role}")

    updated_by = current_user.get("id")

    update_fields = []
    params = []

    # ✅ Handle completion_time
    if payload.completion_time is not None:
        try:
            if isinstance(payload.completion_time, str):
                dt = datetime.fromisoformat(payload.completion_time)
            else:
                dt = payload.completion_time
            update_fields.append("completion_time = %s")
            params.append(dt)
        except Exception as e:
            print("Invalid completion_time format:", e)
            raise HTTPException(status_code=400, detail="Invalid datetime format for completion_time")

    # ✅ Handle task_description
    if payload.task_description is not None:
        update_fields.append("task_description = %s")
        params.append(payload.task_description)

    # ✅ Handle status
    completed_on_should_update = False
    if payload.status is not None:
        update_fields.append("status = %s")
        params.append(payload.status)

        # 👇 If status is completed, mark completed_on timestamp
        if payload.status.lower() == "completed":
            completed_on_should_update = True

    # ✅ Handle completed_on (auto when status = completed)
    if completed_on_should_update:
        update_fields.append("completed_on = NOW() AT TIME ZONE 'UTC'")

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    # ✅ Always update updated_on and updated_by
    set_clause = ", ".join(update_fields)
    query = textwrap.dedent(f"""
        UPDATE public.tasks
        SET {set_clause}, updated_on = NOW() AT TIME ZONE 'UTC', updated_by = %s
        WHERE id = %s
        RETURNING *
    """)

    params.append(updated_by)  # updated_by param
    params.append(task_id)     # task_id for WHERE clause

    print("Final SQL:", query)
    print("Params:", params)

    try:
        result = await execute(query, params)
        print("DB Query Result for edit_task:", result, "Type:", type(result))

        if not result:
            raise HTTPException(status_code=404, detail="Task not found")

        # Return success response
        if isinstance(result, list):
            return {"message": "Task updated successfully", "task": result[0]}

        return {"message": "Task updated successfully", "task": result}

    except HTTPException:
        raise
    except Exception as e:
        print("Exception occurred in edit_task:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update task: {str(e)}")
    
    
# get order details by order id
@router.get("/orders/{order_id}", response_model=dict)
async def get_order(
    order_id: int,
    current_user=Depends(require_roles(["printing"]))
):
    print(f"Current user full dict: {current_user}")

    role = (
        current_user.get('role') or
        (current_user.get('roles', ['unknown'])[0]
         if isinstance(current_user.get('roles'), list)
         else current_user.get('roles', 'unknown'))
    )
    print(f"Current user role: {role}")

    query = textwrap.dedent("""
        SELECT 
            o.*,
            s.staff_name AS created_by_staff_name,
            c.customer_name,
            c.mobile_number,
            c.whatsapp_number,
            c.address
        FROM orders o
        LEFT JOIN staff_credentials u ON o.created_by = u.id
        LEFT JOIN staff_users s ON u.staff_id = s.id
        LEFT JOIN customers c ON o.customer_id = c.id
        WHERE o.id = %s
    """)

    try:
        result = await fetch_one(query, (order_id,))
        if not result:
            raise HTTPException(status_code=404, detail="Order not found")
        print(f"Fetched order {order_id} created by staff: {result.get('created_by_staff_name')}")
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch order: {str(e)}")
    


# -----------------------------------------------------------
# Get All Images for an Order
# -----------------------------------------------------------

@router.get("/orders/images/{order_id}", response_model=List[dict])
async def get_order_images(
    order_id: int,
    current_user=Depends(require_roles(["printing"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    query = textwrap.dedent("""
        SELECT 
            id, order_id, image_url, status, created_at, description, uploaded_by
        FROM order_images 
        WHERE order_id = %s AND status = 'active'
        ORDER BY created_at DESC
    """)
    
    try:
        results = await fetch_all(query, (order_id,))
        print(f"Fetched {len(results)} images for order {order_id}")
        return results
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch order images: {str(e)}")