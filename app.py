from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import date, datetime
import os
import random
import json
import string

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'campuscycle_secret_key_bracu_2026')

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'campuscycle'
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'

mysql = MySQL(app)


def create_digital_receipt(order_id, buyer_id, buyer_name, amount, payment_method, account_number, trx_id, delivery_place, items):
    """Generates a structured JSON digital receipt for an order."""
    if not trx_id:
        prefix_map = {
            'bkash': 'BK',
            'nagad': 'NG',
            'rocket': 'RK',
            'card': 'CD',
            'cash_on_meetup': 'CSH'
        }
        prefix = prefix_map.get(payment_method, 'TX')
        random_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        trx_id = f"{prefix}{random_suffix}"

    method_labels = {
        'bkash': 'bKash Mobile Payment',
        'nagad': 'Nagad Digital Wallet',
        'rocket': 'Dutch-Bangla Rocket',
        'card': 'Credit / Debit Card (Online)',
        'cash_on_meetup': 'Cash on Campus Handover'
    }

    masked_acc = account_number
    if account_number and len(account_number) >= 8:
        masked_acc = account_number[:3] + '****' + account_number[-4:]
    elif payment_method == 'card' and account_number:
        masked_acc = '**** **** **** ' + account_number[-4:]
    elif not account_number:
        masked_acc = 'N/A (Campus Handover)' if payment_method == 'cash_on_meetup' else 'N/A'

    is_paid = payment_method in ['bkash', 'nagad', 'rocket', 'card']

    receipt_data = {
        'receipt_no': f"CC-REC-{order_id:05d}",
        'order_id': order_id,
        'trx_id': trx_id,
        'payment_method': method_labels.get(payment_method, payment_method.capitalize()),
        'payment_method_code': payment_method,
        'account_number': masked_acc,
        'amount': float(amount or 0),
        'payment_status': 'PAID (Verified)' if is_paid else 'PENDING CASH ON HANDOVER',
        'is_paid': is_paid,
        'issued_at': datetime.now().strftime('%d %b %Y, %I:%M %p'),
        'buyer_id': buyer_id,
        'buyer_name': buyer_name,
        'delivery_place': delivery_place or 'UB Gate / Building Lobby',
        'items': items or []
    }
    return json.dumps(receipt_data)


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


