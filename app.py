from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import os
import json
import pandas as pd
import requests
from werkzeug.utils import secure_filename
from datetime import datetime
import time
import threading
import secrets
from flask_apscheduler import APScheduler

# Initialize Flask app
app = Flask(__name__)
app.secret_key = secrets.token_hex(16)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload
app.config['ALLOWED_EXTENSIONS'] = {'xlsx', 'xls'}

# Initialize scheduler
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Global variables
active_orders = {}
stop_loss_orders = {}
instrument_mapping = {}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def load_instrument_mapping():
    global instrument_mapping
    try:
        if os.path.exists('NSE.json'):
            with open('NSE.json', 'r') as f:
                data = json.load(f)
                for item in data:
                    if 'symbol' in item and 'instrument_token' in item:
                        instrument_mapping[item['symbol'].strip().upper()] = int(item['instrument_token'])
            print(f"✅ Loaded {len(instrument_mapping)} instrument mappings")
    except Exception as e:
        print(f"⚠️ Error loading instrument mapping: {e}")

# Load instrument mapping on startup
load_instrument_mapping()

def get_instrument_token(symbol):
    """Get instrument token for a given symbol"""
    if not symbol:
        return None
    
    symbol = symbol.strip().upper()
    return instrument_mapping.get(symbol)

def check_stop_losses():
    """Check all active stop losses and execute if needed"""
    if not stop_loss_orders:
        return
    
    print(f"🔍 Checking {len(stop_loss_orders)} stop loss orders...")
    
    # Get access token from the first stop loss order (assuming all use same token)
    first_order_id = next(iter(stop_loss_orders))
    access_token = stop_loss_orders[first_order_id].get('access_token')
    
    if not access_token:
        print("⚠️ No access token available for stop loss checks")
        return
    
    # Group orders by instrument token to batch price checks
    tokens_to_check = {}
    for order_id, order in stop_loss_orders.items():
        token = order.get('instrument_token')
        if token:
            if token not in tokens_to_check:
                tokens_to_check[token] = []
            tokens_to_check[token].append(order_id)
    
    # Check current prices
    for token, order_ids in tokens_to_check.items():
        try:
            # Get current price for this instrument
            current_price = get_current_price(token, access_token)
            
            if current_price is None:
                continue
                
            # Check each order with this instrument
            for order_id in order_ids:
                order = stop_loss_orders[order_id]
                stop_loss_price = order.get('stop_loss_price')
                
                if stop_loss_price and current_price <= float(stop_loss_price):
                    print(f"🚨 Stop loss triggered for order {order_id}: Current price {current_price} <= Stop loss {stop_loss_price}")
                    # Execute the sell order
                    execute_stop_loss(order_id, order, current_price)
        except Exception as e:
            print(f"⚠️ Error checking price for token {token}: {e}")

def get_current_price(instrument_token, access_token):
    """Get current market price for a given instrument token"""
    try:
        url = f"https://api.upstox.com/v2/market-quote/ltp?instrument_token={instrument_token}"
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }
        
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if response.status_code == 200 and 'data' in data:
            return data['data'].get(str(instrument_token), {}).get('last_price')
        else:
            print(f"⚠️ Failed to get price for {instrument_token}: {data.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"⚠️ Error getting price: {e}")
        return None

def execute_stop_loss(order_id, order, current_price):
    """Execute a stop loss order"""
    try:
        url = "https://api.upstox.com/v2/order/place"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {order["access_token"]}'
        }
        
        payload = {
            "quantity": int(order.get('quantity', 1)),
            "product": order.get('product', 'I'),  # Intraday as default
            "validity": order.get('validity', 'DAY'),
            "price": 0,  # Market order for immediate execution
            "tag": "stop-loss-order",
            "instrument_token": int(order['instrument_token']),
            "order_type": "MARKET",  # Always market for stop loss
            "transaction_type": "SELL",  # Always sell for stop loss
            "disclosed_quantity": 0,
            "trigger_price": 0,
            "is_amo": False
        }
        
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        result = response.json()
        
        order['stop_loss_executed'] = True
        order['execution_price'] = current_price
        order['execution_time'] = datetime.now().isoformat()
        order['execution_response'] = result
        
        print(f"✅ Executed stop loss for order {order_id}: {result}")
        
        # Remove from active stop losses
        if order_id in stop_loss_orders:
            del stop_loss_orders[order_id]
    except Exception as e:
        print(f"⚠️ Error executing stop loss for order {order_id}: {e}")

