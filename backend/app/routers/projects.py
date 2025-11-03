from typing import List
from fastapi import APIRouter, Depends, HTTPException, status 
from ..schemas.projects import ProjectCreate, TaskCreate, TaskUpdateStatus
from ..core.security import require_roles, get_current_user
from ..db.pool import fetch_one, fetch_all, execute
import textwrap
from typing import Optional
import traceback
from datetime import datetime

router = APIRouter(prefix="/projects", tags=["projects"])

from pydantic import BaseModel
class OrderCreate(BaseModel):
    customer_id: int
    category: str | None = None
    project_commit: str | None = None
    start_on: str | None = None
    completion_date: str | None = None
    completed_on: str | None = None
    status: str | None = None
    amount: float | None = None
    description: str | None = None
    


@router.get("/orders", response_model=List[dict])
async def get_orders(
    current_user=Depends(require_roles(["project"]))
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
        ORDER BY o.created_on DESC
    """)

    try:
        results = await fetch_all(query)
        print(f"Fetched {len(results)} orders")
        return results
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch orders: {str(e)}")


@router.get("/orders/{order_id}", response_model=dict)
async def get_order(
    order_id: int,
    current_user=Depends(require_roles(["project"]))
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
    

class OrderUpdate(BaseModel):
    customer_id: int | None = None
    category: str | None = None
    project_commit: str | None = None
    start_on: str | None = None
    completion_date: str | None = None
    completed_on: str | None = None
    status: str | None = None
    amount: float | None = None
    description: str | None = None
    generated_order_id: str | None = None

def clean_value(value):
    if value in (None, ""):
        return None
    return value

@router.put("/orders/{order_id}", response_model=dict)
async def update_order(
    order_id: int,
    payload: "OrderUpdate",  # replace with your Pydantic model
    current_user=Depends(require_roles(["project"]))
):
    # Debug prints
    print(f"Current user full dict: {current_user}")

    role = current_user.get('role') or \
           (current_user.get('roles')[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown'))
    print(f"Current user role: {role}")

    updated_by = current_user.get('id')

    # Build dynamic SET clause
    set_clauses = []
    params = []

    if payload.customer_id is not None:
        set_clauses.append("customer_id = %s")
        params.append(clean_value(payload.customer_id))
    
    if payload.category is not None:
        set_clauses.append("category = %s")
        params.append(clean_value(payload.category))
    
    if payload.project_commit is not None:
        set_clauses.append("project_committed_on = %s")
        params.append(clean_value(payload.project_commit))
    
    if payload.start_on is not None:
        set_clauses.append("start_on = %s")
        params.append(clean_value(payload.start_on))
    
    if payload.completion_date is not None:
        set_clauses.append("completion_date = %s")
        params.append(clean_value(payload.completion_date))
    
    if payload.completed_on is not None:
        set_clauses.append("completed_on = %s")
        params.append(clean_value(payload.completed_on))
    
    if payload.status is not None:
        set_clauses.append("status = %s")
        params.append(clean_value(payload.status))
    
    if payload.amount is not None:
        set_clauses.append("amount = %s")
        params.append(clean_value(payload.amount))
    
    if payload.description is not None:
        set_clauses.append("description = %s")
        params.append(clean_value(payload.description))
        
    if payload.generated_order_id is not None:
        set_clauses.append("generated_order_id = %s")
        params.append(clean_value(payload.generated_order_id))

    # Always update updated_by and updated_on
    set_clauses.append("updated_by = %s")
    params.append(updated_by)
    set_clauses.append("updated_on = (NOW() AT TIME ZONE 'UTC')::timestamptz")

    if not set_clauses:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    set_clause = ", ".join(set_clauses)

    query = textwrap.dedent(f"""
        UPDATE orders
        SET {set_clause}
        WHERE id = %s
        RETURNING *
    """)
    params.append(order_id)

    try:
        result = await execute(query, params)

        # If result is an int (rows affected)
        if isinstance(result, int):
            if result == 0:
                raise HTTPException(status_code=404, detail="Order not found")
            return {"message": "Order updated", "rows_affected": result}

        # If result is a dict, return the updated row
        if isinstance(result, dict):
            print(f"Updated order {order_id} for customer {payload.customer_id if payload.customer_id else 'unchanged'}")
            return result

        raise HTTPException(status_code=500, detail="Unexpected response from database")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update order: {str(e)}")

@router.delete("/orders/{order_id}", response_model=dict)
async def delete_order(
    order_id: int,
    current_user=Depends(require_roles(["project_manager"]))
):
    # Debug print
    print(f"Current user full dict: {current_user}")

    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")

    query = textwrap.dedent("""
        DELETE FROM orders 
        WHERE id = %s
    """)

    try:
        result = await execute(query, (order_id,))
    
        # Assuming execute returns rows affected as int
        if isinstance(result, int):
            if result == 0:
                raise HTTPException(status_code=404, detail="Order not found")
            print(f"Deleted order {order_id}")
            return {"message": "Order deleted", "rows_affected": result}
    
        raise HTTPException(status_code=500, detail="Unexpected response from database")
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete order: {str(e)}")
    
@router.get("/staffs/active", response_model=dict)
async def get_active_staffs(
    current_user=Depends(require_roles(["project"]))
):
    print(f"Current user full dict: {current_user}")

    role = current_user.get('role') or \
           (current_user.get('roles')[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown'))
    print(f"Current user role: {role}")

    query = textwrap.dedent("""
        SELECT id, staff_name, role, address, status
        FROM staff_users
        WHERE status = 'active'
        ORDER BY id ASC
    """)

    try:
        # ✅ CHANGE THIS
        result = await fetch_all(query)

        if not result:
            return {"message": "No active staff found", "staffs": []}

        staffs = [
            {
                "id": row.get("id"),
                "name": row.get("staff_name"),
                "role": row.get("role")
            }
            for row in result
        ]

        return {"message": "Active staffs retrieved successfully", "staffs": staffs}

    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve active staffs: {str(e)}")


class AssignTask(BaseModel):
    order_id: int
    staff_id: int
    description: Optional[str] = None
    completion_date: Optional[str] = None  # Optional estimated completion time

def clean_value(value):
    if value in (None, ""):
        return None
    return value

@router.post("/tasks/assign", response_model=dict)
async def assign_task(
    payload: AssignTask,
    current_user=Depends(require_roles(["project"]))
):
    # Debug prints
    print(f"Current user full dict: {current_user}")
    print("Incoming payload:", payload.dict())

    role = current_user.get('role') or \
           (current_user.get('roles')[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown'))
    print(f"Current user role: {role}")

    assigned_by = current_user.get('id')

    # Prepare insert parameters
    params = [
    assigned_by,  # assigned_by
    payload.staff_id,  # assigned_to
    clean_value(payload.completion_date),  # completion_time
    payload.order_id,  # order_id
    clean_value(payload.description),  # description
    "assigned"  # status
    ]
    print(params)
    query = textwrap.dedent("""
    INSERT INTO public.tasks 
    (assigned_by, assigned_to, assigned_on, completion_time, order_id, task_description, status)
    VALUES (%s, %s, NOW() AT TIME ZONE 'UTC', %s, %s, %s, %s)
    RETURNING *
    """)

    try:
        result = await execute(query, params)
        print("DB Query Result:", result, "Type:", type(result))

        if isinstance(result, int) and result == 1:
           return {"message": "Task assigned successfully"}

        raise HTTPException(status_code=500, detail="Unexpected response from database")

    except HTTPException:
        raise
    except Exception as e:
        print("Exception occurred:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to assign task: {str(e)}")
    

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
    
    assigned_by: Optional[StaffInfo]
    assigned_to: Optional[StaffInfo]
    updated_by: Optional[StaffInfo]
    
@router.get("/tasks", response_model=List[Task])
async def get_all_tasks(current_user=Depends(require_roles(["project"]))):
    query = """
        SELECT 
    t.id,
    t.order_id,
    t.task_description,
    t.status,
    t.assigned_on,
    t.completion_time,
    
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

ORDER BY t.assigned_on DESC;
    """
    
    try:
        rows = await fetch_all(query, [])
        
        # Transform raw rows into nested structure
        tasks = []
        for row in rows:
            tasks.append({
                "id": row["id"],
                "order_id": row["order_id"],
                "task_description": row["task_description"],
                "status": row["status"],
                "assigned_on": row["assigned_on"],
                "completion_time": row["completion_time"],
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
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {str(e)}")

@router.patch("/tasks/{task_id}", response_model=dict)
async def edit_task(
    task_id: int,
    payload: EditTask,
    current_user=Depends(require_roles(["project"]))
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

    # ✅ Handle completion_time safely
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
    if payload.status is not None:
        update_fields.append("status = %s")
        params.append(payload.status)

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    # ✅ Add updated_by and WHERE clause
    set_clause = ", ".join(update_fields)
    query = textwrap.dedent(f"""
        UPDATE public.tasks
        SET {set_clause}, updated_on = NOW() AT TIME ZONE 'UTC', updated_by = %s
        WHERE id = %s
        RETURNING *
    """)

    params.append(updated_by)  # updated_by param
    params.append(task_id)     # task_id for WHERE

    print("Final SQL:", query)
    print("Params:", params)

    try:
        result = await execute(query, params)
        print("DB Query Result for edit_task:", result, "Type:", type(result))

        if not result:
            raise HTTPException(status_code=404, detail="Task not found")

        if isinstance(result, list):
            return {"message": "Task updated successfully", "task": result[0]}

        return {"message": "Task updated successfully", "task": result}

    except HTTPException:
        raise
    except Exception as e:
        print("Exception occurred in edit_task:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update task: {str(e)}")
    
    

@router.get("/tasks/{order_id}", response_model=List[Task])
async def get_tasks_by_order(
    order_id: int,  # order_id will come from the path
    current_user=Depends(require_roles(["project"]))
):
    query = """
        SELECT 
            t.id,
            t.order_id,
            t.task_description,
            t.status,
            t.assigned_on,
            t.completion_time,

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

        WHERE t.order_id = %s
        ORDER BY t.assigned_on DESC;
    """

    try:
        rows = await fetch_all(query, (order_id,))
        
        tasks = []
        for row in rows:
            tasks.append({
                "id": row["id"],
                "order_id": row["order_id"],
                "task_description": row["task_description"],
                "status": row["status"],
                "assigned_on": row["assigned_on"],
                "completion_time": row["completion_time"],
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
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch tasks: {str(e)}")
    

# -----------------------------------------------------------
# Get All Images for an Order
# -----------------------------------------------------------

@router.get("/orders/images/{order_id}", response_model=List[dict])
async def get_order_images(
    order_id: int,
    current_user=Depends(require_roles(["project"]))
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