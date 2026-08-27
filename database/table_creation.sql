-- 1. USER (ver_id FK added after VERIFICATION table exists — circular ref)
CREATE TABLE `user` (
    student_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    gsuite_email VARCHAR(150) UNIQUE NOT NULL,
    mobile_number VARCHAR(20),
    department VARCHAR(100),
    semester VARCHAR(50),
    trust_score DECIMAL(3,2) DEFAULT 0.0,
    purchase_history TEXT,
    sell_history TEXT,
    exchange_history TEXT,
    ver_id INT NULL
);

ALTER TABLE `user`
ADD COLUMN password_hash VARCHAR(255) NULL;

-- 2. VERIFICATION
CREATE TABLE verification (
    verification_id INT AUTO_INCREMENT PRIMARY KEY,
    verification_status VARCHAR(20) DEFAULT 'pending',
    verification_code VARCHAR(10) NULL,
    token VARCHAR(64) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NULL,
    verified_at TIMESTAMP NULL,
    student_id VARCHAR(50) NOT NULL,
    FOREIGN KEY (student_id) REFERENCES `user`(student_id) ON DELETE CASCADE
);

ALTER TABLE `user`
    ADD FOREIGN KEY (ver_id) REFERENCES verification(verification_id);

-- 3. CART (order_id FK added after ORDERS table exists — circular ref)
CREATE TABLE cart (
    cart_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL,
    total_bill DECIMAL(10,2) DEFAULT 0.0,
    recommendation TEXT,
    order_id INT NULL,
    FOREIGN KEY (student_id) REFERENCES `user`(student_id) ON DELETE CASCADE
);

-- 4. ORDERS ('order' is a reserved MySQL keyword, so table is named orders)
-- Only cart_id is a real FK; st_buyer_id is stored but not constrained (per your correction)
CREATE TABLE orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    cart_id INT,
    st_buyer_id VARCHAR(50) NOT NULL,
    final_bill DECIMAL(10,2),
    payment_method VARCHAR(50) DEFAULT 'cash_on_meetup',
    delivery_date DATE,
    delivery_place VARCHAR(200),
    delivery_status VARCHAR(20) DEFAULT 'pending',
    buyer_confirmation BOOLEAN DEFAULT FALSE,
    seller_confirmation BOOLEAN DEFAULT FALSE,
    receipt TEXT,
    confirmation BOOLEAN DEFAULT FALSE,
    order_type VARCHAR(20) DEFAULT 'buy',
    FOREIGN KEY (cart_id) REFERENCES cart(cart_id)
);

ALTER TABLE cart
    ADD FOREIGN KEY (order_id) REFERENCES orders(order_id);

-- 5. PRODUCT
CREATE TABLE product (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    product_name VARCHAR(150) NOT NULL,
    category VARCHAR(50),
    description TEXT,
    selling_price DECIMAL(10,2),
    recommended_price DECIMAL(10,2),
    warranty TEXT,
    used_in_course VARCHAR(100),
    purchase_date DATE,
    sold_date DATE NULL,
    student_id VARCHAR(50) NOT NULL,
    order_id INT NULL,
    FOREIGN KEY (student_id) REFERENCES `user`(student_id) ON DELETE CASCADE,
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);

-- 6. PRODUCT_PHOTO (multivalued attribute; PK matches your diagram exactly — no surrogate key)
CREATE TABLE product_photo (
    product_id INT NOT NULL,
    photo TEXT NOT NULL,
    PRIMARY KEY (product_id, photo(255)),   -- (255) prefix needed since TEXT can't be a full PK column in MySQL
    FOREIGN KEY (product_id) REFERENCES product(product_id) ON DELETE CASCADE
);

-- 7. PRODUCT_PRICE
CREATE TABLE product_price (
    product_id INT PRIMARY KEY,
    selling DECIMAL(10,2),
    FOREIGN KEY (product_id) REFERENCES product(product_id) ON DELETE CASCADE
);

-- 8. PRODUCT_DATE
CREATE TABLE product_date (
    product_id INT PRIMARY KEY,
    purchase DATE,
    sold DATE,
    FOREIGN KEY (product_id) REFERENCES product(product_id) ON DELETE CASCADE
);

-- 9. ADD_TO_CART (junction: user <-> product)
CREATE TABLE add_to_cart (
    product_id INT NOT NULL,
    student_id VARCHAR(50) NOT NULL,
    PRIMARY KEY (product_id, student_id),
    FOREIGN KEY (product_id) REFERENCES product(product_id) ON DELETE CASCADE,
    FOREIGN KEY (student_id) REFERENCES `user`(student_id) ON DELETE CASCADE
);

-- 10. CHAT
CREATE TABLE chat (
    chat_id INT AUTO_INCREMENT PRIMARY KEY,
    text TEXT,
    photo TEXT,
    sender_id VARCHAR(50) NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sender_id) REFERENCES `user`(student_id) ON DELETE SET NULL
);

-- 11. PARTICIPATE (junction: user <-> chat)
CREATE TABLE participate (
    student_id VARCHAR(50) NOT NULL,
    chat_id INT NOT NULL,
    PRIMARY KEY (student_id, chat_id),
    FOREIGN KEY (student_id) REFERENCES `user`(student_id) ON DELETE CASCADE,
    FOREIGN KEY (chat_id) REFERENCES chat(chat_id) ON DELETE CASCADE
);

-- 12. WISHLIST
CREATE TABLE wishlist (
    wishlist_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(50) NOT NULL,
    recommendation TEXT,
    FOREIGN KEY (student_id) REFERENCES `user`(student_id) ON DELETE CASCADE
);

-- 13. INCLUDES (junction: wishlist <-> product)
CREATE TABLE includes (
    wishlist_id INT NOT NULL,
    product_id INT NOT NULL,
    PRIMARY KEY (wishlist_id, product_id),
    FOREIGN KEY (wishlist_id) REFERENCES wishlist(wishlist_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES product(product_id) ON DELETE CASCADE
);

-- 14. ADDED (junction: cart <-> product)
CREATE TABLE added (
    cart_id INT NOT NULL,
    product_id INT NOT NULL,
    PRIMARY KEY (cart_id, product_id),
    FOREIGN KEY (cart_id) REFERENCES cart(cart_id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES product(product_id) ON DELETE CASCADE
);

-- 15. NOTIFICATION (both buyer_notification and user_notification are FKs -> user.student_id)
CREATE TABLE notification (
    n_id INT AUTO_INCREMENT PRIMARY KEY,
    buyer_notification VARCHAR(50),
    user_notification VARCHAR(50),
    wishlist_id INT NULL,
    text TEXT,
    notification_type VARCHAR(50),
    notification_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notification_status VARCHAR(20) DEFAULT 'unread',
    FOREIGN KEY (buyer_notification) REFERENCES `user`(student_id),
    FOREIGN KEY (user_notification) REFERENCES `user`(student_id),
    FOREIGN KEY (wishlist_id) REFERENCES wishlist(wishlist_id)
);

-- 16. REVIEW
CREATE TABLE review (
    r_id INT AUTO_INCREMENT PRIMARY KEY,
    reviewer_id VARCHAR(50) NOT NULL,
    reviewee_id VARCHAR(50) NOT NULL,
    rating INT CHECK (rating BETWEEN 1 AND 5),
    comment TEXT,
    review_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    order_id INT NOT NULL,
    FOREIGN KEY (reviewer_id) REFERENCES `user`(student_id),
    FOREIGN KEY (reviewee_id) REFERENCES `user`(student_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);