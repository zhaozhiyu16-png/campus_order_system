from datetime import datetime
from typing import List, Optional
import sqlite3
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

router = APIRouter(prefix="/orders", tags=["Orders"])


class CartItem(BaseModel):
  item_id: int
  quantity: int


class OrderRequest(BaseModel):
  student_id: Optional[str] = ""
  student_name: Optional[str] = ""
  pickup_time: Optional[str] = "儘快取餐"
  note: Optional[str] = ""
  items: List[CartItem]


def get_db_connection():
  conn = sqlite3.connect("shop.db")
  conn.row_factory = sqlite3.Row
  return conn


def ensure_orders_schema(cursor):
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT DEFAULT '',
            student_name TEXT DEFAULT '',
            pickup_time TEXT DEFAULT '儘快取餐',
            note TEXT DEFAULT '',
            status TEXT DEFAULT '待接單',
            total_price INTEGER NOT NULL,
            created_at TEXT
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            item_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price INTEGER NOT NULL
        )
    """)
  cursor.execute("PRAGMA table_info(orders)")
  existing_cols = {row["name"] for row in cursor.fetchall()}
  extra_columns = {
      "student_id": "TEXT DEFAULT ''",
      "student_name": "TEXT DEFAULT ''",
      "pickup_time": "TEXT DEFAULT '儘快取餐'",
      "note": "TEXT DEFAULT ''",
      "status": "TEXT DEFAULT '待接單'",
  }
  for col_name, col_def in extra_columns.items():
    if col_name not in existing_cols:
      cursor.execute(f"ALTER TABLE orders ADD COLUMN {col_name} {col_def}")


@router.post(
    "", status_code=status.HTTP_201_CREATED, summary="提交訂單與購物車結帳"
)
def create_order(order: OrderRequest):
  current_hour = datetime.now().hour
  if not (9 <= current_hour < 21):
    raise HTTPException(status_code=400, detail="目前非營業時間，無法接單。")

  if not order.items:
    raise HTTPException(status_code=400, detail="購物車不可為空。")

  conn = get_db_connection()
  cursor = conn.cursor()
  ensure_orders_schema(cursor)

  total_price = 0
  order_details = []

  try:
    for item in order.items:
      if item.quantity <= 0:
        raise HTTPException(status_code=400, detail="商品數量必須大於 0。")

      cursor.execute(
          "SELECT * FROM menu WHERE id = ? AND is_available = 1",
          (item.item_id,),
      )
      db_item = cursor.fetchone()
      if not db_item:
        raise HTTPException(
            status_code=404,
            detail=f"商品 ID {item.item_id} 不存在或已下架。",
        )

      subtotal = db_item["price"] * item.quantity
      total_price += subtotal
      order_details.append((item.item_id, item.quantity, db_item["price"]))

    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        """
            INSERT INTO orders (student_id, student_name, pickup_time, note, status, total_price, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
        (
            (order.student_id or "").strip(),
            (order.student_name or "").strip(),
            order.pickup_time or "儘快取餐",
            (order.note or "").strip(),
            "待接單",
            total_price,
            created_at,
        ),
    )
    order_id = cursor.lastrowid

    for item_id, quantity, price in order_details:
      cursor.execute(
          """
                INSERT INTO order_items (order_id, item_id, quantity, price)
                VALUES (?, ?, ?, ?)
                """,
          (order_id, item_id, quantity, price),
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
          "student_id": (order.student_id or "").strip(),
          "student_name": (order.student_name or "").strip(),
          "pickup_time": order.pickup_time or "儘快取餐",
          "note": (order.note or "").strip(),
          "status": "待接單",
          "total_price": total_price,
          "created_at": created_at,
          "items_count": len(order.items),
      },
  }


@router.get("", summary="依學號查詢個人訂單與製作狀態")
def get_student_orders(student_id: str):
  conn = get_db_connection()
  cursor = conn.cursor()
  ensure_orders_schema(cursor)

  cleaned_id = student_id.strip()
  cursor.execute(
      "SELECT * FROM orders WHERE student_id = ? ORDER BY id DESC",
      (cleaned_id,),
  )
  orders = cursor.fetchall()

  result_orders = []
  for row in orders:
    order_dict = dict(row)
    cursor.execute(
        """
            SELECT oi.item_id, oi.quantity, oi.price, m.name
            FROM order_items oi
            LEFT JOIN menu m ON oi.item_id = m.id
            WHERE oi.order_id = ?
            """,
        (row["id"],),
    )
    items_rows = cursor.fetchall()
    order_dict["items"] = [
        {
            "item_id": item_row["item_id"],
            "name": item_row["name"] or f"餐點 #{item_row['item_id']}",
            "quantity": item_row["quantity"],
            "price": item_row["price"],
        }
        for item_row in items_rows
    ]
    result_orders.append(order_dict)

  conn.close()

  if not result_orders:
    return {"student_id": cleaned_id, "message": "查無訂單紀錄", "orders": []}

  return {"student_id": cleaned_id, "orders": result_orders}


@router.get("/{order_id}", summary="查詢單筆訂單明細")
def get_single_order(order_id: int):
  conn = get_db_connection()
  cursor = conn.cursor()
  ensure_orders_schema(cursor)

  cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
  row = cursor.fetchone()
  if not row:
    conn.close()
    raise HTTPException(status_code=404, detail="找不到指定的訂單")

  order_dict = dict(row)
  cursor.execute(
      """
        SELECT oi.item_id, oi.quantity, oi.price, m.name
        FROM order_items oi
        LEFT JOIN menu m ON oi.item_id = m.id
        WHERE oi.order_id = ?
        """,
      (order_id,),
  )
  items_rows = cursor.fetchall()
  order_dict["items"] = [
      {
          "item_id": item_row["item_id"],
          "name": item_row["name"] or f"餐點 #{item_row['item_id']}",
          "quantity": item_row["quantity"],
          "price": item_row["price"],
      }
      for item_row in items_rows
  ]
  conn.close()
  return {"status": "success", "data": order_dict}


@router.delete("/{order_id}", summary="取消並刪除指定訂單")
def cancel_order(order_id: int):
  conn = get_db_connection()
  cursor = conn.cursor()
  ensure_orders_schema(cursor)

  cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,))
  row = cursor.fetchone()
  if not row:
    conn.close()
    raise HTTPException(status_code=404, detail="找不到指定的訂單")

  cursor.execute("DELETE FROM order_items WHERE order_id = ?", (order_id,))
  cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
  conn.commit()
  conn.close()

  return {"ok": True, "message": f"成功取消訂單編號 {order_id}"}