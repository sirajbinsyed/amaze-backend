from fastapi import APIRouter, HTTPException, Depends, status, Body
from datetime import datetime
from pydantic import EmailStr, BaseModel, ConfigDict
from typing import List, Dict, Any, Optional
import textwrap
import traceback
from datetime import date, datetime

from ..schemas.auth import TokenResponse, UserPublic
from ..core.security import (
    hash_password,
    verify_password,
    create_access_token,
    require_roles,
    get_current_user
)
from ..db.pool import fetch_one, execute, fetch_all

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/dashboard", response_model=Dict[str, Any])
async def get_dashboard_stats(current_user: dict = Depends(require_roles(["admin"]))):
    """
    Admin-only dashboard endpoint: Returns summary statistics for the ERP system.
    """
    # Total staff count
    total_staff = await fetch_one("SELECT COUNT(1) AS count FROM staff_credentials", None)
    
    # Active staff count
    active_staff = await fetch_one(
        "SELECT COUNT(1) AS count FROM staff_credentials WHERE status = 'active'", 
        None
    )
    
    # Staff by role
    roles_count = await fetch_all(
        """
        SELECT role, COUNT(1) AS count 
        FROM staff_credentials 
        GROUP BY role
        """,
        None
    )
    roles_dict = {row["role"]: row["count"] for row in roles_count}
    
    # Recent signups (last 7 days)
    recent_signups = await fetch_one(
        """
        SELECT COUNT(1) AS count 
        FROM staff_credentials 
        WHERE created_at >= NOW() - INTERVAL '7 days'
        """,
        None
    )
    
    # Recent logins (if you have a logs table; placeholder for now)
    # Assuming no login logs yet; set to 0 or implement if logs exist
    recent_logins = 0  # TODO: Query from audit_logs if available
    
    return {
        "total_staff": total_staff["count"],
        "active_staff": active_staff["count"],
        "inactive_staff": total_staff["count"] - active_staff["count"],
        "staff_by_role": roles_dict,
        "recent_signups_7d": recent_signups["count"],
        "recent_logins_7d": recent_logins,
        "system_uptime": "99.9%",  # Placeholder; calculate from startup if tracked
    }

@router.get("/staff", response_model=List[UserPublic])
async def list_staffs(current_user: dict = Depends(require_roles(["admin"]))):
    """
    Admin-only endpoint to list all *active* staff members.
    Joins 'staff_users' and 'staff_credentials' tables.
    Only returns records where both statuses are 'active'.
    """
    staffs = await fetch_all(
        """
        SELECT 
            sc.id, 
            sc.staff_id, 
            sc.username, 
            sc.role, 
            sc.status, 
            sc.created_at,
            su.staff_name
        FROM staff_credentials sc
        JOIN staff_users su ON sc.staff_id = su.id
        WHERE sc.status = 'active' AND su.status = 'active'
        ORDER BY sc.created_at DESC
        """,
        None
    )
    
    return [
        UserPublic(
            id=staff["id"],
            username=staff["username"],
            role=staff["role"],
            full_name=staff["staff_name"],
            is_active=(staff["status"] == "active")
        )
        for staff in staffs
    ]
    
class StaffDetailResponse(BaseModel):
    # Model used for /staff/{id} endpoint
    model_config = ConfigDict(arbitrary_types_allowed=True) 
    
    id: int 
    username: str
    staff_name: str
    role: str
    address: Optional[str] = None
    image: Optional[str] = None
    status: str 
    created_at: Optional[str] = None
    staff_id: int # Included for internal consistency
    
