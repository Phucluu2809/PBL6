# Đồ thị chồng tín hiệu theo 4 nhóm

Báo cáo này thực hiện **Bước 1 – kiểm tra lại đồ thị tín hiệu**. Chưa dùng các feature nâng cao và không huấn luyện mô hình.

## Phương pháp

- Nhóm được lấy từ `label_manifest.csv`; phiên paired không nằm trong bốn nhóm này và sẽ được xử lý riêng ở Bước 2.
- Chỉ sử dụng ba pha `BASELINE`, `EXPOSURE`, `RECOVERY`; bỏ `MONITOR` và `WAIT_*`.
- Chỉ giữ dòng cảm biến hợp lệ theo cờ status/fresh/quality; BME688 còn yêu cầu `gas_valid`, `heater_stable` và `new_data`.
- Chuẩn hóa từng cảm biến, từng phiên bằng `R(t) = 100 × (X(t) − B0) / |B0|`, với `B0` là median của BASELINE gốc.
- Trung bình và SD được tính theo từng giây sau khi nội suy riêng từng pha; không nối dữ liệu qua khoảng chờ.
- `Median r hình dạng` là median tương quan Pearson từng cặp đường cong EXPOSURE. Đây là chỉ số thăm dò, không phải kiểm định xác nhận.

Ngưỡng diễn giải `rõ/vừa/yếu` chỉ là quy ước mô tả: biên độ median lần lượt ≥2%, ≥0,5% hoặc thấp hơn, đồng thời yêu cầu tối thiểu 75% phiên cùng chiều.

**Cảnh báo khi đọc biểu đồ:** các giá trị đã qua cờ QC vẫn có thể chứa spike đơn lẻ. Script cố ý không làm mượt hoặc cắt ngọn để người đọc nhìn thấy chúng. Một spike không được xem là phản ứng mùi nếu không kéo dài và không lặp lại ở các phiên khác; vùng ±SD cũng sẽ phình lớn tại những thời điểm này.

## Nhóm A – Human Only

**Số phiên:** 7. **Mục tiêu:** Xác định tín hiệu nền của người.

### Tín hiệu gốc

![Nhóm A – Human Only – tín hiệu gốc](./group_overlays/A_human_only_raw.svg)

### Tín hiệu chuẩn hóa

![Nhóm A – Human Only – tín hiệu chuẩn hóa](./group_overlays/A_human_only_normalized.svg)

### Trung bình và độ phân tán

![Nhóm A – Human Only – trung bình và SD](./group_overlays/A_human_only_mean_sd.svg)

### Đánh giá định lượng

| Cảm biến | Median EXPOSURE | Khoảng giữa phiên | Cùng chiều | Median r hình dạng | Nhận xét |
|---|---:|---:|---:|---:|---|
| BME688 gas | -1.19% (giảm) | -6.96% → 0.68% | 86% | 0.15 | vừa; hình dạng kém ổn định |
| MQ135-1 | 0.21% (tăng) | -0.24% → 3.56% | 86% | -0.03 | yếu; hình dạng kém ổn định |
| MQ3-1 | 0.72% (tăng) | -0.29% → 3.75% | 86% | 0.09 | vừa; hình dạng kém ổn định |
| MQ135-2 | -0.03% (gần 0) | -0.47% → 1.25% | 14% | 0.02 | không cùng chiều; hình dạng kém ổn định |
| MQ3-2 | -0.04% (gần 0) | -1.75% → 0.36% | 14% | -0.05 | không cùng chiều; hình dạng kém ổn định |

## Nhóm B – Human + Coffee

**Số phiên:** 4. **Mục tiêu:** Kiểm tra chiều đáp ứng và độ lặp lại khi Tài mang cà phê.

### Tín hiệu gốc

![Nhóm B – Human + Coffee – tín hiệu gốc](./group_overlays/B_human_coffee_raw.svg)

### Tín hiệu chuẩn hóa

![Nhóm B – Human + Coffee – tín hiệu chuẩn hóa](./group_overlays/B_human_coffee_normalized.svg)

### Trung bình và độ phân tán

![Nhóm B – Human + Coffee – trung bình và SD](./group_overlays/B_human_coffee_mean_sd.svg)

### Đánh giá định lượng

| Cảm biến | Median EXPOSURE | Khoảng giữa phiên | Cùng chiều | Median r hình dạng | Nhận xét |
|---|---:|---:|---:|---:|---|
| BME688 gas | -2.30% (giảm) | -4.08% → 0.93% | 75% | 0.08 | rõ; hình dạng kém ổn định |
| MQ135-1 | 0.05% (gần 0) | -0.01% → 0.38% | 50% | -0.10 | không cùng chiều; hình dạng kém ổn định |
| MQ3-1 | 1.12% (tăng) | -0.98% → 2.64% | 75% | -0.04 | vừa; hình dạng kém ổn định |
| MQ135-2 | 0.11% (tăng) | -0.22% → 0.33% | 75% | 0.24 | yếu; hình dạng kém ổn định |
| MQ3-2 | -0.18% (giảm) | -0.37% → 0.08% | 75% | 0.04 | yếu; hình dạng kém ổn định |

