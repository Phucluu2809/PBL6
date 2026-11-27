# RoboNose V3 với làm mịn nhẹ

V3 là hai lựa chọn thử nghiệm trên dashboard. **04 · Đối sánh** có **ResCNN64 V3 · Làm mịn nhẹ**. **06 · Phát hiện cà phê** có **Logistic V3 · Làm mịn nhẹ**. Có thể chạy lại cùng mẫu với V2 hoặc **Model mặc định** để so kết quả. Mục 03 tiếp tục dùng ResCNN64 gốc.

## Bộ lọc và dữ liệu

Thử hai bộ lọc đối xứng ngắn trên cùng các lượt. Bản đối chứng giữ nguyên chuỗi. Kiểm tra chất lượng trên raw trước khi lọc, giữ nguyên dữ liệu biên, và giữ nguyên giá trị tại nơi cửa sổ đi qua điểm lỗi hoặc khoảng trống thời gian. Các cửa sổ nằm trong một pha và một kênh. Thời gian và số dòng giữ nguyên. File raw được đọc, phần làm mịn diễn ra trong bộ nhớ.

| Cấu hình | Trọng số từ trái sang phải |
| --- | --- |
| `light3` | `[1, 6, 1] / 8` |
| `sg5_half` | Trung bình của giá trị gốc và Savitzky–Golay bậc hai, cửa sổ 5 điểm. Trọng số cuối `[-3, 12, 52, 12, -3] / 70`. |

[Phương pháp Savitzky–Golay gốc](https://doi.org/10.1021/ac60214a047) · [Mã bộ lọc](smoothing.py)

## Đã huấn luyện gì?

- **Đối sánh người** dùng 93 lượt từ ngày 09–20/11/2026. V3 lọc nhẹ tensor exposure 6 × 120 sau khi trừ nền và chuẩn hóa. Sau đó huấn luyện lại bộ hiệu chỉnh baseline, giữ nguyên đầu vào 36 đặc trưng baseline, cấu hình huấn luyện và checkpoint CNN của V2. So các bộ lọc bằng cách giữ riêng từng ngày, chọn theo top 1 trung bình theo lớp và MRR. Dùng 13 lượt hardware từ 4 phiên để chấm khác phiên. [Báo cáo đối sánh](identity_report.json)
- **Cà phê** dùng 141 lượt từ cùng khoảng ngày, gồm 32 lượt có nhãn cà phê, 16 đối chứng không khí và 93 lượt mang tên người dùng làm nhãn âm quy ước. V3 làm mịn riêng baseline và exposure trên ba kênh A1–A3, rồi tính lại trung vị nền và trích 15 đặc trưng. Scaler và Logistic Regression được fit lại ở từng fold. Sau khi chọn bộ lọc bằng balanced accuracy, fit lại trên 141 lượt. Tập 07/11 và hardware nằm ngoài khoảng ngày train. [Báo cáo cà phê](coffee_report.json)

## Kết quả

| Phép đo | V2 | V3 dùng lọc 3 điểm |
| --- | ---: | ---: |
| Người, top 1 khác ngày trên archive | **50/76** | 47/76 |
| Người, top 1 khác phiên trên hardware | 8/13 | 8/13 |
| Người, MRR khác phiên trên hardware | 0,7333 | 0,7372 |
| Cà phê, balanced accuracy khác ngày | 71,8% | 71,8% |
| Cà phê, phát hiện đúng khác ngày | 21/32 | 21/32 |
| Cà phê, phát hiện đúng ngày 07/11 | 1/8 | 1/8 |
| Cà phê, báo dương trên hardware mang tên người | 1/13 | 1/13 |

Cả hai phép thử chọn `light3` trong các cấu hình có làm mịn. Với người, cấu hình này có top 1 trung bình theo lớp cao hơn Savitzky–Golay pha 50%. Với cà phê, hai bộ lọc bằng điểm nên chọn bộ lọc ngắn hơn. Kết quả chưa cho thấy làm mịn cải thiện top 1 người hoặc balanced accuracy cà phê. V3 được đưa lên giao diện dưới dạng tùy chọn riêng để thử cùng mẫu.

## Chạy lại

Dùng Python có PyTorch và scikit-learn. Script chỉ ghi các checkpoint và báo cáo trong `models_v3`.

```powershell
& D:/PBL6/.venv/Scripts/python.exe -m models_v3.train identity
& D:/PBL6/.venv/Scripts/python.exe -m models_v3.train coffee --nov07-root D:/PBL6/curated_raw
```
