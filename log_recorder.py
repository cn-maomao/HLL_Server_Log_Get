# 导入所需的库
import socket
import time
import os
import mysql.connector
import threading
from dotenv import load_dotenv
from datetime import datetime

# 从 .env 文件加载环境变量
load_dotenv()

# --- RCON 类 (与之前相同) ---
class XOR_RCON:
    """处理与 HLL RCON 服务器的连接、加密和通信的类。"""
    def __init__(self, host, port, password, timeout=10):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self.socket = None
        self.xor_key = None

    def connect(self):
        """建立 TCP 连接并登录。"""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.settimeout(self.timeout)
        self.socket.connect((self.host, self.port))
        self.xor_key = self.socket.recv(4096)
        login_response = self.send(f"Login {self.password}")
        if "SUCCESS" in login_response:
            return True
        else:
            print(f"[{self.host}] RCON 登录失败: {login_response}")
            return False

    def xor_crypt(self, data):
        if not self.xor_key: raise ValueError("尚未接收到 XOR 密钥。")
        if isinstance(data, str): data = data.encode('utf-8')
        key_len = len(self.xor_key)
        return bytes(a ^ b for a, b in zip(data, self.xor_key * (len(data) // key_len + 1)))

    def send(self, command):
        encrypted_command = self.xor_crypt(command)
        self.socket.send(encrypted_command)
        return self.receive()

    def receive(self):
        raw_response = self.socket.recv(8192)
        if not raw_response: return ""
        decrypted_response = self.xor_crypt(raw_response)
        return decrypted_response.decode('utf-8', errors='ignore')

    def close(self):
        if self.socket:
            self.socket.close()

# --- 配置加载 ---
def load_servers():
    """从环境变量加载所有服务器配置。"""
    servers = []
    i = 1
    while True:
        name = os.getenv(f"SERVER_{i}_NAME")
        host = os.getenv(f"SERVER_{i}_HOST")
        port = os.getenv(f"SERVER_{i}_PORT")
        password = os.getenv(f"SERVER_{i}_PASSWORD")
        if not all([name, host, port, password]):
            break
        try:
            servers.append({"name": name, "host": host, "port": int(port), "password": password})
        except ValueError:
            print(f"警告: 跳过服务器 {i}，因为端口无效: {port}")
        i += 1
    return servers

# --- 数据保存 ---
def connect_db():
    """连接到 MySQL 数据库。"""
    try:
        db_conn = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            pool_name="log_pool",
            pool_size=5
        )
        return db_conn
    except mysql.connector.Error as err:
        print(f"数据库连接错误: {err}")
        return None

def insert_log_to_db(db_conn, server_name, log_content):
    """将日志内容插入数据库。"""
    try:
        cursor = db_conn.cursor()
        sql = "INSERT INTO logs (server_name, log_content) VALUES (%s, %s)"
        cursor.execute(sql, (server_name, log_content))
        db_conn.commit()
        cursor.close()
    except mysql.connector.Error as err:
        print(f"[{server_name}] 数据库插入错误: {err}")
        db_conn.reconnect()

def save_log_to_file(server_name, keyword, base_file_path, log_content):
    """将日志内容追加到本地文件。"""
    try:
        # 为每个服务器和关键词创建单独的日志文件
        # 如果关键词为空，则使用 "all" 作为文件名的一部分
        keyword_part = keyword if keyword else "all"
        file_path = f"{server_name}_{keyword_part}_{base_file_path}"
        with open(file_path, 'a', encoding='utf-8') as f:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            f.write(f"--- Log fetched at {timestamp} ---\n")
            f.write(log_content)
            f.write("\n\n")
    except IOError as e:
        print(f"[{server_name}] 写入文件错误: {e}")

# --- 工作线程 ---
def worker(server_config, keywords, save_to_db, save_to_file, log_file_path, db_conn):
    """每个服务器的独立工作线程。"""
    server_name = server_config['name']
    print(f"[{server_name}] 工作线程已启动。")
    
    rcon = XOR_RCON(
        host=server_config['host'],
        port=server_config['port'],
        password=server_config['password']
    )

    while True:
        try:
            print(f"[{server_name}] 正在连接...")
            if not rcon.connect():
                print(f"[{server_name}] 连接失败，将在 60 秒后重试...")
                time.sleep(60)
                continue
            print(f"[{server_name}] 连接成功。")

            # 连接成功后，进入内部循环获取日志
            while True:
                # 遍历关键词列表
                for keyword in keywords:
                    command = f'showlog 1 "{keyword}"' if keyword else "showlog 1"
                    print(f"[{server_name}] 发送命令: {command}")
                    logs = rcon.send(command)

                    if logs and logs.strip() != "SUCCESS":
                        # 准备要保存的完整日志内容
                        full_log_content = f"Keyword: {keyword if keyword else 'ALL'}\n{logs}"
                        
                        if save_to_db:
                            insert_log_to_db(db_conn, server_name, full_log_content)
                        if save_to_file:
                            save_log_to_file(server_name, keyword, log_file_path, logs)
                    # 短暂延迟避免过于频繁地发送命令
                    time.sleep(2) 
                
                # 完成一轮关键词查询后，等待60秒
                print(f"[{server_name}] 完成一轮查询，等待 60 秒...")
                time.sleep(60)

        except (socket.error, ValueError, ConnectionResetError) as e:
            print(f"[{server_name}] RCON 连接错误: {e}。将在 60 秒后重试...")
            rcon.close()
            time.sleep(60)
        except Exception as e:
            print(f"[{server_name}] 发生未知错误: {e}。将在 60 秒后重试...")
            time.sleep(60)

# --- 主程序 ---
def main():
    """主函数，加载配置并启动所有工作线程。"""
    servers = load_servers()
    if not servers:
        print("错误：未在 .env 文件中配置任何服务器。")
        return

    # 加载通用配置
    keywords_str = os.getenv("LOG_KEYWORDS", "")
    keywords = [k.strip() for k in keywords_str.split(',') if k.strip()]
    if not keywords: # 如果关键词列表为空，添加一个空字符串以获取所有日志
        keywords.append("")

    save_to_db = os.getenv("SAVE_TO_DB", "False").lower() == 'true'
    save_to_file = os.getenv("SAVE_TO_FILE", "False").lower() == 'true'
    log_file_path = os.getenv("LOG_FILE_PATH", "hll_logs.log")

    if not save_to_db and not save_to_file:
        print("错误: 必须在 .env 文件中启用至少一种保存方式 (SAVE_TO_DB 或 SAVE_TO_FILE)。")
        return

    # 初始化数据库连接（如果需要）
    db_conn = connect_db() if save_to_db else None
    if save_to_db and not db_conn:
        print("警告：无法连接到数据库。数据库保存功能将不可用。")
        save_to_db = False
        if not save_to_file:
            print("所有保存方式均失败，程序退出。")
            return

    # 为每个服务器创建并启动一个线程
    threads = []
    for server_config in servers:
        thread = threading.Thread(
            target=worker,
            args=(server_config, keywords, save_to_db, save_to_file, log_file_path, db_conn)
        )
        threads.append(thread)
        thread.start()

    print(f"{len(threads)} 个服务器的日志记录器已启动。按 CTRL+C 停止。")

    try:
        # 让主线程保持运行，以便捕获 KeyboardInterrupt
        for thread in threads:
            thread.join()
    except KeyboardInterrupt:
        print("\n检测到手动中断，正在关闭所有线程...")
        # 在实际应用中，需要更优雅的方式来停止线程，但对于此脚本，直接退出即可
        os._exit(0)

if __name__ == "__main__":
    main()
