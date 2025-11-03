from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from ..core.security import require_roles
from ..db.pool import fetch_one, fetch_all, execute
from pydantic import BaseModel
from datetime import date, datetime
import textwrap
import traceback

router = APIRouter(prefix="/accounts", tags=["accounts"])

# ------------------------------------------------------------
# Pydantic Models
# ------------------------------------------------------------

class DailySalesReportBase(BaseModel):
    total_sales_order: Optional[int]
    total_sale_order_amount: Optional[float]
    sale_order_collection: Optional[float]
    sale_order_balance_amount: Optional[float]
    total_day_collection: Optional[float]
    total_amount_on_cash: Optional[float]
    total_amount_on_ac: Optional[float]
    iob: Optional[float]
    cd: Optional[float]
    anil: Optional[float]
    remya: Optional[float]
    rgb_186_swiping_machine: Optional[float]
    amaze_ac: Optional[float]
    cheque: Optional[float]

    date: Optional[date]          # <-- NO = None
    created_by: Optional[int]     # <-- NO = None
    updated_by: Optional[int]     # <-- NO = None
    status: Optional[str]         # <-- NO = None


# class DailySalesReportCreate(DailySalesReportBase):
#     date: date
#     total_sales_order: int

class DailySalesReportCreate(BaseModel):
    date: date  # Required
    total_sales_order: Optional[int] = None
    total_sale_order_amount: Optional[float] = None
    sale_order_collection: Optional[float] = None
    sale_order_balance_amount: Optional[float] = None
    total_day_collection: Optional[float] = None
    total_amount_on_cash: Optional[float] = None
    total_amount_on_ac: Optional[float] = None
    iob: Optional[float] = None
    cd: Optional[float] = None
    anil: Optional[float] = None
    remya: Optional[float] = None
    rgb_186_swiping_machine: Optional[float] = None
    amaze_ac: Optional[float] = None
    cheque: Optional[float] = None
    status: Optional[str] = "active"

class DailySalesReport(DailySalesReportBase):
    id: int
    created_on: Optional[datetime]

    class Config:
        orm_mode = True


# ------------------------------------------------------------
# CREATE DAILY SALES REPORT
# ------------------------------------------------------------
@router.post("/daily_sales_report", response_model=dict)
async def create_daily_sales_report(
    payload: DailySalesReportCreate,
    current_user=Depends(require_roles(["accounts"]))
):
    try:
        created_by = current_user.get("id")
        if not created_by:
            raise HTTPException(status_code=401, detail="Invalid or missing user ID")

        updated_by = created_by

        query = textwrap.dedent("""
            INSERT INTO public.daily_sales_report (
                total_sales_order, total_sale_order_amount, sale_order_collection,
                sale_order_balance_amount, total_day_collection, total_amount_on_cash,
                total_amount_on_ac, iob, cd, anil, remya, rgb_186_swiping_machine,
                amaze_ac, cheque, date, created_by, updated_by, status
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
            )
            RETURNING *
        """)

        params = [
            payload.total_sales_order,
            payload.total_sale_order_amount,
            payload.sale_order_collection,
            payload.sale_order_balance_amount,
            payload.total_day_collection,
            payload.total_amount_on_cash,
            payload.total_amount_on_ac,
            payload.iob,
            payload.cd,
            payload.anil,
            payload.remya,
            payload.rgb_186_swiping_machine,
            payload.amaze_ac,
            payload.cheque,
            payload.date,
            created_by,
            updated_by,
            payload.status,
        ]

        result = await execute(query, params)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to create daily sales report")

        return {"message": "Daily sales report created successfully", "report": result}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error creating report: {str(e)}")






# ------------------------------------------------------------
# GET ALL DAILY SALES REPORTS
# ------------------------------------------------------------
@router.get("/daily_sales_report", response_model=List[DailySalesReport])
async def get_all_reports(current_user=Depends(require_roles(["accounts","admin"]))):
    query = textwrap.dedent("""
        SELECT * FROM public.daily_sales_report
        ORDER BY id DESC
    """)
    try:
        records = await fetch_all(query)
        return records
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch reports: {str(e)}")


# ------------------------------------------------------------
# GET DAILY SALES REPORT BY ID
# ------------------------------------------------------------
@router.get("/daily_sales_report/{id}", response_model=DailySalesReport)
async def get_report_by_id(id: int, current_user=Depends(require_roles(["accounts","admin"]))):
    query = textwrap.dedent("""
        SELECT * FROM public.daily_sales_report
        WHERE id = %s
    """)
    try:
        record = await fetch_one(query, (id,))
        if not record:
            raise HTTPException(status_code=404, detail="Daily sales report not found")
        return record
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch report: {str(e)}")


# ------------------------------------------------------------
# UPDATE DAILY SALES REPORT
# ------------------------------------------------------------
@router.patch("/daily_sales_report/{id}", response_model=dict)
async def update_report(
    id: int,
    payload: DailySalesReportBase,
    current_user=Depends(require_roles(["accounts"]))
):
    try:
        updated_by = current_user.get("id")
        if not updated_by:
            raise HTTPException(status_code=401, detail="Invalid or missing user ID")

        update_fields = []
        params = []

        for field, value in payload.dict(exclude_unset=True).items():
            update_fields.append(f"{field} = %s")
            params.append(value)

        # Always update the 'updated_by' column
        update_fields.append("updated_by = %s")
        params.append(updated_by)

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields provided to update")

        query = f"""
            UPDATE public.daily_sales_report
            SET {', '.join(update_fields)}
            WHERE id = %s
            RETURNING *
        """
        params.append(id)

        result = await execute(query, params)
        if not result:
            raise HTTPException(status_code=404, detail="Daily sales report not found")

        return {"message": "Report updated successfully", "report": result}

    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update report: {str(e)}")

# ------------------------------------------------------------
# DELETE DAILY SALES REPORT
# ------------------------------------------------------------
@router.delete("/daily_sales_report/{id}", response_model=dict)
async def delete_report(id: int, current_user=Depends(require_roles(["accounts","admin"]))):
    query = textwrap.dedent("""
        DELETE FROM public.daily_sales_report
        WHERE id = %s
        RETURNING id
    """)
    try:
        result = await execute(query, (id,))
        if not result:
            raise HTTPException(status_code=404, detail="Report not found")
        return {"message": "Report deleted successfully", "id": id}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {str(e)}")
