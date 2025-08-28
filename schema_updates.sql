-- Add missing columns to users table
ALTER TABLE `users` ADD COLUMN `no_of_users` int(11) DEFAULT NULL;

-- Add missing columns to org_info table  
ALTER TABLE `org_info` ADD COLUMN `org_table_nos` int(11) DEFAULT 20;

-- Fix typo in payment_mode table
ALTER TABLE `payment_mode` CHANGE `billder_by` `billed_by` int(11);

-- Fix typo in customer_info table
ALTER TABLE `customer_info` CHANGE `customer_name` `customer_name` varchar(50);

-- Add missing columns to menu table if they don't exist
ALTER TABLE `menu` ADD COLUMN `created_at` timestamp DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE `menu` ADD COLUMN `updated_at` timestamp DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- Insert default user roles
INSERT IGNORE INTO `user_role` (`role_id`, `description`) VALUES 
(1, 'Super Admin'),
(2, 'Client'),
(3, 'Manager'), 
(4, 'Staff');

-- Sample data for testing (optional)
-- INSERT INTO `users` (`name`, `phone`, `password`, `area`, `pincode`, `user_uid`, `parent_uid`, `role`, `org`, `status`, `no_of_users`) VALUES
-- ('Super Admin', '9999999999', 'admin123', 'Admin Area', '000000', 1, 0, 1, 1, 'active', 100);