def get_wishlist_count(student_id):
    """Returns the total number of products saved in student's wishlist."""
    if not student_id:
        return 0
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT COUNT(i.product_id) as count
            FROM wishlist w
            JOIN includes i ON w.wishlist_id = i.wishlist_id
            WHERE w.student_id = %s
        """, (student_id,))
        row = cur.fetchone()
        cur.close()
        return int(row['count']) if row and row['count'] is not None else 0
    except Exception:
        return 0


def get_unread_notifications_count(student_id):
    """Returns the count of unread notifications for a student."""
    if not student_id:
        return 0
    try:
        cur = mysql.connection.cursor()
        cur.execute("""
            SELECT COUNT(*) as count
            FROM notification
            WHERE buyer_notification = %s AND notification_status = 'unread'
        """, (student_id,))
        row = cur.fetchone()
        cur.close()
        return int(row['count']) if row and row['count'] is not None else 0
    except Exception:
        return 0


@app.context_processor
def inject_global_counts():
    """Injects cart, wishlist, and unread notification counts globally across all templates."""
    student_id = session.get('student_id')
    if student_id:
        return {
            'global_cart_count': get_cart_count(student_id),
            'global_wishlist_count': get_wishlist_count(student_id),
            'global_unread_notifications_count': get_unread_notifications_count(student_id)
        }
    return {
        'global_cart_count': 0,
        'global_wishlist_count': 0,
        'global_unread_notifications_count': 0
    }


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
    wishlist_count = get_wishlist_count(student_id) if student_id else 0
    return render_template('home.html', cart_count=cart_count, wishlist_count=wishlist_count)


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
@app.route('/profile/<student_id>')
def profile(student_id=None):
    current_student_id = session.get('student_id')
    if not current_student_id:
        return redirect(url_for('login'))

    target_student_id = student_id if student_id else current_student_id
    is_own_profile = (target_student_id == current_student_id)

    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM user WHERE student_id = %s", (target_student_id,))
    user = cur.fetchone()

    if not user:
        cur.close()
        return redirect(url_for('profile'))

    cur.execute(
        "SELECT * FROM verification WHERE student_id = %s ORDER BY verification_id DESC LIMIT 1", 
        (target_student_id,)
    )
    verification = cur.fetchone()

    if not verification:
        cur.execute(
            "INSERT INTO verification (verification_status, verified_at, student_id) VALUES ('verified', NOW(), %s)",
            (target_student_id,)
        )
        mysql.connection.commit()
        cur.execute(
            "SELECT * FROM verification WHERE student_id = %s ORDER BY verification_id DESC LIMIT 1", 
            (target_student_id,)
        )
        verification = cur.fetchone()

    cur.execute(
        "SELECT AVG(rating) as avg_rating, COUNT(r_id) as total_reviews FROM review WHERE reviewee_id = %s",
        (target_student_id,)
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
               o.delivery_place, o.delivery_status, o.order_type, o.receipt, o.confirmation,
               p.product_id, p.product_name, p.category, p.selling_price, u.name as seller_name,
               (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) as photo
        FROM orders o
        LEFT JOIN product p ON p.order_id = o.order_id
        LEFT JOIN user u ON p.student_id = u.student_id
        WHERE o.st_buyer_id = %s AND (o.order_type = 'buy' OR o.order_type IS NULL)
        ORDER BY o.order_id DESC
    """, (target_student_id,))
    raw_purchases = cur.fetchall() or []
    purchases = []
    for pur in raw_purchases:
        pur_dict = dict(pur)
        if pur_dict.get('receipt'):
            try:
                pur_dict['receipt_data'] = json.loads(pur_dict['receipt'])
            except Exception:
                pur_dict['receipt_data'] = None
        else:
            pur_dict['receipt_data'] = None
        purchases.append(pur_dict)

    cur.execute("""
        SELECT product_id, product_name, category, description,
               selling_price, recommended_price, warranty, used_in_course,
               purchase_date, sold_date, order_id,
               (SELECT photo FROM product_photo pp WHERE pp.product_id = product.product_id LIMIT 1) as photo
        FROM product
        WHERE student_id = %s
        ORDER BY product_id DESC
    """, (target_student_id,))
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
    """, (target_student_id, target_student_id))
    exchanges = cur.fetchall() or []

    cur.close()
    cart_count = get_cart_count(current_student_id)
    wishlist_count = get_wishlist_count(current_student_id)

    return render_template(
        'profile.html',
        user=user,
        verification=verification,
        derived_trust_score=derived_trust_score,
        total_reviews=total_reviews,
        purchases=purchases,
        sales=sales,
        exchanges=exchanges,
        cart_count=cart_count,
        wishlist_count=wishlist_count,
        is_own_profile=is_own_profile
    )



@app.route('/update-profile', methods=['POST'])
def update_profile():
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('login'))

    department = request.form.get('department')
    semester = request.form.get('semester')
    mobile_number = request.form.get('mobile_number')

    cur = mysql.connection.cursor()
    cur.execute("""
        UPDATE user 
        SET department = %s, semester = %s, mobile_number = %s
        WHERE student_id = %s
    """, (department, semester, mobile_number, student_id))
    mysql.connection.commit()
    cur.close()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': True,
            'department': department,
            'semester': semester,
            'mobile_number': mobile_number,
            'message': 'Academic profile updated successfully!'
        })

    return redirect(url_for('profile'))



@app.route('/marketplace')
def marketplace():
    student_id = session.get('student_id')
    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT p.product_id, p.product_name, p.category, p.description,
               p.selling_price, p.recommended_price, p.used_in_course,
               p.purchase_date, p.sold_date, p.student_id AS seller_id,
               u.name AS seller_name,
               (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) as photo
        FROM product p
        LEFT JOIN user u ON p.student_id = u.student_id
        ORDER BY p.product_id DESC
    """)
    products = cur.fetchall() or []

    for p in products:
        p['age'] = compute_product_age(p.get('purchase_date'))

    cur.close()
    cart_count = get_cart_count(student_id) if student_id else 0
    wishlist_count = get_wishlist_count(student_id) if student_id else 0

    return render_template('marketplace.html', products=products, cart_count=cart_count, wishlist_count=wishlist_count)


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

        # 1. Handle device image file uploads
        uploaded_files = request.files.getlist('product_images')
        for file in uploaded_files:
            if file and file.filename and file.filename.strip():
                orig_filename = secure_filename(file.filename)
                if orig_filename:
                    ext = os.path.splitext(orig_filename)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.jfif', '.heic', '.bmp']:
                        unique_filename = f"prod_{target_id}_{int(datetime.now().timestamp())}_{random.randint(100, 999)}{ext}"
                        save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                        file.save(save_path)
                        photo_url = f"/static/uploads/{unique_filename}"
                        try:
                            cur.execute("""
                                INSERT INTO product_photo (product_id, photo)
                                VALUES (%s, %s)
                            """, (target_id, photo_url))
                        except Exception:
                            pass

        # 2. Handle image URLs if provided
        photos = request.form.getlist('photos[]')
        for p_url in photos:
            p_url = p_url.strip()
            if p_url and not p_url.startswith('https://example.com'):
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

        # Trigger instant notifications to students who wishlisted items in this course, category, or product name
        if used_in_course or category or product_name:
            try:
                search_word = product_name.split()[0] if product_name else ''
                cur.execute("""
                    SELECT DISTINCT w.student_id, w.wishlist_id, u.name AS seller_name
                    FROM wishlist w
                    JOIN includes i ON w.wishlist_id = i.wishlist_id
                    JOIN product p ON i.product_id = p.product_id
                    JOIN user u ON u.student_id = %s
                    WHERE w.student_id != %s
                      AND (
                          (p.used_in_course IS NOT NULL AND p.used_in_course != '' AND LOWER(p.used_in_course) = LOWER(%s))
                          OR (p.category IS NOT NULL AND LOWER(p.category) = LOWER(%s))
                          OR (p.product_name IS NOT NULL AND LOWER(p.product_name) LIKE LOWER(%s))
                      )
                """, (student_id, student_id, used_in_course, category, f"%{search_word}%"))
                matching_users = cur.fetchall()
                for mu in matching_users:
                    notif_text = f"⚡ Wishlist Match: '{product_name}'"
                    if used_in_course:
                        notif_text += f" (used in {used_in_course})"
                    notif_text += f" was just posted by {mu.get('seller_name', 'a peer')} for ৳{selling_price:.0f}!"
                    
                    cur.execute("""
                        INSERT INTO notification 
                        (buyer_notification, user_notification, wishlist_id, text, notification_type, notification_status)
                        VALUES (%s, %s, %s, %s, 'wishlist_match', 'unread')
                    """, (mu['student_id'], student_id, mu['wishlist_id'], notif_text))
            except Exception as e:
                print("Error creating wishlist match notifications:", e)

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

    # Strict Course Code Recommendation Engine
    cart_pids = [item['product_id'] for item in cart_items]
    tracked_courses = [item['used_in_course'].strip().upper() for item in cart_items if item.get('used_in_course') and item.get('used_in_course').strip()]
    tracked_courses = list(dict.fromkeys(tracked_courses))  # Unique list

    recommendations = []
    if tracked_courses:
        format_strings = ','.join(['%s'] * len(tracked_courses))
        query = f"""
            SELECT p.product_id, p.product_name, p.category, p.selling_price, 
                   p.recommended_price, p.used_in_course, u.name as seller_name,
                   (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) as photo
            FROM product p
            LEFT JOIN user u ON p.student_id = u.student_id
            WHERE p.sold_date IS NULL
              AND UPPER(TRIM(p.used_in_course)) IN ({format_strings})
        """
        params = list(tracked_courses)
        if cart_pids:
            p_format = ','.join(['%s'] * len(cart_pids))
            query += f" AND p.product_id NOT IN ({p_format})"
            params.extend(cart_pids)
        query += " ORDER BY p.product_id DESC LIMIT 6"
        cur.execute(query, tuple(params))
        recommendations = list(cur.fetchall() or [])

    cur.close()

    return render_template(
        'cart.html',
        cart_items=cart_items,
        total_bill=round(total_bill, 2),
        cart_count=len(cart_items),
        recommendations=recommendations,
        tracked_courses=tracked_courses
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
    user_name = session.get('user_name', 'Student Buyer')
    if not student_id:
        return redirect(url_for('login'))

    delivery_place = request.form.get('delivery_place', 'UB Gate / Building Lobby')
    payment_method = request.form.get('payment_method', 'cash_on_meetup')
    account_number = request.form.get('account_number', '').strip()
    trx_id = request.form.get('trx_id', '').strip()

    cur = mysql.connection.cursor()

    cur.execute("SELECT cart_id FROM cart WHERE student_id = %s LIMIT 1", (student_id,))
    user_cart = cur.fetchone()
    if not user_cart:
        cur.close()
        return redirect(url_for('marketplace'))

    cart_id = user_cart['cart_id']

    cur.execute("""
        SELECT p.product_id, p.product_name, p.selling_price, p.student_id as seller_id, u.name as seller_name
        FROM added a 
        JOIN product p ON a.product_id = p.product_id 
        LEFT JOIN user u ON p.student_id = u.student_id
        WHERE a.cart_id = %s
    """, (cart_id,))
    items = cur.fetchall() or []

    if not items:
        cur.close()
        return redirect(url_for('cart_view'))

    total_bill = sum(float(i['selling_price'] or 0) for i in items)
    is_digital_paid = payment_method in ['bkash', 'nagad', 'rocket', 'card']
    delivery_status = 'confirmed' if is_digital_paid else 'pending'
    buyer_confirmation = 1 if is_digital_paid else 0
    confirmation = 1 if is_digital_paid else 0

    cur.execute("""
        INSERT INTO orders 
        (cart_id, st_buyer_id, final_bill, payment_method, delivery_date, delivery_place, delivery_status, buyer_confirmation, confirmation, order_type)
        VALUES (%s, %s, %s, %s, CURDATE(), %s, %s, %s, %s, 'buy')
    """, (cart_id, student_id, total_bill, payment_method, delivery_place, delivery_status, buyer_confirmation, confirmation))
    order_id = cur.lastrowid

    # Generate Digital Receipt
    items_summary = [{'product_id': i['product_id'], 'product_name': i['product_name'], 'price': float(i['selling_price'] or 0), 'seller_name': i.get('seller_name', 'Peer')} for i in items]
    receipt_json = create_digital_receipt(order_id, student_id, user_name, total_bill, payment_method, account_number, trx_id, delivery_place, items_summary)
    cur.execute("UPDATE orders SET receipt = %s WHERE order_id = %s", (receipt_json, order_id))

    cur.execute("UPDATE cart SET order_id = %s, total_bill = %s WHERE cart_id = %s", (order_id, total_bill, cart_id))

    # Mark items with order_id
    for item in items:
        cur.execute("UPDATE product SET order_id = %s WHERE product_id = %s", (order_id, item['product_id']))

        # Send notification to seller
        seller_id = item.get('seller_id')
        if seller_id and seller_id != student_id:
            msg = f"Order #{order_id}: {user_name} placed an order for '{item['product_name']}' (৳{item['selling_price']}) via {payment_method.replace('_', ' ').upper()}."
            try:
                cur.execute("""
                    INSERT INTO notification (buyer_notification, user_notification, text, notification_type, notification_status)
                    VALUES (%s, %s, %s, 'payment_received', 'unread')
                """, (seller_id, student_id, msg))
            except Exception:
                pass

    # Send notification to buyer
    buyer_msg = f"Order #{order_id} confirmed! Total: ৳{total_bill} via {payment_method.replace('_', ' ').upper()}. Delivery at {delivery_place}."
    try:
        cur.execute("""
            INSERT INTO notification (buyer_notification, user_notification, text, notification_type, notification_status)
            VALUES (%s, %s, %s, 'order_confirmed', 'unread')
        """, (student_id, student_id, buyer_msg))
    except Exception:
        pass

    # Clear current cart added items for next shopping session
    cur.execute("DELETE FROM added WHERE cart_id = %s", (cart_id,))

    mysql.connection.commit()
    cur.close()

    return redirect(url_for('profile'))


@app.route('/buy-now/<int:product_id>', methods=['POST'])
def buy_now(product_id):
    student_id = session.get('student_id')
    user_name = session.get('user_name', 'Student Buyer')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if not student_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Please login to purchase.', 'redirect': url_for('login')}), 401
        return redirect(url_for('login'))

    delivery_place = request.form.get('delivery_place', 'UB Gate / Building Lobby')
    payment_method = request.form.get('payment_method', 'bkash')
    account_number = request.form.get('account_number', '').strip()
    trx_id = request.form.get('trx_id', '').strip()

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT p.product_id, p.product_name, p.selling_price, p.student_id as seller_id, u.name as seller_name
        FROM product p
        LEFT JOIN user u ON p.student_id = u.student_id
        WHERE p.product_id = %s
    """, (product_id,))
    product = cur.fetchone()

    if not product:
        cur.close()
        if is_ajax:
            return jsonify({'success': False, 'message': 'Product not found.'}), 404
        return redirect(url_for('marketplace'))

    if product['seller_id'] == student_id:
        cur.close()
        if is_ajax:
            return jsonify({'success': False, 'message': 'You cannot purchase your own listed item.'}), 400
        return redirect(url_for('product_detail', product_id=product_id))

    # Ensure student cart exists
    cur.execute("SELECT cart_id FROM cart WHERE student_id = %s LIMIT 1", (student_id,))
    user_cart = cur.fetchone()
    if not user_cart:
        cur.execute("INSERT INTO cart (student_id, total_bill) VALUES (%s, 0)", (student_id,))
        mysql.connection.commit()
        cart_id = cur.lastrowid
    else:
        cart_id = user_cart['cart_id']

    total_bill = float(product['selling_price'] or 0)
    is_digital_paid = payment_method in ['bkash', 'nagad', 'rocket', 'card']
    delivery_status = 'confirmed' if is_digital_paid else 'pending'
    buyer_confirmation = 1 if is_digital_paid else 0
    confirmation = 1 if is_digital_paid else 0

    cur.execute("""
        INSERT INTO orders 
        (cart_id, st_buyer_id, final_bill, payment_method, delivery_date, delivery_place, delivery_status, buyer_confirmation, confirmation, order_type)
        VALUES (%s, %s, %s, %s, CURDATE(), %s, %s, %s, %s, 'buy')
    """, (cart_id, student_id, total_bill, payment_method, delivery_place, delivery_status, buyer_confirmation, confirmation))
    order_id = cur.lastrowid

    # Generate Digital Receipt
    items_summary = [{'product_id': product['product_id'], 'product_name': product['product_name'], 'price': total_bill, 'seller_name': product.get('seller_name', 'Peer')}]
    receipt_json = create_digital_receipt(order_id, student_id, user_name, total_bill, payment_method, account_number, trx_id, delivery_place, items_summary)
    cur.execute("UPDATE orders SET receipt = %s WHERE order_id = %s", (receipt_json, order_id))

    # Mark product with order_id
    cur.execute("UPDATE product SET order_id = %s WHERE product_id = %s", (order_id, product_id))

    # Notifications
    seller_id = product.get('seller_id')
    if seller_id and seller_id != student_id:
        msg = f"Order #{order_id}: {user_name} purchased '{product['product_name']}' (৳{total_bill}) via {payment_method.replace('_', ' ').upper()}."
        try:
            cur.execute("""
                INSERT INTO notification (buyer_notification, user_notification, text, notification_type, notification_status)
                VALUES (%s, %s, %s, 'payment_received', 'unread')
            """, (seller_id, student_id, msg))
        except Exception:
            pass

    buyer_msg = f"Order #{order_id} placed! ৳{total_bill} for '{product['product_name']}' via {payment_method.replace('_', ' ').upper()}. Handover at {delivery_place}."
    try:
        cur.execute("""
            INSERT INTO notification (buyer_notification, user_notification, text, notification_type, notification_status)
            VALUES (%s, %s, %s, 'order_confirmed', 'unread')
        """, (student_id, student_id, buyer_msg))
    except Exception:
        pass

    mysql.connection.commit()
    cur.close()

    if is_ajax:
        return jsonify({
            'success': True,
            'message': f"Order #{order_id} confirmed via {payment_method.replace('_', ' ').upper()}! Digital receipt generated.",
            'order_id': order_id,
            'redirect': url_for('profile')
        })

    return redirect(url_for('profile'))


@app.route('/pay-order/<int:order_id>', methods=['POST'])
def pay_order(order_id):
    student_id = session.get('student_id')
    user_name = session.get('user_name', 'Student Buyer')
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json

    if not student_id:
        if is_ajax:
            return jsonify({'success': False, 'message': 'Please login.'}), 401
        return redirect(url_for('login'))

    payment_method = request.form.get('payment_method', 'bkash')
    account_number = request.form.get('account_number', '').strip()
    trx_id = request.form.get('trx_id', '').strip()

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT o.order_id, o.final_bill, o.st_buyer_id, o.delivery_place,
               p.product_id, p.product_name, p.selling_price, p.student_id as seller_id, u.name as seller_name
        FROM orders o
        LEFT JOIN product p ON p.order_id = o.order_id
        LEFT JOIN user u ON p.student_id = u.student_id
        WHERE o.order_id = %s AND o.st_buyer_id = %s
    """, (order_id, student_id))
    order_rows = cur.fetchall() or []

    if not order_rows:
        cur.close()
        if is_ajax:
            return jsonify({'success': False, 'message': 'Order not found.'}), 404
        return redirect(url_for('profile'))

    order_info = order_rows[0]
    total_bill = float(order_info['final_bill'] or 0)
    items_summary = [{'product_id': r['product_id'], 'product_name': r['product_name'] or 'Campus Item', 'price': float(r['selling_price'] or 0), 'seller_name': r.get('seller_name', 'Peer')} for r in order_rows if r.get('product_id')]

    receipt_json = create_digital_receipt(order_id, student_id, user_name, total_bill, payment_method, account_number, trx_id, order_info['delivery_place'], items_summary)

    cur.execute("""
        UPDATE orders 
        SET payment_method = %s, receipt = %s, delivery_status = 'confirmed', buyer_confirmation = 1, confirmation = 1
        WHERE order_id = %s
    """, (payment_method, receipt_json, order_id))

    # Notify sellers
    for r in order_rows:
        seller_id = r.get('seller_id')
        if seller_id and seller_id != student_id:
            try:
                cur.execute("""
                    INSERT INTO notification (buyer_notification, user_notification, text, notification_type, notification_status)
                    VALUES (%s, %s, %s, 'payment_received', 'unread')
                """, (seller_id, student_id, f"Order #{order_id} payment of ৳{total_bill} received via {payment_method.replace('_', ' ').upper()}!"))
            except Exception:
                pass

    mysql.connection.commit()
    cur.close()

    if is_ajax:
        return jsonify({
            'success': True,
            'message': f"Payment of ৳{total_bill} confirmed via {payment_method.replace('_', ' ').upper()}! Receipt issued.",
            'order_id': order_id,
            'redirect': url_for('profile')
        })

    return redirect(url_for('profile'))


