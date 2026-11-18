# QUY TRÌNH TIỀN XỬ LÝ DỮ LIỆU TÍN HIỆU E-NOSE

**Bước 01. Kiểm tra dữ liệu thô (Raw Data Inspection)**
- Kiểm tra cấu trúc dữ liệu (Schema).
- Kiểm tra thời gian lấy mẫu (Timestamp).
- Kiểm tra dữ liệu thiếu (Missing Values).
- Kiểm tra tính hợp lệ của dữ liệu (Data Validity).

**Bước 02. Kiểm tra chất lượng phép đo (Signal Quality Assessment)**
- Kiểm tra mức độ nhiễu (Noise).
- Phát hiện tín hiệu lỗi (Signal Errors).
- Đánh giá độ ổn định tín hiệu (Signal Stability).

**Bước 03. Phân đoạn tín hiệu (Signal Segmentation)**
- Giai đoạn nền (Baseline).
- Giai đoạn tiếp xúc mẫu (Exposure).
- Giai đoạn phục hồi (Recovery).

**Bước 04. Phát hiện và xử lý điểm bất thường (Outlier Detection and Handling)**
- Phát hiện nhiễu xung (Spike Detection).
- Xử lý dữ liệu không hợp lệ (Invalid Data).
- Phát hiện và xử lý các giá trị ngoại lai do lỗi kỹ thuật (Technical Outliers).

**Bước 05. Lọc nhiễu tín hiệu (Signal Denoising)**
- Bộ lọc trung vị (Median Filter).
- Bộ lọc trung bình trượt (Moving Average Filter).
- Bộ lọc Savitzky–Golay (Savitzky–Golay Filter).
- So sánh và lựa chọn phương pháp lọc phù hợp.

**Bước 06. Hiệu chỉnh đường nền (Baseline Correction)**
- Xác định giá trị nền của từng cảm biến.
- Loại bỏ ảnh hưởng của mức nền ban đầu.
- Tính tín hiệu chênh lệch so với nền.

**Bước 07. Chuẩn hóa đáp ứng (Response Normalization)**
- Chuẩn hóa theo tỷ lệ đáp ứng (Relative Response).
- Chuẩn hóa theo độ thay đổi tương đối (Fractional Response).
- Đảm bảo tính nhất quán giữa các lần đo.

**Bước 08. Kiểm tra ảnh hưởng môi trường và độ trôi cảm biến (Environmental Effects and Sensor Drift)**
- Đánh giá ảnh hưởng nhiệt độ (Temperature).
- Đánh giá ảnh hưởng độ ẩm (Humidity).
- Kiểm tra độ trôi cảm biến theo thời gian (Sensor Drift).
- Xem xét hiệu chỉnh khi có đủ dữ liệu và cơ sở thực nghiệm.

**Bước 09. Đánh giá dữ liệu sau tiền xử lý (Preprocessing Evaluation)**
- So sánh tín hiệu trước và sau xử lý.
- Kiểm tra khả năng bảo toàn hình dạng và đặc trưng tín hiệu.
- Đánh giá mức giảm nhiễu.
- Kiểm tra tính hợp lệ của dữ liệu đầu ra.
- Lưu dữ liệu đã tiền xử lý để phục vụ trích xuất đặc trưng.

---

**Kết quả đầu ra:** Bộ dữ liệu tín hiệu đã được kiểm tra, làm sạch, lọc nhiễu, hiệu chỉnh đường nền và chuẩn hóa đáp ứng, sẵn sàng cho giai đoạn trích xuất đặc trưng (Feature Extraction) và phân tích dữ liệu.