from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
import os
import random

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'campuscycle_secret_key_bracu_2026')

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'campuscycle'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)


def compute_product_age(purchase_date):
    """Derives human-readable item age from original purchase date."""
    if not purchase_date:
        return "Not specified"
    if isinstance(purchase_date, str):
        try:
            purchase_date = datetime.strptime(purchase_date, '%Y-%m-%d').date()
        except Exception:
            return "Recently"
    today = date.today()
    days = (today - purchase_date).days
    if days < 0:
        return "Brand New"
    if days < 30:
        return f"{days} days old"
    months = days // 30
    if months < 12:
        return f"{months} month{'s' if months > 1 else ''} old"
    years = round(days / 365, 1)
    return f"{years} year{'s' if years != 1 else ''} old"


def compute_recommended_price(selling_price, category=None):
    """Calculates Derived Attribute: Recommended Price based on category & fair market discount."""
    try:
        price = float(selling_price)
    except (ValueError, TypeError):
        return 0.0
    factor = 0.95
    if category == 'Books':
        factor = 0.92
    elif category == 'Electronics':
        factor = 0.94
    elif category == 'Scientific Calculator':
        factor = 0.90
    return round(price * factor, 2)


def get_cart_count(student_id):
    """Returns the total number of products added to student's cart."""
    if not student_id:
        return 0
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT COUNT(a.product_id) as count
            FROM cart c
            JOIN added a ON c.cart_id = a.cart_id
            WHERE c.student_id = %s
        """, (student_id,))
        row = cur.fetchone()
        cur.close()
        return int(row['count']) if row and row['count'] is not None else 0
    except Exception:
        return 0


def format_message_time(dt):
    """Formats timestamp into a friendly human-readable format."""
    if not dt:
        return ""
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
        except Exception:
            return dt
    now = datetime.now()
    diff = now - dt
    if diff.days == 0:
        return dt.strftime('%I:%M %p')
    elif diff.days == 1:
        return 'Yesterday, ' + dt.strftime('%I:%M %p')
    elif diff.days < 7:
        return dt.strftime('%a, %I:%M %p')
    else:
        return dt.strftime('%b %d, %I:%M %p')


@app.route('/')
def home():
    student_id = session.get('student_id')
    cart_count = get_cart_count(student_id) if student_id else 0
    return render_template('home.html', cart_count=cart_count)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if session.get('student_id'):
        return redirect(url_for('profile'))

    if request.method == 'POST':
        student_id = request.form.get('student_id', '').strip()
        name = request.form.get('name', '').strip()
        email = request.form.get('gsuite_email', '').strip()
        password = request.form.get('password', '')
        mobile = request.form.get('mobile_number', '').strip()
        department = request.form.get('department', '').strip()
        semester = request.form.get('semester', '').strip()

        if not (email.endswith('@g.bracu.ac.bd') or email.endswith('@bracu.ac.bd')):
            return render_template(
                'signup.html', 
                error="Only BRACU email (@g.bracu.ac.bd or @bracu.ac.bd) is allowed."
            )

        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT * FROM user WHERE gsuite_email = %s OR student_id = %s",
            (email, student_id)
        )
        existing_user = cur.fetchone()

        if existing_user:
            cur.close()
            return render_template(
                'signup.html', 
                error="An account with this Email or Student ID already exists. Please login."
            )

        password_hash = generate_password_hash(password)

        cur.execute("""
            INSERT INTO user
            (student_id, name, gsuite_email, mobile_number,
             department, semester, password_hash, trust_score)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            student_id,
            name,
            email,
            mobile,
            department,
            semester if semester else None,
            password_hash,
            5.0
        ))

        # Create verification record
        cur.execute("""
            INSERT INTO verification (verification_status, verified_at, student_id)
            VALUES ('verified', NOW(), %s)
        """, (student_id,))

        # Initialize student cart
        cur.execute("INSERT INTO cart (student_id, total_bill) VALUES (%s, 0)", (student_id,))

        mysql.connection.commit()
        cur.close()

        session['student_id'] = student_id
        session['user_name'] = name
        session['gsuite_email'] = email

        return redirect(url_for('profile'))

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('student_id'):
        return redirect(url_for('profile'))

    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '')

        if not identifier or not password:
            return render_template('login.html', error="Please provide both Email/Student ID and Password.", identifier=identifier)

        cur = mysql.connection.cursor()
        cur.execute(
            "SELECT * FROM user WHERE gsuite_email = %s OR student_id = %s",
            (identifier, identifier)
        )
        user = cur.fetchone()

        if not user:
            cur.close()
            return render_template('login.html', error="No account found with this Email or Student ID. Please sign up.", identifier=identifier)

        password_valid = False
        stored_hash = user.get('password_hash')

        if stored_hash:
            if stored_hash.startswith(('pbkdf2:', 'scrypt:', 'argon2:')):
                password_valid = check_password_hash(stored_hash, password)
            else:
                password_valid = (stored_hash == password)
                if password_valid:
                    new_hash = generate_password_hash(password)
                    cur.execute("UPDATE user SET password_hash = %s WHERE student_id = %s", (new_hash, user['student_id']))
                    mysql.connection.commit()
        else:
            password_valid = True
            new_hash = generate_password_hash(password)
            cur.execute("UPDATE user SET password_hash = %s WHERE student_id = %s", (new_hash, user['student_id']))
            mysql.connection.commit()

        cur.close()

        if not password_valid:
            return render_template('login.html', error="Invalid password. Please check your credentials.", identifier=identifier)

        session['student_id'] = user['student_id']
        session['user_name'] = user['name']
        session['gsuite_email'] = user['gsuite_email']

        return redirect(url_for('profile'))

    return render_template('login.html')


