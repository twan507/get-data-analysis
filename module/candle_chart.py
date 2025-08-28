import sys
import os

sys.path.append(os.path.join(os.path.dirname(os.getcwd()), "import"))

from import_default import *
from import_database import *
from import_other import *


# ==============================================================================
# 1. CÁC HÀM TIỆN ÍCH VÀ CHUẨN BỊ DỮ LIỆU
# ==============================================================================


def _prepare_chart_data(df, config, line_columns):
    """
    Chuẩn bị các dữ liệu cần thiết cho việc vẽ biểu đồ.
    """
    max_volume = df["volume"].max()
    df["volume_color"] = np.where(df["close"] >= df["open"], config["color_up"], config["color_down"])
    return line_columns, max_volume


def _get_style_for_column(col_name):
    """Hàm hỗ trợ để lấy style cho các đường chỉ báo kỹ thuật."""
    style_mapping = {
        "SMA_20": {"color": "#00B1EC", "dash": "solid", "width": 2},
        "SMA_60": {"color": "#006080", "dash": "solid", "width": 2},
        "open": {"color": "#C71585", "dash": "dash", "width": 1.5, "line_shape": "hv"},
        "prev": {"color": "#808080", "dash": "dash", "width": 1.5, "line_shape": "hv"},
        "MFIBO": {"color": "#DFBD01", "dash": "dot", "width": 1.5, "line_shape": "hv"},
        "YFIBO": {"color": "#DFBD01", "dash": "dot", "width": 1.5, "line_shape": "hv"},
        "MPIVOT": {"color": "#E61300", "dash": "dot", "width": 1.5, "line_shape": "hv"},
        "YPIVOT": {"color": "#E61300", "dash": "dot", "width": 1.5, "line_shape": "hv"},
    }
    for key, style in style_mapping.items():
        if key in col_name:
            return style
    return {"width": 1.2, "color": "black", "dash": "solid"}


# ==============================================================================
# 2. CÁC HÀM VẼ CÁC THÀNH PHẦN CỦA BIỂU ĐỒ
# ==============================================================================


def _add_candlestick_chart(fig, df, config):
    """Thêm biểu đồ nến vào subplot chính."""
    fig.add_trace(
        go.Candlestick(
            x=df["date"],
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            increasing_line_color=config["color_up"],
            decreasing_line_color=config["color_down"],
            increasing_fillcolor=config["color_up"],
            decreasing_fillcolor=config["color_down"],
            line=dict(width=1),
            name="Giá",
        ),
        row=1,
        col=1,
        secondary_y=False,
    )


def _add_volume_chart(fig, df):
    """Thêm biểu đồ khối lượng vào subplot chính."""
    fig.add_trace(
        go.Bar(x=df["date"], y=df["volume"], marker=dict(color=df["volume_color"], opacity=0.3), name="Volume"),
        row=1,
        col=1,
        secondary_y=True,
    )


def _add_technical_lines(fig, df, line_columns, line_name_dict):
    """Thêm các đường chỉ báo kỹ thuật và trả về thông tin để tạo nhãn."""
    line_info = []
    for col in line_columns:
        if col in df.columns and not df[col].isnull().all():
            line_style_full = _get_style_for_column(col)
            line_shape_value = line_style_full.pop("line_shape", None)

            trace_args = {"x": df["date"], "y": df[col], "mode": "lines", "line": line_style_full, "name": col}

            if line_shape_value:
                trace_args["line_shape"] = line_shape_value

            fig.add_trace(go.Scatter(**trace_args), row=1, col=1, secondary_y=False)

            last_valid_idx = df[col].last_valid_index()
            if last_valid_idx is not None:
                display_name = line_name_dict.get(col, col)
                last_value = df[col].loc[last_valid_idx]
                line_info.append(
                    {
                        "name": f"{display_name}: {last_value:.2f}",
                        "value": last_value,
                        "color": _get_style_for_column(col).get("color", "black"),
                    }
                )
    return line_info


