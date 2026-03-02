-- SQL script to create the parking_details table
CREATE TABLE IF NOT EXISTS parking_details (
    id SERIAL PRIMARY KEY,
    device_name VARCHAR(100) NOT NULL,
    camera_side VARCHAR(10) NOT NULL, -- 'left' or 'right'
    car_number VARCHAR(50) NOT NULL,
    start_time TIMESTAMP NOT NULL,
    end_time TIMESTAMP,
    total_amount DECIMAL(10, 2),
    is_paid BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
