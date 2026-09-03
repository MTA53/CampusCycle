-- 1. USER (corrected gsuite_email format)
-- ================================
INSERT INTO `user` (student_id, name, gsuite_email, mobile_number, department, semester, trust_score)
VALUES 
('STU001', 'Rafi Ahmed', 'rafi.ahmed@g.bracu.ac.bd', '01700000001', 'CSE', 5, 4.5),
('STU002', 'Nusrat Jahan', 'nusrat.jahan@g.bracu.ac.bd', '01700000002', 'EEE', 3, 4.0);

-- ================================
-- 2. VERIFICATION
-- ================================
INSERT INTO verification (verification_status, verified_at, student_id)
VALUES 
('verified', NOW(), 'STU001'),
('verified', NOW(), 'STU002');

-- ================================
-- 3. CART
-- ================================
INSERT INTO cart (student_id, total_bill)
VALUES ('STU002', 0);

-- ================================
-- 4. PRODUCT (7 items)
-- ================================
INSERT INTO product (product_id, product_name, category, description, selling_price, recommended_price, used_in_course, purchase_date, student_id)
VALUES 
(1, 'Calculus Textbook 3rd Ed', 'Books', 'Lightly used, no markings', 500.00, 480.00, 'MATH101', '2024-01-10', 'STU001'),
(2, 'Scientific Calculator FX-991', 'Electronics', 'Used one semester, works fine', 800.00, 750.00, 'MATH101', '2024-02-01', 'STU002'),
(3, 'Dell Laptop Inspiron 15', 'Electronics', 'Good condition, minor scratches on lid', 25000.00, 24000.00, 'CSE101', '2023-11-15', 'STU001'),
(4, 'History of Economic Thought', 'Books', 'Original textbook for ECO101, clean pages with minor highlights.', 350.00, 320.00, 'ECO101', '2024-03-01', 'STU001'),
(5, 'Digital Logic Trainer Kit & Breadboard', 'Lab Equipment', 'Complete breadboard with 74-series logic gate ICs and jumper wires, tested for CSE260/EEE241 lab.', 1200.00, 1100.00, 'CSE260, EEE241', '2024-02-15', 'STU002'),
(6, 'Introduction to Algorithms (CLRS 3rd Ed)', 'Books', 'Comprehensive algorithms textbook for CSE221. Clean binding with minimal annotations.', 650.00, 600.00, 'CSE221', '2024-01-20', 'STU001'),
(7, 'Arduino Uno R3 Microcontroller Kit', 'Electronics', 'Original Arduino board with sensor modules, USB cable, and breadboard for robotics & IoT projects.', 1800.00, 1650.00, 'CSE321, EEE305', '2023-12-10', 'STU002');

-- ================================
-- 5. PRODUCT_PHOTO
-- ================================
INSERT INTO product_photo (product_id, photo)
VALUES 
(1, '/static/uploads/calculus_3rd_ed.jpg'),
(2, '/static/uploads/casio_fx991ex.jpg'),
(3, '/static/uploads/dell_inspiron_15.png'),
(4, '/static/uploads/economic_thought_cover.png'),
(4, '/static/uploads/economic_thought_page.png'),
(5, '/static/uploads/prod_5_1787767105_954.png'),
(6, '/static/uploads/prod_6_1788430910_601.png'),
(7, '/static/uploads/prod_7_1788431317_237.png');

-- ================================
-- 6. PRODUCT_PRICE
-- ================================
INSERT INTO product_price (product_id, selling)
VALUES 
(1, 500.00),
(2, 800.00),
(3, 25000.00),
(4, 350.00),
(5, 1200.00),
(6, 650.00),
(7, 1800.00);

-- ================================
-- 7. PRODUCT_DATE
-- ================================
INSERT INTO product_date (product_id, purchase, sold)
VALUES 
(1, '2024-01-10', NULL),
(2, '2024-02-01', NULL),
(3, '2023-11-15', NULL),
(4, '2024-03-01', NULL),
(5, '2024-02-15', NULL),
(6, '2024-01-20', NULL),
(7, '2023-12-10', NULL);

-- ================================
-- 8. ADD_TO_CART
-- ================================
INSERT INTO add_to_cart (product_id, student_id)
VALUES (1, 'STU002');

-- ================================
-- 9. ORDERS
-- ================================
INSERT INTO orders (cart_id, st_buyer_id, final_bill, payment_method, delivery_date, delivery_place, delivery_status, order_type)
VALUES (1, 'STU002', 500.00, 'cash_on_meetup', '2024-01-15', 'Library Gate', 'pending', 'buy');

UPDATE cart SET order_id = 1 WHERE cart_id = 1;

-- ================================
-- 10. CHAT
-- ================================
INSERT INTO chat (text, sent_at)
VALUES ('Hi, is this textbook still available?', NOW());

-- ================================
-- 11. PARTICIPATE
-- ================================
INSERT INTO participate (student_id, chat_id)
VALUES ('STU002', 1), ('STU001', 1);

-- ================================
-- 12. WISHLIST
-- ================================
INSERT INTO wishlist (student_id, recommendation)
VALUES ('STU002', 'Looking for used calculators');

-- ================================
-- 13. INCLUDES
-- ================================
INSERT INTO includes (wishlist_id, product_id)
VALUES (1, 1);

-- ================================
-- 14. ADDED
-- ================================
INSERT INTO added (cart_id, product_id)
VALUES (1, 1);

-- ================================
-- 15. NOTIFICATION
-- ================================
INSERT INTO notification (buyer_notification, user_notification, wishlist_id, text, notification_type, notification_status)
VALUES ('STU002', 'STU001', 1, 'Your wishlist item is now available', 'wishlist_match', 'unread');

-- ================================
-- 16. REVIEW
-- ================================
INSERT INTO review (reviewer_id, reviewee_id, rating, comment, order_id)
VALUES ('STU002', 'STU001', 5, 'Great seller, item as described', 1);