def _add_rsi_chart(fig, df, config):
    """Thêm biểu đồ RSI hoàn chỉnh."""
    rsi_col = "RSI_14"
    if rsi_col not in df.columns or df[rsi_col].isnull().all():
        return

    fig.add_trace(
        go.Scatter(x=df["date"], y=df[rsi_col], mode="lines", line=dict(color=config["color_rsi_line"], width=1.5), name="RSI"),
        row=2,
        col=1,
    )
    fig.add_hline(y=config["rsi_upper_bound"], line_dash="dash", line_color=config["color_rsi_bound_line"], line_width=1.5, row=2, col=1)
    fig.add_hline(y=config["rsi_lower_bound"], line_dash="dash", line_color=config["color_rsi_bound_line"], line_width=1.5, row=2, col=1)
    fig.add_hrect(
        y0=config["rsi_lower_bound"],
        y1=config["rsi_upper_bound"],
        fillcolor=config["color_rsi_bound_fill"],
        opacity=1,
        layer="below",
        line_width=0,
        row=2,
        col=1,
    )

    last_rsi = df[rsi_col].iloc[-1]
    fig.add_annotation(
        x=0.013,
        y=1,
        xref="x domain",
        yref="y domain",
        text=f"RSI 14: <b style='color:{config['color_rsi_line']};'>{last_rsi:.2f}</b>",
        showarrow=False,
        xanchor="left",
        yanchor="top",
        font=dict(size=config["font_size_subplot_title"], family=config["font_family"], color="black"),
        xshift=-13,
        yshift=18,
        row=2,
        col=1,
    )

    y_axis_range = df[rsi_col].max() - df[rsi_col].min()
    if y_axis_range == 0:
        y_axis_range = 20
    min_spacing = config["rsi_label_min_spacing_ratio"] * y_axis_range

    y_upper_pos = float(config["rsi_upper_bound"])
    y_lower_pos = float(config["rsi_lower_bound"])

    if abs(last_rsi - y_upper_pos) < min_spacing:
        y_upper_pos = last_rsi + min_spacing
    if abs(last_rsi - y_lower_pos) < min_spacing:
        y_lower_pos = last_rsi - min_spacing

    tag_font = dict(size=config["font_size_tag"], family=config["font_family"])
    annotations = [
        {
            "y": y_upper_pos,
            "text": f"<b>RSI {config['rsi_upper_bound']:.2f}</b>",
            "font_color": config["color_rsi_bound_tag"],
            "bgcolor": config["tag_bgcolor"],
            "bordercolor": config["color_rsi_bound_tag"],
        },
        {
            "y": y_lower_pos,
            "text": f"<b>RSI {config['rsi_lower_bound']:.2f}</b>",
            "font_color": config["color_rsi_bound_tag"],
            "bgcolor": config["tag_bgcolor"],
            "bordercolor": config["color_rsi_bound_tag"],
        },
        {
            "y": last_rsi,
            "text": f"<b>RSI {last_rsi:.2f}</b>",
            "font_color": "white",
            "bgcolor": config["color_rsi_line"],
            "bordercolor": config["color_rsi_line"],
        },
    ]

    for anno in annotations:
        fig.add_annotation(
            x=config["label_x_position"],
            y=anno["y"],
            xref="x domain",
            yref="y",
            text=anno["text"],
            ax=-10,
            ay=0,
            xanchor="left",
            yanchor="middle",
            font={**tag_font, "color": anno["font_color"]},
            bgcolor=anno["bgcolor"],
            bordercolor=anno["bordercolor"],
            borderwidth=1,
            row=2,
            col=1,
        )


# ==============================================================================
# 3. HÀM XỬ LÝ NHÃN GIÁ (ANNOTATIONS) - LOGIC MỚI
# ==============================================================================


