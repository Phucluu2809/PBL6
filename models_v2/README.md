# Đối sánh V2 bằng toàn bộ baseline

## Bộ hiệu chỉnh đã học

Trong **04 · Đối sánh**, chọn **ResCNN64 V2 · Bộ hiệu chỉnh đã học**.
Mạng hiệu chỉnh nhận sáu cửa sổ 10 giây trên mỗi kênh baseline. Mạng học
mức bù và độ dốc có giới hạn cho từng kênh exposure đã chuẩn hóa.
ResCNN64 gốc tạo embedding 64 chiều từ đầu vào đã hiệu chỉnh.

Hàm mất mát dùng nhãn danh tính qua classifier đã khóa của ResCNN64
và phạt mức hiệu chỉnh quá lớn. Các cấu hình thử nghiệm contrastive dùng thêm
mẫu cùng nhãn từ ngày khác. CNN gốc được giữ ở chế độ eval và khóa trọng số.
Bộ hiệu chỉnh học để hỗ trợ phân biệt danh tính, chưa được huấn luyện
để tái tạo đường tín hiệu blank.

Phiên bản hiện tại chọn cấu hình bằng cách giữ riêng từng ngày trong
tập ngày 09–20/11/2026. Tên mẫu có nhãn rõ được ánh xạ vào 9 lớp gốc.
Các lượt chưa hoàn chỉnh, trùng UUID/hash, không rõ nhãn hoặc không qua
kiểm tra tín hiệu và cấu hình được ghi vào báo cáo. Cấu hình được chọn theo
top 1 trung bình theo lớp, dùng MRR để phân xử khi bằng điểm. Tập
`data/hardware` chỉ được mở để đánh giá sau khi chốt cấu hình.

Chạy lại từ thư mục gốc bằng môi trường Python có PyTorch:

```powershell
& D:/PBL6/.venv/Scripts/python.exe -m models_v2.improve
```

Kết quả lưu trong `baseline_corrector_grouped.pt` và `grouped_training_report.json`.
Checkpoint `baseline_corrector.pt` và báo cáo cũ ghi lại lần thử ban đầu.
Checkpoint bộ hiệu chỉnh chỉ chạy cùng bản CNN và thông số chuẩn hóa khớp hash.
Đánh giá đối sánh dùng các lượt hardware khác phiên và loại UUID/hash trùng với
danh sách tham chiếu đã biết. Các lượt hardware này đã được dùng để đánh giá
những lần thử trước, nên cần một đợt đo mới nếu muốn xác nhận khả năng tổng quát.

## Bản thử nghiệm bù xu hướng và blank

Ở dashboard, lưu các mẫu tại **05 · Danh sách mẫu**, vào **04 · Đối sánh**,
chọn **ResCNN64 V2 · Hiệu chỉnh toàn bộ baseline (thử nghiệm)**, chọn một mẫu tham chiếu
rồi chạy. Có thể chạy lại cùng mẫu với **Model mặc định** để so thứ hạng.
V2 dùng kiến trúc, checkpoint và thông số chuẩn hóa của ResCNN64 hiện có.
Checkpoint đã học với pipeline cũ. V2 thử đưa đầu vào đã hiệu chỉnh mới qua
chính encoder đó, chưa fine-tune. Mục 03 tiếp tục dùng model danh tính và model cà phê hiện có.

V2 đọc các lượt hardware hoàn chỉnh, cần 60 điểm BASELINE và 120 điểm EXPOSURE
đều ở 1 Hz qua đầu lấy mẫu. Mức nền lấy từ trung vị toàn bộ baseline. Tín hiệu
exposure được biểu diễn thành tensor 6 × 120 theo đơn vị đầu vào gốc của CNN.
Sau hiệu chỉnh, ResCNN64 tạo embedding 64 chiều và V2 xếp hạng cosine giữa các
embedding. Nhiệt độ và độ ẩm baseline hỗ trợ chọn blank.

- Để ghi một blank, chạy một lượt bình thường với đầu lấy mẫu để trống.
  Đặt tên `blank` hoặc `blank_sau_cf` khi lưu. Không tick lượt blank dùng để hiệu chỉnh
  vào danh sách đối sánh của lần chạy đó.
- Nếu mọi lượt có blank hợp lệ cùng phiên và cấu hình, chọn blank gần nhất theo
  mức, độ dốc và độ dao động baseline rồi trừ phần biến thiên exposure của blank.
- Nếu thiếu blank phù hợp, dùng cùng một phương pháp bù xu hướng cho toàn bộ lần chạy.
  Độ dốc được ước lượng từ cả baseline. Phần bù bị chặn ở độ rộng P90−P10 của baseline
  để hạn chế ngoại suy quá mức. Giao diện ghi rõ phương pháp đã dùng.

Điểm cosine đo độ giống giữa hai embedding. Kiểm tra khả năng nhận diện
trên phiên đo giữ riêng trước khi sử dụng V2 làm model chính. Dữ liệu raw chỉ được đọc.