@app.route('/profile')
def profile():
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM user WHERE student_id = %s", (student_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        session.clear()
        return redirect(url_for('login'))

    cur.execute(
        "SELECT * FROM verification WHERE student_id = %s ORDER BY verification_id DESC LIMIT 1", 
        (student_id,)
    )
    verification = cur.fetchone()

    cur.execute(
        "SELECT AVG(rating) as avg_rating, COUNT(r_id) as total_reviews FROM review WHERE reviewee_id = %s",
        (student_id,)
    )
    trust_data = cur.fetchone()

    if trust_data and trust_data['total_reviews'] and trust_data['total_reviews'] > 0:
        derived_trust_score = float(trust_data['avg_rating'])
        total_reviews = trust_data['total_reviews']
    elif user.get('trust_score') is not None and float(user['trust_score']) > 0:
        derived_trust_score = float(user['trust_score'])
        total_reviews = 1
    else:
        derived_trust_score = 5.0
        total_reviews = 0

    cur.execute("""
        SELECT o.order_id, o.final_bill, o.payment_method, o.delivery_date, 
               o.delivery_place, o.delivery_status, o.order_type,
               p.product_name, p.category, p.selling_price, u.name as seller_name
        FROM orders o
        LEFT JOIN cart c ON o.cart_id = c.cart_id
        LEFT JOIN added a ON c.cart_id = a.cart_id
        LEFT JOIN product p ON a.product_id = p.product_id
        LEFT JOIN user u ON p.student_id = u.student_id
        WHERE o.st_buyer_id = %s AND (o.order_type = 'buy' OR o.order_type IS NULL)
        ORDER BY o.order_id DESC
    """, (student_id,))
    purchases = cur.fetchall() or []

    cur.execute("""
        SELECT product_id, product_name, category, description,
               selling_price, recommended_price, warranty, used_in_course,
               purchase_date, sold_date, order_id
        FROM product
        WHERE student_id = %s
        ORDER BY product_id DESC
    """, (student_id,))
    sales = cur.fetchall() or []

    cur.execute("""
        SELECT o.order_id, o.final_bill, o.delivery_date, 
               o.delivery_place, o.delivery_status, o.order_type,
               p.product_name, p.category
        FROM orders o
        LEFT JOIN cart c ON o.cart_id = c.cart_id
        LEFT JOIN added a ON c.cart_id = a.cart_id
        LEFT JOIN product p ON a.product_id = p.product_id
        WHERE (o.st_buyer_id = %s OR p.student_id = %s) AND o.order_type = 'exchange'
        ORDER BY o.order_id DESC
    """, (student_id, student_id))
    exchanges = cur.fetchall() or []

    cur.close()
    cart_count = get_cart_count(student_id)

    return render_template(
        'profile.html',
        user=user,
        verification=verification,
        derived_trust_score=derived_trust_score,
        total_reviews=total_reviews,
        purchases=purchases,
        sales=sales,
        exchanges=exchanges,
        cart_count=cart_count
    )


