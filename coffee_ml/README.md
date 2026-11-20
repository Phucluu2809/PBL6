# So sánh ba mô hình phát hiện cà phê trên người

Chạy từ `D:\PBL6` bằng Python trong môi trường `.venv` hiện có.

```powershell
.\.venv\Scripts\python.exe coffee_ml\run.py
```

Để thêm lượt thu, chép thư mục chứa `raw.csv` vào một trong hai nhóm sau rồi chạy lại lệnh trên. Script tạo sẵn hai thư mục này ở lần chạy đầu.

```text
coffee_ml/data/
├── no_coffee/               # 0 = người không có cà phê
│   └── luot_01/raw.csv
└── coffee/                  # 1 = người có cà phê
    └── luot_02/raw.csv
```

Giữ `timestamp`, `phase`, `phase_elapsed_s`, BME688 gas, MQ3 và các cột trạng thái cảm biến trong file gốc. `--input <thư_mục>` đọc thêm dữ liệu từ một nơi khác có cùng cấu trúc.

## Phạm vi và cách đánh giá

- Mỗi lần chạy, chương trình quét `data/`, `curated_raw/` và thư mục dữ liệu thêm. Nguồn nhãn hiện có gồm `label_manifest.csv`, các nhóm đã phân loại trong `curated_raw` và quy ước của detector cũ cho ngày 30/10/2026. Các nhãn theo tên hoặc nhóm vẫn mang tính tạm thời.
- File giống nhau theo SHA-256 được tính một lần. File thiếu nhãn, mẫu đối chứng cà phê riêng và không khí, mẫu có nhãn mâu thuẫn hoặc lỗi tín hiệu đều có trạng thái trong báo cáo.
- Mỗi lượt đo tạo 10 đặc trưng từ BME688 gas và MQ3/MQ3-1. Mỗi kênh được chuẩn hóa theo median `BASELINE` rồi tính trung bình toàn pha và cửa sổ 40–80 giây, hai phân vị và độ dốc trong `EXPOSURE`.
- Cả ba mô hình dùng cùng các lượt đo và cùng cách chia theo ngày. Mỗi vòng giữ trọn một ngày làm test, dùng các ngày còn lại để train. Kết quả tổng hợp từ dự đoán test của từng lượt đo.

## Kết quả

- `results/summary.csv` lưu Accuracy, Balanced Accuracy, F1 cho lớp có cà phê và TP, FP, TN, FN của từng mô hình.
- `results/trials.csv` lưu nhãn, nguồn nhãn, ngày thu và dự đoán của cả ba mô hình cho từng lượt được đánh giá. Các file khác có trạng thái và chi tiết khi có lỗi hoặc trùng nội dung.
