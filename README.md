# RoboNose – Nhận diện người bằng mùi cơ thể

RoboNose là pipeline thử nghiệm nhận diện một người trong nhóm đã biết bằng tín hiệu chuỗi thời gian từ mảng cảm biến khí. Hệ thống hiện sử dụng dữ liệu BME gas và MQ135-1, chuyển mỗi phiên đo thành vector bảy chiều rồi so sánh với profile từng người bằng cosine similarity.

> Trạng thái hiện tại: proof-of-concept. Model và ngưỡng nhận diện đã chạy được đầu-cuối, nhưng cần thêm phiên đo thật độc lập cho mỗi người trước khi dùng như hệ thống xác nhận danh tính.

## Luồng xử lý

```text
raw.csv mới
   ↓ kiểm tra chất lượng
BASELINE / EXPOSURE / RECOVERY
   ↓ chuẩn hóa và nội suy
7 đặc trưng
   ↓ z-score + L2 normalization
vector cosine
   ↓ so với identity_model.json
identity_accepted / identity_rejected / quality_rejected
```

## Cấu trúc chính

```text
analysis/
├── augment_and_extract_odor_features.py  # Làm giàu, trích đặc trưng, tạo model
├── predict_odor_identity.py              # Kiểm tra một mẫu mới
└── generate_2026_10_25_readme.py         # Tạo báo cáo và biểu đồ dữ liệu

data/
├── 2026-10-25/                           # Dữ liệu thật ban đầu
│   ├── README.md                         # Phân tích riêng bộ dữ liệu này
│   └── report_assets/                    # Các biểu đồ SVG
└── 2026-10-25_augmented/                 # Dữ liệu và model đã sinh
    ├── augmented_signals.csv
    ├── feature_vectors.csv
    ├── identity_profiles.csv
    ├── identity_model.json
    ├── scaler.json
    └── run_quality.csv
```

## Yêu cầu đầu vào

Một phiên mới phải được thu bằng cùng hệ cảm biến và cùng protocol:

```text
BASELINE 60 giây → EXPOSURE 120 giây → RECOVERY 60 giây
```

File `raw.csv` phải giữ tên cột giống dữ liệu huấn luyện, đặc biệt gồm:

- `phase`, `phase_elapsed_s`
- `gas_resistance_ohm`, `bme_status`, `bme_fresh`
- `gas_valid`, `heater_stable`, `new_data`
- `mq135_1_voltage_v`, `mq135_1_status`, `mq135_1_fresh`, `mq135_1_quality`

Không làm augmentation cho mẫu cần nhận diện. Predictor luôn xử lý trực tiếp phiên đo thật.

## Sử dụng nhanh

### Cách đơn giản nhất: chạy `main.py`

Đặt file của lần thu mới ở bất kỳ đâu, giữ nguyên định dạng `raw.csv`, rồi chạy:

```powershell
python main.py "đường_dẫn\tới\raw.csv"
```

Ví dụ:

```powershell
python main.py "data\mau_moi\raw.csv"
```

Bạn cũng có thể chạy không kèm đường dẫn, sau đó dán đường dẫn khi chương trình hỏi:

```powershell
python main.py
```

Chương trình tái sử dụng pipeline trong `analysis\predict_odor_identity.py`: kiểm tra chất lượng, trích bảy đặc trưng, chuẩn hóa thành vector, tính cosine similarity với profile bốn người và áp dụng ngưỡng chấp nhận. Kết quả đầy đủ được ghi vào `prediction.json` cạnh file đầu vào.

### 1. Tạo lại dữ liệu augmented và model

Chạy tại thư mục gốc của repository:

```powershell
python analysis\augment_and_extract_odor_features.py
```

Pipeline sẽ:

1. Đọc các phiên trong `data/2026-10-25/`.
2. Loại phiên không đạt quality gate.
3. Chuẩn hóa và làm giàu tín hiệu.
4. Trích vector đặc trưng cho từng mẫu.
5. Tạo profile và ngưỡng tương thích cho từng người.
6. Ghi model vào `data/2026-10-25_augmented/`.

### 2. Kiểm tra một phiên mới

Truyền cả thư mục chứa `raw.csv`:

```powershell
python analysis\predict_odor_identity.py --input "data\mau_moi"
```

Hoặc truyền trực tiếp file:

```powershell
python analysis\predict_odor_identity.py --input "data\mau_moi\raw.csv"
```

Kết quả được lưu thành `prediction.json` bên cạnh file đầu vào.