@app.route('/marketplace')
def marketplace():
    student_id = session.get('student_id')
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT p.product_id, p.product_name, p.category, p.description,
               p.selling_price, p.recommended_price, p.used_in_course,
               p.purchase_date, p.sold_date,
               (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) as photo
        FROM product p
        ORDER BY p.product_id DESC
    """)
    products = cur.fetchall() or []

    for p in products:
        p['age'] = compute_product_age(p.get('purchase_date'))

    cur.close()
    cart_count = get_cart_count(student_id) if student_id else 0

    return render_template('marketplace.html', products=products, cart_count=cart_count)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    student_id = session.get('student_id')
    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM product WHERE product_id = %s", (product_id,))
    product = cur.fetchone()

    if not product:
        cur.close()
        return redirect(url_for('marketplace'))

    cur.execute("SELECT photo FROM product_photo WHERE product_id = %s", (product_id,))
    photo_rows = cur.fetchall() or []
    photos = [r['photo'] for r in photo_rows if r.get('photo')]
    if not photos:
        photos = ['https://images.unsplash.com/photo-1544716278-ca5e3f4abd8c?w=600']

    cur.execute("""
        SELECT student_id, name, department, semester, trust_score 
        FROM user 
        WHERE student_id = %s
    """, (product['student_id'],))
    seller = cur.fetchone()

    seller_trust_score = 4.5
    if seller:
        cur.execute("""
            SELECT AVG(rating) as avg_rating, COUNT(r_id) as total_reviews 
            FROM review 
            WHERE reviewee_id = %s
        """, (seller['student_id'],))
        t_data = cur.fetchone()
        if t_data and t_data['total_reviews'] and t_data['total_reviews'] > 0:
            seller_trust_score = float(t_data['avg_rating'])
        elif seller.get('trust_score'):
            seller_trust_score = float(seller['trust_score'])

    cur.close()

    product_age = compute_product_age(product.get('purchase_date'))
    cart_count = get_cart_count(student_id) if student_id else 0

    return render_template(
        'product_detail.html',
        product=product,
        photos=photos,
        seller=seller,
        seller_trust_score=seller_trust_score,
        product_age=product_age,
        cart_count=cart_count
    )


@app.route('/sell', methods=['GET', 'POST'])
def sell_product():
    if not session.get('student_id'):
        return redirect(url_for('login'))

    student_id = session.get('student_id')
    cur = mysql.connection.cursor()

    if request.method == 'POST':
        product_id_input = request.form.get('product_id', '').strip()
        product_name = request.form.get('product_name', '').strip()
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        selling_price = float(request.form.get('selling_price', 0))
        recommended_price_input = request.form.get('recommended_price', '').strip()
        warranty = request.form.get('warranty', '').strip()
        used_in_course = request.form.get('used_in_course', '').strip()
        purchase_date = request.form.get('purchase_date', '').strip() or None
        sold_date = request.form.get('sold_date', '').strip() or None

        if recommended_price_input:
            try:
                recommended_price = float(recommended_price_input)
            except ValueError:
                recommended_price = compute_recommended_price(selling_price, category)
        else:
            recommended_price = compute_recommended_price(selling_price, category)

        if product_id_input and product_id_input.isdigit():
            target_id = int(product_id_input)
            cur.execute("""
                INSERT INTO product 
                (product_id, product_name, category, description, selling_price, 
                 recommended_price, warranty, used_in_course, purchase_date, sold_date, student_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                target_id, product_name, category, description, selling_price,
                recommended_price, warranty, used_in_course, purchase_date, sold_date, student_id
            ))
        else:
            cur.execute("""
                INSERT INTO product 
                (product_name, category, description, selling_price, 
                 recommended_price, warranty, used_in_course, purchase_date, sold_date, student_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                product_name, category, description, selling_price,
                recommended_price, warranty, used_in_course, purchase_date, sold_date, student_id
            ))
            target_id = cur.lastrowid

        photos = request.form.getlist('photos[]')
        for p_url in photos:
            p_url = p_url.strip()
            if p_url:
                try:
                    cur.execute("""
                        INSERT INTO product_photo (product_id, photo)
                        VALUES (%s, %s)
                    """, (target_id, p_url))
                except Exception:
                    pass

        try:
            cur.execute("""
                INSERT INTO product_price (product_id, selling)
                VALUES (%s, %s)
            """, (target_id, selling_price))
        except Exception:
            pass

        try:
            cur.execute("""
                INSERT INTO product_date (product_id, purchase, sold)
                VALUES (%s, %s, %s)
            """, (target_id, purchase_date, sold_date))
        except Exception:
            pass

        mysql.connection.commit()
        cur.close()

        return redirect(url_for('product_detail', product_id=target_id))

    cur.execute("SELECT COALESCE(MAX(product_id), 0) + 1 AS next_id FROM product")
    row = cur.fetchone()
    next_id = row['next_id'] if row else 1
    cur.close()

    cart_count = get_cart_count(student_id)
    return render_template('sell_product.html', next_id=next_id, cart_count=cart_count)


# =========================================================================
# CART & CHECKOUT ROUTES
# =========================================================================

@app.route('/cart')
def cart_view():
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT p.product_id, p.product_name, p.category, p.selling_price, 
               p.used_in_course, u.name as seller_name,
               (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) as photo
        FROM cart c
        JOIN added a ON c.cart_id = a.cart_id
        JOIN product p ON a.product_id = p.product_id
        LEFT JOIN user u ON p.student_id = u.student_id
        WHERE c.student_id = %s
        ORDER BY p.product_id DESC
    """, (student_id,))
    cart_items = cur.fetchall() or []

    total_bill = sum(float(item['selling_price'] or 0) for item in cart_items)
    cur.close()

    return render_template(
        'cart.html',
        cart_items=cart_items,
        total_bill=round(total_bill, 2),
        cart_count=len(cart_items)
    )


