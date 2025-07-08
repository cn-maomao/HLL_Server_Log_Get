--此脚本为HLL日志记录器设置数据库和表。
--请在MySQL客户端中执行这些命令。

--1.创建数据库（如果不存在）
--您可以将“hll_log”更改为首选数据库名称，
--但也要确保在.env文件中更新它。
CREATE DATABASE IF NOT EXISTS hll_log CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- 2. 使用新创建的数据库
USE hll_log;

-- 3. 创建日志表
--此表将存储从RCON服务器获取的日志。
--我们添加“server_name”以区分来自不同服务器的日志。
CREATE TABLE IF NOT EXISTS logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    server_name VARCHAR(255) NOT NULL,
    log_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    log_content TEXT NOT NULL,
    KEY idx_server_name (server_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
