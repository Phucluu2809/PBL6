# RoboNose preprocessing pipeline

Chạy toàn bộ pipeline cho một ngày:

```powershell
.\.venv\Scripts\python.exe analysis\run_preprocessing.py 2026-11-07
```

Đầu ra được tạo lại tại:

```text
data/<YYYY-MM-DD>/PREPROCESSED/
```

Pipeline thực hiện tự động:

1. Tìm toàn bộ `trials/*/raw.csv`.
2. Kiểm tra trạng thái và tính hợp lệ từng cảm biến.
3. Nội suy gap tối đa 3 giây trong cùng pha.
4. Hampel cho tín hiệu khí.
5. Savitzky–Golay riêng từng pha.
6. Chuẩn hóa theo baseline.
7. Xuất CSV, QC và manifest.

Mọi tham số nằm trong `config.py`. Không sửa dữ liệu nguồn.
