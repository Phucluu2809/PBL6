# Sơ đồ CNN-1D cho hệ thống mũi điện tử

## 1. Mục tiêu

CNN-1D nhận chuỗi thời gian từ **BME688, MQ135 và MQ3**, học hình dạng đáp ứng của cảm biến trong một chu kỳ đo, sau đó trả kết quả có cấu trúc cho backend và web dashboard.

Hai bộ dữ liệu hiện có dùng cùng schema nhưng **không có cùng bài toán nhãn**:

| Bộ dữ liệu | Vai trò đề xuất | Nhãn mục tiêu |
|---|---|---|
| `data/first_trial/` | Thử nghiệm pipeline phân loại mùi | `không khí`, `áo`, `nách`, `nước hoa`, `mắm tôm` |
| `data/chua_co_loc_khi_van_3_c/` | Thử nghiệm nhận dạng trong điều kiện thực địa | người, vị trí đo, trạng thái có/không áo |

Vì vậy không nên ghép tất cả thành một softmax duy nhất. Hai model có thể dùng **cùng kiến trúc encoder CNN-1D**, nhưng cần đầu ra và cách chia tập riêng.

## 2. Dữ liệu đầu vào

Mỗi phiên hoàn chỉnh có tần số lấy mẫu khoảng `1 Hz` và ba pha chính:

```mermaid
flowchart LR
    B["Baseline<br/>60 s"] --> E["Exposure<br/>120 s"] --> R["Recovery<br/>60 s"]
```

Sau khi loại các pha chờ và warm-up, một mẫu đưa vào model có kích thước:

```text
X.shape = (240 thời điểm, 5 kênh)
```

Năm kênh đề xuất:

1. `log(gas_resistance_ohm / R0)` của BME688.
2. `(mq135_voltage_v - V0) / (abs(V0) + epsilon)`.
3. `(mq3_voltage_v - V0) / (abs(V0) + epsilon)`.
4. `temperature_c - T0`.
5. `humidity_pct - H0`.

`R0`, `V0`, `T0`, `H0` là trung vị của pha baseline trong **chính phiên đo đó**. `pressure_hpa`, trạng thái heater và cờ hợp lệ nên dùng cho kiểm tra chất lượng, không nhất thiết đưa vào model ở phiên bản đầu.

## 3. Luồng chuẩn bị dữ liệu

```mermaid
flowchart TD
    A1["first_trial/raw.csv<br/>chỉ trial01 và trial02"]
    A2["chua_co_loc_khi_van_3_c/raw.csv<br/>bỏ folder warm-up dạng số"]

    A1 --> P["Đọc raw.csv + metadata.json"]
    A2 --> P

    P --> F["Giữ BASELINE, EXPOSURE, RECOVERY"]
    F --> Q{"Đạt kiểm tra chất lượng?"}
    Q -->|Không| X["Loại hoặc gắn cờ sample_quality"]
    Q -->|Có| S["Sắp theo phase_elapsed_s<br/>resample 1 Hz"]
    S --> I["Nội suy điểm thiếu ngắn<br/>không nội suy khoảng mất dài"]
    I --> N["Chuẩn hóa theo baseline của từng phiên"]
    N --> T["Tensor 240 x 5"]

    T --> D1["Dataset A: loại mẫu<br/>5 lớp mùi"]
    T --> D2["Dataset B: người/vị trí<br/>nhãn thực địa"]

    D1 --> M1["CNN-1D A"]
    D2 --> M2["CNN-1D B"]
```

Các điều kiện kiểm tra chất lượng tối thiểu:

- Đủ khoảng `60 + 120 + 60` mẫu ở ba pha chính.
- `gas_valid = True`, `heater_stable = True` ở phần lớn chuỗi.
- Không bão hòa ADC của MQ3/MQ135.
- Không có khoảng mất mẫu dài hoặc timestamp đảo thứ tự.
- Baseline không trôi quá ngưỡng đã định.
- Recovery được ghi nhận; chưa hồi phục phải trở thành cảnh báo chất lượng.

## 4. Kiến trúc CNN-1D đề xuất

```mermaid
flowchart LR
    IN["Input<br/>240 x 5"]

    C1["Conv1D<br/>32 filters, kernel 7<br/>padding same"]
    B1["BatchNorm + ReLU"]
    P1["MaxPool1D 2<br/>120 x 32"]

    C2["Conv1D<br/>64 filters, kernel 5<br/>padding same"]
    B2["BatchNorm + ReLU"]
    P2["MaxPool1D 2<br/>60 x 64"]

    C3["Conv1D<br/>128 filters, kernel 3<br/>padding same"]
    B3["BatchNorm + ReLU"]
    G["GlobalAveragePooling1D<br/>128"]
    DR["Dropout 0.30"]
    EMB["Dense 64 + ReLU<br/>embedding"]

    H1["Head A<br/>Dense 5 + Softmax<br/>loại mẫu"]
    H2["Head B<br/>Dense N + Softmax<br/>người hoặc vị trí"]
    OOD["Ngưỡng tin cậy / OOD<br/>unknown nếu không chắc"]

    IN --> C1 --> B1 --> P1 --> C2 --> B2 --> P2 --> C3 --> B3 --> G --> DR --> EMB
    EMB --> H1 --> OOD
    EMB --> H2 --> OOD
```

### Kích thước qua từng tầng

| Tầng | Đầu ra |
|---|---:|
| Input | `240 × 5` |
| Conv1D(32, 7) + MaxPool(2) | `120 × 32` |
| Conv1D(64, 5) + MaxPool(2) | `60 × 64` |
| Conv1D(128, 3) | `60 × 128` |
| GlobalAveragePooling1D | `128` |
| Dense embedding | `64` |
| Softmax | `5` hoặc `N` lớp |

