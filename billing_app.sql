CREATE TABLE `clients` (
  `id` int(11) PRIMARY KEY,
  `name` varchar(100),
  `org_id` int(11),
  `no_of_users` int(11)
);

CREATE TABLE `org_info` (
  `id` int(11) PRIMARY KEY,
  `org_id` int(11),
  `org_name` varchar(100),
  `org_address` varchar(500),
  `org_phone` varchar(20),
  `org_gst` varchar(50),
  `org_fssai` varchar(50),
  `org_status` int(11),
  `created_at` timestamp,
  `updated_at` timestamp
);

CREATE TABLE `users` (
  `id` integer PRIMARY KEY,
  `name` varchar(255),
  `phone` varchar(15),
  `password` varchar(255),
  `area` varchar(255),
  `pincode` char(6),
  `user_uid` int(11),
  `parent_uid` int(11),
  `role` int(11),
  `org` int(11),
  `status` varchar(10),
  `created_at` timestamp,
  `updated_at` timestamp
);

CREATE TABLE `user_role` (
  `id` int(11) PRIMARY KEY,
  `role_id` int(11),
  `description` varchar(100)
);

CREATE TABLE `menu` (
  `id` int(11) PRIMARY KEY,
  `item_id` char(10) UNIQUE,
  `item_name` varchar(100),
  `item_cat` varchar(50),
  `item_qty` int(11),
  `item_price` int(11),
  `item_status` char(1),
  `item_created_at` timestamp,
  `item_updated_at` timestamp,
  `org_id` int(11),
  `manager_id` int(11)
);

CREATE TABLE `cart` (
  `id` int(11) PRIMARY KEY,
  `order_id` char(10),
  `cart_id` char(10),
  `item_id` char(10),
  `item_qty` int(11),
  `order_created_at` timestamp,
  `order_updated_at` timestamp,
  `manager_id` int(11),
  `status` char(10)
);

CREATE TABLE `customer_info` (
  `id` int(11) PRIMARY KEY,
  `order_id` char(10),
  `customer_phone` varchar(20),
  `customer_name` varchat(50)
);

CREATE TABLE `payment_mode` (
  `id` int(11) PRIMARY KEY,
  `order_id` char(10),
  `mode` varchar(100),
  `org_id` int(11),
  `billder_by` int(11)
);

ALTER TABLE `user_role` ADD FOREIGN KEY (`role_id`) REFERENCES `users` (`role`);

ALTER TABLE `menu` ADD FOREIGN KEY (`org_id`) REFERENCES `users` (`org`);

ALTER TABLE `cart` ADD FOREIGN KEY (`item_id`) REFERENCES `menu` (`item_id`);

ALTER TABLE `menu` ADD FOREIGN KEY (`manager_id`) REFERENCES `users` (`parent_uid`);

ALTER TABLE `cart` ADD FOREIGN KEY (`manager_id`) REFERENCES `users` (`parent_uid`);

ALTER TABLE `clients` ADD FOREIGN KEY (`org_id`) REFERENCES `users` (`org`);

ALTER TABLE `org_info` ADD FOREIGN KEY (`org_id`) REFERENCES `users` (`org`);

ALTER TABLE `customer_info` ADD FOREIGN KEY (`order_id`) REFERENCES `cart` (`order_id`);

ALTER TABLE `payment_mode` ADD FOREIGN KEY (`order_id`) REFERENCES `cart` (`order_id`);