@app.route('/add-to-cart/<int:product_id>', methods=['GET', 'POST'])
def add_to_cart_route(product_id):
    student_id = session.get('student_id')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if not student_id:
        if is_ajax:
            return jsonify({'success': False, 'redirect': url_for('login')}), 401
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    cur.execute("SELECT cart_id FROM cart WHERE student_id = %s LIMIT 1", (student_id,))
    user_cart = cur.fetchone()
    if not user_cart:
        cur.execute("INSERT INTO cart (student_id, total_bill) VALUES (%s, 0)", (student_id,))
        mysql.connection.commit()
        cart_id = cur.lastrowid
    else:
        cart_id = user_cart['cart_id']

    try:
        cur.execute("INSERT IGNORE INTO added (cart_id, product_id) VALUES (%s, %s)", (cart_id, product_id))
    except Exception:
        pass

    try:
        cur.execute("INSERT IGNORE INTO add_to_cart (product_id, student_id) VALUES (%s, %s)", (product_id, student_id))
    except Exception:
        pass

    cur.execute("SELECT COUNT(product_id) as cnt FROM added WHERE cart_id = %s", (cart_id,))
    count_row = cur.fetchone()
    new_count = int(count_row['cnt']) if count_row else 0

    mysql.connection.commit()
    cur.close()

    if is_ajax or request.method == 'POST':
        return jsonify({
            'success': True,
            'cart_count': new_count,
            'message': f'Item added to cart! Total: {new_count} item(s).'
        })

    return redirect(url_for('cart_view'))


@app.route('/remove-from-cart/<int:product_id>')
def remove_from_cart(product_id):
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT cart_id FROM cart WHERE student_id = %s LIMIT 1", (student_id,))
    user_cart = cur.fetchone()
    if user_cart:
        cart_id = user_cart['cart_id']
        cur.execute("DELETE FROM added WHERE cart_id = %s AND product_id = %s", (cart_id, product_id))
        cur.execute("DELETE FROM add_to_cart WHERE student_id = %s AND product_id = %s", (student_id, product_id))
        mysql.connection.commit()
    cur.close()

    return redirect(url_for('cart_view'))


