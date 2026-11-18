# Hướng dẫn chạy RoboNose

Mở thư mục dự án trong VS Code. Các lệnh bên dưới chạy từ PowerShell tại `D:\PBL6`. Mã nguồn và notebook nằm trong Git. Dữ liệu và model được lưu riêng trên máy.

## 1. Chuẩn bị Python

Nếu máy chưa có môi trường `.venv`, tạo bằng Python 3.11:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r odor_embed\requirements.txt
```

Trong VS Code, mở notebook và chọn kernel `.venv\Scripts\python.exe`.

## 2. Duyệt và chuẩn bị dữ liệu

Đặt dữ liệu đã thu trong `data/`. Để xem raw, duyệt chất lượng và sao chép lượt vào thư mục nhãn, chạy:

```powershell
.\.venv\Scripts\python.exe processing\app.py
```

Mở địa chỉ localhost mà terminal in ra. Nạp thư mục nguồn và đặt đích là `D:\PBL6\curated_raw`. Tạo nhãn rồi kéo lượt vào thư mục tương ứng. Mỗi lượt trong `curated_raw/<nhãn>/<lượt>/` cần có `raw.csv` và `metadata.json`.

- `CF` là đối chứng chỉ có cà phê trong exposure.
- `kk_baseline` là đối chứng không khí phòng.
- `phuc_cf`, `tai_cf` và các nhóm người tương tự giữ nhãn người, với cà phê là điều kiện đo riêng.

## 3. Train và kiểm tra bằng notebook

Mở [train_rescnn64.ipynb](odor_embed/train_rescnn64.ipynb) và bấm **Run All**.

1. **ResCNN-64:** đọc `curated_raw`, ghi báo cáo QC, lấy 120 điểm exposure trên sáu kênh, hiệu chỉnh theo baseline và train embedding 64 chiều. Notebook hiện loss theo epoch và đường dẫn kết quả. `ALL_DATA = True` dùng toàn bộ lượt người đủ điều kiện. Chọn `ALL_DATA = False` trước khi chạy nếu muốn giữ riêng ngày đo để kiểm tra.
2. **Bảng nhận diện:** so embedding từng lượt với vector trung bình theo nhãn rồi hiện **nhãn thật → model đoán → đúng/sai**. Bảng ở cuối phần embedding có thể gồm cả `CF` và `kk_baseline`. Kết quả từ lượt model đã học dùng để kiểm tra luồng.
3. **Random Forest:** có thể chạy riêng từ tiêu đề **Random Forest · Cà phê và không khí**. Phần này chỉ lấy nhóm `CF` và `kk_baseline`, dùng 10 đặc trưng từ BME gas và MQ3 #1, rồi giữ riêng từng ngày để kiểm tra. Notebook hiện ma trận nhầm lẫn, biểu đồ đặc trưng và bảng đúng/sai. Điền `RF_SAMPLE` để thử một lượt đối chứng mới.

Muốn chỉ train từ terminal:

```powershell
.\.venv\Scripts\python.exe -m odor_embed.run train --arch rescnn64 --all-data --baseline-warn --epochs 40
```

## 4. Lưu riêng model và kết quả

Mỗi lần train sinh một thư mục `odor_embed/runs/<tên-lần-chạy>/`.

| File | Dùng để làm gì |
| --- | --- |
| `model.pt` và `model.json` | Giữ cùng nhau để nạp encoder, nhãn và chuẩn hóa đúng cấu hình |
| `embeddings.json` | Vector của từng lượt train |
| `manifest.json`, `report.json` | Nguồn, nhãn, cách chia tập, QC và kết quả |
| `training_history.json` | Loss và tiến độ từng epoch |
| `pair_eval_*/reference_embeddings.json` | Vector mẫu gốc theo nhãn, gồm các đối chứng có dữ liệu tham chiếu |
| `pair_eval_*/recognition_all_labels.csv` | Dự đoán từng lượt với bộ mẫu gốc đầy đủ |

Nếu cần chuyển máy, sao chép thư mục lần chạy và thư mục báo cáo ra nơi lưu riêng. Khi tái tạo báo cáo từ raw, vẫn cần bộ dữ liệu gốc tương ứng.

## 5. Chuẩn bị đưa code lên Git

`.gitignore` bỏ qua dữ liệu raw, bản nén, registry duyệt, kết quả train và các định dạng model thông dụng. Có thể kiểm tra phần code cần đưa lên trước khi commit:

```powershell
git add -- .gitignore HUONG_DAN.md odor_embed coffee_ml processing
git diff --cached --stat
git diff --cached --name-only
```

Git ignore áp dụng cho file chưa được theo dõi. Repo hiện đã theo dõi một số file trong `data/`, `data.zip`, `tmp/` và `analysis/results/` từ trước. Lệnh kiểm tra `git ls-files -- data data.zip tmp analysis/results` cho thấy các file đó. Nếu mục tiêu là bỏ chúng khỏi phiên bản tiếp theo của repo, cần một thay đổi Git riêng. Lịch sử Git cũ cũng cần xử lý riêng nếu từng chứa dữ liệu cần giữ kín.

Notebook có thể chứa output đã lưu, gồm tên mẫu, bảng và biểu đồ. Xóa output trong VS Code trước khi stage notebook nếu chỉ muốn đưa code.

Chi tiết về pipeline và các lần đánh giá nằm trong [tài liệu processing](processing/README.md).
