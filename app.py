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
            server_condition = " AND c.manager_id = %s"
            params.append(server_id)
        elif manager_id:
            server_condition = " AND c.manager_id = %s"
            params.append(manager_id)
        
        # Total orders and items sold
        cursor.execute(f"""
            SELECT COUNT(DISTINCT order_id) as total_orders,
                   COUNT(*) as total_items,
                   COALESCE(SUM(c.item_qty * m.item_price), 0) as total_revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 'completed'{server_condition}
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
                "overview": overview
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
            filter_condition = " AND c.manager_id = %s"
            params.append(server_id)
        elif manager_id:
            filter_condition = " AND c.manager_id = %s"
            params.append(manager_id)
        
        cursor.execute(f"""
            SELECT m.item_name, SUM(c.item_qty) as total_quantity,
                   COUNT(*) as order_count,
                   SUM(c.item_qty * m.item_price) as revenue
            FROM cart c
            JOIN menu m ON c.item_id = m.item_id
            WHERE {date_condition} AND c.status = 'completed'{filter_condition}
            GROUP BY c.item_id, m.item_name
            ORDER BY total_quantity DESC
            LIMIT 5
        """, params)
        popular_items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "data": popular_items})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

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
        
        # Generate unique cart_id
        cursor.execute("SELECT COUNT(*) as count FROM cart WHERE cart_id LIKE 'CRT_%'")
        count_result = cursor.fetchone()
        cart_number = count_result['count'] + 1
        cart_id = f"CRT_{cart_number}"
        
        # Generate order_id
        cursor.execute("SELECT COUNT(*) as count FROM cart WHERE order_id LIKE 'ORD_%'")
        count_result = cursor.fetchone()
        order_number = count_result['count'] + 1
        order_id = f"ORD_{order_number}"
        
        current_time = datetime.now(ist)
        cursor.execute("""
            INSERT INTO cart (order_id, cart_id, item_id, item_qty, order_created_at, order_updated_at, manager_id, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (order_id, cart_id, item_id, item_qty, current_time, current_time, manager_id, 'pending'))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Item added to cart", "data": {"cart_id": cart_id, "order_id": order_id}})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/cart/complete', methods=['POST'])
def complete_order():
    try:
        data = request.get_json()
        order_id = data.get('order_id')
        
        if not order_id:
            return jsonify({"success": False, "message": "Missing order_id"}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        current_time = datetime.now(ist)
        cursor.execute("""
            UPDATE cart SET status = 'completed', order_updated_at = %s 
            WHERE order_id = %s
        """, (current_time, order_id))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"success": True, "message": "Order completed successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": "Server error"}), 500

@app.route('/', methods=['GET'])
def home():
    return "<h1>Welcome to Billing App Flask API</h1><p>API is running successfully!</p>"

if __name__ == '__main__':
    initialize_connection_pool()
    app.run(host='0.0.0.0', port=5000, debug=True)