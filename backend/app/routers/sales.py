from typing import List
from urllib.parse import uses_relative
from fastapi import APIRouter, Depends, HTTPException, status, Body, UploadFile, File, Form
from ..schemas.crm import LeadCreate, LeadUpdate, LeadPublic
from ..core.security import require_roles
from ..db.pool import fetch_all, fetch_one, execute
import textwrap
import re
from typing import Optional

router = APIRouter(prefix="/sales", tags=["sales"])

@router.post("/customers", status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_data: dict = Body(...),
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    # Access id from dict
    if 'id' not in current_user:
        raise HTTPException(status_code=400, detail=f"User ID not found in token: {list(current_user.keys())}")
    staff_id = int(current_user['id'])
    
    # Validate required fields
    required_fields = ['customer_name', 'mobile_number', 'whatsapp_number', 'address', 'requirements']
    for field in required_fields:
        if field not in customer_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    # Print incoming data for debugging
    print(f"Incoming customer data: {customer_data}")
    
    # Fixed query: Use %s placeholders for psycopg3
    query = textwrap.dedent("""
        INSERT INTO customers (customer_name, mobile_number, whatsapp_number, address, requirements, created_on, status, created_by)
        VALUES (%s, %s, %s, %s, %s, NOW(), 'pending', %s)
        RETURNING id, customer_name, mobile_number, whatsapp_number, address, requirements, created_on, status, created_by
    """)
    
    params = (
        customer_data['customer_name'],
        customer_data['mobile_number'],
        customer_data['whatsapp_number'],
        customer_data['address'],
        customer_data['requirements'],
        staff_id
    )
    
    try:
        result = await fetch_one(query, params)  # Use fetch_one for RETURNING single row
        if not result:
            raise HTTPException(status_code=500, detail="Failed to retrieve inserted customer")
        print(f"Insert result: {result}")  # Debug the result
        return result
    except Exception as e:
        print(f"Database error details: {str(e)}")  # More detailed error log
        raise HTTPException(status_code=400, detail=f"Failed to create customer: {str(e)}")

@router.get("/customers", response_model=List[dict])
async def get_customers(
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    query = textwrap.dedent("""
        SELECT 
            c.*, 
            s.staff_name AS created_by_staff_name
        FROM customers c
        LEFT JOIN staff_credentials u ON c.created_by = u.id
        LEFT JOIN staff_users s ON u.staff_id = s.id
        LEFT JOIN orders o ON c.id = o.customer_id
        WHERE o.customer_id IS NULL
        ORDER BY c.created_on DESC
    """)
    try:
        results = await fetch_all(query)  # No params
        print(f"Fetched {len(results)} customers")  # Debug log
        return results
    except Exception as e:
        print(f"Database error details: {str(e)}")  # More detailed error log
        raise HTTPException(status_code=500, detail=f"Failed to fetch customers: {str(e)}")

@router.get("/customers/{customer_id}", response_model=dict)
async def get_customer(
    customer_id: int,
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    query = textwrap.dedent("""
        SELECT 
            c.*, 
            s.staff_name as created_by_staff_name,
        FROM customers c
        LEFT JOIN staff_credentials u ON c.created_by = u.id
        LEFT JOIN staff_users s ON u.staff_id = s.id
        WHERE c.id = %s
    """)
    try:
        result = await fetch_one(query, (customer_id,))
        if not result:
            raise HTTPException(status_code=404, detail="Customer not found")
        print(f"Fetched customer {customer_id} created by staff: {result.get('created_by_staff_name')}")  # Debug log
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")  # More detailed error log
        raise HTTPException(status_code=500, detail=f"Failed to fetch customer: {str(e)}")

@router.put("/customers/{customer_id}", response_model=dict)
async def update_customer(
    customer_id: int,
    customer_data: dict = Body(...),
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    # Validate at least one field to update
    if not customer_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    
    # Build dynamic update query with %s
    set_clauses = ["updated_on = NOW()"]  # Always update timestamp (if column exists)
    params = []
    
    for key, value in customer_data.items():
        if key in ['customer_name', 'mobile_number', 'whatsapp_number', 'address', 'requirements', 'status']:
            set_clauses.append(f"{key} = %s")
            params.append(value)
    
    if len(set_clauses) == 1:  # Only updated_on
        raise HTTPException(status_code=400, detail="No valid fields provided to update")
    
    query = textwrap.dedent(f"""
        UPDATE customers 
        SET {', '.join(set_clauses)}
        WHERE id = %s
        RETURNING id, customer_name, mobile_number, whatsapp_number, address, requirements, created_on, status, created_by
    """)
    params.append(customer_id)
    
    print(f"Updating customer {customer_id} with fields: {customer_data}")  # Debug log
    
    try:
        result = await fetch_one(query, tuple(params))  # Use fetch_one for RETURNING
        if not result:
            raise HTTPException(status_code=404, detail="Customer not found")
        print(f"Updated customer {customer_id}, updated_on: {result.get('updated_on')}")  # Debug log
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")  # More detailed error log
        raise HTTPException(status_code=400, detail=f"Failed to update customer: {str(e)}")

@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    query = textwrap.dedent("DELETE FROM customers WHERE id = %s RETURNING id")
    try:
        result = await fetch_one(query, (customer_id,))  # Use fetch_one to check RETURNING
        if not result:
            raise HTTPException(status_code=404, detail="Customer not found")
        print(f"Deleted customer {customer_id}")  # Debug log
        return None
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")  # More detailed error log
        raise HTTPException(status_code=500, detail=f"Failed to delete customer: {str(e)}")
    
# Assuming you have a function to insert, e.g., await execute(query, params) that returns the inserted row
# If not, adjust based on your DB setup

from pydantic import BaseModel

class OrderCreate(BaseModel):
    customer_id: int
    category: str | None = None
    project_commit: str | None = None
    start_on: str | None = None
    completion_date: str | None = None
    status: str | None = None
    amount: float | None = None
    description: str | None = None
    order_type: str | None = None
    quantity: int | None = None
    payment_status: str | None = None
    amount_payed: float | None = None
    payment_method: str | None = None
    delivery_type: str | None = None
    delivery_address: str | None = None
    product_name: str | None = None
    additional_amount: float | None = 0.0
    total_amount: float | None = 0.0
    account_name: str | None = None

    # <<< NEW COLUMN >>>
    design_amount: float | None = 0.0          # default 0.0 when creating


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
    order_type: str | None = None
    quantity: int | None = None
    payment_status: str | None = None
    amount_payed: float | None = None
    payment_method: str | None = None
    delivery_type: str | None = None
    delivery_address: str | None = None
    product_name: str | None = None
    additional_amount: float | None = None
    total_amount: float | None = None
    account_name: str | None = None

    # <<< NEW COLUMN >>>
    design_amount: float | None = None        # optional on update

def clean_value(value):
    if value in (None, ""):
        return None
    return value


# -----------------------------------------------------------
# CREATE ORDER
# -----------------------------------------------------------

@router.post("/orders", response_model=dict)
async def create_order(
    payload: OrderCreate,
    current_user=Depends(require_roles(["crm", "sales"]))
):
    print(f"Current user full dict: {current_user}")

    role = (
        current_user.get('role') or
        (current_user.get('roles', ['unknown'])[0]
         if isinstance(current_user.get('roles'), list)
         else current_user.get('roles', 'unknown'))
    )
    print(f"Current user role: {role}")

    created_by = current_user.get('id')

    query = """
        INSERT INTO orders (
            customer_id, category, project_committed_on, start_on, completion_date,
            status, created_by, amount, description,
            order_type, quantity, payment_status, amount_payed,
            payment_method, delivery_type, delivery_address,
            product_name, additional_amount, total_amount, account_name,
            design_amount, created_on
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s, %s,
            %s, NOW()
        ) RETURNING *
    """

    params = (
        payload.customer_id,
        payload.category,
        payload.project_commit,
        payload.start_on,
        payload.completion_date,
        payload.status,
        created_by,
        payload.amount,
        payload.description,
        payload.order_type,
        payload.quantity,
        payload.payment_status,
        payload.amount_payed,
        payload.payment_method,
        payload.delivery_type,
        payload.delivery_address,
        payload.product_name,
        payload.additional_amount,
        payload.total_amount,
        payload.account_name,
        payload.design_amount  # NEW PARAM
    )

    try:
        result = await execute(query, params)

        if isinstance(result, int):
            return {"message": "Order created", "id": result}

        if isinstance(result, dict):
            print(f"Created order {result.get('id')} for customer {payload.customer_id}")
            return result

        raise HTTPException(status_code=500, detail="Unexpected response from database")

    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to create order: {str(e)}")


# -----------------------------------------------------------
# GET ALL ORDERS (by current user)
# -----------------------------------------------------------

@router.get("/orders", response_model=List[dict])
async def get_orders(
    current_user=Depends(require_roles(["crm", "sales"]))
):
    print(f"Current user full dict: {current_user}")
    
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    user_id = current_user.get('id')
    print(f"this is the userid: {user_id}")

    query = textwrap.dedent("""
        SELECT 
            o.*, 
            s.staff_name as created_by_staff_name
        FROM orders o
        LEFT JOIN staff_credentials u ON o.created_by = u.id
        LEFT JOIN staff_users s ON u.staff_id = s.id
        WHERE o.created_by = %s
        ORDER BY o.created_on DESC
    """)
    try:
        results = await fetch_all(query, (user_id,))
        print(f"Fetched {len(results)} orders")
        return results
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch orders: {str(e)}")


# -----------------------------------------------------------
# GET SINGLE ORDER
# -----------------------------------------------------------

@router.get("/orders/{order_id}", response_model=dict)
async def get_order(
    order_id: int,
    current_user=Depends(require_roles(["crm", "sales"]))
):
    print(f"Current user full dict: {current_user}")
    
    role = current_user.get('role') or (
        current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list)
        else current_user.get('roles', 'unknown')
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
        
        print(f"Fetched order {order_id}: created by {result.get('created_by_staff_name')} for customer {result.get('customer_name')}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch order: {str(e)}")


# -----------------------------------------------------------
# UPDATE ORDER
# -----------------------------------------------------------

@router.put("/orders/{order_id}", response_model=dict)
async def update_order(
    order_id: int,
    payload: OrderUpdate,
    current_user=Depends(require_roles(["crm", "sales"]))
):
    print(f"Current user: {current_user}")
    role = current_user.get("role") or (
        current_user.get("roles")[0]
        if isinstance(current_user.get("roles"), list)
        else current_user.get("roles", "unknown")
    )

    updated_by = current_user.get("id")
    set_clauses = []
    params = []

    # Map all possible updatable columns including design_amount
    field_map = {
        "customer_id": payload.customer_id,
        "category": payload.category,
        "project_committed_on": payload.project_commit,
        "start_on": payload.start_on,
        "completion_date": payload.completion_date,
        "completed_on": payload.completed_on,
        "status": payload.status,
        "amount": payload.amount,
        "description": payload.description,
        "order_type": payload.order_type,
        "quantity": payload.quantity,
        "payment_status": payload.payment_status,
        "amount_payed": payload.amount_payed,
        "payment_method": payload.payment_method,
        "delivery_type": payload.delivery_type,
        "delivery_address": payload.delivery_address,
        "product_name": payload.product_name,
        "additional_amount": payload.additional_amount,
        "total_amount": payload.total_amount,
        "account_name": payload.account_name,
        "design_amount": payload.design_amount  # NEW FIELD
    }

    for col, val in field_map.items():
        if val is not None:
            set_clauses.append(f"{col} = %s")
            params.append(clean_value(val))

    set_clauses.append("updated_by = %s")
    params.append(updated_by)
    set_clauses.append("updated_on = NOW()")

    if not set_clauses:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    set_clause = ", ".join(set_clauses)
    query = f"UPDATE orders SET {set_clause} WHERE id = %s RETURNING *"
    params.append(order_id)

    try:
        result = await execute(query, params)
        if isinstance(result, int):
            if result == 0:
                raise HTTPException(status_code=404, detail="Order not found")
            return {"message": "Order updated", "rows_affected": result}
        return result
    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update order: {e}")


@router.delete("/orders/{order_id}", response_model=dict)
async def delete_order(
    order_id: int,
    current_user=Depends(require_roles(["crm", "sales"]))
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
    
@router.get("/real_customers", response_model=List[dict])
async def get_real_customers(
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    query = textwrap.dedent("""
    SELECT 
        DISTINCT rc.*, 
        s.staff_name AS created_by_staff_name
    FROM customers rc
    INNER JOIN orders o ON rc.id = o.customer_id
    LEFT JOIN staff_credentials u ON rc.created_by = u.id
    LEFT JOIN staff_users s ON u.staff_id = s.id
    ORDER BY rc.created_on DESC
    """)

    try:
        results = await fetch_all(query)  # No params
        print(f"Fetched {len(results)} real_customers")  # Debug log
        return results
    except Exception as e:
        print(f"Database error details: {str(e)}")  # More detailed error log
        raise HTTPException(status_code=500, detail=f"Failed to fetch real_customers: {str(e)}")

@router.get("/real_customers/{real_customer_id}", response_model=dict)
async def get_real_customer(
    real_customer_id: int,
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    query = textwrap.dedent("""
        SELECT 
            rc.*, 
            s.staff_name as created_by_staff_name
        FROM customers rc
        LEFT JOIN staff_credentials u ON rc.created_by = u.id
        LEFT JOIN staff_users s ON u.staff_id = s.id
        WHERE rc.id = %s
    """)
    try:
        result = await fetch_one(query, (real_customer_id,))
        if not result:
            raise HTTPException(status_code=404, detail="Real customer not found")
        print(f"Fetched real_customer {real_customer_id} created by staff: {result.get('created_by_staff_name')}")  # Debug log
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")  # More detailed error log
        raise HTTPException(status_code=500, detail=f"Failed to fetch real_customer: {str(e)}")

@router.put("/real_customers/{real_customer_id}", response_model=dict)
async def update_real_customer(
    real_customer_id: int,
    real_customer_data: dict = Body(...),
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    # Validate at least one field to update
    if not real_customer_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    
    # Build dynamic update query with %s
    set_clauses = ["updated_on = NOW()"]  # Always update timestamp (if column exists)
    params = []
    
    for key, value in real_customer_data.items():
        if key in ['customer_name', 'mobile_number', 'whatsapp_number', 'address', 'requirements', 'status']:
            set_clauses.append(f"{key} = %s")
            params.append(value)
    
    if len(set_clauses) == 1:  # Only updated_on
        raise HTTPException(status_code=400, detail="No valid fields provided to update")
    
    query = textwrap.dedent(f"""
        UPDATE customers 
        SET {', '.join(set_clauses)}
        WHERE id = %s
        RETURNING id, customer_name, mobile_number, whatsapp_number, address, requirements, created_on, status, created_by
    """)
    params.append(real_customer_id)
    
    print(f"Updating real_customer {real_customer_id} with fields: {real_customer_data}")  # Debug log
    
    try:
        result = await fetch_one(query, tuple(params))  # Use fetch_one for RETURNING
        if not result:
            raise HTTPException(status_code=404, detail="Real customer not found")
        print(f"Updated real_customer {real_customer_id}, updated_on: {result.get('updated_on')}")  # Debug log
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"Database error details: {str(e)}")  # More detailed error log
        raise HTTPException(status_code=400, detail=f"Failed to update real_customer: {str(e)}")



    
@router.get("/staff_by_roles", response_model=List[dict])
async def get_staff_by_roles(
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Debug: print current user info
    print(f"Current user: {current_user}")

    # SQL query to fetch staff with roles 'sales' or 'crm'
    query = textwrap.dedent("""
        SELECT 
            id,
            staff_name,
            role
        FROM staff_users
        WHERE role IN ('sales', 'crm')
        ORDER BY staff_name ASC
    """)

    try:
        results = await fetch_all(query)
        print(f"Fetched {len(results)} staff members with roles sales/crm")
        return results
    except Exception as e:
        print(f"Database error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch staff list: {e}")
 
 
 
 
 
    
# import cloudinary
# import cloudinary.uploader
# from cloudinary.utils import cloudinary_url
# # Configure Cloudinary if not already done globally (add your credentials here or via env vars)
# cloudinary.config(
#     cloud_name="dxkx8durf",
#     api_key="831192657531599",
#     api_secret="cVagnFRJqHw-_BRBgesJ1z2IYjc"
# )


# @router.post("/orders/images/{order_id}", response_model=dict)
# async def upload_order_image(
#     order_id: int,
#     file: UploadFile = File(...),
#     # 🛑 THE FIX: Changed Body(None) to Form(None) and updated type hint
#     description: Optional[str] = Form(None), 
#     current_user=Depends(require_roles(["crm", "sales"]))
# ):
    
#     print(f"Received description: {description}")
#     print(f"Received file: {file.filename}, type={file.content_type}")
    
#     # Access user ID
#     if 'id' not in current_user:
#         raise HTTPException(status_code=400, detail="User ID not found in token")
#     uploaded_by = int(current_user['id'])
    
#     # Validate file content
#     if not file.content_type.startswith('image/'):
#         raise HTTPException(status_code=400, detail="File must be an image")
    
#     # Read file content
#     contents = await file.read()
    
#     # Upload to Cloudinary
#     try:
#         upload_result = cloudinary.uploader.upload(
#             contents,
#             folder=f"orders/{order_id}",
#             resource_type="image",
#             public_id=f"{order_id}_{file.filename}"
#         )
#         image_url = upload_result.get('secure_url')
#         if not image_url:
#             raise HTTPException(status_code=500, detail="Failed to get image URL from Cloudinary")
        
#         print(f"Uploaded image to Cloudinary: {image_url}")
#     except Exception as cloudinary_error:
#         print(f"Cloudinary upload error: {str(cloudinary_error)}")
#         raise HTTPException(status_code=500, detail=f"Failed to upload image to Cloudinary: {str(cloudinary_error)}")
    
#     # Insert into order_images table
#     query = textwrap.dedent("""
#         INSERT INTO order_images (order_id, image_url, status, created_at, description, uploaded_by)
#         VALUES (%s, %s, %s, NOW(), %s, %s)
#         RETURNING id, order_id, image_url, status, created_at, description, uploaded_by
#     """)
    
#     params = (
#         order_id,
#         image_url,
#         'active',
#         description, # This value is correctly None if not provided
#         uploaded_by
#     )
    
#     try:
#         result = await fetch_one(query, params)
#         print(f"Inserted image record: {result}")
#         return result
#     except Exception as e:
#         print(f"Database error details: {str(e)}")
#         raise HTTPException(status_code=500, detail=f"Failed to save image record: {str(e)}")

# --- Pydantic Schema for Incoming JSON Payload ---
class ImageUploadPayload(BaseModel):
    image_url: str
    description: Optional[str] = None


@router.post("/orders/images/{order_id}", response_model=dict)
async def upload_order_image(
    order_id: int,
    # 🛑 THE FIX: Accepts JSON payload directly, removes file handling
    payload: ImageUploadPayload, 
    current_user=Depends(require_roles(["crm", "sales"]))
):
    
    # Extract data from the validated Pydantic payload
    image_url = payload.image_url
    description = payload.description
    
    print(f"Received image_url: {image_url}")
    print(f"Received description: {description}")
    
    # Access user ID
    if 'id' not in current_user:
        raise HTTPException(status_code=400, detail="User ID not found in token")
    uploaded_by = int(current_user['id'])
    
    # CRITICAL: We skip all file validation and Cloudinary upload, 
    # as those steps happened on the frontend.
    
    # Insert into order_images table
    query = textwrap.dedent("""
        INSERT INTO order_images (order_id, image_url, status, created_at, description, uploaded_by)
        VALUES (%s, %s, %s, NOW(), %s, %s)
        RETURNING id, order_id, image_url, status, created_at, description, uploaded_by
    """)
    
    params = (
        order_id,
        image_url,
        'active',
        description, # This is now directly from the payload (str or None)
        uploaded_by
    )
    
    try:
        result = await fetch_one(query, params)
        print(f"Inserted image record: {result}")
        return result
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save image record: {str(e)}")
    

# -----------------------------------------------------------
# Get All Images for an Order
# -----------------------------------------------------------

@router.get("/orders/images/{order_id}", response_model=List[dict])
async def get_order_images(
    order_id: int,
    current_user=Depends(require_roles(["crm", "sales"]))
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

# -----------------------------------------------------------
# Update Image (e.g., description or status)
# -----------------------------------------------------------

@router.put("/orders/images/{image_id}", response_model=dict)
async def update_order_image(
    image_id: int,
    update_data: dict = Body(...),  # e.g., {"description": "Updated desc", "status": "inactive"}
    current_user=Depends(require_roles(["crm", "sales"]))
):
    # Print the entire current_user for debugging
    print(f"Current user full dict: {current_user}")
    
    # Print the role for debugging (safe dict access)
    role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
    print(f"Current user role: {role}")
    
    # Validate at least one field to update
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    
    # Allowed fields
    allowed_fields = ['description', 'status']
    set_clauses = []
    params = []
    
    for key, value in update_data.items():
        if key in allowed_fields:
            set_clauses.append(f"{key} = %s")
            params.append(value)
    
    if not set_clauses:
        raise HTTPException(status_code=400, detail="No valid fields provided to update")
    
    set_clauses.append("updated_at = NOW()")  # Assuming you add an updated_at column; otherwise remove this
    
    query = textwrap.dedent(f"""
        UPDATE order_images 
        SET {', '.join(set_clauses)}
        WHERE id = %s
        RETURNING id, order_id, image_url, status, created_at, description, uploaded_by
    """)
    params.append(image_id)
    
    print(f"Updating image {image_id} with fields: {update_data}")
    
    try:
        result = await fetch_one(query, tuple(params))
        if not result:
            raise HTTPException(status_code=404, detail="Image not found")
        print(f"Updated image {image_id}")
        return result
    except Exception as e:
        print(f"Database error details: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update image: {str(e)}")

# -----------------------------------------------------------
# Delete Image (from DB and Cloudinary)
# -----------------------------------------------------------

# @router.delete("/orders/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
# async def delete_order_image(
#     image_id: int,
#     current_user=Depends(require_roles(["crm", "sales"]))
# ):
#     # Print the entire current_user for debugging
#     print(f"Current user full dict: {current_user}")
    
#     # Print the role for debugging (safe dict access)
#     role = current_user.get('role') or current_user.get('roles', ['unknown'])[0] if isinstance(current_user.get('roles'), list) else current_user.get('roles', 'unknown')
#     print(f"Current user role: {role}")
    
#     # First, fetch the image to get image_url for Cloudinary delete
#     fetch_query = textwrap.dedent("""
#         SELECT image_url FROM order_images WHERE id = %s
#     """)
    
#     try:
    #     image_record = await fetch_one(fetch_query, (image_id,))
    #     if not image_record:
    #         raise HTTPException(status_code=404, detail="Image not found")
        
    #     image_url = image_record['image_url']
        
    #     # Parse public_id and folder from image_url (Cloudinary format: https://res.cloudinary.com/<cloud>/image/upload/v<version>/<folder>/<public_id>.<ext>)
    #     # Simple regex to extract public_id (assumes no subfolders beyond 'orders/{order_id}')
    #     public_id_match = re.search(r'/upload/v\d+/(orders/\d+)/([^/]+\.[^/]+)$', image_url)
    #     if not public_id_match:
    #         # Fallback: use cloudinary_url to generate signature or adjust regex if needed
    #         raise HTTPException(status_code=500, detail="Could not parse public_id from URL")
        
    #     folder = public_id_match.group(1)
    #     full_public_id = public_id_match.group(2)  # Includes extension, but destroy accepts without ext
        
    #     # Delete from Cloudinary
    #     cloudinary.uploader.destroy(
    #         public_id=full_public_id,
    #         folder=folder.replace('/orders/', ''),  # Extract just order_id if needed; adjust based on your folder structure
    #         resource_type="image"
    #     )
    #     print(f"Deleted image from Cloudinary: {full_public_id} in folder {folder}")
        
    #     # Now delete from DB
    #     delete_query = textwrap.dedent("""
    #         DELETE FROM order_images WHERE id = %s RETURNING id
    #     """)
    #     result = await fetch_one(delete_query, (image_id,))
    #     if not result:
    #         raise HTTPException(status_code=404, detail="Image not found in database")
        
    #     print(f"Deleted image record {image_id}")
    #     return None
        
    # except HTTPException:
    #     raise
    # except Exception as e:
    #     print(f"Error during delete: {str(e)}")
    #     raise HTTPException(status_code=500, detail=f"Failed to delete image: {str(e)}")
    
    
@router.delete("/orders/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_order_image(
    image_id: int,
    current_user=Depends(require_roles(["crm", "sales"]))
):
    try:
        # 1️⃣ Check if the image record exists
        fetch_query = """
            SELECT id FROM order_images WHERE id = %s
        """
        image_record = await fetch_one(fetch_query, (image_id,))
        if not image_record:
            raise HTTPException(status_code=404, detail="Image not found")

        # 2️⃣ Delete only from database
        delete_query = """
            DELETE FROM order_images WHERE id = %s RETURNING id
        """
        deleted = await fetch_one(delete_query, (image_id,))
        if not deleted:
            raise HTTPException(status_code=404, detail="Image record not found")

        print(f"✅ Deleted image record {image_id} from database")

        # 3️⃣ Return 204 No Content
        return None

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error deleting image record: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete image record: {str(e)}")