def _process_and_add_annotations(fig, df, line_info, symbol_name, config):
    """
    Hàm tổng hợp xử lý và thêm tất cả các nhãn giá vào biểu đồ chính.
    Logic mới: Gộp tất cả các tag, sắp xếp theo giá trị, sau đó đẩy tuần tự
    từ trên xuống để đảm bảo không chồng chéo và giữ đúng thứ tự.
    """
    # --- 1. GOM TẤT CẢ CÁC TAG LẠI ---
    last_close = df["close"].iloc[-1]
    last_open = df["open"].iloc[-1]
    price_color = config["color_up"] if last_close >= last_open else config["color_down"]

    # Thêm tag giá vào danh sách chung, cùng với các tag chỉ báo
    line_info.append(
        {
            "name": f"{symbol_name}: {last_close:.2f}",
            "value": last_close,
            "is_price_tag": True,  # Đánh dấu để có style riêng
            "color": price_color,
        }
    )

    # Vẽ đường hline cho giá đóng cửa
    fig.add_hline(y=last_close, line_color=price_color, line_width=1, line_dash="dash", row=1, col=1)

    # --- 2. SẮP XẾP TẤT CẢ TAG THEO GIÁ TRỊ GIẢM DẦN ---
    # Đây là bước quan trọng nhất để đảm bảo thứ tự trực quan
    sorted_tags = sorted(line_info, key=lambda x: x["value"], reverse=True)

    # --- 3. TÍNH TOÁN VỊ TRÍ Y AN TOÀN VÀ VẼ LÊN BIỂU ĐỒ ---
    visible_y_range = df["high"].max() - df["low"].min()
    if visible_y_range == 0:
        visible_y_range = df["close"].iloc[0] * 0.1  # Tránh chia cho 0
    min_spacing = visible_y_range * config["label_min_spacing_ratio"]

    last_placed_y = None  # Dùng để lưu vị trí Y của tag ngay phía trên

    for tag_info in sorted_tags:
        y_pos = tag_info["value"]

        # Nếu đây không phải tag đầu tiên, kiểm tra xung đột với tag ngay phía trên nó
        if last_placed_y is not None:
            # Nếu vị trí hiện tại quá gần vị trí đã đặt trước đó (tức là nằm trong vùng an toàn)
            if y_pos > last_placed_y - min_spacing:
                # Đẩy vị trí hiện tại xuống để tạo khoảng trống
                y_pos = last_placed_y - min_spacing

        # Cập nhật vị trí cuối cùng đã đặt cho lần lặp tiếp theo
        last_placed_y = y_pos

        # Chuẩn bị style và vẽ annotation
        is_price_tag = tag_info.get("is_price_tag", False)

        if is_price_tag:
            font_config = dict(size=config["font_size_price_tag"], color="white", family=config["font_family"])
            bgcolor = tag_info["color"]
            bordercolor = tag_info["color"]
        else:
            font_config = dict(size=config["font_size_tag"], color=tag_info["color"], family=config["font_family"])
            bgcolor = config["tag_bgcolor"]
            bordercolor = tag_info["color"]

        fig.add_annotation(
            x=config["label_x_position"],
            y=y_pos,
            xref="x domain",
            yref="y",
            text=f"<b>{tag_info['name']}</b>",
            font=font_config,
            bgcolor=bgcolor,
            bordercolor=bordercolor,
            borderwidth=1,
            xanchor="left",
            yanchor="middle",
            ax=-10,
            ay=0,
            row=1,
            col=1,
        )


# ==============================================================================
# 4. CÁC HÀM CẤU HÌNH LAYOUT VÀ TRỤC
# ==============================================================================


def _configure_layout_and_axes(fig, df, max_volume, config, width, height):
    """Cấu hình layout tổng thể, các trục X, Y và tiêu đề."""
    last_day = df.iloc[-1]
    o, h, l, c = last_day.get("open", 0), last_day.get("high", 0), last_day.get("low", 0), last_day.get("close", 0)
    diff, pct_change = last_day.get("diff", 0), last_day.get("pct_change", 0)
    value_color = config["color_up"] if c >= o else config["color_down"]
    sign = "+" if diff >= 0 else ""
    title_text = (
        f"{config['symbol_name']} {config['time_frame']}   "
        f"<span style='color:black;'>O:</span><b style='color:{value_color};'>{o:.2f}</b> "
        f"<span style='color:black;'>H:</span><b style='color:{value_color};'>{h:.2f}</b> "
        f"<span style='color:black;'>L:</span><b style='color:{value_color};'>{l:.2f}</b> "
        f"<span style='color:black;'>C:</span><b style='color:{value_color};'>{c:.2f}</b>  "
        f"<span style='color:{value_color}; font-weight:bold;'>{sign}{diff:.2f} ({sign}{pct_change:.2%})</span>"
    )

    fig.update_layout(
        height=height,
        width=width,
        xaxis_rangeslider_visible=False,
        showlegend=False,
        margin=config["margin"],
        plot_bgcolor=config["plot_bgcolor"],
        paper_bgcolor=config["paper_bgcolor"],
        hovermode="x unified",
        font=dict(family=config["font_family"]),
        title={
            "text": title_text,
            "y": 0.98,
            "x": 0.047,
            "xanchor": "left",
            "yanchor": "top",
            "font": dict(size=config["font_size_title"], family=config["font_family"], color="black"),
        },
    )

    tick_labels, tick_vals = _generate_xaxis_ticks(df)
    fig.update_xaxes(
        showgrid=False,
        type="category",
        tickmode="array",
        tickvals=tick_vals,
        ticktext=tick_labels,
        tickfont=dict(size=config["font_size_axis"], color=config["tick_color"]),
    )

    fig.update_yaxes(
        row=1,
        col=1,
        secondary_y=False,
        showgrid=True,
        gridcolor=config["grid_color"],
        tickfont=dict(size=config["font_size_axis"], color=config["tick_color"]),
    )

    fig.update_yaxes(
        row=1,
        col=1,
        secondary_y=True,
        showgrid=False,
        showticklabels=False,
        range=[0, max_volume * config["volume_yaxis_range_multiplier"]],
    )

    fig.update_yaxes(
        row=2,
        col=1,
        showgrid=True,
        gridcolor=config["grid_color"],
        autorange=True,
        fixedrange=False,
        tickfont=dict(size=config["font_size_axis"], color=config["tick_color"]),
    )

    for i in range(10, len(df), 10):
        fig.add_shape(
            type="line", x0=i, x1=i, y0=0, y1=1, xref="x", yref="paper", line=dict(color=config["grid_color"], width=1), layer="below"
        )


