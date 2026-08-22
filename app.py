from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime
import os



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



@app.route('/')
def home():
    return render_template('home.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    # If already logged in, redirect directly to profile
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

        
        cur.execute("""
            INSERT INTO verification (verification_status, verified_at, student_id)
            VALUES ('verified', NOW(), %s)
        """, (student_id,))

        mysql.connection.commit()
        cur.close()

       
        session['student_id'] = student_id
        session['user_name'] = name
        session['gsuite_email'] = email

        return redirect(url_for('profile'))

    return render_template('signup.html')



@app.route('/login', methods=['GET', 'POST'])
def login():
    # If already logged in, redirect straight to profile
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
                # Plain text fallback for raw sample seed data
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

        # Establish user session
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
    cart_count = get_cart_count(student_id)

    return render_template('marketplace.html', products=products, cart_count=cart_count)



@app.route('/product/<int:product_id>')
def product_detail(product_id):
    student_id = session.get('student_id')
    cur = mysql.connection.cursor()

    # 1. Fetch Product details
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
    cart_count = get_cart_count(student_id)

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

    return render_template('sell_product.html', next_id=next_id)



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

    
    cur.execute("""
        SELECT COUNT(product_id) as cnt FROM added WHERE cart_id = %s
    """, (cart_id,))
    count_row = cur.fetchone()
    new_count = int(count_row['cnt']) if count_row else 0

    mysql.connection.commit()
    cur.close()

    if is_ajax or request.method == 'POST':
        return jsonify({
            'success': True,
            'cart_count': new_count,
            'message': f'Item added! Cart count: {new_count}. Full cart page will be built in the future.'
        })

    return redirect(url_for('product_detail', product_id=product_id))



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