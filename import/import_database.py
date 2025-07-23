import os
import sys
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ExecutionTimeout, PyMongoError
from sqlalchemy import create_engine

# Thêm đường dẫn import_default
sys.path.append(os.path.join(os.path.dirname(os.getcwd()), "import"))
from import_default import *

# Load environment variables from .env file (cùng thư mục với file này)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

# Kết nối MongoDB
mongo_client = MongoClient(os.getenv("PROD_MONGO_URI"))
stock_db = mongo_client["stock_db"]
ref_db = mongo_client["ref_db"]

# Tạo các engine kết nối đến các database khác nhau
vsuccess_engine = create_engine(os.getenv("VSUCCESS_URI"))
twan_engine = create_engine(os.getenv("TWAN_URI"))
cts_engine = create_engine(os.getenv("CTS_URI"))
t2m_engine = create_engine(os.getenv("T2M_URI"))


# Các hàm tương tác DBs
def get_mongo_collection(db_collection, df_name, find_query=None, projection=None):
    # Các tham số cho việc thử lại và timeout
    MAX_RETRIES = 3  # Số lần thử lại tối đa
    OPERATION_TIMEOUT_SECONDS = 30  # Thời gian timeout cho mỗi lần thử (giây)
    RETRY_DELAY_SECONDS = 1  # Thời gian chờ giữa các lần thử lại (giây)

    # Kiểm tra df_name có tồn tại trong db_collection không
    if df_name not in db_collection.list_collection_names():
        raise ValueError(f"Collection '{df_name}' không tồn tại trong database.")

    collection = db_collection[df_name]
    if find_query is None:
        find_query = {}
    if projection is None:
        projection = {"_id": 0}

    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            # Thực hiện lệnh find với điều kiện, projection và max_time_ms
            # max_time_ms được áp dụng cho các hoạt động của cursor trên server MongoDB
            cursor = collection.find(find_query, projection)
            cursor.max_time_ms(OPERATION_TIMEOUT_SECONDS * 1000)  # Chuyển đổi giây sang mili giây

            # Dữ liệu thực sự được lấy khi chuyển cursor thành list
            # Đây là nơi ExecutionTimeout có thể xảy ra nếu server mất quá nhiều thời gian
            docs_list = list(cursor)

            # Chuyển đổi kết quả sang DataFrame và trả về
            df = pd.DataFrame(docs_list)
            return df
        except ExecutionTimeout as e:
            last_exception = e
            print(f"Truy vấn cho '{df_name}' bị timeout (lần thử {attempt + 1}/{MAX_RETRIES}). Lỗi: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Đang thử lại sau {RETRY_DELAY_SECONDS} giây...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                print(f"Đã đạt số lần thử lại tối đa cho '{df_name}'.")
        except PyMongoError as e:  # Bắt các lỗi khác liên quan đến MongoDB
            last_exception = e
            print(f"Lỗi MongoDB khi truy vấn '{df_name}' (lần thử {attempt + 1}/{MAX_RETRIES}). Lỗi: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Đang thử lại sau {RETRY_DELAY_SECONDS} giây...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                print(f"Đã đạt số lần thử lại tối đa cho '{df_name}'.")
        except Exception as e:  # Bắt các lỗi không mong muốn khác
            last_exception = e
            print(f"Lỗi không mong muốn khi truy vấn '{df_name}' (lần thử {attempt + 1}/{MAX_RETRIES}). Lỗi: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Đang thử lại sau {RETRY_DELAY_SECONDS} giây...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                print(f"Đã đạt số lần thử lại tối đa cho '{df_name}'.")

    # Nếu tất cả các lần thử đều thất bại, raise một lỗi Runtime
    if last_exception:
        raise RuntimeError(
            f"Không thể lấy dữ liệu cho '{df_name}' sau {MAX_RETRIES} lần thử. Lỗi cuối cùng: {last_exception}"
        ) from last_exception
    else:
        # Trường hợp này không nên xảy ra nếu có lỗi và đã được bắt lại
        raise RuntimeError(f"Không thể lấy dữ liệu cho '{df_name}' sau {MAX_RETRIES} lần thử (không rõ nguyên nhân).")


def overwrite_mongo_collection(collection, df):
    # Lấy tên collection hiện tại và database
    collection_name = collection.name
    db = collection.database  # Truy cập database từ collection
    temp_collection_name = f"temp_{collection_name}"
    old_collection_name = f"old_{collection_name}"

    # Reset index của DataFrame
    df_reset = df.reset_index(drop=True)
    records = df_reset.replace({pd.NaT: None}).to_dict(orient="records")

    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 1
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            # 1. Lưu dữ liệu vào collection tạm
            temp_collection = db[temp_collection_name]
            temp_collection.drop()  # Đảm bảo collection tạm sạch trước khi insert
            if records:  # Ensure records is not empty before inserting
                temp_collection.insert_many(records)

            # 2. Rename collection cũ thành 'old_' (nếu tồn tại)
            if collection_name in db.list_collection_names():
                db[collection_name].rename(old_collection_name, dropTarget=True)

            # 3. Rename collection tạm thành tên chuẩn
            # Check if temp_collection exists before renaming, as it might have been dropped or not created if records were empty
            if temp_collection_name in db.list_collection_names():
                temp_collection.rename(collection_name, dropTarget=True)
            elif not records and collection_name not in db.list_collection_names():
                # If records were empty and original collection didn't exist, effectively we are creating an empty collection
                pass  # Or db.create_collection(collection_name) if explicit creation is desired
            elif not records and collection_name in db.list_collection_names():
                # If records were empty and original collection existed, it means we want to empty it.
                # The old collection was renamed to old_collection_name, so the current state is an empty collection_name.
                # This case is handled by the rename of old_collection_name and then its deletion.
                pass

            # 4. Xóa collection 'old_' (nếu tồn tại)
            if old_collection_name in db.list_collection_names():
                db[old_collection_name].drop()

            return  # Exit if successful

        except (PyMongoError, Exception) as e:
            last_exception = e
            print(f"Error overwriting collection '{collection_name}' (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Retrying in {RETRY_DELAY_SECONDS} seconds...")
                time.sleep(RETRY_DELAY_SECONDS)
            else:
                print(f"Failed to overwrite collection '{collection_name}' after {MAX_RETRIES} attempts.")

    if last_exception:
        raise RuntimeError(
            f"Failed to overwrite collection '{collection_name}' after {MAX_RETRIES} attempts. Last error: {last_exception}"
        ) from last_exception


def save_to_mssql(engine, df, table_name, if_exists="replace", index=False, max_retries=5):
    """
    Lưu DataFrame vào SQL với cơ chế thử lại khi gặp lỗi

    Parameters:
    - df: pandas DataFrame cần lưu
    - engine: SQLAlchemy engine
    - table_name: tên bảng trong database
    - if_exists: hành động khi bảng đã tồn tại ('replace', 'append', 'fail')
    - index: có lưu index hay không
    - max_retries: số lần thử lại tối đa
    - retry_delay: thời gian chờ giữa các lần thử (giây)

    Returns:
    - True nếu thành công, raise exception nếu thất bại sau tất cả lần thử
    """
    last_exception = None
    for _ in range(max_retries):
        try:
            df.to_sql(table_name, engine, if_exists=if_exists, index=index)
            return True
        except Exception as e:
            last_exception = e

    # Nếu tất cả các lần thử đều thất bại
    if last_exception:
        raise RuntimeError(f"Không thể lưu dữ liệu vào bảng '{table_name}'. Lỗi: {last_exception}") from last_exception
