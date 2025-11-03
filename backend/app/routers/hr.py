from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from ..core.security import require_roles
from ..db.pool import fetch_one, fetch_all, execute
from pydantic import BaseModel
from datetime import datetime
import textwrap
import traceback
from datetime import date, datetime

router = APIRouter(prefix="/hr", tags=["hr"])






# ------------------------------------------------------------
# GET ALL ACTIVE STAFFS
# ------------------------------------------------------------

@router.get("/staffs/active", response_model=dict)
async def get_active_staffs(
    current_user=Depends(require_roles(["hr"]))
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




class AttendanceBase(BaseModel):
    staff_id: Optional[int]
    date: Optional[date]
    checkin_time: Optional[datetime]
    checkout_time: Optional[datetime]
    status: Optional[str]

class AttendanceCreate(BaseModel):
    staff_id: int
    date: date
    checkin_time: datetime
    status: str
    checkout_time: Optional[datetime] = None  # 👈 optional

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



# ------------------------------------------------------------
# CREATE ATTENDANCE RECORD (Check-in Only)
# ------------------------------------------------------------
@router.post("/attendance", response_model=dict)
async def create_attendance(payload: AttendanceCreate, current_user=Depends(require_roles(["hr"]))):
    try:
        # ✅ Extract user ID from JWT token
        updated_by = current_user.get("id")

        if not updated_by:
            raise HTTPException(status_code=401, detail="Invalid or missing user ID in token")

        # ✅ Check if attendance already exists for the staff on the given date
        check_query = """
            SELECT id FROM public.attendance_details
            WHERE staff_id = %s AND date = %s
        """
        check_params = [payload.staff_id, payload.date]
        existing = await fetch_one(check_query, check_params)

        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Attendance already recorded for staff ID {payload.staff_id} on {payload.date}"
            )

        # ✅ Insert only checkin_time (checkout_time = NULL)
        insert_query = """
            INSERT INTO public.attendance_details (staff_id, date, checkin_time, status, updated_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
        """
        insert_params = [
            payload.staff_id,
            payload.date,
            payload.checkin_time,
            payload.status,
            updated_by
        ]

        result = await execute(insert_query, insert_params)

        if not result:
            raise HTTPException(status_code=500, detail="Failed to create attendance record")

        return {
            "message": "Attendance record created successfully (Check-in recorded)",
            "attendance": result
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating attendance record: {str(e)}")
    
# ------------------------------------------------------------
# UPDATE ATTENDANCE RECORD (Check-out Only)
# ------------------------------------------------------------
@router.put("/attendance/checkout", response_model=dict)
async def update_checkout(
    staff_id: int,
    date: date,
    checkout_time: datetime,
    status: Optional[str] = None,
    current_user=Depends(require_roles(["hr"]))
):
    try:
        # ✅ Extract user ID from JWT token
        updated_by = current_user.get("id")

        if not updated_by:
            raise HTTPException(status_code=401, detail="Invalid or missing user ID in token")

        # ✅ Check if attendance exists for the staff on the given date
        check_query = """
            SELECT id, checkout_time FROM public.attendance_details
            WHERE staff_id = %s AND date = %s
        """
        check_params = [staff_id, date]
        existing = await fetch_one(check_query, check_params)

        # ❌ If no record found → staff hasn't checked in yet
        if not existing:
            raise HTTPException(
                status_code=400,
                detail=f"Staff ID {staff_id} has no check-in record for {date}"
            )

        # ⚠️ If already checked out → block duplicate checkout
        if existing.get("checkout_time"):
            raise HTTPException(
                status_code=400,
                detail=f"Staff ID {staff_id} has already checked out for {date}"
            )

        # ✅ Update checkout_time and optionally status
        update_query = """
            UPDATE public.attendance_details
            SET checkout_time = %s,
                status = COALESCE(%s, status),
                updated_by = %s
            WHERE staff_id = %s AND date = %s
            RETURNING *
        """
        update_params = [checkout_time, status, updated_by, staff_id, date]

        result = await execute(update_query, update_params)

        if not result:
            raise HTTPException(status_code=500, detail="Failed to update checkout")

        return {
            "message": "Checkout time recorded successfully",
            "attendance": result
        }

    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error updating checkout: {str(e)}")

# ------------------------------------------------------------
# GET ALL ATTENDANCE RECORDS WITH JOINED STAFF DETAILS
# ------------------------------------------------------------
@router.get("/attendance", response_model=List[Attendance])
async def get_all_attendance(current_user=Depends(require_roles(["hr"]))):
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


# ------------------------------------------------------------
# GET ATTENDANCE BY ID WITH JOINED STAFF DETAILS
# ------------------------------------------------------------
@router.get("/attendance/{id}", response_model=Attendance)
async def get_attendance_by_id(id: int, current_user=Depends(require_roles(["hr"]))):
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
        WHERE a.id = %s
    """)
    try:
        record = await fetch_one(query, (id,))
        if not record:
            raise HTTPException(status_code=404, detail="Attendance record not found")
        return record
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch attendance record: {str(e)}")



# ------------------------------------------------------------
# UPDATE ATTENDANCE RECORD
# ------------------------------------------------------------
@router.patch("/attendance/{id}", response_model=dict)
async def update_attendance(
    id: int,
    payload: AttendanceBase,
    current_user=Depends(require_roles(["hr"]))
):
    update_fields = []
    params = []

    if payload.staff_id is not None:
        update_fields.append("staff_id = %s")
        params.append(payload.staff_id)
    if payload.date is not None:
        update_fields.append("date = %s")
        params.append(payload.date)
    if payload.checkin_time is not None:
        update_fields.append("checkin_time = %s")
        params.append(payload.checkin_time)
    if payload.checkout_time is not None:
        update_fields.append("checkout_time = %s")
        params.append(payload.checkout_time)
    if payload.status is not None:
        update_fields.append("status = %s")
        params.append(payload.status)

    # ✅ Automatically set updated_by from token
    updated_by = current_user.get("id")
    if updated_by:
        update_fields.append("updated_by = %s")
        params.append(updated_by)

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    set_clause = ", ".join(update_fields)
    query = textwrap.dedent(f"""
        UPDATE public.attendance_details
        SET {set_clause}
        WHERE id = %s
        RETURNING *
    """)

    params.append(id)

    try:
        result = await execute(query, params)
        if not result:
            raise HTTPException(status_code=404, detail="Attendance record not found")
        return {"message": "Attendance updated successfully", "attendance": result}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update attendance: {str(e)}")


# ------------------------------------------------------------
# DELETE ATTENDANCE RECORD
# ------------------------------------------------------------
@router.delete("/attendance/{id}", response_model=dict)
async def delete_attendance(id: int, current_user=Depends(require_roles(["hr"]))):
    query = textwrap.dedent("""
        DELETE FROM public.attendance_details
        WHERE id = %s
        RETURNING id
    """)
    try:
        result = await execute(query, (id,))
        if not result:
            raise HTTPException(status_code=404, detail="Attendance record not found")
        return {"message": "Attendance record deleted successfully", "id": id}
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to delete attendance record: {str(e)}")
