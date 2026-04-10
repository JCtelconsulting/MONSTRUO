
import sys
import os

sys.path.append(os.path.join(os.getcwd(), "code"))
from app.core.db import get_conn

def main():
    print("--- Syncing Many-to-Many Categories ---")
    conn = get_conn()
    try:
        # 1. Fetch all items with a valid category set in the main column
        cur = conn.execute("SELECT id, categoria_id FROM cat_items WHERE categoria_id IS NOT NULL AND categoria_id > 0")
        items = cur.fetchall()
        print(f"Found {len(items)} items to sync.")
        
        count = 0
        for item in items:
            item_id = item['id']
            cat_id = item['categoria_id']
            
            # Check if M2M matches (Strict 1:1 sync for this cleanup)
            # We want to ensure M2M has exactly this category.
            
            # First, check what's there
            cur_m2m = conn.execute("SELECT categoria_id FROM cat_item_categories WHERE item_id=?", (item_id,))
            rows = cur_m2m.fetchall()
            current_ids = [r['categoria_id'] for r in rows]
            
            if len(current_ids) == 1 and current_ids[0] == cat_id:
                continue # Already synced
                
            # Needs Sync: Delete all and insert correct one
            conn.execute("DELETE FROM cat_item_categories WHERE item_id=?", (item_id,))
            conn.execute("INSERT INTO cat_item_categories (item_id, categoria_id, created_at) VALUES (?, ?, NOW())", (item_id, cat_id))
            count += 1
            
            if count % 100 == 0:
                print(f"Synced {count} items...")
                
        conn.commit()
        print(f"Done. Synced {count} items.")

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    main()