@app.route('/checkout', methods=['POST'])
def checkout():
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('login'))

    delivery_place = request.form.get('delivery_place', 'UB Gate / Building Lobby')
    cur = mysql.connection.cursor()

    cur.execute("SELECT cart_id FROM cart WHERE student_id = %s LIMIT 1", (student_id,))
    user_cart = cur.fetchone()
    if not user_cart:
        cur.close()
        return redirect(url_for('marketplace'))

    cart_id = user_cart['cart_id']

    cur.execute("""
        SELECT p.product_id, p.selling_price 
        FROM added a 
        JOIN product p ON a.product_id = p.product_id 
        WHERE a.cart_id = %s
    """, (cart_id,))
    items = cur.fetchall() or []

    if not items:
        cur.close()
        return redirect(url_for('cart_view'))

    total_bill = sum(float(i['selling_price'] or 0) for i in items)

    cur.execute("""
        INSERT INTO orders 
        (cart_id, st_buyer_id, final_bill, payment_method, delivery_date, delivery_place, delivery_status, order_type)
        VALUES (%s, %s, %s, 'cash_on_meetup', CURDATE(), %s, 'pending', 'buy')
    """, (cart_id, student_id, total_bill, delivery_place))
    order_id = cur.lastrowid

    cur.execute("UPDATE cart SET order_id = %s, total_bill = %s WHERE cart_id = %s", (order_id, total_bill, cart_id))

    # Mark items with order_id
    for item in items:
        cur.execute("UPDATE product SET order_id = %s WHERE product_id = %s", (order_id, item['product_id']))

    # Clear current cart added items for next shopping session
    cur.execute("DELETE FROM added WHERE cart_id = %s", (cart_id,))

    mysql.connection.commit()
    cur.close()

    return redirect(url_for('profile'))


# =========================================================================
# CHAT APPLICATION ROUTES (CHAT & PARTICIPATE ENTITIES)
# =========================================================================

