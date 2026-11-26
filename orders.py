# --- 3. POST 路由：送出訂單與購物車結帳 ---
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List, Literal, Optional
import sqlite3

router = APIRouter(prefix="/orders", tags=["Orders"])
class CartItem(BaseModel):
    item_id: int
    quantity: int

class OrderRequest(BaseModel):
    student_id: str          # 👈 新增：學號欄位
    customer_name: str       # 👈 新增：姓名欄位
    items: List[CartItem]

AllowedOrderStatus = Literal["製作中", "可取餐", "已取消"]

class OrderStatusUpdate(BaseModel):
    status: AllowedOrderStatus
    estimated_completion_time: Optional[str] = None

def ensure_orders_table(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            total_price INTEGER NOT NULL,
            status TEXT DEFAULT '製作中',
            estimated_completion_time TEXT,
            created_at TEXT NOT NULL
        )
    """)

    python -m uvicorn main:app --reloadcursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price INTEGER NOT NULL
        )
    """)
    
    cursor.execute("PRAGMA table_info(orders)")
    columns = {row["name"] for row in cursor.fetchall()}
    if "status" not in columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN status TEXT DEFAULT '製作中'")
    if "estimated_completion_time" not in columns:
        cursor.execute("ALTER TABLE orders ADD COLUMN estimated_completion_time TEXT")
    conn.commit()


def get_db_connection():
    conn = sqlite3.connect("shop.db")
    conn.row_factory = sqlite3.Row
    ensure_orders_table(conn)
    return conn

@router.post("", status_code=status.HTTP_201_CREATED, summary="提交訂單與購物車結帳")
def create_order(order: OrderRequest):
    # 1. 後端檢查項目：檢查營業時間 (暫時註解)
    # current_hour = datetime.now().hour
    # if not (9 <= current_hour < 21):
    #     raise HTTPException(status_code=400, detail="目前非營業時間，無法接單。")

    conn = get_db_connection()
    cursor = conn.cursor()

    total_price = 0
    order_details = []

    try:
        for item in order.items:
            # 2. 後端檢查項目：檢查品項是否存在與上架狀態
            cursor.execute("SELECT * FROM menu WHERE id = ? AND is_available = 1", (item.item_id,))
            db_item = cursor.fetchone()
            if not db_item:
                raise HTTPException(status_code=404, detail=f"商品 ID {item.item_id} 不存在或已下架。")

            subtotal = db_item["price"] * item.quantity
            total_price += subtotal
            order_details.append((item.item_id, item.quantity, db_item["price"]))

        # 3. 寫入訂單主檔（包含學號與姓名）
        cursor.execute(
            "INSERT INTO orders (student_id, customer_name, total_price, created_at) VALUES (?, ?, ?, ?)",
            (order.student_id, order.customer_name, total_price, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        order_id = cursor.lastrowid

        # 4. 寫入訂單明細
        for item_id, quantity, price in order_details:
            cursor.execute(
                "INSERT INTO order_items (order_id, item_id, quantity, price) VALUES (?, ?, ?, ?)",
                (order_id, item_id, quantity, price)
            )

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return {
        "status": "success",
        "message": "訂單建立成功",
        "data": {
            "order_id": order_id,
            "student_id": order.student_id,
            "customer_name": order.customer_name,
            "total_price": total_price,
            "items_count": len(order.items)
        }
    }

  
@router.patch("/{order_id}/status", summary="更新訂單狀態與預計完成時間")
def update_order_status(order_id: int, update_data: OrderStatusUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
        order = cursor.fetchone()
        if not order:
            raise HTTPException(status_code=404, detail=f"找不到編號為 {order_id} 的訂單。")

        new_eta = (
            update_data.estimated_completion_time
            if update_data.estimated_completion_time is not None
            else order["estimated_completion_time"]
        )

        cursor.execute(
            """
            UPDATE orders
            SET status = ?, estimated_completion_time = ?
            WHERE id = ?
            """,
            (update_data.status, new_eta, order_id),
        )
        conn.commit()
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

    return {
        "status": "success",
        "message": f"訂單 #{order_id} 狀態已更新為：{update_data.status}",
        "data": {
            "order_id": order_id,
            "status": update_data.status,
            "estimated_completion_time": new_eta,
        },
    }