@app.route('/')
def index():
    return render_template('index.html', 
                          active_orders_count=len(active_orders),
                          stop_loss_count=len(stop_loss_orders),
                          mapped_instruments=len(instrument_mapping))

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        flash('No file part', 'error')
        return redirect(request.url)
    
    file = request.files['file']
    access_token = request.form.get('access_token', '')
    
    if file.filename == '':
        flash('No selected file', 'error')
        return redirect(request.url)
    
    if not access_token:
        flash('Access token is required', 'error')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Process the file in a separate thread
        thread = threading.Thread(target=process_excel_file, args=(filepath, access_token))
        thread.start()
        
        flash('File uploaded and processing started', 'success')
        return redirect(url_for('index'))
    
    flash('Invalid file type', 'error')
    return redirect(request.url)

def process_excel_file(filepath, access_token):
    """Process uploaded Excel file and place orders"""
    try:
        df = pd.read_excel(filepath)
        df.columns = df.columns.str.strip().str.lower()
        
        url = "https://api.upstox.com/v2/order/place"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {access_token}'
        }
        
        for index, row in df.iterrows():
            try:
                symbol = row.get('symbol', '')
                instrument_token = row.get('instrument_token')
                
                # Try to map symbol to token if not provided
                if not instrument_token and symbol:
                    instrument_token = get_instrument_token(symbol)
                
                if not instrument_token:
                    print(f"⚠️ Skipping row {index+1}: Missing or invalid instrument token for symbol '{symbol}'")
                    continue
                
                # Extract order details
                transaction_type = row.get('transaction_type', 'BUY').upper()
                quantity = int(row.get('quantity', 1))
                price = float(row.get('price', 0))
                order_type = row.get('order_type', 'MARKET').upper()
                product = row.get('product', 'I').upper()  # Default to Intraday
                
                # Handle stop loss information
                stop_loss_price = row.get('stop_loss_price', None)
                
                # Create order payload
                payload = {
                    "quantity": quantity,
                    "product": product,
                    "validity": row.get('validity', 'DAY'),
                    "price": price,
                    "tag": row.get('tag', 'excel-order'),
                    "instrument_token": int(instrument_token),
                    "order_type": order_type,
                    "transaction_type": transaction_type,
                    "disclosed_quantity": int(row.get('disclosed_quantity', 0)),
                    "trigger_price": float(row.get('trigger_price', 0)),
                    "is_amo": bool(row.get('is_amo', False))
                }
                
                # Place the order
                response = requests.post(url, headers=headers, data=json.dumps(payload))
                result = response.json()
                
                # Generate a unique order ID
                order_id = result.get('data', {}).get('order_id', f"manual-{int(time.time())}-{index}")
                
                # Store order information
                active_orders[order_id] = {
                    'symbol': symbol,
                    'instrument_token': instrument_token,
                    'transaction_type': transaction_type,
                    'quantity': quantity,
                    'price': price,
                    'order_type': order_type,
                    'product': product,
                    'time': datetime.now().isoformat(),
                    'status': 'placed',
                    'response': result,
                    'access_token': access_token  # Store token for later use
                }
                
                # If it's a BUY order and has stop loss, add to stop loss monitoring
                if transaction_type == 'BUY' and stop_loss_price is not None:
                    stop_loss_orders[order_id] = {
                        'symbol': symbol,
                        'instrument_token': instrument_token,
                        'quantity': quantity,
                        'product': product,
                        'stop_loss_price': float(stop_loss_price),
                        'buy_price': price,
                        'access_token': access_token
                    }
                
                print(f"✅ Order {index+1} placed: {result}")
                
            except Exception as e:
                print(f"⚠️ Error processing row {index+1}: {e}")
                continue
                
    except Exception as e:
        print(f"⚠️ Error processing file {filepath}: {e}")

@app.route('/orders')
def view_orders():
    return render_template('orders.html', 
                          active_orders=active_orders, 
                          stop_loss_orders=stop_loss_orders)

@app.route('/mapping')
def view_mapping():
    # Convert dict to list of dicts for easier template rendering
    mappings = [{'symbol': symbol, 'token': token} 
               for symbol, token in instrument_mapping.items()]
    return render_template('mapping.html', mappings=mappings)

@app.route('/api/orders')
def api_orders():
    return jsonify({
        'active_orders': active_orders,
        'stop_loss_orders': stop_loss_orders,
        'counts': {
            'active': len(active_orders),
            'stop_loss': len(stop_loss_orders)
        }
    })

# Schedule stop loss checker to run every minute
@scheduler.task('interval', id='check_stop_losses', seconds=60)
def scheduled_check_stop_losses():
    with app.app_context():
        check_stop_losses()

if __name__ == '__main__':
    app.run(debug=True)