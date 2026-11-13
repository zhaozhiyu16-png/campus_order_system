# --- 3. POST 路由：送出訂單與購物車結帳 ---
from datetime import datetime
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import List
import sqlite3

router = APIRouter(prefix="/orders", tags=["Orders"])
class CartItem(BaseModel):
    item_id: int
    quantity: int

class OrderRequest(BaseModel):
    items: List[CartItem]

def get_db_connection():
    conn = sqlite3.connect("shop.db")
    conn.row_factory = sqlite3.Row
    return conn

@router.post("", status_code=status.HTTP_201_CREATED, summary="提交訂單與購物車結帳")
def create_order(order: OrderRequest):
    # 1. 後端檢查項目：檢查營業時間（假設營業時間為 09:00 - 21:00）
    current_hour = datetime.now().hour
    if not (9 <= current_hour < 21):
        raise HTTPException(status_code=400, detail="目前非營業時間，無法接單。")

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

        # 3. 寫入訂單主檔
        cursor.execute("INSERT INTO orders (total_price, created_at) VALUES (?, ?)", (total_price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        order_id = cursor.lastrowid

        # 4. 寫入訂單明細
        for item_id, quantity, price in order_details:
            cursor.execute("INSERT INTO order_items (order_id, item_id, quantity, price) VALUES (?, ?, ?, ?)", 
                           (order_id, item_id, quantity, price))

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
            "total_price": total_price,
            "items_count": len(order.items)
        }
    }