@app.route('/chat')
@app.route('/messages')
def chat_view():
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('login'))

    target_peer_id = request.args.get('user', '').strip()
    product_id_arg = request.args.get('product_id', '').strip()

    cur = mysql.connection.cursor()

    # 1. Fetch conversations list for the current student
    cur.execute("""
        SELECT DISTINCT 
            u.student_id, u.name, u.department, u.semester, u.trust_score,
            (
                SELECT c.text 
                FROM participate p1 
                JOIN participate p2 ON p1.chat_id = p2.chat_id 
                JOIN chat c ON c.chat_id = p1.chat_id 
                WHERE p1.student_id = %s AND p2.student_id = u.student_id 
                ORDER BY c.sent_at DESC, c.chat_id DESC 
                LIMIT 1
            ) AS last_message,
            (
                SELECT c.sent_at 
                FROM participate p1 
                JOIN participate p2 ON p1.chat_id = p2.chat_id 
                JOIN chat c ON c.chat_id = p1.chat_id 
                WHERE p1.student_id = %s AND p2.student_id = u.student_id 
                ORDER BY c.sent_at DESC, c.chat_id DESC 
                LIMIT 1
            ) AS last_message_time,
            (
                SELECT c.sender_id 
                FROM participate p1 
                JOIN participate p2 ON p1.chat_id = p2.chat_id 
                JOIN chat c ON c.chat_id = p1.chat_id 
                WHERE p1.student_id = %s AND p2.student_id = u.student_id 
                ORDER BY c.sent_at DESC, c.chat_id DESC 
                LIMIT 1
            ) AS last_sender_id
        FROM user u
        WHERE u.student_id IN (
            SELECT DISTINCT p2.student_id
            FROM participate p1
            JOIN participate p2 ON p1.chat_id = p2.chat_id
            WHERE p1.student_id = %s AND p2.student_id != %s
        )
        ORDER BY last_message_time DESC
    """, (student_id, student_id, student_id, student_id, student_id))
    conversations = cur.fetchall() or []

    for c in conversations:
        c['formatted_time'] = format_message_time(c.get('last_message_time'))

    # If no peer is specified, pick the most recent conversation
    active_peer_id = target_peer_id
    if not active_peer_id and conversations:
        active_peer_id = conversations[0]['student_id']

    # 2. Fetch active peer info
    active_peer = None
    active_peer_trust_score = 4.5
    if active_peer_id:
        cur.execute("SELECT student_id, name, department, semester, trust_score FROM user WHERE student_id = %s", (active_peer_id,))
        active_peer = cur.fetchone()

        if active_peer:
            cur.execute("SELECT AVG(rating) as avg_rating, COUNT(r_id) as total_reviews FROM review WHERE reviewee_id = %s", (active_peer_id,))
            t_data = cur.fetchone()
            if t_data and t_data['total_reviews'] and t_data['total_reviews'] > 0:
                active_peer_trust_score = float(t_data['avg_rating'])
            elif active_peer.get('trust_score'):
                active_peer_trust_score = float(active_peer['trust_score'])

    # 3. Fetch message history between current user and active peer
    messages = []
    if active_peer:
        cur.execute("""
            SELECT c.chat_id, c.text, c.photo, c.sender_id, c.sent_at,
                   u.name as sender_name
            FROM participate p1
            JOIN participate p2 ON p1.chat_id = p2.chat_id
            JOIN chat c ON c.chat_id = p1.chat_id
            LEFT JOIN user u ON c.sender_id = u.student_id
            WHERE p1.student_id = %s AND p2.student_id = %s
            ORDER BY c.sent_at ASC, c.chat_id ASC
        """, (student_id, active_peer['student_id']))
        messages = cur.fetchall() or []

        for m in messages:
            m['formatted_time'] = format_message_time(m.get('sent_at'))

    # 4. Optional Contextual Product Info
    product_context = None
    if product_id_arg and product_id_arg.isdigit():
        cur.execute("""
            SELECT p.product_id, p.product_name, p.selling_price, p.category,
                   (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) as photo
            FROM product p
            WHERE p.product_id = %s
        """, (int(product_id_arg),))
        product_context = cur.fetchone()

    # 5. Fetch all BRACU students for the "+ New Chat" picker
    cur.execute("""
        SELECT student_id, name, department, semester, trust_score
        FROM user
        WHERE student_id != %s
        ORDER BY name ASC
    """, (student_id,))
    all_students = cur.fetchall() or []

    cur.close()
    cart_count = get_cart_count(student_id)

    return render_template(
        'chat.html',
        conversations=conversations,
        active_peer=active_peer,
        active_peer_trust_score=active_peer_trust_score,
        messages=messages,
        product_context=product_context,
        all_students=all_students,
        cart_count=cart_count
    )


