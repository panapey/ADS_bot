CREATE TABLE users (
    id INT,
    username VARCHAR(255),
    role VARCHAR(255),
    city VARCHAR(255),
    organization VARCHAR(255),
    full_name VARCHAR(255)
);

CREATE TABLE requests (
    id INT PRIMARY KEY IDENTITY,
    user_id INT,
    subject VARCHAR(255),
    text TEXT,
    status VARCHAR(255),
);