def _generate_xaxis_ticks(df):
    """Tạo các nhãn và vị trí cho trục X một cách thông minh."""
    dates = pd.to_datetime(df["date"])
    labels = [""] * len(df)
    indices = []
    current_month = None

    def add_day_labels(day_indices, tick_labels):
        n = len(day_indices)
        if n >= 15:
            num = 3
        elif 8 <= n < 15:
            num = 2
        elif 4 <= n < 8:
            num = 1
        else:
            return
        pos = [(n * (j + 1)) // (num + 1) for j in range(num)]
        for p in pos:
            if p < len(day_indices):
                idx = day_indices[p]
                tick_labels[idx] = str(dates.iloc[idx].day)

    for i, date in enumerate(dates):
        if date.month != current_month:
            if indices:
                add_day_labels(indices, labels)
            current_month, indices = date.month, [i]
            if date.day < 8:
                labels[i] = date.strftime("%b")
        else:
            indices.append(i)
    if indices:
        add_day_labels(indices, labels)
    return labels, list(range(len(df)))


# ==============================================================================
# 5. HÀM CHÍNH TỔNG HỢP (ORCHESTRATION FUNCTION)
# ==============================================================================
def create_chart_config(title_font_size, axis_font_size, tag_font_size, price_tag_font_size, min_spacing_ratio, margin):
    return {
        # ---- Font Family ----
        "font_family": "Calibri",
        # ---- Font Sizes ----
        "font_size_title": title_font_size,
        "font_size_subplot_title": title_font_size,
        "font_size_axis": axis_font_size,
        "font_size_tag": tag_font_size,
        "font_size_price_tag": price_tag_font_size,
        # ---- Colors ----
        "color_up": "#00A040",
        "color_down": "#E53935",
        "tick_color": "#5E5E5E",
        "grid_color": "rgba(230, 230, 230, 0.8)",
        "plot_bgcolor": "white",
        "paper_bgcolor": "white",
        "tag_bgcolor": "rgba(255, 255, 255, 0.85)",
        # ---- RSI Colors ----
        "color_rsi_line": "#8c68c8",
        "color_rsi_bound_line": "#c3c5ca",
        "color_rsi_bound_fill": "#f2eef9",
        "color_rsi_bound_tag": "#7f7f7f",
        # ---- Chart Constants & Layout ----
        "label_x_position": 1.02,
        "label_min_spacing_ratio": min_spacing_ratio,
        "volume_yaxis_range_multiplier": 4.0,
        "rsi_upper_bound": 70,
        "rsi_lower_bound": 30,
        "rsi_label_min_spacing_ratio": min_spacing_ratio,
        "margin": margin,
    }


def create_financial_chart(
    df: pd.DataFrame,
    width,
    height,
    line_name_dict: dict,
    line_columns: list,
    chart_config: dict,
    path: str,
    image_name: str,
    symbol_name: str,
    time_frame: str = "1D",
):
    """
    Hàm chính để tạo biểu đồ tài chính hoàn chỉnh.
    """
    if df.empty:
        print("DataFrame is empty. Cannot create chart.")
        return go.Figure()

    chart_config["symbol_name"] = symbol_name
    chart_config["time_frame"] = time_frame

    line_columns, max_volume = _prepare_chart_data(df, chart_config, line_columns)

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.8, 0.2],
        specs=[[{"secondary_y": True}], [{"secondary_y": False}]],
    )

    # Các hàm vẽ thành phần
    _add_candlestick_chart(fig, df, chart_config)
    _add_volume_chart(fig, df)
    line_info = _add_technical_lines(fig, df, line_columns, line_name_dict)
    _add_rsi_chart(fig, df, chart_config)

    # Xử lý và vẽ annotations với logic mới
    _process_and_add_annotations(fig, df, line_info, symbol_name, chart_config)

    # Cấu hình layout cuối cùng
    _configure_layout_and_axes(fig, df, max_volume, chart_config, width, height)

    # Chuyển đổi fig thành dạng bytes để có thể upload hoặc dùng sau này
    image_bytes = fig.to_image(format="png", width=width, height=height, scale=2)

    # Lưu file nếu có đường dẫn
    if path and image_name:
        if not os.path.exists(path):
            os.makedirs(path)
        full_path = os.path.join(path, image_name)
        # Ghi lại từ dạng bytes đã tạo để không phải render lần 2
        with open(full_path, "wb") as f:
            f.write(image_bytes)

    # Trả về 2 giá trị như code gốc của bạn mong đợi
    return fig, image_bytes