Kiến trúc này cố ý nhỏ để hạn chế overfit và đủ nhẹ để chạy trên laptop backend. Chưa nên tăng số block hoặc thêm attention khi số phiên đo còn ít.

## 5. Cách dùng hai bộ dữ liệu

### Model A — kiểm chứng pipeline bằng `first_trial`

Chỉ dùng 10 phiên chính có tiền tố `trial01_` và `trial02_`. Các folder còn lại là dữ liệu test/tối ưu theo `note.txt`.

```mermaid
flowchart LR
    T1["trial01<br/>5 loại mẫu"] --> TRAIN["Huấn luyện / tuning"]
    T2["trial02<br/>5 loại mẫu"] --> TEST["Kiểm tra khác lượt đo"]
    TRAIN --> A["CNN-1D<br/>5 lớp"]
    A --> TEST
```

Có thể đảo `trial01` và `trial02`, rồi báo cáo trung bình hai lượt. Không chia ngẫu nhiên các cửa sổ của cùng một phiên vào cả train và test vì sẽ gây rò rỉ dữ liệu.

### Model B — dữ liệu thực địa `chua_co_loc_khi_van_3_c`

Theo `README.txt`, folder tên hoàn toàn bằng số là warm-up; folder đặt tên bằng chữ mới là ứng viên cho dữ liệu đo. Metadata cần được chuẩn hóa thành các cột:

```text
person | body_location | clothing | date | session_id | condition
```

Nếu mục tiêu là nhận dạng người, chia train/validation/test theo **ngày hoặc session**, không chia ngẫu nhiên theo dòng. Nếu mục tiêu là nhận dạng vị trí đo, cần group theo `person + date` để model không học danh tính người thay cho vị trí.

```mermaid
flowchart TD
    F["Phiên thực địa đã lọc"] --> G["Group split theo ngày/session"]
    G --> TR["Train"]
    G --> VA["Validation"]
    G --> TE["Test độc lập"]
    TR --> B["CNN-1D cùng kiến trúc"]
    VA --> B
    B --> TE
    TE --> R["Accuracy + macro F1<br/>confusion matrix + unknown rate"]
```

## 6. Luồng suy luận trong hệ thống đề xuất

```mermaid
sequenceDiagram
    participant ESP as ESP32 + cảm biến
    participant MQTT as MQTT broker
    participant API as Backend API
    participant QC as Quality gate
    participant CNN as CNN-1D service
    participant DB as Cơ sở dữ liệu
    participant WEB as Web dashboard
    participant AGENT as Trợ lý giọng nói

    ESP->>MQTT: telemetry theo session_id
    MQTT->>API: dữ liệu BME688, MQ135, MQ3
    API->>DB: lưu raw measurements
    API->>WEB: stream tiến trình qua WSS
    API->>QC: phiên baseline/exposure/recovery hoàn tất
    QC-->>API: quality flags + tensor 240x5
    alt mẫu đạt chất lượng
        API->>CNN: predict(tensor, model_version)
        CNN-->>API: label, score, embedding, ood_score
        API->>DB: lưu kết quả và model_version
        API-->>WEB: hiển thị dự đoán + cảnh báo
        API-->>AGENT: cho phép đọc kết quả đã lưu
    else mẫu không đạt
        API-->>WEB: yêu cầu đo lại, không kết luận nhãn
    end
```

Model service nên trả về:

```json
{
  "session_id": "...",
  "predicted_label": "...",
  "model_score": 0.82,
  "ood_score": 0.14,
  "sample_quality": "pass",
  "quality_flags": [],
  "model_version": "cnn1d-2026-10-v1"
}
```

`model_score` chỉ được gọi là xác suất khi model đã được hiệu chuẩn trên tập validation độc lập. Nếu score thấp hoặc OOD cao, backend phải trả nhãn `unknown` thay vì ép chọn một lớp.

## 7. Lưu ý quan trọng với dữ liệu hiện tại

- `first_trial` chỉ có 2 lượt cho mỗi lớp, chưa đủ để chứng minh CNN tổng quát hóa.
- Dữ liệu thực địa hiện có ít phiên, không cân bằng người/vị trí/trang phục và có ảnh hưởng mạnh của ngày đo.
- Cắt một phiên thành nhiều cửa sổ làm tăng số tensor nhưng **không làm tăng số mẫu độc lập**.
- Nên thu thêm tối thiểu nhiều phiên cho mỗi lớp, trên nhiều ngày, đảo thứ tự mẫu và giữ quy trình baseline/exposure/recovery giống nhau.
- Trước khi đủ dữ liệu, CNN-1D nên được xem là prototype; cần so sánh với baseline đơn giản như nearest centroid, logistic regression hoặc random forest trên đặc trưng thủ công.

## 8. Cấu hình huấn luyện khởi đầu

| Thành phần | Giá trị đề xuất |
|---|---|
| Loss | Cross entropy có class weight |
| Optimizer | Adam, learning rate `1e-3` |
| Batch size | `4–8` do dữ liệu nhỏ |
| Epoch tối đa | `100` |
| Early stopping | patience `12–15` |
| Regularization | Dropout `0.30`, weight decay `1e-4` |
| Model selection | Macro F1 trên group validation |
| Augmentation nhẹ | jitter nhỏ, scale nhỏ, time shift tối đa vài giây |
| Không nên dùng | đảo thời gian, trộn pha, augmentation làm đổi biên phase |

Pipeline tiền xử lý phải được lưu cùng model và dùng nguyên trạng ở backend; không tính normalization từ toàn bộ dataset trước khi chia train/test.