@router.get("/staff/{staff_credentials_id}", response_model=StaffDetailResponse)
async def get_staff_details(staff_credentials_id: int, current_user: dict = Depends(require_roles(["admin"]))):
    """
    Admin-only endpoint to get detailed information about a single staff member
    using their staff_credentials ID (the primary ID used for API operations).
    """
    
    staff = await fetch_one(
        """
        SELECT 
            sc.id, 
            sc.staff_id,         
            sc.username, 
            sc.role, 
            sc.status, 
            sc.created_at,
            su.staff_name,
            su.address,   
            su.image      
        FROM staff_credentials sc
        JOIN staff_users su ON sc.staff_id = su.id
        WHERE sc.id = %s
        """,
        (staff_credentials_id,) 
    )
    
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staff member not found"
        )
    
    # FIX: Format the datetime object to an ISO string for Pydantic validation
    created_at_str = staff["created_at"].isoformat() if isinstance(staff["created_at"], datetime) else staff["created_at"]
    
    return StaffDetailResponse(
        id=staff["id"],
        staff_id=staff["staff_id"],
        staff_name=staff["staff_name"],
        username=staff["username"],
        role=staff["role"],
        address=staff["address"],
        image=staff["image"],
        status=staff["status"],
        created_at=created_at_str,
    )

