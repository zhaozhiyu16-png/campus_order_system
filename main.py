from datetime import datetime
import os
import sqlite3
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(
    title="校園小吃線上點餐系統 API",
    description="Asia University Campus Snack Ordering System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def init_db():
  conn = sqlite3.connect("shop.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS menu (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price INTEGER NOT NULL,
            is_available INTEGER DEFAULT 1,
            created_at TEXT
        )
    """)
  cursor.execute("SELECT COUNT(*) FROM menu")
  count = cursor.fetchone()[0]
  if count == 0:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    default_items = [
        ("香煎雞腿便當", 100, 1, now_str),
        ("香噴噴滷肉飯", 60, 1, now_str),
        ("酥脆炸雞腿", 75, 1, now_str),
        ("珍珠奶茶", 50, 1, now_str),
    ]
    cursor.executemany(
        "INSERT INTO menu (name, price, is_available, created_at) VALUES (?, ?, ?, ?)",
        default_items,
    )
  conn.commit()
  conn.close()


@app.on_event("startup")
def startup_event():
  init_db()


class MenuItemCreate(BaseModel):
  name: str
  price: int
  is_available: int = 1


@app.get("/menus", summary="列出所有開放中的餐點與價格")
def get_menus():
  conn = sqlite3.connect("shop.db")
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()
  cursor.execute("SELECT * FROM menu WHERE is_available = 1")
  rows = cursor.fetchall()
  conn.close()
  return {"status": "success", "data": [dict(row) for row in rows]}


@app.post(
    "/menus",
    status_code=status.HTTP_201_CREATED,
    summary="新增一筆餐點項目",
)
def create_menu_item(item: MenuItemCreate):
  if item.price <= 0:
    raise HTTPException(status_code=400, detail="餐點價格必須大於 0")

  created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

  conn = sqlite3.connect("shop.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO menu (name, price, is_available, created_at)
        VALUES (?, ?, ?, ?)
    """,
      (item.name, item.price, item.is_available, created_at),
  )
  conn.commit()
  new_id = cursor.lastrowid
  conn.close()

  return {
      "status": "success",
      "message": "餐點新增成功",
      "data": {
          "id": new_id,
          "name": item.name,
          "price": item.price,
          "is_available": item.is_available,
          "created_at": created_at,
      },
  }


from orders import router as orders_router

app.include_router(orders_router)

# 若專案資料夾內有 html 檔，直接掛載根目錄方便從瀏覽器開啟
base_dir = os.path.dirname(os.path.abspath(__file__))
app.mount("/", StaticFiles(directory=base_dir, html=True), name="static")