@app.route('/api/order/<int:order_id>/receipt')
def get_order_receipt(order_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT o.order_id, o.st_buyer_id, o.final_bill, o.payment_method, o.delivery_place, 
               o.delivery_date, o.delivery_status, o.receipt,
               p.product_name, p.selling_price, u.name as seller_name
        FROM orders o
        LEFT JOIN product p ON p.order_id = o.order_id
        LEFT JOIN user u ON p.student_id = u.student_id
        WHERE o.order_id = %s AND (o.st_buyer_id = %s OR p.student_id = %s)
    """, (order_id, student_id, student_id))
    rows = cur.fetchall() or []
    cur.close()

    if not rows:
        return jsonify({'success': False, 'message': 'Receipt not found or access denied.'}), 404

    row = rows[0]
    receipt_data = None
    if row.get('receipt'):
        try:
            receipt_data = json.loads(row['receipt'])
        except Exception:
            receipt_data = {'raw_text': row['receipt']}

    if not receipt_data or not isinstance(receipt_data, dict):
        is_paid = (row.get('payment_method') or '') in ['bkash', 'nagad', 'rocket', 'card']
        receipt_data = {
            'receipt_no': f"CC-REC-{order_id:05d}",
            'order_id': order_id,
            'trx_id': f"TX-{order_id:05d}",
            'payment_method': (row.get('payment_method') or 'cash_on_meetup').replace('_', ' ').title(),
            'payment_method_code': row.get('payment_method') or 'cash_on_meetup',
            'amount': float(row.get('final_bill') or 0),
            'payment_status': 'PAID (Verified)' if is_paid else 'PENDING CASH ON HANDOVER',
            'is_paid': is_paid,
            'delivery_place': row.get('delivery_place') or 'UB Gate / Building Lobby',
            'items': [{'product_name': r.get('product_name') or 'Item', 'price': float(r.get('selling_price') or 0)} for r in rows if r.get('product_name')]
        }

    return jsonify({'success': True, 'receipt': receipt_data})


# =========================================================================
# WISHLIST & NOTIFICATION APPLICATION ROUTES (WISHLIST, INCLUDES, NOTIFICATION)
# =========================================================================

@app.route('/wishlist')
def wishlist_view():
    student_id = session.get('student_id')
    if not student_id:
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    # 1. Fetch or initialize wishlist record for this student
    cur.execute("SELECT wishlist_id, recommendation FROM wishlist WHERE student_id = %s LIMIT 1", (student_id,))
    wishlist_row = cur.fetchone()
    if not wishlist_row:
        cur.execute("INSERT INTO wishlist (student_id, recommendation) VALUES (%s, %s)", (student_id, ''))
        mysql.connection.commit()
        cur.execute("SELECT wishlist_id, recommendation FROM wishlist WHERE student_id = %s LIMIT 1", (student_id,))
        wishlist_row = cur.fetchone()

    wishlist_id = wishlist_row['wishlist_id']
    stored_recommendation = wishlist_row['recommendation'] or ''

    # 2. Fetch all products currently saved in the user's wishlist
    cur.execute("""
        SELECT p.product_id, p.product_name, p.category, p.description,
               p.selling_price, p.recommended_price, p.used_in_course,
               p.sold_date, p.student_id AS seller_id, u.name AS seller_name,
               u.trust_score AS seller_trust_score,
               (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) AS photo
        FROM includes i
        JOIN product p ON i.product_id = p.product_id
        JOIN user u ON p.student_id = u.student_id
        WHERE i.wishlist_id = %s
        ORDER BY p.product_id DESC
    """, (wishlist_id,))
    wishlist_items = cur.fetchall()

    wishlisted_product_ids = [item['product_id'] for item in wishlist_items]
    wishlisted_courses = list(set([item['used_in_course'].strip().upper() for item in wishlist_items if item['used_in_course'] and item['used_in_course'].strip()]))
    wishlisted_categories = list(set([item['category'].strip() for item in wishlist_items if item['category'] and item['category'].strip()]))

    # 3. Intelligent Course & Related Recommendations
    recommendations = []
    if wishlisted_courses:
        format_strings = ','.join(['%s'] * len(wishlisted_courses))
        query = f"""
            SELECT DISTINCT p.product_id, p.product_name, p.category, p.description,
                   p.selling_price, p.recommended_price, p.used_in_course,
                   u.name AS seller_name, u.trust_score AS seller_trust_score,
                   (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) AS photo,
                   'Same Course: ' AS reason_type, p.used_in_course AS reason_value
            FROM product p
            JOIN user u ON p.student_id = u.student_id
            WHERE p.sold_date IS NULL
              AND p.student_id != %s
              AND UPPER(p.used_in_course) IN ({format_strings})
        """
        params = [student_id] + wishlisted_courses
        if wishlisted_product_ids:
            p_format = ','.join(['%s'] * len(wishlisted_product_ids))
            query += f" AND p.product_id NOT IN ({p_format})"
            params += wishlisted_product_ids
        query += " ORDER BY p.product_id DESC LIMIT 8"
        cur.execute(query, tuple(params))
        recommendations = list(cur.fetchall())

    # Fallback or supplementary recommendations
    if len(recommendations) < 4:
        exclude_ids = wishlisted_product_ids + [r['product_id'] for r in recommendations]
        fallback_query = """
            SELECT DISTINCT p.product_id, p.product_name, p.category, p.description,
                   p.selling_price, p.recommended_price, p.used_in_course,
                   u.name AS seller_name, u.trust_score AS seller_trust_score,
                   (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) AS photo,
                   'Popular on Campus' AS reason_type, p.category AS reason_value
            FROM product p
            JOIN user u ON p.student_id = u.student_id
            WHERE p.sold_date IS NULL
              AND p.student_id != %s
        """
        params = [student_id]
        if exclude_ids:
            p_format = ','.join(['%s'] * len(exclude_ids))
            fallback_query += f" AND p.product_id NOT IN ({p_format})"
            params += exclude_ids
        fallback_query += " ORDER BY p.product_id DESC LIMIT %s"
        needed = 8 - len(recommendations)
        params.append(needed)
        cur.execute(fallback_query, tuple(params))
        recommendations.extend(cur.fetchall())

    # 4. Fetch Wishlist & Match Notifications for this student
    cur.execute("""
        SELECT n.n_id, n.text, n.notification_type, n.notification_status,
               n.notification_date, n.user_notification AS sender_id,
               u.name AS sender_name
        FROM notification n
        LEFT JOIN user u ON n.user_notification = u.student_id
        WHERE n.buyer_notification = %s
        ORDER BY n.notification_date DESC
        LIMIT 15
    """, (student_id,))
    notifications = cur.fetchall()

    cart_count = get_cart_count(student_id)
    wishlist_count = len(wishlist_items)
    unread_notifs = sum(1 for n in notifications if n['notification_status'] == 'unread')

    cur.close()

    return render_template(
        'wishlist.html',
        wishlist_items=wishlist_items,
        recommendations=recommendations,
        notifications=notifications,
        wishlisted_courses=wishlisted_courses,
        cart_count=cart_count,
        wishlist_count=wishlist_count,
        unread_notifs=unread_notifs,
        stored_recommendation=stored_recommendation
    )


@app.route('/wishlist/add/<int:product_id>', methods=['GET', 'POST'])
def add_to_wishlist(product_id):
    student_id = session.get('student_id')
    if not student_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'message': 'Please login first', 'redirect': url_for('login')}), 401
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()

    # Get product info
    cur.execute("SELECT product_id, product_name, category, used_in_course, selling_price FROM product WHERE product_id = %s", (product_id,))
    product = cur.fetchone()
    if not product:
        cur.close()
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'message': 'Product not found'}), 404
        return redirect(url_for('marketplace'))

    # Get or create wishlist
    cur.execute("SELECT wishlist_id FROM wishlist WHERE student_id = %s LIMIT 1", (student_id,))
    w_row = cur.fetchone()
    if not w_row:
        cur.execute("INSERT INTO wishlist (student_id, recommendation) VALUES (%s, %s)", (student_id, ''))
        wishlist_id = cur.lastrowid
    else:
        wishlist_id = w_row['wishlist_id']

    # Insert into includes if not already present
    cur.execute("SELECT * FROM includes WHERE wishlist_id = %s AND product_id = %s", (wishlist_id, product_id))
    already_included = cur.fetchone()
    if not already_included:
        cur.execute("INSERT INTO includes (wishlist_id, product_id) VALUES (%s, %s)", (wishlist_id, product_id))

    # Fetch course-based recommendations for instant feedback
    course = product.get('used_in_course', '')
    course_recommendations = []
    if course and course.strip():
        cur.execute("""
            SELECT p.product_id, p.product_name, p.category, p.selling_price, p.used_in_course,
                   (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) AS photo
            FROM product p
            WHERE p.sold_date IS NULL
              AND p.student_id != %s
              AND p.product_id != %s
              AND UPPER(p.used_in_course) = UPPER(%s)
            LIMIT 4
        """, (student_id, product_id, course.strip()))
        course_recommendations = list(cur.fetchall())

        # Update wishlist recommendation text
        rec_text = f"Smart recommendations for {course.strip()}: " + ", ".join([r['product_name'] for r in course_recommendations]) if course_recommendations else f"Added {product['product_name']} for {course.strip()}"
        cur.execute("UPDATE wishlist SET recommendation = %s WHERE wishlist_id = %s", (rec_text, wishlist_id))

    mysql.connection.commit()
    cur.close()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': True,
            'message': f"Added '{product['product_name']}' to your wishlist!",
            'already_in': bool(already_included),
            'wishlist_count': get_wishlist_count(student_id),
            'course': course,
            'recommendations': course_recommendations
        })

    return redirect(url_for('wishlist_view'))


@app.route('/wishlist/remove/<int:product_id>', methods=['GET', 'POST'])
def remove_from_wishlist(product_id):
    student_id = session.get('student_id')
    if not student_id:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'success': False, 'message': 'Please login first'}), 401
        return redirect(url_for('login'))

    cur = mysql.connection.cursor()
    cur.execute("SELECT wishlist_id FROM wishlist WHERE student_id = %s LIMIT 1", (student_id,))
    w_row = cur.fetchone()
    if w_row:
        cur.execute("DELETE FROM includes WHERE wishlist_id = %s AND product_id = %s", (w_row['wishlist_id'], product_id))
        mysql.connection.commit()
    cur.close()

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
        return jsonify({
            'success': True,
            'message': 'Item removed from wishlist',
            'wishlist_count': get_wishlist_count(student_id)
        })

    return redirect(url_for('wishlist_view'))


@app.route('/api/wishlist/recommendations/<int:product_id>')
def api_wishlist_recommendations(product_id):
    student_id = session.get('student_id')
    cur = mysql.connection.cursor()
    cur.execute("SELECT product_id, product_name, category, used_in_course FROM product WHERE product_id = %s", (product_id,))
    product = cur.fetchone()
    if not product:
        cur.close()
        return jsonify({'success': False, 'recommendations': []})

    course = product.get('used_in_course', '')
    recs = []
    if course and course.strip():
        cur.execute("""
            SELECT p.product_id, p.product_name, p.category, p.selling_price, p.used_in_course,
                   u.name AS seller_name,
                   (SELECT photo FROM product_photo pp WHERE pp.product_id = p.product_id LIMIT 1) AS photo
            FROM product p
            JOIN user u ON p.student_id = u.student_id
            WHERE p.sold_date IS NULL
              AND p.product_id != %s
              AND UPPER(p.used_in_course) = UPPER(%s)
            LIMIT 4
        """, (product_id, course.strip()))
        recs = cur.fetchall()

    cur.close()
    return jsonify({
        'success': True,
        'course': course,
        'recommendations': recs
    })


@app.route('/api/notifications/read/<int:n_id>', methods=['POST'])
def mark_notification_read(n_id):
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'success': False}), 401

    cur = mysql.connection.cursor()
    cur.execute("UPDATE notification SET notification_status = 'read' WHERE n_id = %s AND buyer_notification = %s", (n_id, student_id))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True, 'unread_count': get_unread_notifications_count(student_id)})


@app.route('/api/notifications/read-all', methods=['POST'])
def mark_all_notifications_read():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'success': False}), 401

    cur = mysql.connection.cursor()
    cur.execute("UPDATE notification SET notification_status = 'read' WHERE buyer_notification = %s", (student_id,))
    mysql.connection.commit()
    cur.close()
    return jsonify({'success': True, 'unread_count': 0})


@app.route('/api/notifications/latest')
def get_latest_notifications():
    student_id = session.get('student_id')
    if not student_id:
        return jsonify({'success': False, 'notifications': [], 'unread_count': 0})

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT n.n_id, n.text, n.notification_type, n.notification_status,
               n.notification_date, n.user_notification AS sender_id,
               u.name AS sender_name
        FROM notification n
        LEFT JOIN user u ON n.user_notification = u.student_id
        WHERE n.buyer_notification = %s
        ORDER BY n.notification_date DESC
        LIMIT 10
    """, (student_id,))
    notifs = cur.fetchall() or []

    formatted_notifs = []
    for notif in notifs:
        dt = notif.get('notification_date')
        time_str = format_message_time(dt) if dt else 'Recently'
        formatted_notifs.append({
            'n_id': notif['n_id'],
            'text': notif['text'],
            'type': notif['notification_type'],
            'status': notif['notification_status'],
            'time': time_str,
            'sender_name': notif.get('sender_name') or 'Peer'
        })

    cur.close()
    unread_count = get_unread_notifications_count(student_id)
    return jsonify({
        'success': True,
        'notifications': formatted_notifs,
        'unread_count': unread_count
    })


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
        sender_name = session.get('user_name') or 'A student'
        msg_preview = f'"{text[:40]}..."' if (text and len(text) > 40) else (f'"{text}"' if text else 'Sent an attachment photo')
        notif_text = f"💬 {sender_name} texted you: {msg_preview}"
        cur.execute("""
            INSERT INTO notification 
            (buyer_notification, user_notification, text, notification_type, notification_status)
            VALUES (%s, %s, %s, 'chat', 'unread')
        """, (receiver_id, student_id, notif_text))
    except Exception as e:
        print("Error creating chat notification:", e)

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
        except Exception:
            pass

        try:
            sender_name = session.get('user_name') or 'A student'
            msg_preview = f'"{text[:40]}..."' if (text and len(text) > 40) else (f'"{text}"' if text else 'Sent an attachment photo')
            notif_text = f"💬 {sender_name} texted you: {msg_preview}"
            cur.execute("""
                INSERT INTO notification 
                (buyer_notification, user_notification, text, notification_type, notification_status)
                VALUES (%s, %s, %s, 'chat', 'unread')
            """, (receiver_id, student_id, notif_text))
        except Exception:
            pass

        mysql.connection.commit()
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