# add staff
@router.post("/staff", response_model=UserPublic)
async def create_staff(
    staff_name: str = Body(...),
    image: Optional[str] = Body(None),  # URL or path to image
    role: str = Body(...),  # Selected by admin, e.g., "sales", "admin"
    address: Optional[str] = Body(None),
    status: str = Body("active"),  # Default "active"
    username: str = Body(...),
    password: str = Body(...),
    current_user: dict = Depends(require_roles(["admin"]))
):
    """
    Admin-only endpoint to create a new staff member.
    Inserts into 'staff' table and linked 'staff_credentials' table.
    """
    # Validate inputs
    if len(password.encode("utf-8")) > 72:
        raise HTTPException(status_code=400, detail="Password cannot exceed 72 bytes")
    
    # Validate status
    if status not in ["active", "inactive"]:
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'inactive'")
    
    # Check if username already exists
    existing_user = await fetch_one(
        "SELECT id FROM staff_credentials WHERE username = %s",
        (username,)
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already exists")
    
    created_at = datetime.utcnow()
    
    # Step 1: Insert into staff table
    await execute(
        """
        INSERT INTO staff_users (staff_name, image, role, address, status)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (staff_name, image, role, address, status),
    )
    
    # Fetch the new staff_id
    new_staff = await fetch_one(
        "SELECT id FROM staff_users WHERE staff_name = %s ORDER BY id DESC LIMIT 1",
        (staff_name,)
    )
    staff_id = new_staff["id"]
    
    # Step 2: Hash password
    hashed_password = hash_password(password[:72])
    
    # Step 3: Insert into staff_credentials
    await execute(
        """
        INSERT INTO staff_credentials (staff_id, username, password_hash, role, status, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (staff_id, username, hashed_password, role, status, created_at),
    )
    
    # Fetch created credentials
    created_user = await fetch_one(
        "SELECT id, staff_id, username, role, status, created_at FROM staff_credentials WHERE username = %s",
        (username,)
    )
    
    return UserPublic(
        id=created_user["id"],
        username=created_user["username"],
        role=created_user["role"],
        full_name=staff_name,  # Map staff_name to full_name
        is_active=(created_user["status"] == "active")
    )
    
@router.put("/staff/{cred_id}", response_model=UserPublic)
async def update_staff(
    cred_id: int,
    staff_name: Optional[str] = Body(None),
    image: Optional[str] = Body(None),
    role: Optional[str] = Body(None),
    address: Optional[str] = Body(None),
    status: Optional[str] = Body(None),
    username: Optional[str] = Body(None),
    password: Optional[str] = Body(None),
    current_user: dict = Depends(require_roles(["admin"]))
):
    """
    Admin-only endpoint to edit/update a staff member.
    Updates both staff_users and staff_credentials using cred_id.
    """

    print(f"🔹 Attempting to update cred_id={cred_id}")

    # Fetch all credentials (debug)
    existing_all_creds = await fetch_all("SELECT id, staff_id FROM staff_credentials")
    print(f"this is all creds: {existing_all_creds}")

    # ✅ Step 1: Get credentials by ID (not staff_id)
    existing_creds = await fetch_one(
        "SELECT id, staff_id, username FROM staff_credentials WHERE id = %s",
        (cred_id,)
    )

    if not existing_creds:
        print(f"❌ No credentials found for id={cred_id}")
        raise HTTPException(status_code=404, detail=f"No credentials found for id {cred_id}")

    staff_id = existing_creds["staff_id"]  # extract linked staff_id
    print(f"✅ Found linked staff_id={staff_id} for cred_id={cred_id}")

    # ✅ Step 2: Check if staff exists
    existing_staff = await fetch_one(
        "SELECT id, staff_name FROM staff_users WHERE id = %s",
        (staff_id,)
    )
    if not existing_staff:
        print(f"❌ Staff ID {staff_id} not found in staff_users")
        raise HTTPException(status_code=404, detail=f"Staff ID {staff_id} not found")

    # ✅ Step 3: Validate fields
    if status is not None and status not in ["active", "inactive"]:
        raise HTTPException(status_code=400, detail="Status must be 'active' or 'inactive'")

    hashed_password = None
    if password is not None:
        if len(password.encode("utf-8")) > 72:
            raise HTTPException(status_code=400, detail="Password cannot exceed 72 bytes")
        hashed_password = hash_password(password[:72])

    if username is not None and username != existing_creds["username"]:
        dup_check = await fetch_one(
            "SELECT id FROM staff_credentials WHERE username = %s",
            (username,)
        )
        if dup_check:
            raise HTTPException(status_code=400, detail="Username already exists")

    # ✅ Step 4: Prepare updates
    staff_updates, staff_params = [], []
    if staff_name is not None:
        staff_updates.append("staff_name = %s")
        staff_params.append(staff_name)
    if image is not None:
        staff_updates.append("image = %s")
        staff_params.append(image)
    if role is not None:
        staff_updates.append("role = %s")
        staff_params.append(role)
    if address is not None:
        staff_updates.append("address = %s")
        staff_params.append(address)
    if status is not None:
        staff_updates.append("status = %s")
        staff_params.append(status)

    creds_updates, creds_params = [], []
    if username is not None:
        creds_updates.append("username = %s")
        creds_params.append(username)
    if hashed_password is not None:
        creds_updates.append("password_hash = %s")
        creds_params.append(hashed_password)
    if role is not None:
        creds_updates.append("role = %s")
        creds_params.append(role)
    if status is not None:
        creds_updates.append("status = %s")
        creds_params.append(status)

    # ✅ Step 5: Execute updates
    if staff_updates:
        staff_params.append(staff_id)
        await execute(
            f"UPDATE staff_users SET {', '.join(staff_updates)} WHERE id = %s",
            tuple(staff_params)
        )
        print(f"✅ staff_users updated for ID {staff_id}")

    if creds_updates:
        creds_params.append(cred_id)
        await execute(
            f"UPDATE staff_credentials SET {', '.join(creds_updates)} WHERE id = %s",
            tuple(creds_params)
        )
        print(f"✅ staff_credentials updated for id={cred_id}")

    if not staff_updates and not creds_updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # ✅ Step 6: Fetch updated data
    updated_user = await fetch_one(
        "SELECT id, staff_id, username, role, status, created_at FROM staff_credentials WHERE id = %s",
        (cred_id,)
    )
    updated_staff = await fetch_one(
        "SELECT staff_name FROM staff_users WHERE id = %s",
        (staff_id,)
    )

    print(f"✅ Staff update successful for cred_id={cred_id}")

    return UserPublic(
        id=updated_user["id"],
        username=updated_user["username"],
        role=updated_user["role"],
        full_name=updated_staff["staff_name"],
        is_active=(updated_user["status"] == "active")
    )

@router.delete("/staff/{cred_id}")
async def delete_staff(
    cred_id: int,
    current_user: dict = Depends(require_roles(["admin"]))
):
    """
    Admin-only endpoint to soft delete a staff member.
    Instead of deleting records, it sets 'status' = 'inactive'
    in both 'staff_users' and 'staff_credentials' tables.
    """

    print(f"🗑️ Attempting to soft delete cred_id={cred_id}")

    # Step 1: Find credentials record
    existing_creds = await fetch_one(
        "SELECT id, staff_id, status FROM staff_credentials WHERE id = %s",
        (cred_id,)
    )
    if not existing_creds:
        print(f"❌ No credentials found for id={cred_id}")
        raise HTTPException(status_code=404, detail=f"No credentials found for id {cred_id}")

    staff_id = existing_creds["staff_id"]
    print(f"✅ Found linked staff_id={staff_id} for cred_id={cred_id}")

    # Step 2: Update staff_credentials status to 'inactive'
    await execute(
        "UPDATE staff_credentials SET status = 'inactive' WHERE id = %s",
        (cred_id,)
    )
    print(f"✅ staff_credentials marked inactive for cred_id={cred_id}")

    # Step 3: Update staff_users status to 'inactive' if exists
    existing_staff = await fetch_one(
        "SELECT id, status FROM staff_users WHERE id = %s",
        (staff_id,)
    )
    if existing_staff:
        await execute(
            "UPDATE staff_users SET status = 'inactive' WHERE id = %s",
            (staff_id,)
        )
        print(f"✅ staff_users marked inactive for staff_id={staff_id}")
    else:
        print(f"⚠️ No staff_users found for id={staff_id}")

    # Step 4: Return success response
    return {
        "message": f"Staff soft-deleted successfully (cred_id={cred_id}, staff_id={staff_id})",
        "status": "inactive"
    }



# ---------  add product category    ------------


class ProductCategoryPublic(BaseModel):
    id: int
    name: str
    is_active: bool

@router.get("/product_category", response_model=List[ProductCategoryPublic])
async def list_product_categories(current_user: dict = Depends(require_roles(["admin"]))):
    """
    Admin-only endpoint to list all active product categories.
    Only shows categories with status = true.
    """
    categories = await fetch_all(
        """
        SELECT 
            id, 
            name, 
            status
        FROM product_category
        WHERE status = true
        ORDER BY id DESC
        """,
        None
    )
    
    return [
        ProductCategoryPublic(
            id=cat["id"],
            name=cat["name"],
            is_active=cat["status"]
        )
        for cat in categories
    ]

# add product category
@router.post("/product_category", response_model=ProductCategoryPublic)
async def create_product_category(
    name: str = Body(...),
    status: bool = Body(True),  # Default True (active)
    current_user: dict = Depends(require_roles(["admin"]))
):
    """
    Admin-only endpoint to create a new product category.
    Inserts into 'product_category' table.
    """
    # Validate inputs
    if not name or len(name) > 255:
        raise HTTPException(status_code=400, detail="Name must be provided and cannot exceed 255 characters")
    
    # Check if name already exists (case insensitive)
    existing_category = await fetch_one(
        "SELECT id FROM product_category WHERE LOWER(name) = LOWER(%s)",
        (name,)
    )
    if existing_category:
        raise HTTPException(status_code=400, detail="Category name already exists")
    
    # Insert into product_category (plain execute, no fetch)
    await execute(
        """
        INSERT INTO product_category (name, status)
        VALUES (%s, %s)
        """,
        (name, status),
    )
    
    # Fetch the new category_id (query by name, since names are unique)
    new_category = await fetch_one(
        "SELECT id FROM product_category WHERE LOWER(name) = LOWER(%s) ORDER BY id DESC LIMIT 1",
        (name,)
    )
    category_id = new_category["id"]
    
    # Fetch full created category details
    created_category = await fetch_one(
        "SELECT id, name, status FROM product_category WHERE id = %s",
        (category_id,)
    )
    
    return ProductCategoryPublic(
        id=created_category["id"],
        name=created_category["name"],
        is_active=created_category["status"]
    )

@router.put("/product_category/{category_id}", response_model=ProductCategoryPublic)
async def update_product_category(
    category_id: int,
    name: Optional[str] = Body(None),
    status: Optional[bool] = Body(None),
    current_user: dict = Depends(require_roles(["admin"]))
):
    """
    Admin-only endpoint to edit/update a product category.
    Updates 'product_category' table as needed.
    """
    # Check if category exists
    existing_category = await fetch_one(
        "SELECT id FROM product_category WHERE id = %s",
        (category_id,)
    )
    if not existing_category:
        raise HTTPException(status_code=404, detail="Product category not found")

    # Check name uniqueness if changing (case insensitive)
    if name is not None:
        dup_check = await fetch_one(
            "SELECT id FROM product_category WHERE LOWER(name) = LOWER(%s) AND id != %s",
            (name, category_id)
        )
        if dup_check:
            raise HTTPException(status_code=400, detail="Category name already exists")

    # Prepare updates
    updates = []
    params = []
    if name is not None:
        updates.append("name = %s")
        params.append(name)
    if status is not None:
        updates.append("status = %s")
        params.append(status)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    params.append(category_id)
    updates_str = ", ".join(updates)
    await execute(
        f"""
        UPDATE product_category 
        SET {updates_str} 
        WHERE id = %s
        """,
        tuple(params)
    )

    # Fetch updated category
    updated_category = await fetch_one(
        "SELECT id, name, status FROM product_category WHERE id = %s",
        (category_id,)
    )

    return ProductCategoryPublic(
        id=updated_category["id"],
        name=updated_category["name"],
        is_active=updated_category["status"]
    )

@router.delete("/product_category/{category_id}")
async def delete_product_category(
    category_id: int,
    current_user: dict = Depends(require_roles(["admin"]))
):
    """
    Admin-only endpoint to soft delete a product category.
    Sets status to false instead of deleting the row.
    """
    # Check if category exists
    existing_category = await fetch_one(
        "SELECT id FROM product_category WHERE id = %s",
        (category_id,)
    )
    if not existing_category:
        raise HTTPException(status_code=404, detail="Product category not found")

    # Soft delete: set status to false
    await execute(
        "UPDATE product_category SET status = false WHERE id = %s",
        (category_id,)
    )

    return {"message": "Product category soft deleted successfully"}

# ---- product api end ---------

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
    current_user=Depends(require_roles(["admin"]))
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
    current_user=Depends(require_roles(["admin"]))
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
    current_user=Depends(require_roles(["admin"]))
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
    current_user=Depends(require_roles(["admin"]))
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
    current_user=Depends(require_roles(["admin"]))
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
    current_user=Depends(require_roles(["admin"]))
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
async def get_all_tasks(current_user=Depends(require_roles(["admin"]))):
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
    current_user=Depends(require_roles(["admin"]))
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
    current_user=Depends(require_roles(["admin"]))
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
    current_user=Depends(require_roles(["admin"]))
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
    
    
    
# ------------------------------------------------------------
# GET ALL ATTENDANCE RECORDS WITH JOINED STAFF DETAILS
# ------------------------------------------------------------

class AttendanceBase(BaseModel):
    staff_id: Optional[int]
    date: Optional[date]
    checkin_time: Optional[datetime]
    checkout_time: Optional[datetime]
    status: Optional[str]

class Attendance(AttendanceBase):
    id: int
    updated_by: Optional[int]

    # ✅ Joined fields (from LEFT JOINs)
    staff_name: Optional[str]
    staff_role: Optional[str]
    updated_by_name: Optional[str]
    updated_by_role: Optional[str]

    class Config:
        orm_mode = True
        
@router.get("/attendance", response_model=List[Attendance])
async def get_all_attendance(current_user=Depends(require_roles(["admin"]))):
    query = textwrap.dedent("""
        SELECT 
            a.id,
            a.staff_id,
            su.staff_name AS staff_name,
            su.role AS staff_role,
            a.date,
            a.checkin_time,
            a.checkout_time,
            a.status,
            a.updated_by,
            su2.staff_name AS updated_by_name,
            su2.role AS updated_by_role
        FROM public.attendance_details a
        LEFT JOIN public.staff_users su 
            ON a.staff_id = su.id
        LEFT JOIN public.staff_credentials sc 
            ON a.updated_by = sc.id
        LEFT JOIN public.staff_users su2 
            ON sc.staff_id = su2.id
        ORDER BY a.id ASC
    """)
    try:
        records = await fetch_all(query)
        return records
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch attendance records: {str(e)}")

