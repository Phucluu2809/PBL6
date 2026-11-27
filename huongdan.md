# Hướng dẫn sử dụng RoboNose trên Windows

## 1. Mở dashboard

Trên laptop chạy RoboNose, mở [dashboard tại cổng 18081](http://127.0.0.1:18081). Nếu server chưa chạy, mở PowerShell trong thư mục gốc dự án và chạy lệnh sau.

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --port COM5 --serial-kind native-cdc --web --web-port 18081
```

Giữ cửa sổ PowerShell mở và vào địa chỉ hiện sau chữ `web`. Dùng **Danh sách mẫu**, **Đối sánh** và **Dự đoán danh tính** trên dữ liệu đã lưu ngay khi dashboard ở trạng thái **IDLE**. Khi demo dữ liệu đã thu, để phiên ở trạng thái chờ và chỉ bấm **Bắt đầu phiên** nếu muốn thu thật. Địa chỉ `127.0.0.1` dùng ngay trên laptop này, kể cả khi mất Wi-Fi.

Để demo cả biểu đồ realtime bằng tín hiệu giả lập, chạy chế độ demo trên cổng riêng rồi mở [dashboard demo tại cổng 18082](http://127.0.0.1:18082) và bấm **Bắt đầu phiên**.

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo --web --web-port 18082
```

## 2. Chọn mẫu đối sánh ở mục 05

1. Vào **05 · Danh sách mẫu**. Tìm theo tên hoặc `trial_id`. Đổi **Tất cả trạng thái** thành **COMPLETE** để tập trung vào các lượt đã thu xong.
2. Tick ô trong cột **Chọn mẫu** ở từng dòng muốn dùng làm tập đối sánh. Bạn có thể tìm và tick qua nhiều lượt lọc. Mẫu bị ẩn bởi bộ lọc vẫn giữ lựa chọn. Nếu nhiều dòng trùng tên, xem cột **Trial ID** và **Thời gian** để chọn đúng lượt.
3. Bấm **Lưu lựa chọn** ngay cạnh bộ lọc trạng thái. Dòng **Đã lưu … mẫu** xác nhận số lượng mà mục 04 sẽ dùng. Để thay đổi danh sách, tick hoặc bỏ tick rồi lưu lại.

Lựa chọn được lưu theo trình duyệt và địa chỉ web. Tải lại cùng địa chỉ sẽ giữ danh sách đã lưu. Khi cuộn trong bảng, tiêu đề cột và thanh lọc phía trên giữ nguyên vị trí. Ô chọn chỉ khả dụng với lượt **COMPLETE** đã lưu hoàn chỉnh.

## 3. Chạy đối sánh ở mục 04

1. Vào **04 · Đối sánh**. Chọn một lượt đã lưu hoàn chỉnh trong ô **Mẫu tham chiếu** hoặc dán `trial_id` lấy từ nút **Sao chép** ở mục 05.
2. Kiểm tra số mẫu đã lưu hiển thị dưới ô tham chiếu. Nếu chính lượt tham chiếu đã được tick ở mục 05, ứng dụng tự loại lượt đó khỏi lần đối sánh. Cần ít nhất một lượt khác trong danh sách.
3. Bấm **Chạy đối sánh**. Mục **Xếp hạng tương đồng** hiển thị tên, trial ID và điểm cosine theo thứ tự từ cao xuống thấp. Điểm càng cao thì tín hiệu của hai lượt càng gần nhau theo model. Cuộn trong vùng xếp hạng để xem thêm, còn ô tham chiếu và các nút giữ nguyên vị trí.
4. Nếu có dòng **Mẫu chưa xếp hạng**, xem lý do cạnh từng lượt. Model ResCNN64 hiện dùng 60 điểm baseline và 120 điểm exposure, đồng thời kiểm tra độ hợp lệ của tín hiệu.

Ví dụ, nếu muốn xem lượt A giống B hay C hơn, tick B và C ở mục 05 rồi lưu. Sau đó chọn A ở mục 04 và chạy đối sánh. Lượt có điểm cao hơn sẽ đứng trước.

Khi demo kết quả trên dữ liệu thật, kiểm tra banner **MODEL THẬT · RESCNN64_TORCH**. Banner **MODEL GIẢ LẬP** cho biết kết quả phục vụ kiểm tra giao diện.

Để chạy thử cách tiền xử lý mới với checkpoint đã huấn luyện, đổi **Model đối sánh** sang **ResCNN64 V2 · Hiệu chỉnh toàn bộ baseline (thử nghiệm)** rồi chạy lại cùng các mẫu. Kết quả ghi rõ V2 đã trừ blank hay dùng bù xu hướng khi thiếu blank. Xem cách thu blank trong [hướng dẫn V2](models_v2/README.md).

Để dùng bộ hiệu chỉnh đã được huấn luyện trên baseline, chọn **ResCNN64 V2 · Bộ hiệu chỉnh đã học**. CNN vẫn dùng checkpoint gốc. Có thể chạy cùng các mẫu bằng **Model mặc định** để so thứ hạng.

## 4. Thu thêm một mẫu thật

1. Cắm ESP32-S3 qua USB. Trong **Device Manager → Ports (COM & LPT)**, xem cổng của ESP và thay `COM5` trong lệnh ở mục 1 nếu cần.
2. Bấm **Bắt đầu phiên** trên dashboard. Sau khi kết nối và kiểm tra hợp lệ, bơm tự chạy ở PWM 80%. Xem số đo ở **01 · Tín hiệu & thiết bị**, rồi chờ trạng thái **MONITOR**.
3. Vào **02 · Điều khiển thu mẫu**, bấm **Bắt đầu baseline**. Chờ 60 giây mặc định và trạng thái **WAIT_EXPOSURE**.
4. Đặt mẫu rồi bấm **Mẫu đã đặt · Exposure**. Chờ 120 giây mặc định và trạng thái **WAIT_RECOVERY**.
5. Bấm **Bắt đầu recovery** để chuyển sang khí lọc. Sau 60 giây mặc định, bấm **Hoàn thành lượt**.
6. Nhập và **Lưu tên mẫu**, ghi chú nếu cần, rồi bấm **Lưu mẫu**. Lượt đã chốt xuất hiện ở mục 05 và được ghi vào `data/hardware`.
7. Khi thu xong, bấm **Kết thúc phiên**. Dùng **Ctrl+C** trong PowerShell khi muốn tắt luôn server.

## 5. Kiểm tra cà phê

Trên dashboard, vào **06 · Phát hiện cà phê**, chọn một mẫu hardware hoàn chỉnh và bấm **Kiểm tra cà phê**. Mục **03 · Dự đoán danh tính** chạy riêng model nhận diện người.

Để kiểm tra cả tập bằng notebook, làm theo các bước sau.

1. Mở [test_coffee_hardware.ipynb](test_coffee_hardware.ipynb) trong VS Code.
2. Chọn kernel Python có `ipykernel` rồi bấm **Run All**.
3. Xem bảng ở cell cuối. Mỗi lượt trong `data/hardware` chiếm một dòng, gồm tên, trạng thái, nhãn theo tên mẫu, kết quả dự đoán và lý do nếu chưa dự đoán được. Các lượt chưa xác nhận nhãn được hiển thị để đối chiếu. Tỷ lệ phát hiện chỉ tính trên nhóm có nhãn cà phê.

## Khi gặp lỗi lúc demo

| Hiện tượng | Cách xử lý |
| --- | --- |
| Trang báo từ chối kết nối | Kiểm tra cửa sổ PowerShell còn chạy. Mở chính xác địa chỉ server in ra. Nếu cổng đang bận, đổi `--web-port` và mở lại địa chỉ với cổng mới. |
| Dashboard ở IDLE, biểu đồ chưa có tín hiệu | Với dữ liệu đã lưu, mở thẳng mục 05 hoặc 04. Muốn có biểu đồ realtime khi chưa cắm ESP, chạy lệnh `--demo` ở mục 1. |
| Nút Chạy đối sánh bị mờ | Vào mục 05, tick và lưu ít nhất một mẫu hoàn chỉnh khác lượt tham chiếu. |
| PowerShell báo `Model startup failed` | Kiểm tra `web_model_dir` và `web_model_python` trong `configs/paths.local.json`. Đường dẫn Python phải trỏ đến môi trường có PyTorch để chạy ResCNN64. |
| Terminal báo `Found ... prior PARTIAL/ERROR sessions` | Đây là thông báo về phiên cũ. Kiểm tra dòng chứa địa chỉ `web` để biết server đã mở cổng nào. |