## Nhóm C – Coffee Only

**Số phiên:** 4. **Mục tiêu:** Khảo sát fingerprint của cà phê riêng.

### Tín hiệu gốc

![Nhóm C – Coffee Only – tín hiệu gốc](./group_overlays/C_coffee_only_raw.svg)

### Tín hiệu chuẩn hóa

![Nhóm C – Coffee Only – tín hiệu chuẩn hóa](./group_overlays/C_coffee_only_normalized.svg)

### Trung bình và độ phân tán

![Nhóm C – Coffee Only – trung bình và SD](./group_overlays/C_coffee_only_mean_sd.svg)

### Đánh giá định lượng

| Cảm biến | Median EXPOSURE | Khoảng giữa phiên | Cùng chiều | Median r hình dạng | Nhận xét |
|---|---:|---:|---:|---:|---|
| BME688 gas | -3.93% (giảm) | -6.79% → -1.99% | 100% | 0.07 | rõ; hình dạng kém ổn định |
| MQ135-1 | -0.19% (giảm) | -0.92% → 0.11% | 75% | -0.24 | yếu; hình dạng kém ổn định |
| MQ3-1 | 1.64% (tăng) | 0.69% → 4.13% | 100% | 0.02 | vừa; hình dạng kém ổn định |
| MQ135-2 | -0.34% (giảm) | -1.15% → -0.14% | 100% | 0.03 | yếu; hình dạng kém ổn định |
| MQ3-2 | 0.06% (tăng) | -0.38% → 0.16% | 75% | 0.09 | yếu; hình dạng kém ổn định |

## Nhóm D – Air

**Số phiên:** 1. **Mục tiêu:** Kiểm tra tín hiệu nền và carry-over.

### Tín hiệu gốc

![Nhóm D – Air – tín hiệu gốc](./group_overlays/D_air_raw.svg)

### Tín hiệu chuẩn hóa

![Nhóm D – Air – tín hiệu chuẩn hóa](./group_overlays/D_air_normalized.svg)

### Trung bình và độ phân tán

![Nhóm D – Air – trung bình và SD](./group_overlays/D_air_mean_sd.svg)

### Đánh giá định lượng

| Cảm biến | Median EXPOSURE | Khoảng giữa phiên | Cùng chiều | Median r hình dạng | Nhận xét |
|---|---:|---:|---:|---:|---|
| BME688 gas | 0.11% (tăng) | 0.11% → 0.11% | 100% | NA | yếu; chưa đo lặp |
| MQ135-1 | 4.44% (tăng) | 4.44% → 4.44% | 100% | NA | rõ; chưa đo lặp |
| MQ3-1 | -1.03% (giảm) | -1.03% → -1.03% | 100% | NA | vừa; chưa đo lặp |
| MQ135-2 | -0.22% (giảm) | -0.22% → -0.22% | 100% | NA | yếu; chưa đo lặp |
| MQ3-2 | -0.74% (giảm) | -0.74% → -0.74% | 100% | NA | vừa; chưa đo lặp |

Nhóm Air chỉ có một phiên nên không thể đánh giá độ lặp lại hoặc độ phân tán giữa các lần đo.

## Trả lời câu hỏi chính

### Cảm biến nào phản ứng rõ trong nhóm Human + Coffee?

Theo quy ước mô tả ở trên: **BME688 gas**.
Kết quả này chỉ nói về biên độ trung vị và chiều đáp ứng. Với BME688, đồ thị vẫn có spike rất sâu ở một phiên và median tương quan hình dạng thấp, nên chưa thể gọi là fingerprint ổn định.

### Phản ứng có cùng chiều không?

Xem cột `Cùng chiều` của Nhóm B. Một cảm biến chỉ được xem là nhất quán sơ bộ khi đạt ít nhất 75%; tỷ lệ thấp hơn cho thấy dấu đáp ứng đổi giữa các phiên.

### Hình dạng có tương tự giữa các lần đo không?

Không cảm biến nào đạt median tương quan đường cong EXPOSURE ≥0,70.

Độ giống hình dạng không đồng nghĩa với khả năng phân biệt cà phê: đường cong có thể lặp lại nhưng vẫn giống Human Only hoặc Air. Cần so sánh chéo nhóm ở các bước tiếp theo.

## File đầu ra

- Dữ liệu định lượng: [`group_overlay_summary.csv`](./group_overlay_summary.csv).
- Bộ 12 SVG: thư mục [`group_overlays`](./group_overlays/).
- Script tái lập: [`../../analysis/generate_group_overlay_report.py`](../../analysis/generate_group_overlay_report.py).