@app.route('/api/chat/messages/<peer_id>')
def api_chat_messages(peer_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT c.chat_id, c.text, c.photo, c.sender_id, c.sent_at,
               u.name as sender_name
        FROM participate p1
        JOIN participate p2 ON p1.chat_id = p2.chat_id
        JOIN chat c ON c.chat_id = p1.chat_id
        LEFT JOIN user u ON c.sender_id = u.student_id
        WHERE p1.student_id = %s AND p2.student_id = %s
        ORDER BY c.sent_at ASC, c.chat_id ASC
    """, (student_id, peer_id))
    messages = cur.fetchall() or []
    cur.close()

    result = []
    for m in messages:
        result.append({
            'chat_id': m['chat_id'],
            'text': m['text'],
            'photo': m['photo'],
            'sender_id': m['sender_id'],
            'sender_name': m['sender_name'],
            'sent_at': str(m['sent_at']),
            'formatted_time': format_message_time(m.get('sent_at')),
            'is_me': (m['sender_id'] == student_id)
        })

    return jsonify({'success': True, 'messages': result})


@app.route('/api/chat/send', methods=['POST'])
def api_chat_send():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or request.form
    receiver_id = data.get('receiver_id', '').strip()
    text = data.get('text', '').strip()
    photo = data.get('photo', '').strip() or None

    if not receiver_id:
        return jsonify({'success': False, 'error': 'Receiver student ID is required'}), 400

    if not text and not photo:
        return jsonify({'success': False, 'error': 'Message content cannot be empty'}), 400

    cur = mysql.connection.cursor()

    # Verify receiver exists
    cur.execute("SELECT student_id, name FROM user WHERE student_id = %s", (receiver_id,))
    receiver = cur.fetchone()
    if not receiver:
        cur.close()
        return jsonify({'success': False, 'error': 'Recipient not found'}), 404

    # 1. Insert into CHAT entity
    cur.execute("""
        INSERT INTO chat (text, photo, sender_id, sent_at)
        VALUES (%s, %s, %s, NOW())
    """, (text, photo, student_id))
    new_chat_id = cur.lastrowid

    # 2. Insert into PARTICIPATE entity (both sender and receiver)
    try:
        cur.execute("INSERT IGNORE INTO participate (student_id, chat_id) VALUES (%s, %s)", (student_id, new_chat_id))
        cur.execute("INSERT IGNORE INTO participate (student_id, chat_id) VALUES (%s, %s)", (receiver_id, new_chat_id))
    except Exception as e:
        pass

    # 3. Create a peer notification
    try:
        cur.execute("""
            INSERT INTO notification 
            (buyer_notification, user_notification, text, notification_type, notification_status)
            VALUES (%s, %s, %s, 'chat', 'unread')
        """, (receiver_id, student_id, f"New message: {text[:50]}..." if len(text) > 50 else f"New message: {text}"))
    except Exception:
        pass

    mysql.connection.commit()
    cur.close()

    now_dt = datetime.now()
    return jsonify({
        'success': True,
        'chat': {
            'chat_id': new_chat_id,
            'text': text,
            'photo': photo,
            'sender_id': student_id,
            'sent_at': str(now_dt),
            'formatted_time': format_message_time(now_dt)
        }
    })


@app.route('/chat/send', methods=['POST'])
def form_chat_send():
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('login'))

    receiver_id = request.form.get('receiver_id', '').strip()
    text = request.form.get('text', '').strip()
    photo = request.form.get('photo', '').strip() or None

    if receiver_id and (text or photo):
        cur = mysql.connection.cursor()
        cur.execute("""
            INSERT INTO chat (text, photo, sender_id, sent_at)
            VALUES (%s, %s, %s, NOW())
        """, (text, photo, student_id))
        new_chat_id = cur.lastrowid

        try:
            cur.execute("INSERT IGNORE INTO participate (student_id, chat_id) VALUES (%s, %s)", (student_id, new_chat_id))
            cur.execute("INSERT IGNORE INTO participate (student_id, chat_id) VALUES (%s, %s)", (receiver_id, new_chat_id))
            mysql.connection.commit()
        except Exception:
            pass
        cur.close()

    return redirect(url_for('chat_view', user=receiver_id))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/reset-password', methods=['POST'])
def reset_password():
    identifier = request.form.get('reset_identifier', '').strip()
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')

    if not identifier:
        return render_template('login.html', reset_error="Please enter your Email or Student ID.")

    if not new_password or not confirm_password:
        return render_template('login.html', reset_error="Please fill in both password fields.")

    if new_password != confirm_password:
        return render_template('login.html', reset_error="Passwords do not match. Please try again.")

    if len(new_password) < 4:
        return render_template('login.html', reset_error="Password must be at least 4 characters long.")

    cur = mysql.connection.cursor()
    cur.execute(
        "SELECT * FROM user WHERE gsuite_email = %s OR student_id = %s",
        (identifier, identifier)
    )
    user = cur.fetchone()

    if not user:
        cur.close()
        return render_template('login.html', reset_error="No account found with this Email or Student ID.")

    new_hash = generate_password_hash(new_password)
    cur.execute(
        "UPDATE user SET password_hash = %s WHERE student_id = %s",
        (new_hash, user['student_id'])
    )
    mysql.connection.commit()
    cur.close()

    return render_template(
        'login.html',
        success="Password reset successfully! You can now login with your new password.",
        identifier=identifier
    )


if __name__ == '__main__':
    app.run(debug=True)
