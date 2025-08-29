from flask import Flask, request, jsonify
import mysql.connector
from mysql.connector import pooling
import db_config
from flask_cors import CORS
from datetime import datetime
import pytz

app = Flask(__name__)
app.secret_key = 'billing_app_secret_key'
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
            pool_name="billing_pool",
            pool_size=10,
            pool_reset_session=True,
            **db_cred
        )
    except Exception as e:
        connection_pool = None

def get_db_connection():
    if connection_pool is None:
        return mysql.connector.connect(**db_cred)
    return connection_pool.get_connection()

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    phone = data.get("phone")
    password = data.get("password")

    if not phone or not password:
        return jsonify({"success": False, "message": "Missing phone or password"}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM users WHERE phone = %s AND password = %s AND status = 'active'", (phone, password))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user:
        return jsonify({
            "success": True, 
            "message": "Login successful!",
            "name": user['name'],
            "user_uid": user['user_uid'],
            "parent_uid": user['parent_uid'],
            "role": user['role'],
            "org": user['org']
        })
    else:
        return jsonify({"success": False, "message": "Invalid credentials or account inactive"}), 401

@app.route('/menu', methods=['GET'])
def get_menu():
    try:
        org_id = request.args.get('org_id')
        manager_id = request.args.get('manager_id')
        all_items = request.args.get('all_items', 'false').lower() == 'true'
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Base query without status filter if all_items=true
        status_condition = "" if all_items else "item_status = 1 AND "
        
        if org_id and manager_id:
            query = f"SELECT * FROM menu WHERE {status_condition}org_id = %s AND manager_id = %s"
            cursor.execute(query, (org_id, manager_id))
        elif org_id:
            query = f"SELECT * FROM menu WHERE {status_condition}org_id = %s"
            cursor.execute(query, (org_id,))
        else:
            query = f"SELECT * FROM menu WHERE {status_condition}1=1"
            cursor.execute(query)
        
        menu_items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": menu_items})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500



@app.route('/cart/add', methods=['POST'])
def add_to_cart():
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        item_qty = data.get('item_qty')
        manager_id = data.get('manager_id')
        
        if not all([item_id, item_qty, manager_id]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Check for existing pending order for this manager
        cursor.execute("SELECT order_id FROM cart WHERE manager_id = %s AND status = 0 LIMIT 1", (manager_id,))
        existing_order = cursor.fetchone()
        
        if existing_order:
            order_id = existing_order['order_id']
            
            # Check if item already exists in this order
            cursor.execute("SELECT cart_id, item_qty FROM cart WHERE order_id = %s AND item_id = %s", (order_id, item_id))
            existing_item = cursor.fetchone()
            
            if existing_item:
                # Update existing item quantity
                new_qty = existing_item['item_qty'] + item_qty
                cursor.execute("""
                    UPDATE cart SET item_qty = %s, order_updated_at = %s 
                    WHERE cart_id = %s
                """, (new_qty, datetime.now(ist), existing_item['cart_id']))
                cart_id = existing_item['cart_id']
            else:
                # Add new item to existing order
                cursor.execute("SELECT COUNT(*) as count FROM cart WHERE cart_id LIKE 'CRT_%'")
                count_result = cursor.fetchone()
                cart_number = count_result['count'] + 1
                cart_id = f"CRT_{cart_number}"
                
                current_time = datetime.now(ist)
                cursor.execute("""
                    INSERT INTO cart (order_id, cart_id, item_id, item_qty, order_created_at, order_updated_at, manager_id, status) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (order_id, cart_id, item_id, item_qty, current_time, current_time, manager_id, 0))
        else:
            # Create new order
            cursor.execute("SELECT COUNT(*) as count FROM cart WHERE order_id LIKE 'ORD_%'")
            count_result = cursor.fetchone()
            order_number = count_result['count'] + 1
            order_id = f"ORD_{order_number}"
            
            cursor.execute("SELECT COUNT(*) as count FROM cart WHERE cart_id LIKE 'CRT_%'")
            count_result = cursor.fetchone()
            cart_number = count_result['count'] + 1
            cart_id = f"CRT_{cart_number}"
            
            current_time = datetime.now(ist)
            cursor.execute("""
                INSERT INTO cart (order_id, cart_id, item_id, item_qty, order_created_at, order_updated_at, manager_id, status) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (order_id, cart_id, item_id, item_qty, current_time, current_time, manager_id, 0))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item added to cart", "data": {"cart_id": cart_id, "order_id": order_id}})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/items', methods=['GET'])
def get_cart_items():
    try:
        manager_id = request.args.get('manager_id')
        
        if not manager_id:
            return jsonify({"success": False, "message": "Missing manager_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT c.*, m.item_name, m.item_price 
            FROM cart c 
            JOIN menu m ON c.item_id = m.item_id 
            WHERE c.manager_id = %s AND c.status IN (0, 1)
            ORDER BY c.order_created_at DESC
        """, (manager_id,))
        
        cart_items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": cart_items})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/update', methods=['POST'])
def update_cart_item():
    try:
        data = request.get_json()
        cart_id = data.get('cart_id')
        item_qty = data.get('item_qty')
        
        if not cart_id or item_qty is None:
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if item_qty <= 0:
            cursor.execute("DELETE FROM cart WHERE cart_id = %s", (cart_id,))
        else:
            cursor.execute("""
                UPDATE cart SET item_qty = %s, order_updated_at = %s 
                WHERE cart_id = %s
            """, (item_qty, datetime.now(ist), cart_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Cart updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/checkout', methods=['POST'])
def checkout_order():
    try:
        data = request.get_json()
        manager_id = data.get('manager_id')
        
        if not manager_id:
            return jsonify({"success": False, "message": "Missing manager_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now(ist)
        cursor.execute("""
            UPDATE cart SET status = 1, order_updated_at = %s 
            WHERE manager_id = %s AND status = 0
        """, (current_time, manager_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Order checked out successfully"})
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
        
        if not order_id or not billed_by:
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Insert payment mode (mode can be null if not selected)
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

@app.route('/cart/print', methods=['POST'])
def print_order():
    try:
        data = request.get_json()
        manager_id = data.get('manager_id')
        payment_mode = data.get('payment_mode')
        
        if not manager_id:
            return jsonify({"success": False, "message": "Missing manager_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get the order_id for payment mode saving
        cursor.execute("SELECT DISTINCT order_id FROM cart WHERE manager_id = %s AND status = 1 LIMIT 1", (manager_id,))
        order_result = cursor.fetchone()
        
        if order_result:
            order_id = order_result['order_id']
            
            # Save payment mode if provided
            if payment_mode:
                cursor.execute("""
                    INSERT INTO payment_mode (order_id, mode, org_id, billed_by) 
                    VALUES (%s, %s, %s, %s)
                """, (order_id, payment_mode, None, manager_id))
        
        current_time = datetime.now(ist)
        cursor.execute("""
            UPDATE cart SET status = 2, order_updated_at = %s 
            WHERE manager_id = %s AND status = 1
        """, (current_time, manager_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Order printed successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/back-to-edit', methods=['POST'])
def back_to_edit():
    try:
        data = request.get_json()
        manager_id = data.get('manager_id')
        
        if not manager_id:
            return jsonify({"success": False, "message": "Missing manager_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now(ist)
        cursor.execute("""
            UPDATE cart SET status = 0, order_updated_at = %s 
            WHERE manager_id = %s AND status = 1
        """, (current_time, manager_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Order moved back to editing mode"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

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

@app.route('/dashboard_insights/overview', methods=['GET'])
def dashboard_insights_overview():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
        manager_id = request.args.get('manager_id')
      
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Always use date filter if provided, otherwise default to today
        if from_date and to_date:
            date_condition = "DATE(c.order_created_at) BETWEEN %s AND %s"
            params = [from_date, to_date]
        else:
            # Default to today's data (Asia/Kolkata timezone)
            current_date = datetime.now(ist).date()
            date_condition = "DATE(c.order_created_at) = %s"
            params = [current_date]
        
        # Add manager filter if provided
        manager_condition = ""
        if manager_id:
            manager_condition = " AND c.manager_id = %s"
            params.append(manager_id)
        
        # Total orders and items sold
        cursor.execute(f"""
            SELECT COUNT(DISTINCT order_id) as total_orders,
                   COUNT(*) as total_items,
                   COALESCE(SUM(c.item_qty * m.item_price), 0) as total_revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 2{manager_condition}
        """, params)
        overview = cursor.fetchone()
        
        # Ensure overview has default values if null
        if not overview or overview['total_orders'] is None:
            overview = {
                'total_orders': 0,
                'total_items': 0,
                'total_revenue': 0
            }
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True, 
            "data": {
                "overview": overview,
                "debug": {
                    "from_date": from_date,
                    "to_date": to_date,
                    "manager_id": manager_id,
                    "params": params
                }
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/dashboard_insights/popular_items', methods=['GET'])
def dashboard_insights_popular_items():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
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
        
        # Add manager filter if provided
        filter_condition = ""
        if manager_id:
            filter_condition = " AND c.manager_id = %s"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT m.item_name, SUM(c.item_qty) as total_quantity,
                   COUNT(*) as order_count,
                   SUM(c.item_qty * m.item_price) as revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 2{filter_condition}
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
        
        # Add manager filter if provided
        filter_condition = ""
        if manager_id:
            filter_condition = " AND c.manager_id = %s"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT HOUR(c.order_created_at) as hour,
                   COUNT(DISTINCT c.order_id) as orders,
                   COUNT(*) as items,
                   SUM(c.item_qty * m.item_price) as revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 2{filter_condition}
            GROUP BY HOUR(c.order_created_at)
            ORDER BY hour
        """, params)
        hourly_data = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": hourly_data})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/dashboard_insights/payment_mode_revenue', methods=['GET'])
def dashboard_insights_payment_mode_revenue():
    try:
        from_date = request.args.get('from_date')
        to_date = request.args.get('to_date')
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
        
        # Add manager filter if provided
        manager_condition = ""
        if manager_id:
            manager_condition = " AND c.manager_id = %s"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT pm.mode as payment_mode,
                   SUM(c.item_qty * m.item_price) as revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            JOIN payment_mode pm ON c.order_id = pm.order_id
            WHERE {date_condition} AND c.status = 2{manager_condition}
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
        
        # Add manager filter if provided
        filter_condition = ""
        if manager_id:
            filter_condition = " AND manager_id = %s"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT 
                CASE 
                    WHEN status = 0 THEN 'Cart'
                    WHEN status = 1 THEN 'Checked Out'
                    WHEN status = 2 THEN 'Completed'
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
        
        if not all([item_name, item_price, item_cat, org_id]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Generate item_id
        cursor.execute("SELECT COUNT(*) as count FROM menu WHERE item_id LIKE 'ITM_%'")
        count_result = cursor.fetchone()
        item_number = count_result[0] + 1
        item_id = f"ITM_{item_number}"
        
        current_time = datetime.now(ist)
        cursor.execute("""
            INSERT INTO menu (item_id, item_name, item_price, item_cat, item_status, org_id, manager_id, created_at) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (item_id, item_name, item_price, item_cat, item_status, org_id, manager_id, current_time))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item added successfully", "item_id": item_id})
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
        item_status = data.get('item_status')
        org_id = data.get('org_id')
        
        if not all([item_id, item_name, item_price, item_cat]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Try with updated_at first, fallback to without it
        try:
            current_time = datetime.now(ist)
            cursor.execute("""
                UPDATE menu SET item_name = %s, item_price = %s, item_cat = %s, item_status = %s, updated_at = %s 
                WHERE item_id = %s
            """, (item_name, item_price, item_cat, item_status, current_time, item_id))
        except:
            # If updated_at column doesn't exist, update without it
            cursor.execute("""
                UPDATE menu SET item_name = %s, item_price = %s, item_cat = %s, item_status = %s 
                WHERE item_id = %s
            """, (item_name, item_price, item_cat, item_status, item_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/menu/update-status', methods=['POST'])
def update_menu_item_status():
    try:
        data = request.get_json()
        item_id = data.get('item_id')
        item_status = data.get('item_status')
        org_id = data.get('org_id')
        
        if item_id is None or item_status is None:
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Try with updated_at first, fallback to without it
        try:
            current_time = datetime.now(ist)
            cursor.execute("""
                UPDATE menu SET item_status = %s, updated_at = %s 
                WHERE item_id = %s
            """, (item_status, current_time, item_id))
        except:
            # If updated_at column doesn't exist, update without it
            cursor.execute("""
                UPDATE menu SET item_status = %s 
                WHERE item_id = %s
            """, (item_status, item_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item status updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/menu/delete/<item_id>', methods=['DELETE'])
def delete_menu_item(item_id):
    try:
        org_id = request.args.get('org_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM menu WHERE item_id = %s", (item_id,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/menu/categories', methods=['GET'])
def get_menu_categories():
    try:
        org_id = request.args.get('org_id')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if org_id:
            cursor.execute("SELECT DISTINCT item_cat FROM menu WHERE org_id = %s AND item_status = 1", (org_id,))
        else:
            cursor.execute("SELECT DISTINCT item_cat FROM menu WHERE item_status = 1")
        
        categories = [row[0] for row in cursor.fetchall()]
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": categories})
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
        
        # Base query for completed orders (status = 2)
        base_query = """
            SELECT DISTINCT c.order_id, 
                   SUM(c.item_qty * m.item_price) as total_amount,
                   MIN(c.order_created_at) as order_created_at,
                   pm.mode as payment_mode
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            LEFT JOIN payment_mode pm ON c.order_id = pm.order_id
            WHERE c.status = 2
        """
        
        params = []
        conditions = []
        
        if from_date and to_date:
            conditions.append("DATE(c.order_created_at) BETWEEN %s AND %s")
            params.extend([from_date, to_date])
        
        if manager_id:
            conditions.append("c.manager_id = %s")
            params.append(manager_id)
        
        if conditions:
            base_query += " AND " + " AND ".join(conditions)
        
        base_query += " GROUP BY c.order_id, pm.mode ORDER BY MIN(c.order_created_at) DESC"
        
        cursor.execute(base_query, params)
        orders_data = cursor.fetchall()
        
        # Get items for each order
        orders = []
        for order in orders_data:
            cursor.execute("""
                SELECT m.item_name, c.item_qty, m.item_price, 
                       (c.item_qty * m.item_price) as total
                FROM cart c
                JOIN menu m ON c.item_id = m.item_id
                WHERE c.order_id = %s AND c.status = 2
            """, (order['order_id'],))
            
            items = cursor.fetchall()
            
            orders.append({
                'order_id': order['order_id'],
                'total_amount': float(order['total_amount']),
                'order_created_at': order['order_created_at'].isoformat() if order['order_created_at'] else None,
                'payment_mode': order['payment_mode'],
                'items': items
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "orders": orders})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/export/orders', methods=['POST'])
def export_orders():
    try:
        data = request.get_json()
        from_date = data.get('from_date')
        to_date = data.get('to_date')
        export_type = data.get('export_type', 'full')
        manager_id = data.get('manager_id')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if export_type == 'summary':
            # Summary export - order totals with payment info
            query = """
                SELECT c.order_id, 
                       SUM(c.item_qty * m.item_price) as total_amount,
                       MIN(c.order_created_at) as order_created_at,
                       pm.mode as payment_mode,
                       COUNT(c.item_id) as total_items
                FROM cart c
                JOIN menu m ON c.item_id = m.item_id
                LEFT JOIN payment_mode pm ON c.order_id = pm.order_id
                WHERE c.status = 2
            """
            
            params = []
            if from_date and to_date:
                query += " AND DATE(c.order_created_at) BETWEEN %s AND %s"
                params.extend([from_date, to_date])
            
            if manager_id:
                query += " AND c.manager_id = %s"
                params.append(manager_id)
            
            query += " GROUP BY c.order_id, pm.mode ORDER BY MIN(c.order_created_at) DESC"
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Generate CSV
            csv_content = "Order ID,Date,Total Amount,Payment Mode,Total Items\n"
            for row in results:
                csv_content += f"{row['order_id']},{row['order_created_at']},{row['total_amount']},{row['payment_mode'] or 'N/A'},{row['total_items']}\n"
            
        else:
            # Full export - all order details with items
            query = """
                SELECT c.order_id, c.order_created_at, m.item_name, 
                       c.item_qty, m.item_price, 
                       (c.item_qty * m.item_price) as item_total,
                       pm.mode as payment_mode
                FROM cart c
                JOIN menu m ON c.item_id = m.item_id
                LEFT JOIN payment_mode pm ON c.order_id = pm.order_id
                WHERE c.status = 2
            """
            
            params = []
            if from_date and to_date:
                query += " AND DATE(c.order_created_at) BETWEEN %s AND %s"
                params.extend([from_date, to_date])
            
            if manager_id:
                query += " AND c.manager_id = %s"
                params.append(manager_id)
            
            query += " ORDER BY c.order_created_at DESC, c.order_id"
            
            cursor.execute(query, params)
            results = cursor.fetchall()
            
            # Generate CSV
            csv_content = "Order ID,Date,Item Name,Quantity,Price,Item Total,Payment Mode\n"
            for row in results:
                csv_content += f"{row['order_id']},{row['order_created_at']},{row['item_name']},{row['item_qty']},{row['item_price']},{row['item_total']},{row['payment_mode'] or 'N/A'}\n"
        
        cursor.close()
        conn.close()
        
        # Return CSV as response
        filename = f"orders_{export_type}_{from_date}_{to_date}.csv"
        
        from flask import Response
        return Response(
            csv_content,
            mimetype='text/csv',
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Type': 'text/csv'
            }
        )
        
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

# Client Management Endpoints
@app.route('/clients', methods=['GET'])
def get_clients():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT u.user_uid, u.name, u.phone, u.area, u.pincode, u.status, u.org, u.password, c.no_of_users,
                   oi.org_name, oi.org_address, oi.org_phone, oi.org_gst, oi.org_fssai
            FROM users u
            LEFT JOIN clients c ON u.user_uid = c.org_id
            LEFT JOIN org_info oi ON u.user_uid = oi.org_id
            WHERE u.role = 2
            ORDER BY u.name
        """)
        
        clients = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": {"data": clients}})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/clients/update', methods=['POST'])
def update_client():
    try:
        data = request.get_json()
        user_uid = data.get('user_uid')
        name = data.get('name')
        phone = data.get('phone')
        area = data.get('area')
        pincode = data.get('pincode')
        status = data.get('status')
        password = data.get('password')
        no_of_users = data.get('no_of_users')
        org_name = data.get('org_name')
        org_address = data.get('org_address')
        org_phone = data.get('org_phone')
        org_gst = data.get('org_gst')
        org_fssai = data.get('org_fssai')
        org_id = data.get('org_id')
        
        if not all([user_uid, name, phone, area, pincode]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update user info
        if password:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, 
                                status = %s, password = %s
                WHERE user_uid = %s
            """, (name, phone, area, pincode, status, password, user_uid))
        else:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, status = %s
                WHERE user_uid = %s
            """, (name, phone, area, pincode, status, user_uid))
        
        # Update clients table if no_of_users is provided
        if no_of_users:
            cursor.execute("""
                UPDATE clients SET no_of_users = %s WHERE org_id = %s
            """, (no_of_users, user_uid))
        
        # Update org info if provided
        if org_id and org_name:
            cursor.execute("""
                UPDATE org_info SET org_name = %s, org_address = %s, org_phone = %s, 
                                   org_gst = %s, org_fssai = %s
                WHERE org_id = %s
            """, (org_name, org_address, org_phone, org_gst, org_fssai, org_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Client updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/clients/delete/<user_uid>', methods=['DELETE'])
def delete_client(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM users WHERE user_uid = %s AND role = 2", (user_uid,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Client deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

# Staff Management Endpoints
@app.route('/staff', methods=['GET'])
def get_staff():
    try:
        parent_uid = request.args.get('parent_uid')
        
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        if parent_uid:
            cursor.execute("""
                SELECT s.*, m.name as manager_name
                FROM users s
                LEFT JOIN users m ON s.parent_uid = m.user_uid
                WHERE s.role = 4 AND s.parent_uid = %s
                ORDER BY s.name
            """, (parent_uid,))
        else:
            cursor.execute("""
                SELECT s.*, m.name as manager_name
                FROM users s
                LEFT JOIN users m ON s.parent_uid = m.user_uid
                WHERE s.role = 4
                ORDER BY s.name
            """)
        
        staff = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": staff})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/managers', methods=['GET'])
def get_managers():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT * FROM users
            WHERE role = 3
            ORDER BY name
        """)
        
        managers = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": managers})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

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
        role = data.get('role')
        no_of_users = data.get('no_of_users')
        org_name = data.get('org_name')
        org_address = data.get('org_address')
        org_phone = data.get('org_phone')
        org_gst = data.get('org_gst')
        org_fssai = data.get('org_fssai')
        
        if not all([name, phone, password, area, pincode, user_id, role]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if user_id already exists
        cursor.execute("SELECT user_uid FROM users WHERE user_uid = %s", (user_id,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"success": False, "message": "User ID already exists"}), 400
        
        current_time = datetime.now(ist)
        
        # Insert user
        cursor.execute("""
            INSERT INTO users (user_uid, name, phone, password, area, pincode, 
                              parent_uid, org, status, role, no_of_users, created_at) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, name, phone, password, area, pincode, parent_uid, org, 
              status, role, no_of_users, current_time))
        
        # Insert into clients table and org_info table if role is 2 (client)
        if role == 2:
            cursor.execute("""
                INSERT INTO clients (name, org_id, no_of_users)
                VALUES (%s, %s, %s)
            """, (name, org, no_of_users))
            
            # Insert organization info if provided
            if org_name:
                cursor.execute("""
                    INSERT INTO org_info (org_id, org_name, org_address, org_phone, 
                                         org_gst, org_fssai, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (org, org_name, org_address, org_phone, org_gst, org_fssai, 
                      current_time))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Member added successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/staff/update', methods=['POST'])
def update_staff():
    try:
        data = request.get_json()
        user_uid = data.get('user_uid')
        name = data.get('name')
        phone = data.get('phone')
        area = data.get('area')
        pincode = data.get('pincode')
        status = data.get('status')
        password = data.get('password')
        
        if not all([user_uid, name, phone, area, pincode]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if password:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, 
                                status = %s, password = %s
                WHERE user_uid = %s AND role = 4
            """, (name, phone, area, pincode, status, password, user_uid))
        else:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, status = %s
                WHERE user_uid = %s AND role = 4
            """, (name, phone, area, pincode, status, user_uid))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Staff updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/managers/update', methods=['POST'])
def update_manager():
    try:
        data = request.get_json()
        user_uid = data.get('user_uid')
        name = data.get('name')
        phone = data.get('phone')
        area = data.get('area')
        pincode = data.get('pincode')
        status = data.get('status')
        password = data.get('password')
        
        if not all([user_uid, name, phone, area, pincode]):
            return jsonify({"success": False, "message": "Missing required fields"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if password:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, 
                                status = %s, password = %s
                WHERE user_uid = %s AND role = 3
            """, (name, phone, area, pincode, status, password, user_uid))
        else:
            cursor.execute("""
                UPDATE users SET name = %s, phone = %s, area = %s, pincode = %s, status = %s
                WHERE user_uid = %s AND role = 3
            """, (name, phone, area, pincode, status, user_uid))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Manager updated successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/staff/delete/<user_uid>', methods=['DELETE'])
def delete_staff(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM users WHERE user_uid = %s AND role = 4", (user_uid,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Staff deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/managers/delete/<user_uid>', methods=['DELETE'])
def delete_manager(user_uid):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM users WHERE user_uid = %s AND role = 3", (user_uid,))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Manager deleted successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/users-left/<org_id>', methods=['GET'])
def get_users_left(org_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get org info to find max users allowed
        cursor.execute("SELECT no_of_users FROM users WHERE org = %s AND role = 2 LIMIT 1", (org_id,))
        org_info = cursor.fetchone()
        
        if not org_info:
            return jsonify({"success": False, "message": "Organization not found"}), 404
        
        max_users = org_info['no_of_users'] or 0
        
        # Count current users (managers + staff)
        cursor.execute("SELECT COUNT(*) as count FROM users WHERE org = %s AND role IN (3, 4)", (org_id,))
        current_users = cursor.fetchone()['count']
        
        users_left = max(0, max_users - current_users)
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "users_left": users_left})
    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500

@app.route('/', methods=['GET'])
def home():
    return "<h1>Welcome to Billing App Flask API</h1><p>API is running successfully!</p>"

if __name__ == '__main__':
    initialize_connection_pool()
    app.run(host='0.0.0.0', port=5000, debug=True)