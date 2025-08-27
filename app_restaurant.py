from flask import Flask, request, jsonify, session, send_from_directory, Response
import mysql.connector
from mysql.connector import pooling
import db_config
from flask_cors import CORS
from datetime import datetime
import pytz
import uuid
import io
import csv

app = Flask(__name__)
app.secret_key = 'your_secret_key'
CORS(app)

# Define the IST timezone
ist = pytz.timezone('Asia/Kolkata')

# Load DB credentials
db_cred = db_config.db_config_cred_react_natvie()

# Connection pool
connection_pool = None

def initialize_connection_pool():
    global connection_pool
    try:
        connection_pool = pooling.MySQLConnectionPool(
            pool_name="restaurant_pool",
            pool_size=10,
            pool_reset_session=True,
            **db_cred
        )

    except Exception as e:

        connection_pool = None

def get_db_connection():
    if connection_pool is None:
        # Fallback to direct connection
        return mysql.connector.connect(**db_cred)
    return connection_pool.get_connection()

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    phone = data.get("phone")
    password = data.get("password")

    if not phone or not password:
        return jsonify({"success": False, "message": "Missing phone or password"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE phone = %s", (phone,))
    existing_user = cursor.fetchone()

    if existing_user:
        cursor.close()
        conn.close()
        return jsonify({"success": False, "message": "User already exists"}), 409

    cursor.execute("INSERT INTO users (phone, password) VALUES (%s, %s)", (phone, password))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({"success": True, "message": "Registration successful"}), 201


@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    phone = data.get("phone")
    password = data.get("password")

    if not phone or not password:
        return jsonify({"success": False, "message": "Missing Phone or password"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE phone = %s AND password = %s AND status = 'active'", (phone, password))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user:
        return jsonify({
            "success": True, 
            "message": "Awesome, you are logged in!",
            "name": user['name'],
            "user_uid": user['user_uid'],
            "parent_uid": user['parent_uid'],
            "role": user['role']
        })
    else:
        return jsonify({"success": False, "message": "Invalid credentials or account inactive"}), 401


@app.route('/menu', methods=['GET'])
def get_menu():
    try:
        org_id = request.args.get('org_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if org_id and manager_id:
            cursor.execute("SELECT * FROM menu WHERE item_status = 1 AND org_id = %s AND manager_id = %s", (org_id, manager_id))
        elif org_id:
            cursor.execute("SELECT * FROM menu WHERE item_status = 1 AND org_id = %s", (org_id,))
        else:
            cursor.execute("SELECT * FROM menu WHERE item_status = 1")
        
        menu_items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": menu_items})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error while fetching menu"}), 500

@app.route('/menu/all', methods=['GET'])
def get_all_menu():
    try:
        org_id = request.args.get('org_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
            SELECT m.*, u.name as manager_name 
            FROM menu m 
            LEFT JOIN users u ON m.manager_id = u.user_uid
        """
        
        conditions = []
        params = []
        
        if org_id:
            conditions.append("m.org_id = %s")
            params.append(org_id)
        
        if manager_id:
            conditions.append("m.manager_id = %s")
            params.append(manager_id)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY m.item_name"
        
        cursor.execute(query, params)
        menu_items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": menu_items})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error while fetching menu"}), 500

@app.route('/menu/update-status', methods=['POST'])
def update_menu_status():
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        item_status = data.get('item_status')
        org_id = data.get('org_id')
        manager_id = data.get('manager_id')
        
        if not item_id or item_status is None:
            return jsonify({"success": False, "message": "Missing item_id or item_status"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if org_id and manager_id:
            cursor.execute("UPDATE menu SET item_status = %s WHERE item_id = %s AND org_id = %s AND manager_id = %s", (item_status, item_id, org_id, manager_id))
        elif org_id:
            cursor.execute("UPDATE menu SET item_status = %s WHERE item_id = %s AND org_id = %s", (item_status, item_id, org_id))
        else:
            cursor.execute("UPDATE menu SET item_status = %s WHERE item_id = %s", (item_status, item_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item status updated"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/menu/update', methods=['POST'])
def update_menu_item():
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        item_name = data.get('item_name')
        item_price = data.get('item_price')
        item_cat = data.get('item_cat')
        item_status = data.get('item_status', 1)
        org_id = data.get('org_id')
        manager_id = data.get('manager_id')
        
        if not all([item_id, item_name, item_price, item_cat]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if org_id and manager_id:
            cursor.execute("""
                UPDATE menu SET item_name = %s, item_price = %s, item_cat = %s, item_status = %s 
                WHERE item_id = %s AND org_id = %s AND manager_id = %s
            """, (item_name, item_price, item_cat, item_status, item_id, org_id, manager_id))
        elif org_id:
            cursor.execute("""
                UPDATE menu SET item_name = %s, item_price = %s, item_cat = %s, item_status = %s 
                WHERE item_id = %s AND org_id = %s
            """, (item_name, item_price, item_cat, item_status, item_id, org_id))
        else:
            cursor.execute("""
                UPDATE menu SET item_name = %s, item_price = %s, item_cat = %s, item_status = %s 
                WHERE item_id = %s
            """, (item_name, item_price, item_cat, item_status, item_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/menu/add', methods=['POST'])
def add_menu_item():
    try:
        data = request.get_json()
        item_name = data.get('item_name')
        item_price = data.get('item_price')
        item_cat = data.get('item_cat')
        item_status = data.get('item_status', 1)
        org_id = data.get('org_id')
        manager_id = data.get('manager_id')
        
        if not all([item_name, item_price, item_cat, org_id, manager_id]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Generate new item_id - get max existing ID and increment
        cursor.execute("SELECT COALESCE(MAX(CAST(item_id AS UNSIGNED)), 0) as max_id FROM menu")
        result = cursor.fetchone()
        new_id = (result['max_id'] or 0) + 1
        
        cursor.execute("""
            INSERT INTO menu (item_id, item_name, item_price, item_cat, item_status, org_id, manager_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (str(new_id), item_name, item_price, item_cat, item_status, org_id, manager_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item added successfully", "item_id": str(new_id)})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/menu/upload-image/<item_id>', methods=['POST'])
def upload_menu_image(item_id):
    try:

        
        if 'image' not in request.files and 'image' not in request.form:
            return jsonify({"success": False, "message": "No image file found"}), 400
        
        if 'image' in request.files:
            file = request.files['image']
        else:
            # Handle form data - React Native sends raw binary data
            from io import BytesIO
            image_data = request.form['image']
            # Image data is already binary from React Native
            file = BytesIO(image_data.encode('latin1'))
            file.filename = f"{item_id}.png"

        
        if not file or file.filename == '':
            return jsonify({"success": False, "message": "No file selected"}), 400
        
        import os
        upload_folder = os.path.abspath('APP/Restaurant/menu_items')
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        
        filename = f"{item_id}.png"
        file_path = os.path.join(upload_folder, filename)
        
        if hasattr(file, 'save'):
            file.save(file_path)
        else:
            with open(file_path, 'wb') as f:
                f.write(file.getvalue())
        

        
        return jsonify({"success": True, "message": "Image uploaded successfully"})
    except Exception as e:

        return jsonify({"success": False, "message": f"Upload error: {str(e)}"}), 500

@app.route('/menu/delete/<item_id>', methods=['DELETE'])
def delete_menu_item(item_id):
    try:
        org_id = request.args.get('org_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Delete from database
        if org_id and manager_id:
            cursor.execute("DELETE FROM menu WHERE item_id = %s AND org_id = %s AND manager_id = %s", (item_id, org_id, manager_id))
        elif org_id:
            cursor.execute("DELETE FROM menu WHERE item_id = %s AND org_id = %s", (item_id, org_id))
        else:
            cursor.execute("DELETE FROM menu WHERE item_id = %s", (item_id,))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Item not found"}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Delete image file
        import os
        image_path = os.path.join('APP/Restaurant/menu_items', f"{item_id}.png")
        if os.path.exists(image_path):
            os.remove(image_path)
        
        return jsonify({"success": True, "message": "Item deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/APP/Restaurant/menu_items/<filename>')
def serve_image(filename):
    import os
    return send_from_directory('APP/Restaurant/menu_items', filename)


@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        item_qty = data.get('item_qty')
        table_id = data.get('table_id')
        server_id = data.get('server_id')
        manager_id = data.get('manager_id')
        chef_id = data.get('chef_id', 1)
        status = data.get('status', 0)
        
        if not all([item_id, item_qty, table_id, server_id, manager_id]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check for existing item with status 0
        cursor.execute("""
            SELECT cart_id, item_qty FROM cart 
            WHERE table_id = %s AND server_id = %s AND item_id = %s AND status = 0
            ORDER BY order_created_at DESC LIMIT 1
        """, (table_id, server_id, item_id))
        
        existing_item = cursor.fetchone()
        
        if existing_item:
            # Update existing item - only update quantity and updated_at, leave created_at unchanged
            new_qty = existing_item['item_qty'] + item_qty
            current_time = datetime.now(ist)
            cursor.execute("""
                UPDATE cart SET item_qty = %s, order_updated_at = %s, order_created_at = order_created_at 
                WHERE cart_id = %s
            """, (new_qty, current_time, existing_item['cart_id']))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return jsonify({"success": True, "message": "Item updated", "data": {"cart_id": existing_item['cart_id']}})
        else:
            # Create new item
            # Check for existing active order for this table and server
            cursor.execute("""
                SELECT order_id FROM cart 
                WHERE table_id = %s AND server_id = %s AND status < 5 
                ORDER BY order_created_at DESC LIMIT 1
            """, (table_id, server_id))
            
            existing_order = cursor.fetchone()
            
            if existing_order:
                order_id = existing_order['order_id']
            else:
                # Generate new order_id
                cursor.execute("SELECT COUNT(*) as count FROM cart WHERE order_id LIKE 'ORD_%'")
                count_result = cursor.fetchone()
                order_number = count_result['count'] + 1
                order_id = f"ORD_{order_number}"
            
            # Generate unique cart_id
            cursor.execute("SELECT COUNT(*) as count FROM cart WHERE cart_id LIKE 'CRT_%'")
            count_result = cursor.fetchone()
            cart_number = count_result['count'] + 1
            cart_id = f"CRT_{cart_number}"
            
            current_time = datetime.now(ist)
            cursor.execute("""
                INSERT INTO cart (order_id, cart_id, item_id, item_qty, table_id, server_id, chef_id, manager_id, order_created_at, order_updated_at, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (order_id, cart_id, item_id, item_qty, table_id, server_id, chef_id, manager_id, current_time, current_time, status))
            
            conn.commit()
            cursor.close()
            conn.close()
            
            return jsonify({"success": True, "message": "Item added to cart", "data": {"cart_id": cart_id, "order_id": order_id}})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/update', methods=['POST'])
def update_cart():
    try:
        data = request.get_json()
        cart_id = data.get('cart_id')
        item_qty = data.get('item_qty')
        
        if not cart_id or not item_qty:
            return jsonify({"success": False, "message": "Missing cart_id or item_qty"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now(ist)
        cursor.execute("""
            UPDATE cart SET item_qty = %s, order_updated_at = %s, order_created_at = order_created_at WHERE cart_id = %s
        """, (item_qty, current_time, cart_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Cart updated"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/remove', methods=['POST'])
def remove_from_cart():
    try:
        data = request.get_json()
        cart_id = data.get('cart_id')
        
        if not cart_id:
            return jsonify({"success": False, "message": "Missing cart_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM cart WHERE cart_id = %s", (cart_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item removed from cart"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/items', methods=['GET'])
def get_cart_items():
    try:
        table_id = request.args.get('table_id')
        server_id = request.args.get('server_id')
        status_filter = request.args.get('status')
        include_menu = request.args.get('include_menu', 'false').lower() == 'true'
        org_id = request.args.get('org_id')
        
        if not table_id or not server_id:
            return jsonify({"success": False, "message": "Missing table_id or server_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        org_condition = " AND m.org_id = %s" if org_id and include_menu else ""
        
        if include_menu:
            base_query = f"""
                SELECT c.*, m.item_name, m.item_price 
                FROM cart c 
                JOIN menu m ON c.item_id = m.item_id 
                WHERE c.table_id = %s AND c.server_id = %s{org_condition}
            """
        else:
            base_query = """
                SELECT * FROM cart 
                WHERE table_id = %s AND server_id = %s
            """
        
        params = [table_id, server_id]
        if org_id and include_menu:
            params.append(org_id)
        
        if status_filter == 'pending':
            base_query += " AND c.status = 4" if include_menu else " AND status = 4"
        elif status_filter == 'menu':
            # Optimized query using window function
            if include_menu:
                base_query = """
                    SELECT c.*, m.item_name, m.item_price 
                    FROM (
                        SELECT *, ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY cart_id DESC) as rn
                        FROM cart 
                        WHERE table_id = %s AND server_id = %s AND status = 0
                    ) c
                    JOIN menu m ON c.item_id = m.item_id 
                    WHERE c.rn = 1
                """
            else:
                base_query = """
                    SELECT * FROM (
                        SELECT *, ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY cart_id DESC) as rn
                        FROM cart 
                        WHERE table_id = %s AND server_id = %s AND status = 0
                    ) c WHERE c.rn = 1
                """
        elif status_filter:
            base_query += " AND c.status = %s" if include_menu else " AND status = %s"
            params.append(int(status_filter))
        else:
            base_query += " AND c.status < 5" if include_menu else " AND status < 5"
        
        if status_filter != 'menu':
            base_query += " ORDER BY order_created_at DESC" if not include_menu else " ORDER BY c.order_created_at DESC"
        
        cursor.execute(base_query, params)
        items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": items})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/send-to-kitchen', methods=['POST'])
def send_to_kitchen():
    try:
        data = request.get_json()
        table_id = data.get('table_id')
        server_id = data.get('server_id')
        
        if not table_id or not server_id:
            return jsonify({"success": False, "message": "Missing table_id or server_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now(ist)
        cursor.execute("""
            UPDATE cart SET status = 1, order_updated_at = %s, order_created_at = order_created_at 
            WHERE table_id = %s AND server_id = %s AND status = 0
        """, (current_time, table_id, server_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Order sent to kitchen"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/send-selected-to-kitchen', methods=['POST'])
def send_selected_to_kitchen():
    try:
        data = request.get_json()
        cart_ids = data.get('cart_ids')
        
        if not cart_ids or not isinstance(cart_ids, list):
            return jsonify({"success": False, "message": "Missing or invalid cart_ids"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update selected items to status 1 (sent to kitchen)
        placeholders = ','.join(['%s'] * len(cart_ids))
        current_time = datetime.now(ist)
        cursor.execute(f"""
            UPDATE cart SET status = 1, order_updated_at = %s, order_created_at = order_created_at 
            WHERE cart_id IN ({placeholders}) AND status = 0
        """, [current_time] + cart_ids)
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Selected items sent to kitchen"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/mark-served', methods=['POST'])
def mark_served():
    try:
        data = request.get_json()
        cart_id = data.get('cart_id')
        
        if not cart_id:
            return jsonify({"success": False, "message": "Missing cart_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now(ist)
        cursor.execute("""
            UPDATE cart SET status = 4, order_updated_at = %s, order_created_at = order_created_at WHERE cart_id = %s
        """, (current_time, cart_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item marked as served"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/update-status', methods=['POST'])
def update_status():
    try:
        data = request.get_json()
        cart_id = data.get('cart_id')
        status = data.get('status')
        chef_id = data.get('chef_id')
        
        if not cart_id or status is None:
            return jsonify({"success": False, "message": "Missing cart_id or status"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now(ist)
        # If status is 2 (preparing) and chef_id is provided, update chef_id
        if status == 2 and chef_id:
            cursor.execute("""
                UPDATE cart SET status = %s, chef_id = %s, order_updated_at = %s, order_created_at = order_created_at WHERE cart_id = %s
            """, (status, chef_id, current_time, cart_id))
        else:
            cursor.execute("""
                UPDATE cart SET status = %s, order_updated_at = %s, order_created_at = order_created_at WHERE cart_id = %s
            """, (status, current_time, cart_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Status updated"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/kitchen/orders', methods=['GET'])
def get_kitchen_orders():
    try:
        manager_id = request.args.get('manager_id')
        org_id = request.args.get('org_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Only show items that are sent to kitchen (1), preparing (2), or ready (3)
        # Filter by manager_id and include server name
        if manager_id:
            if org_id:
                cursor.execute("""
                    SELECT c.*, m.item_name, m.item_price, u.name as server_name
                    FROM cart c 
                    JOIN menu m ON c.item_id = m.item_id 
                    JOIN users u ON c.server_id = u.user_uid
                    WHERE c.status IN (1, 2, 3) AND c.manager_id = %s AND m.org_id = %s
                    ORDER BY c.order_created_at ASC
                """, (manager_id, org_id))
            else:
                cursor.execute("""
                    SELECT c.*, m.item_name, m.item_price, u.name as server_name
                    FROM cart c 
                    JOIN menu m ON c.item_id = m.item_id 
                    JOIN users u ON c.server_id = u.user_uid
                    WHERE c.status IN (1, 2, 3) AND c.manager_id = %s
                    ORDER BY c.order_created_at ASC
                """, (manager_id,))
        else:
            if org_id:
                cursor.execute("""
                    SELECT c.*, m.item_name, m.item_price, u.name as server_name
                    FROM cart c 
                    JOIN menu m ON c.item_id = m.item_id 
                    JOIN users u ON c.server_id = u.user_uid
                    WHERE c.status IN (1, 2, 3) AND m.org_id = %s
                    ORDER BY c.order_created_at ASC
                """, (org_id,))
            else:
                cursor.execute("""
                    SELECT c.*, m.item_name, m.item_price, u.name as server_name
                    FROM cart c 
                    JOIN menu m ON c.item_id = m.item_id 
                    JOIN users u ON c.server_id = u.user_uid
                    WHERE c.status IN (1, 2, 3)
                    ORDER BY c.order_created_at ASC
                """)
        
        orders = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": orders})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500



@app.route('/cart/send-to-bill', methods=['POST'])
def send_to_bill():
    try:
        data = request.get_json()
        table_id = data.get('table_id')
        server_id = data.get('server_id')
        customer_name = data.get('customer_name')
        customer_phone = data.get('customer_phone')
        
        if not table_id or not server_id:
            return jsonify({"success": False, "message": "Missing table_id or server_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get the order_id for this table and server
        cursor.execute("""
            SELECT DISTINCT order_id FROM cart 
            WHERE table_id = %s AND server_id = %s AND status = 4
            LIMIT 1
        """, (table_id, server_id))
        
        order_result = cursor.fetchone()
        
        if order_result and (customer_name or customer_phone):
            order_id = order_result['order_id']
            
            # Save customer information if provided
            cursor.execute("""
                INSERT INTO customer_info (order_id, customer_name, customer_phone) 
                VALUES (%s, %s, %s)
            """, (order_id, customer_name, customer_phone))
        
        current_time = datetime.now(ist)
        # Update all served items to billed status (5)
        cursor.execute("""
            UPDATE cart SET status = 5, order_updated_at = %s, order_created_at = order_created_at 
            WHERE table_id = %s AND server_id = %s AND status = 4
        """, (current_time, table_id, server_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Order sent to bill"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/notification/send', methods=['POST'])
def send_notification():
    try:
        data = request.get_json()
        server_id = data.get('server_id')
        message = data.get('message')
        table_id = data.get('table_id')
        
        if not all([server_id, message, table_id]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        

        
        return jsonify({"success": True, "message": "Notification sent"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/dashboard_insights/overview', methods=['GET'])
def dashboard_insights_overview():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        server_id = request.args.get('server_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if from_date and to_date:
            date_condition = "DATE(c.order_created_at) BETWEEN %s AND %s"
            params = [from_date, to_date]
        else:
            current_date = datetime.now(ist).date()
            date_condition = "DATE(c.order_created_at) = %s"
            params = [current_date]
        
        # Add server filter if provided
        server_condition = ""
        if server_id:
            server_condition = " AND (c.server_id = %s OR c.chef_id = %s)"
            params.extend([server_id, server_id])
        elif manager_id:
            server_condition = " AND c.server_id IN (SELECT user_uid FROM users WHERE parent_uid = %s)"
            params.append(manager_id)
        
        # Total orders - only status 6 (completed)
        cursor.execute(f"""
            SELECT COUNT(DISTINCT order_id) as total_orders,
                   COUNT(*) as total_items,
                   COALESCE(SUM(c.item_qty * m.item_price), 0) as total_revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 6{server_condition}
        """, params)
        overview = cursor.fetchone()
        
        # Ensure overview has default values if null
        if not overview or overview['total_orders'] is None:
            overview = {
                'total_orders': 0,
                'total_items': 0,
                'total_revenue': 0
            }
        
        # Orders by status
        cursor.execute(f"""
            SELECT status, COUNT(*) as count
            FROM cart c
            WHERE {date_condition} AND status = 6{server_condition}
            GROUP BY status
        """, params)
        status_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True, 
            "data": {
                "overview": overview,
                "status_breakdown": status_data
            }
        })
    except Exception as e:

        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/dashboard_insights/popular_items', methods=['GET'])
def dashboard_insights_popular_items():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        server_id = request.args.get('server_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if from_date and to_date:
            date_condition = "DATE(c.order_created_at) BETWEEN %s AND %s"
            params = [from_date, to_date]
        else:
            current_date = datetime.now(ist).date()
            date_condition = "DATE(c.order_created_at) = %s"
            params = [current_date]
        
        # Add server/manager filter if provided
        filter_condition = ""
        if server_id:
            filter_condition = " AND (c.server_id = %s OR c.chef_id = %s)"
            params.extend([server_id, server_id])
        elif manager_id:
            filter_condition = " AND c.server_id IN (SELECT user_uid FROM users WHERE parent_uid = %s)"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT m.item_name, SUM(c.item_qty) as total_quantity,
                   COUNT(*) as order_count,
                   SUM(c.item_qty * m.item_price) as revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 6{filter_condition}
            GROUP BY c.item_id, m.item_name
            ORDER BY total_quantity DESC
            LIMIT 10
        """, params)
        popular_items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": popular_items})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/dashboard_insights/hourly_orders', methods=['GET'])
def dashboard_insights_hourly_orders():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        server_id = request.args.get('server_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if from_date and to_date:
            date_condition = "DATE(c.order_created_at) BETWEEN %s AND %s"
            params = [from_date, to_date]
        else:
            current_date = datetime.now(ist).date()
            date_condition = "DATE(c.order_created_at) = %s"
            params = [current_date]
        
        # Add server/manager filter if provided
        filter_condition = ""
        if server_id:
            filter_condition = " AND (c.server_id = %s OR c.chef_id = %s)"
            params.extend([server_id, server_id])
        elif manager_id:
            filter_condition = " AND c.server_id IN (SELECT user_uid FROM users WHERE parent_uid = %s)"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT HOUR(c.order_created_at) as hour,
                   COUNT(DISTINCT c.order_id) as orders,
                   COUNT(*) as items,
                   SUM(c.item_qty * m.item_price) as revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 6{filter_condition}
            GROUP BY HOUR(c.order_created_at)
            ORDER BY hour
        """, params)
        hourly_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": hourly_data})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/dashboard_insights/table_performance', methods=['GET'])
def dashboard_insights_table_performance():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        server_id = request.args.get('server_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if from_date and to_date:
            date_condition = "DATE(c.order_created_at) BETWEEN %s AND %s"
            params = [from_date, to_date]
        else:
            current_date = datetime.now(ist).date()
            date_condition = "DATE(c.order_created_at) = %s"
            params = [current_date]
        
        # Add server/manager filter if provided
        filter_condition = ""
        if server_id:
            filter_condition = " AND (c.server_id = %s OR c.chef_id = %s)"
            params.extend([server_id, server_id])
        elif manager_id:
            filter_condition = " AND c.server_id IN (SELECT user_uid FROM users WHERE parent_uid = %s)"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT c.table_id,
                   COUNT(DISTINCT c.order_id) as total_orders,
                   COUNT(*) as total_items,
                   SUM(c.item_qty * m.item_price) as revenue,
                   AVG(c.item_qty * m.item_price) as avg_order_value
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 6{filter_condition}
            GROUP BY c.table_id
            ORDER BY revenue DESC
        """, params)
        table_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": table_data})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/dashboard_insights/server_performance', methods=['GET'])
def dashboard_insights_server_performance():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        server_id = request.args.get('server_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if from_date and to_date:
            date_condition = "DATE(c.order_created_at) BETWEEN %s AND %s"
            params = [from_date, to_date]
        else:
            current_date = datetime.now(ist).date()
            date_condition = "DATE(c.order_created_at) = %s"
            params = [current_date]
        
        # Add server/manager filter if provided
        filter_condition = ""
        if server_id:
            filter_condition = " AND (c.server_id = %s OR c.chef_id = %s)"
            params.extend([server_id, server_id])
        elif manager_id:
            filter_condition = " AND c.server_id IN (SELECT user_uid FROM users WHERE parent_uid = %s)"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT u.name as server_name, c.server_id,
                   COUNT(DISTINCT c.order_id) as total_orders,
                   COUNT(*) as total_items,
                   SUM(c.item_qty * m.item_price) as revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            LEFT JOIN users u ON c.server_id = u.user_uid
            WHERE {date_condition} AND c.status = 6{filter_condition}
            GROUP BY c.server_id, u.name
            ORDER BY revenue DESC
        """, params)
        server_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": server_data})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/dashboard_insights/payment_mode_revenue', methods=['GET'])
def dashboard_insights_payment_mode_revenue():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        server_id = request.args.get('server_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if from_date and to_date:
            date_condition = "DATE(c.order_created_at) BETWEEN %s AND %s"
            params = [from_date, to_date]
        else:
            current_date = datetime.now(ist).date()
            date_condition = "DATE(c.order_created_at) = %s"
            params = [current_date]
        
        # Add server filter if provided
        server_condition = ""
        if server_id:
            server_condition = " AND (c.server_id = %s OR c.chef_id = %s)"
            params.extend([server_id, server_id])
        elif manager_id:
            server_condition = " AND c.server_id IN (SELECT user_uid FROM users WHERE parent_uid = %s)"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT pm.mode as payment_mode,
                   SUM(c.item_qty * m.item_price) as revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            JOIN payment_mode pm ON c.order_id = pm.order_id
            WHERE {date_condition} AND c.status = 6{server_condition}
            GROUP BY pm.mode
            ORDER BY revenue DESC
        """, params)
        payment_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": payment_data})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/dashboard_insights/status_counts', methods=['GET'])
def dashboard_insights_status_counts():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        server_id = request.args.get('server_id')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if from_date and to_date:
            date_condition = "DATE(order_created_at) BETWEEN %s AND %s"
            params = [from_date, to_date]
        else:
            current_date = datetime.now(ist).date()
            date_condition = "DATE(order_created_at) = %s"
            params = [current_date]
        
        # Add server/manager filter if provided
        filter_condition = ""
        if server_id:
            filter_condition = " AND (server_id = %s OR chef_id = %s)"
            params.extend([server_id, server_id])
        elif manager_id:
            filter_condition = " AND server_id IN (SELECT user_uid FROM users WHERE parent_uid = %s)"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT 
                CASE 
                    WHEN status = 0 THEN 'Cart'
                    WHEN status = 1 THEN 'Kitchen'
                    WHEN status = 2 THEN 'Preparing'
                    WHEN status = 3 THEN 'Ready'
                    WHEN status = 4 THEN 'Served'
                    WHEN status = 5 THEN 'Billed'
                    WHEN status = 6 THEN 'Completed'
                    ELSE 'Unknown'
                END as status_name,
                status,
                COUNT(DISTINCT order_id) as count
            FROM cart
            WHERE {date_condition}{filter_condition}
            GROUP BY status
            ORDER BY status
        """, params)
        status_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": status_data})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/categories/popular', methods=['GET'])
def get_popular_categories():
    try:
        org_id = request.args.get('org_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if org_id:
            cursor.execute("""
                SELECT m.item_cat as category, 
                       SUM(c.item_qty) as total_quantity,
                       COUNT(DISTINCT c.order_id) as total_orders,
                       SUM(c.item_qty * m.item_price) as revenue
                FROM cart c
                JOIN menu m ON c.item_id = m.item_id
                WHERE c.status = 5 AND m.org_id = %s
                GROUP BY m.item_cat
                ORDER BY total_quantity DESC
            """, (org_id,))
        else:
            cursor.execute("""
                SELECT m.item_cat as category, 
                       SUM(c.item_qty) as total_quantity,
                       COUNT(DISTINCT c.order_id) as total_orders,
                       SUM(c.item_qty * m.item_price) as revenue
                FROM cart c
                JOIN menu m ON c.item_id = m.item_id
                WHERE c.status = 5
                GROUP BY m.item_cat
                ORDER BY total_quantity DESC
            """)
        categories = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": categories})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/add_member', methods=['POST'])
def add_member():
    try:
        data = request.get_json()
        name = data.get('name')
        phone = data.get('phone')
        password = data.get('password')
        area = data.get('area')
        pincode = data.get('pincode')
        user_id = data.get('user_id')
        parent_uid = data.get('parent_uid')
        org = data.get('org')
        status = data.get('status', 'active')
        role = data.get('role')  # Role must be provided
        org_name = data.get('org_name')
        org_address = data.get('org_address')
        org_phone = data.get('org_phone')
        org_gst = data.get('org_gst')
        org_fssai = data.get('org_fssai')
        org_table_nos = data.get('org_table_nos', 20)
        

        
        if not all([name, phone, password, area, pincode, user_id, parent_uid, role]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Check user limit for roles 3 and 4
        if role in [3, 4]:
            # Get user limit from clients table using org
            cursor.execute("SELECT no_of_users FROM clients WHERE org_id = %s", (org,))
            client_result = cursor.fetchone()
            if not client_result:
                cursor.close()
                conn.close()
                return jsonify({"success": False, "message": "Client configuration not found"}), 404
            
            user_limit = client_result['no_of_users']
            
            # Count existing users under this org
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE org = %s AND role IN (3, 4)", (org,))
            count_result = cursor.fetchone()
            current_count = count_result['count'] if count_result else 0
            
            if current_count >= user_limit:
                cursor.close()
                conn.close()
                return jsonify({"success": False, "message": f"User limit exceeded. Maximum {user_limit} users allowed."}), 400
        
        # Check if phone already exists
        cursor.execute("SELECT user_uid FROM users WHERE phone = %s", (phone,))
        phone_result = cursor.fetchone()
        if phone_result:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "Phone number already exists"}), 409
        
        # Check if user_id already exists
        cursor.execute("SELECT user_uid FROM users WHERE user_uid = %s", (user_id,))
        uid_result = cursor.fetchone()
        if uid_result:
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "User ID already exists"}), 409
        
        # Set org based on role
        if role == 2:  # Client
            final_org = user_id  # For clients, org = user_uid
        else:  # Manager or Staff
            final_org = org  # For others, use the org of the user adding them
        
        # Insert new member
        cursor.execute("""
            INSERT INTO users (user_uid, name, phone, password, area, pincode, parent_uid, org, status, role)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, name, phone, password, area, pincode, parent_uid, final_org, status, role))
        
        # Insert into clients table and org_info table if role is 2 (client)
        if role == 2:
            no_of_users = data.get('no_of_users', 0)
            cursor.execute("""
                INSERT INTO clients (name, org_id, no_of_users)
                VALUES (%s, %s, %s)
            """, (name, final_org, no_of_users))
            
            # Insert organization info if provided
            if org_name and org_address and org_phone:
                cursor.execute("""
                    INSERT INTO org_info (org_id, org_name, org_address, org_phone, org_gst, org_fssai, org_table_nos, org_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (final_org, org_name, org_address, org_phone, org_gst, org_fssai, org_table_nos, 1))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Member added successfully"})
    except Exception as e:

        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/user/<int:user_uid>', methods=['GET'])
def get_user(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT * FROM users WHERE user_uid = %s", (user_uid,))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user:
            return jsonify({
                "success": True,
                "data": {
                    "user_uid": user['user_uid'],
                    "name": user['name'],
                    "phone": user['phone'],
                    "parent_uid": user['parent_uid'],
                    "role": user['role'],
                    "area": user.get('area'),
                    "pincode": user.get('pincode'),
                    "org": user.get('org'),
                    "status": user.get('status')
                }
            })
        else:
            return jsonify({"success": False, "message": "User not found"}), 404
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/biller/orders', methods=['GET'])
def get_biller_orders():
    try:
        manager_id = request.args.get('manager_id')
        org_id = request.args.get('org_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get orders with status 5 (sent to bill) grouped by order_id with customer info and server name
        if manager_id:
            if org_id:
                cursor.execute("""
                    SELECT c.order_id, c.table_id, c.server_id, c.order_created_at,
                           c.item_id, SUM(c.item_qty) as item_qty,
                           m.item_name, m.item_price,
                           (SUM(c.item_qty) * m.item_price) as total,
                           ci.customer_name, ci.customer_phone,
                           u.name as server_name,
                           MIN(c.cart_id) as cart_id
                    FROM cart c
                    JOIN menu m ON c.item_id = m.item_id
                    JOIN users u ON c.server_id = u.user_uid
                    LEFT JOIN customer_info ci ON c.order_id = ci.order_id
                    WHERE c.status = 5 AND c.manager_id = %s AND m.org_id = %s
                    GROUP BY c.order_id, c.table_id, c.server_id, c.order_created_at, 
                             c.item_id, m.item_name, m.item_price, 
                             ci.customer_name, ci.customer_phone, u.name
                    ORDER BY c.order_created_at DESC, c.order_id
                """, (manager_id, org_id))
            else:
                cursor.execute("""
                    SELECT c.order_id, c.table_id, c.server_id, c.order_created_at,
                           c.item_id, SUM(c.item_qty) as item_qty,
                           m.item_name, m.item_price,
                           (SUM(c.item_qty) * m.item_price) as total,
                           ci.customer_name, ci.customer_phone,
                           u.name as server_name,
                           MIN(c.cart_id) as cart_id
                    FROM cart c
                    JOIN menu m ON c.item_id = m.item_id
                    JOIN users u ON c.server_id = u.user_uid
                    LEFT JOIN customer_info ci ON c.order_id = ci.order_id
                    WHERE c.status = 5 AND c.manager_id = %s
                    GROUP BY c.order_id, c.table_id, c.server_id, c.order_created_at, 
                             c.item_id, m.item_name, m.item_price, 
                             ci.customer_name, ci.customer_phone, u.name
                    ORDER BY c.order_created_at DESC, c.order_id
                """, (manager_id,))
        else:
            if org_id:
                cursor.execute("""
                    SELECT c.order_id, c.table_id, c.server_id, c.order_created_at,
                           c.item_id, SUM(c.item_qty) as item_qty,
                           m.item_name, m.item_price,
                           (SUM(c.item_qty) * m.item_price) as total,
                           ci.customer_name, ci.customer_phone,
                           u.name as server_name,
                           MIN(c.cart_id) as cart_id
                    FROM cart c
                    JOIN menu m ON c.item_id = m.item_id
                    JOIN users u ON c.server_id = u.user_uid
                    LEFT JOIN customer_info ci ON c.order_id = ci.order_id
                    WHERE c.status = 5 AND m.org_id = %s
                    GROUP BY c.order_id, c.table_id, c.server_id, c.order_created_at, 
                             c.item_id, m.item_name, m.item_price, 
                             ci.customer_name, ci.customer_phone, u.name
                    ORDER BY c.order_created_at DESC, c.order_id
                """, (org_id,))
            else:
                cursor.execute("""
                    SELECT c.order_id, c.table_id, c.server_id, c.order_created_at,
                           c.item_id, SUM(c.item_qty) as item_qty,
                           m.item_name, m.item_price,
                           (SUM(c.item_qty) * m.item_price) as total,
                           ci.customer_name, ci.customer_phone,
                           u.name as server_name,
                           MIN(c.cart_id) as cart_id
                    FROM cart c
                    JOIN menu m ON c.item_id = m.item_id
                    JOIN users u ON c.server_id = u.user_uid
                    LEFT JOIN customer_info ci ON c.order_id = ci.order_id
                    WHERE c.status = 5
                    GROUP BY c.order_id, c.table_id, c.server_id, c.order_created_at, 
                             c.item_id, m.item_name, m.item_price, 
                             ci.customer_name, ci.customer_phone, u.name
                    ORDER BY c.order_created_at DESC, c.order_id
                """)
        
        cart_items = cursor.fetchall()
        
        # Group items by order_id
        orders = {}
        for item in cart_items:
            order_id = item['order_id']
            if order_id not in orders:
                orders[order_id] = {
                    'order_id': order_id,
                    'table_id': item['table_id'],
                    'server_id': item['server_id'],
                    'server_name': item['server_name'],
                    'order_created_at': item['order_created_at'].isoformat() if item['order_created_at'] else None,
                    'customer_name': item['customer_name'],
                    'customer_phone': item['customer_phone'],
                    'items': [],
                    'total_amount': 0
                }
            
            orders[order_id]['items'].append({
                'cart_id': item['cart_id'],
                'item_name': item['item_name'],
                'item_qty': item['item_qty'],
                'item_price': item['item_price'],
                'total': item['total']
            })
            orders[order_id]['total_amount'] += item['total']
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": list(orders.values())})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/payment/mode', methods=['POST'])
def save_payment_mode():
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        mode = data.get('mode')
        org_id = data.get('org_id')
        billed_by = data.get('billed_by')
        
        if not all([order_id, mode, org_id, billed_by]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO payment_mode (order_id, mode, org_id, billed_by) 
            VALUES (%s, %s, %s, %s)
        """, (order_id, mode, org_id, billed_by))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Payment mode saved"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/biller/complete-order', methods=['POST'])
def complete_order():
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        
        if not order_id:
            return jsonify({"success": False, "message": "Missing order_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now(ist)
        # Update order status to 6 (completed)
        cursor.execute("""
            UPDATE cart SET status = 6, order_updated_at = %s, order_created_at = order_created_at 
            WHERE order_id = %s AND status = 5
        """, (current_time, order_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Order completed successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/completed_orders', methods=['GET'])
def get_completed_orders():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        manager_id = request.args.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Build date condition
        if from_date and to_date:
            date_condition = "DATE(c.order_created_at) BETWEEN %s AND %s AND"
            params = [from_date, to_date]
        else:
            current_date = datetime.now(ist).date()
            date_condition = "DATE(c.order_created_at) = %s AND"
            params = [current_date]
        
        org_id = request.args.get('org_id')
        
        # Get completed orders with their items
        if manager_id:
            # For managers (role 3), only show orders from their staff
            if org_id:
                cursor.execute(f"""
                    SELECT c.order_id, c.table_id, c.order_created_at,
                           c.cart_id, c.item_id, c.item_qty,
                           m.item_name, m.item_price,
                           (c.item_qty * m.item_price) as total
                    FROM cart c
                    JOIN menu m ON c.item_id = m.item_id
                    JOIN users u ON c.server_id = u.user_uid
                    WHERE {date_condition} c.status = 6 AND u.parent_uid = %s AND m.org_id = %s
                    ORDER BY c.order_created_at DESC, c.order_id
                """, params + [manager_id, org_id])
            else:
                cursor.execute(f"""
                    SELECT c.order_id, c.table_id, c.order_created_at,
                           c.cart_id, c.item_id, c.item_qty,
                           m.item_name, m.item_price,
                           (c.item_qty * m.item_price) as total
                    FROM cart c
                    JOIN menu m ON c.item_id = m.item_id
                    JOIN users u ON c.server_id = u.user_uid
                    WHERE {date_condition} c.status = 6 AND u.parent_uid = %s
                    ORDER BY c.order_created_at DESC, c.order_id
                """, params + [manager_id])
        else:
            if org_id:
                cursor.execute(f"""
                    SELECT c.order_id, c.table_id, c.order_created_at,
                           c.cart_id, c.item_id, c.item_qty,
                           m.item_name, m.item_price,
                           (c.item_qty * m.item_price) as total
                    FROM cart c
                    JOIN menu m ON c.item_id = m.item_id
                    WHERE {date_condition} c.status = 6 AND m.org_id = %s
                    ORDER BY c.order_created_at DESC, c.order_id
                """, params + [org_id])
            else:
                cursor.execute(f"""
                    SELECT c.order_id, c.table_id, c.order_created_at,
                           c.cart_id, c.item_id, c.item_qty,
                           m.item_name, m.item_price,
                           (c.item_qty * m.item_price) as total
                    FROM cart c
                    JOIN menu m ON c.item_id = m.item_id
                    WHERE {date_condition} c.status = 6
                    ORDER BY c.order_created_at DESC, c.order_id
                """, params)
        
        cart_items = cursor.fetchall()
        
        # Group items by order_id
        orders_dict = {}
        for item in cart_items:
            order_id = item['order_id']
            if order_id not in orders_dict:
                orders_dict[order_id] = {
                    'id': len(orders_dict) + 1,  # Simple ID for frontend
                    'order_id': order_id,
                    'table_number': str(item['table_id']),
                    'created_at': item['order_created_at'].isoformat() if item['order_created_at'] else None,
                    'items': [],
                    'total_amount': 0
                }
            
            orders_dict[order_id]['items'].append({
                'item_name': item['item_name'],
                'quantity': item['item_qty'],
                'price': float(item['item_price']),
                'total': float(item['total'])
            })
            orders_dict[order_id]['total_amount'] += float(item['total'])
        
        orders = list(orders_dict.values())
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'orders': orders
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/menu/categories', methods=['GET'])
def get_categories():
    try:
        org_id = request.args.get('org_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if org_id:
            cursor.execute("SELECT DISTINCT item_cat FROM menu WHERE item_cat IS NOT NULL AND item_cat != '' AND org_id = %s ORDER BY item_cat", (org_id,))
        else:
            cursor.execute("SELECT DISTINCT item_cat FROM menu WHERE item_cat IS NOT NULL AND item_cat != '' ORDER BY item_cat")
        categories = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        category_list = [cat['item_cat'] for cat in categories]
        return jsonify({"success": True, "data": category_list})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/org/info', methods=['GET'])
def get_org_info():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT org_id, org_name, org_address, org_gst, org_fssai, org_phone, org_status FROM org_info WHERE org_status = 1 LIMIT 1")
        org_info = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": org_info})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/org/tables/<user_uid>', methods=['GET'])
def get_org_tables(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT oi.org_table_nos 
            FROM users u 
            JOIN org_info oi ON u.org = oi.org_id 
            WHERE u.user_uid = %s
        """, (user_uid,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return jsonify({
                'success': True,
                'data': {
                    'org_table_nos': result['org_table_nos']
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'User or organization not found'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/org/info/<user_uid>', methods=['GET'])
def get_org_info_by_user(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT oi.org_name, oi.org_address, oi.org_phone, oi.org_gst, oi.org_fssai 
            FROM users u 
            JOIN org_info oi ON u.org = oi.org_id 
            WHERE u.user_uid = %s
        """, (user_uid,))
        
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if result:
            return jsonify({
                'success': True,
                'data': {
                    'org_name': result['org_name'],
                    'org_address': result['org_address'],
                    'org_phone': result['org_phone'],
                    'org_gst': result['org_gst'],
                    'org_fssai': result['org_fssai']
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'User or organization not found'
            }), 404
            
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

@app.route('/export/orders', methods=['POST'])
def export_orders():
    try:
        data = request.get_json()
        from_date = data.get('from_date')
        to_date = data.get('to_date')
        export_type = data.get('export_type', 'full')
        
        if not from_date or not to_date:
            return jsonify({"success": False, "message": "Missing from_date or to_date"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get org name for filename
        cursor.execute("SELECT org_name FROM org_info WHERE org_status = 1 LIMIT 1")
        org_result = cursor.fetchone()
        org_name = org_result['org_name'].replace(' ', '_') if org_result else 'Restaurant'
        
        if export_type == 'summary':
            # Summary export query
            query = """
                SELECT DISTINCT
                    c.order_id,
                    us.name as server_name,
                    uc.name as chef_name,
                    SUM(c.item_qty * m.item_price) as bill_amount,
                    pm.mode as payment_mode,
                    c.order_updated_at as order_completed_date,
                    ci.customer_name,
                    ci.customer_phone
                FROM cart c
                JOIN menu m ON c.item_id = m.item_id
                LEFT JOIN users us ON c.server_id = us.user_uid
                LEFT JOIN users uc ON c.chef_id = uc.user_uid
                LEFT JOIN payment_mode pm ON c.order_id = pm.order_id
                LEFT JOIN customer_info ci ON c.order_id = ci.order_id
                WHERE DATE(c.order_created_at) BETWEEN %s AND %s 
                AND c.status = 6
                GROUP BY c.order_id, us.name, uc.name, pm.mode, c.order_updated_at, ci.customer_name, ci.customer_phone
                ORDER BY c.order_updated_at DESC
            """
            
            cursor.execute(query, [from_date, to_date])
            results = cursor.fetchall()
            
            if not results:
                conn.close()
                return jsonify({"success": False, "message": "No data found for the selected dates"}), 404
            
            # Convert to CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Order ID', 'Customer Name', 'Customer Phone', 'Server Name', 'Chef Name', 'Bill Amount', 'Payment Mode', 'Order Completed Date'])
            
            # Write data
            for row in results:
                writer.writerow([
                    row['order_id'],
                    row['customer_name'] or 'N/A',
                    row['customer_phone'] or 'N/A',
                    row['server_name'] or 'N/A',
                    row['chef_name'] or 'N/A',
                    row['bill_amount'],
                    row['payment_mode'] or 'N/A',
                    row['order_completed_date']
                ])
            
            filename = f"{org_name}_summary_export_{from_date}_{to_date}.csv"
        else:
            # Full export query (existing)
            query = """
                SELECT 
                    c.order_id,
                    c.table_id,
                    u.name as server_name,
                    m.item_name,
                    m.item_cat,
                    c.item_qty,
                    m.item_price,
                    (c.item_qty * m.item_price) as total_price,
                    DATE(c.order_created_at) as order_date,
                    TIME(c.order_created_at) as order_time,
                    CASE 
                        WHEN c.status = 6 THEN 'Completed'
                        WHEN c.status = 5 THEN 'Billed'
                        WHEN c.status = 4 THEN 'Served'
                        ELSE 'Other'
                    END as status
                FROM cart c
                JOIN menu m ON c.item_id = m.item_id
                LEFT JOIN users u ON c.server_id = u.user_uid
                WHERE DATE(c.order_created_at) BETWEEN %s AND %s 
                AND c.status = 6
                ORDER BY c.order_created_at DESC, c.order_id
            """
            
            cursor.execute(query, [from_date, to_date])
            results = cursor.fetchall()
            
            if not results:
                conn.close()
                return jsonify({"success": False, "message": "No data found for the selected dates"}), 404
            
            # Convert to CSV
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write header
            writer.writerow(['Order ID', 'Table', 'Server', 'Item Name', 'Category', 'Quantity', 'Unit Price', 'Total Price', 'Order Date', 'Order Time', 'Status'])
            
            # Write data
            for row in results:
                writer.writerow([
                    row['order_id'],
                    row['table_id'],
                    row['server_name'] or 'N/A',
                    row['item_name'],
                    row['item_cat'],
                    row['item_qty'],
                    row['item_price'],
                    row['total_price'],
                    row['order_date'],
                    row['order_time'],
                    row['status']
                ])
            
            filename = f"{org_name}_full_export_{from_date}_{to_date}.csv"
        
        conn.close()
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-disposition": f"attachment; filename={filename}"}
        )
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Export error: {str(e)}"}), 500

# Get users by role
@app.route('/users', methods=['GET'])
def get_users():
    try:
        role = request.args.get('role')
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if role:
            cursor.execute("SELECT user_uid, name, role FROM users WHERE role = %s", (role,))
        else:
            cursor.execute("SELECT user_uid, name, role FROM users")
        
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'users': users
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Get attendance data for a user
@app.route('/attendance/<user_id>', methods=['GET'])
def get_attendance(user_id):
    try:
        year = request.args.get('year')
        month = request.args.get('month')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        query = """
        SELECT DATE(order_created_at) as order_date, SUM(item_qty) as item_count
        FROM cart 
        WHERE (server_id = %s OR chef_id = %s)
        AND YEAR(order_created_at) = %s 
        AND MONTH(order_created_at) = %s
        GROUP BY DATE(order_created_at)
        """
        
        cursor.execute(query, (user_id, user_id, year, month))
        results = cursor.fetchall()
        
        attendance = {}
        for row in results:
            attendance[row['order_date'].strftime('%Y-%m-%d')] = row['item_count']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'attendance': attendance
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Staff management endpoints
@app.route('/staff', methods=['GET'])
def get_staff():
    try:
        parent_uid = request.args.get('parent_uid')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if parent_uid:
            cursor.execute("""
                SELECT s.user_uid, s.name, s.phone, s.area, s.pincode, s.status, s.parent_uid, m.name as manager_name
                FROM users s
                LEFT JOIN users m ON s.parent_uid = m.user_uid
                WHERE s.role = 4 AND s.parent_uid = %s
            """, (parent_uid,))
        else:
            cursor.execute("""
                SELECT s.user_uid, s.name, s.phone, s.area, s.pincode, s.status, s.parent_uid, m.name as manager_name
                FROM users s
                LEFT JOIN users m ON s.parent_uid = m.user_uid
                WHERE s.role = 4
            """)
        
        staff = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'data': staff})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/managers', methods=['GET'])
def get_managers():
    try:
        org_id = request.args.get('org_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if org_id:
            cursor.execute("SELECT user_uid, name, phone, area, pincode, status FROM users WHERE role = 3 AND org = %s", (org_id,))
        else:
            cursor.execute("SELECT user_uid, name, phone, area, pincode, status FROM users WHERE role = 3")
        
        managers = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'data': managers})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# Client management endpoints
@app.route('/clients', methods=['GET'])
def get_clients():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT u.user_uid, u.name, u.phone, u.area, u.pincode, u.status, u.org, u.password, c.no_of_users,
                   oi.org_name, oi.org_address, oi.org_phone, oi.org_gst, oi.org_fssai, oi.org_table_nos
            FROM users u
            LEFT JOIN clients c ON u.user_uid = c.org_id
            LEFT JOIN org_info oi ON u.user_uid = oi.org_id
            WHERE u.role = 2
        """)
        clients = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'data': clients})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/clients/update', methods=['POST'])
def update_client():
    try:
        data = request.get_json()
        user_uid = data.get('user_uid')
        name = data.get('name')
        phone = data.get('phone')
        area = data.get('area')
        pincode = data.get('pincode')
        password = data.get('password')
        status = data.get('status')
        org = data.get('org', 1)
        org_name = data.get('org_name')
        org_address = data.get('org_address')
        org_phone = data.get('org_phone')
        org_gst = data.get('org_gst')
        org_fssai = data.get('org_fssai')
        org_table_nos = data.get('org_table_nos', 20)
        
        if not all([user_uid, name, phone, area, pincode]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if password:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, password = %s, status = %s
                WHERE user_uid = %s AND role = 2
            """, (name, phone, area, pincode, password, status, user_uid))
        else:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, status = %s
                WHERE user_uid = %s AND role = 2
            """, (name, phone, area, pincode, status, user_uid))
        
        # Update clients table if no_of_users is provided
        no_of_users = data.get('no_of_users')
        if no_of_users:
            cursor.execute("""
                UPDATE clients SET no_of_users = %s WHERE org_id = %s
            """, (no_of_users, user_uid))
        
        # Update org_info table if organization data is provided
        if org_name or org_address or org_phone:
            # Check if org_info record exists
            cursor.execute("SELECT org_id FROM org_info WHERE org_id = %s", (user_uid,))
            existing_org = cursor.fetchone()
            
            if existing_org:
                # Update existing record
                cursor.execute("""
                    UPDATE org_info SET 
                    org_name = %s, org_address = %s, org_phone = %s, 
                    org_gst = %s, org_fssai = %s, org_table_nos = %s
                    WHERE org_id = %s
                """, (org_name, org_address, org_phone, org_gst, org_fssai, org_table_nos, user_uid))
            else:
                # Insert new record
                cursor.execute("""
                    INSERT INTO org_info (org_id, org_name, org_address, org_phone, org_gst, org_fssai, org_table_nos, org_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (user_uid, org_name, org_address, org_phone, org_gst, org_fssai, org_table_nos, 1))
        
        # Cascade status change to managers and staff based on org id
        if status == 'inactive':
            # Deactivate all managers and staff with org = client's user_uid
            cursor.execute("""
                UPDATE users SET status = 'inactive' 
                WHERE org = %s AND role IN (3, 4)
            """, (user_uid,))
        elif status == 'active':
            # Activate all managers and staff with org = client's user_uid
            cursor.execute("""
                UPDATE users SET status = 'active' 
                WHERE org = %s AND role IN (3, 4)
            """, (user_uid,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Client updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/clients/delete/<user_uid>', methods=['DELETE'])
def delete_client(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM users WHERE user_uid = %s AND role = 2", (user_uid,))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Client not found'}), 404
        
        cursor.execute("DELETE FROM clients WHERE org_id = %s", (user_uid,))
        cursor.execute("DELETE FROM org_info WHERE org_id = %s", (user_uid,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Client deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/staff/update', methods=['POST'])
def update_staff():
    try:
        data = request.get_json()
        user_uid = data.get('user_uid')
        name = data.get('name')
        phone = data.get('phone')
        area = data.get('area')
        pincode = data.get('pincode')
        password = data.get('password')
        status = data.get('status')
        
        if not all([user_uid, name, phone, area, pincode]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if password:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, password = %s, status = %s
                WHERE user_uid = %s AND role = 4
            """, (name, phone, area, pincode, password, status, user_uid))
        else:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, status = %s
                WHERE user_uid = %s AND role = 4
            """, (name, phone, area, pincode, status, user_uid))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Staff updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/staff/delete/<user_uid>', methods=['DELETE'])
def delete_staff(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM users WHERE user_uid = %s AND role = 4", (user_uid,))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Staff not found'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Staff deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/users-left/<org_id>', methods=['GET'])
def get_users_left(org_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get user limit from clients table
        cursor.execute("SELECT no_of_users FROM clients WHERE org_id = %s", (org_id,))
        client_result = cursor.fetchone()
        
        if not client_result:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Client not found'}), 404
        
        user_limit = client_result['no_of_users']
        
        # Count existing users under this org
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE org = %s AND role IN (3, 4)", (org_id,))
        count_result = cursor.fetchone()
        current_count = count_result['count'] if count_result else 0
        
        users_left = max(0, user_limit - current_count)
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True, 
            'users_left': users_left,
            'total_limit': user_limit,
            'current_count': current_count
        })
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/managers/update', methods=['POST'])
def update_manager():
    try:
        data = request.get_json()
        user_uid = data.get('user_uid')
        name = data.get('name')
        phone = data.get('phone')
        area = data.get('area')
        pincode = data.get('pincode')
        password = data.get('password')
        status = data.get('status')
        
        if not all([user_uid, name, phone, area, pincode]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if password:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, password = %s, status = %s
                WHERE user_uid = %s AND role = 3
            """, (name, phone, area, pincode, password, status, user_uid))
        else:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, status = %s
                WHERE user_uid = %s AND role = 3
            """, (name, phone, area, pincode, status, user_uid))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Manager updated successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/managers/delete/<user_uid>', methods=['DELETE'])
def delete_manager(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM users WHERE user_uid = %s AND role = 3", (user_uid,))
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'message': 'Manager not found'}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Manager deleted successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/', methods=['GET'])
def home():
    return "<h1>Welcome to Restaurant Flask API</h1><p>API is running successfully!</p>"

@app.route('/client-dashboard', methods=['GET'])
def get_client_dashboard():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all clients with organization info
        cursor.execute("""
            SELECT 
                c.name,
                c.org_id,
                c.no_of_users,
                u.created_at as onboard_date,
                oi.org_name,
                oi.org_address as address,
                oi.org_phone as phone
            FROM clients c
            LEFT JOIN users u ON c.org_id = u.user_uid AND u.role = 2
            LEFT JOIN org_info oi ON c.org_id = oi.org_id
            ORDER BY c.name
        """)
        
        clients = cursor.fetchall()
        
        # Format the data with separate queries for counts
        formatted_clients = []
        for client in clients:
            org_id = client['org_id']
            
            # Count managers
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE org = %s AND role = 3", (org_id,))
            managers_result = cursor.fetchone()
            managers_count = managers_result['count'] if managers_result else 0
            
            # Count staff
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE org = %s AND role = 4", (org_id,))
            staff_result = cursor.fetchone()
            staff_count = staff_result['count'] if staff_result else 0
            
            # Calculate revenue
            cursor.execute("""
                SELECT COALESCE(SUM(cart.item_qty * menu.item_price), 0) as revenue
                FROM cart 
                JOIN menu ON cart.item_id = menu.item_id 
                JOIN users u3 ON cart.server_id = u3.user_uid 
                WHERE u3.org = %s AND cart.status = 6
            """, (org_id,))
            revenue_result = cursor.fetchone()
            total_revenue = revenue_result['revenue'] if revenue_result else 0
            
            formatted_clients.append({
                'name': client['name'],
                'org_id': client['org_id'],
                'no_of_users': client['no_of_users'],
                'managers_count': managers_count,
                'staff_count': staff_count,
                'total_revenue': float(total_revenue) if total_revenue else 0,
                'onboard_date': client['onboard_date'].strftime('%Y-%m-%d') if client['onboard_date'] else 'N/A',
                'org_name': client['org_name'],
                'address': client['address'],
                'phone': client['phone']
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'data': formatted_clients})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Server error: {str(e)}'}), 500

if __name__ == '__main__':
    initialize_connection_pool()
    app.run(host='0.0.0.0', port=5000, debug=True)
