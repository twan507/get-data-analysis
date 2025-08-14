import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.getcwd()), "import"))

from import_default import *
from import_database import *
from import_other import *


def transform_to_long_format(df):
    # --- 1. Làm sạch tên cột định danh ---
    # Giả định 4 cột đầu tiên luôn là cột định danh
    id_cols = df.columns[:4]
    new_id_cols = {
        id_cols[0]: 'ticker',
        id_cols[1]: 'company_name',
        id_cols[2]: 'exchange',
        id_cols[3]: 'industry'
    }
    df.rename(columns=new_id_cols, inplace=True)

    # --- 2. Chuyển đổi từ wide sang long format ---
    id_vars = list(new_id_cols.values())
    value_vars = df.columns[4:]
    df_long = pd.melt(df, id_vars=id_vars, value_vars=value_vars, var_name='indicator_full', value_name='value')
    
    # Loại bỏ các dòng có giá trị rỗng để tối ưu hóa xử lý
    df_long.dropna(subset=['value'], inplace=True)

    # --- 3. Trích xuất thông tin từ cột phức hợp ---
    def parse_indicator(indicator_full):
        parts = indicator_full.strip().split('\n')
        name = parts[0] if len(parts) > 0 else None
        
        # Tìm period (Ngày hoặc Quý)
        period_str = ' '.join(parts[1:])
        date_match = re.search(r'(\d{4}-\d{2}-\d{2})', period_str)
        quarter_match = re.search(r'(Q\d-\d{4})', period_str)
        
        period = None
        if date_match:
            period = pd.to_datetime(date_match.group(1))
        elif quarter_match:
            period = quarter_match.group(1)
        else:
            period = "N/A"

        # Tìm unit
        unit_str = parts[-1] if 'Đơn vị:' in parts[-1] else None
        unit = unit_str.replace('Đơn vị:', '').strip() if unit_str else None
        
        return name, period, unit

    parsed_cols = df_long['indicator_full'].apply(lambda x: pd.Series(parse_indicator(x), index=['name', 'period', 'unit']))
    df_long = pd.concat([df_long, parsed_cols], axis=1)

    # --- 4. Chuẩn hóa đơn vị và giá trị (Phần linh hoạt nhất) ---
    # Từ điển định nghĩa các quy tắc chuyển đổi. Dễ dàng mở rộng.
    unit_map = {
        'Nghìn VND': {'multiplier': 1000, 'new_unit': 'VND'},
        'Tỷ VND':   {'multiplier': 1_000_000_000, 'new_unit': 'VND'},
    }

    def adjust_value_and_unit(row):
        unit = row['unit']
        value = row['value']
        
        if unit in unit_map:
            rule = unit_map[unit]
            new_value = value * rule['multiplier']
            new_unit = rule['new_unit']
            return pd.Series([new_value, new_unit])
        
        return pd.Series([value, unit]) # Trả về giá trị và đơn vị gốc nếu không có quy tắc

    df_long[['value', 'unit']] = df_long.apply(adjust_value_and_unit, axis=1)

    # --- 5. Hoàn thiện DataFrame cuối cùng ---
    final_df = df_long[['ticker', 'industry', 'name', 'period', 'unit', 'value']].copy()
    
    return final_df

def get_open_excel_workbooks():
    """
    Lấy danh sách tên các workbook Excel đang mở
    """
    try:
        excel = win32com.client.GetActiveObject("Excel.Application")
        workbook_names = []
        for workbook in excel.Workbooks:
            workbook_names.append(workbook.Name)
        return workbook_names
    except:
        return []

def get_financial_statements(stock, year, quarter, period_count, file_name="workbook.xlsx"):
    """
    Lấy dữ liệu báo cáo tài chính từ Excel sử dụng FA functions
    
    Parameters:
    - stock: mã cổ phiếu (str)
    - year: năm (str hoặc int)
    - quarter: quý (str hoặc int)
    - period_count: số kỳ (str hoặc int)
    - file_name: tên file Excel (str, mặc định "workbook.xlsx")
    
    Returns:
    - fs_dict: dictionary chứa DataFrame cho từng loại báo cáo
    """
    
    # Khởi tạo dictionary để lưu kết quả
    report_list = ['IncomeStatement', 'BalanceSheet', 'CashFlow']
    fs_dict = {
        'IncomeStatement': {},
        'BalanceSheet': {},
        'CashFlow': {}
    }
    
    try:
        # Kết nối với Excel đang mở
        open_workbooks = get_open_excel_workbooks()
        excel = win32com.client.GetActiveObject("Excel.Application")
        excel.Visible = True  # Đảm bảo Excel hiển thị để kiểm tra
        
        # Duyệt qua danh sách báo cáo
        if file_name in open_workbooks:
            workbook = excel.Workbooks(file_name)
            worksheet = workbook.ActiveSheet
            
            for report_name in report_list:
                while True:
                    try:
                        worksheet.UsedRange.ClearContents()  # Xóa nội dung và công thức
                        worksheet.UsedRange.ClearFormats()   # Xóa định dạng để loại bỏ spill range cũ

                        worksheet.Range("A1").Formula2 = f'=FA.{report_name}.Reports("{stock}",{year},{quarter},{period_count},1000000)'
                        
                        # **Đọc dữ liệu từ UsedRange**
                        used_range = worksheet.UsedRange
                        rows = used_range.Rows.Count
                        cols = used_range.Columns.Count

                        data = []
                        for i in range(1, rows + 1):
                            row_data = []
                            for j in range(1, cols + 1):
                                value = worksheet.Cells(i, j).Value
                                row_data.append(value)
                            data.append(row_data)
                        break

                    except Exception as e:
                        time.sleep(0.01)

                # **Tạo DataFrame**
                temp_df = pd.DataFrame(data)
                if rows > 0:
                    temp_df.columns = temp_df.iloc[0]  # Dùng hàng đầu làm tiêu đề
                    temp_df = temp_df.iloc[1:].reset_index(drop=True)  # Bỏ hàng đầu và reset index
                else:
                    temp_df.columns = None

                fs_dict[report_name] = temp_df
        else:
            print(f"Workbook '{file_name}' không được tìm thấy trong danh sách workbook đang mở.")
            
    except Exception as e:
        print(f"Lỗi khi kết nối với Excel: {e}")
    
    return fs_dict