### 3. Ghi đè ngưỡng nhận diện

Mặc định predictor dùng ngưỡng trong `identity_model.json`. Sau khi đã hiệu chỉnh bằng dữ liệu thật độc lập, có thể truyền ngưỡng riêng:

```powershell
python analysis\predict_odor_identity.py `
  --input "data\mau_moi\raw.csv" `
  --reject-below 0.80 `
  --min-margin 0.10
```

Hai con số trên chỉ là ví dụ cú pháp, không phải ngưỡng đã được khuyến nghị cho bộ dữ liệu hiện tại.

## Đọc `prediction.json`

| Trạng thái | Ý nghĩa |
|---|---|
| `identity_accepted` | Mẫu vượt ngưỡng cosine và margin của profile đứng đầu. |
| `identity_rejected` | Mẫu không đủ giống hoặc hai profile đứng đầu quá gần nhau. |
| `quality_rejected` | Dữ liệu thiếu, lỗi hoặc không đủ tỷ lệ hợp lệ để trích đặc trưng. |
| `ranked_match_only` | Chỉ xếp hạng cosine vì model không có ngưỡng tương thích. |

Các trường quan trọng:

```text
prediction.person                    # Người được chấp nhận; null nếu bị từ chối
prediction.best_match                # Profile có cosine cao nhất
prediction.best_cosine_similarity    # Điểm cosine top-1
prediction.second_match              # Profile đứng thứ hai
prediction.margin                    # Chênh lệch top-1 và top-2
prediction.similarity_threshold      # Ngưỡng cosine đã áp dụng
prediction.margin_threshold          # Ngưỡng margin đã áp dụng
scores                               # Điểm chi tiết của toàn bộ người đã biết
```

## Đặc trưng đang sử dụng

Mỗi phiên được nén thành bảy đặc trưng:

1. Mean BME gas trong EXPOSURE.
2. Mean BME gas ở một phần ba giữa EXPOSURE.
3. Phân vị 10% của BME gas trong EXPOSURE.
4. Phân vị 90% của BME gas trong EXPOSURE.
5. Mean MQ135-1 ở một phần ba giữa EXPOSURE.
6. Slope MQ135-1 trong EXPOSURE.
7. Mean 10 giây cuối RECOVERY của MQ135-1.

Scaler chỉ được fit từ các phiên thật đạt chất lượng. Centroid từng người được cân bằng theo `source_run`: các biến thể augmented được trung bình trong từng phiên trước, sau đó các phiên thật mới được trung bình với trọng số bằng nhau.

## Các file model

| File | Vai trò |
|---|---|
| `scaler.json` | Mean/std để biến đặc trưng mới sang cùng không gian với model. |
| `identity_model.json` | Vector profile, ngưỡng cosine và ngưỡng margin từng người. |
| `identity_profiles.csv` | Bản dạng bảng của profile để kiểm tra thủ công. |
| `feature_vectors.csv` | Vector của toàn bộ mẫu thật và augmented. |
| `run_quality.csv` | Phiên được giữ hoặc loại cùng lý do. |

## Tạo lại báo cáo dữ liệu

```powershell
python analysis\generate_2026_10_25_readme.py
```

Báo cáo chi tiết, biểu đồ và đánh giá cảm biến nằm tại [`data/2026-10-25/README.md`](data/2026-10-25/README.md).

## Giới hạn hiện tại

- Bộ ngày 25/10 có 7 phiên, trong đó chỉ 6 phiên đạt quality gate.
- Tai có 3 phiên sạch; Dung, Minh và Quy chỉ có một phiên sạch/người.
- Augmentation tạo biến thể nhiễu quanh phiên gốc, không thay thế được biến thiên giữa các lần thu thật.
- Ngưỡng trong model được ước lượng từ dữ liệu augmented nên có thể lạc quan.
- Chỉ nên đánh giá model bằng phiên thật chưa tham gia tạo scaler, profile hoặc threshold.

## Tài liệu liên quan

- [`data/2026-10-25/README.md`](data/2026-10-25/README.md): mô tả và phân tích bộ dữ liệu ngày 25/10.
- [`data/2026-10-25_augmented/README.md`](data/2026-10-25_augmented/README.md): mô tả các artifact sau augmentation.
- [`CNN_1D_HE_THONG_MUI_DIEN_TU.md`](CNN_1D_HE_THONG_MUI_DIEN_TU.md): ghi chú hướng phát triển mô hình CNN 1D.
