# RoboNose local web dashboard

Web là presentation adapter của host hiện có. Nó không mở COM, không sở hữu
timer pha, không điều khiển GPIO trực tiếp và không ghi/sửa raw. Mọi lệnh web
được đưa vào `Session.post()` giống terminal; ESP32-S3 vẫn là phase owner trong
HARDWARE.

## Chạy bằng một file cấu hình

Sửa `configs/run.json`, sau đó chỉ cần chạy:

```powershell
.\.venv\Scripts\python.exe scripts\run_robonose.py
```

Các trường chính: `mode` (`demo` hoặc `hardware`), `interface` (`web` hoặc
`qt`), `hardware.port`, `hardware.serial_kind`, địa chỉ/port web và thư mục
model. Mặc định là demo để không mở COM hay bật tải ngoài ý muốn. Khi chọn
hardware, startup hợp lệ vẫn tự bật bơm PWM 80% theo hợp đồng firmware.

Host chấp nhận firmware 3.0.0 revision `usb_irq_handoff.v3` và revision hiện có
`session_durations.v4` để tiếp tục thu hardware mà chưa cần nạp lại.
Trong chế độ này ba thời lượng cố định 60/120/60 và form chỉnh thời gian bị
khóa. Firmware 3.1.0 mới hỗ trợ `CONFIG`; web tự nhận biết từ HELLO, không yêu
cầu người dùng chọn version bằng tay.

Web và model luôn ưu tiên catalog `data/hardware`; `data/simulation` chỉ là
nguồn bổ sung khi chạy demo. Trang **Danh sách mẫu** hiển thị tên, trial UUID,
nguồn, COMPLETE/ABORTED, QC, thời gian và thao tác sao chép/dự đoán.

## Chạy demo trên Windows

Từ root workspace, dùng đúng interpreter cục bộ:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo --web
```

Mở `http://127.0.0.1:8000`. Có thể đổi cổng bằng `--web-port 8080`.
Đóng tab hoặc refresh không dừng acquisition. Dùng nút **Dừng hệ thống**,
Ctrl+C hoặc terminal tương tác để đóng phiên.

## Chạy hardware trên Windows

Chỉ dùng sau khi cổng và firmware được xác minh:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --port COM_THUC_TE --serial-kind native-cdc --web
```

Không có nút bật bơm. Sau handshake, preflight và log/sync hợp lệ, host vẫn tự
gửi BEGIN và ESP32 bật PWM 80% theo hợp đồng hiện có.

## Raspberry Pi 4 sau này

Pi dùng venv Linux riêng, cổng ổn định `/dev/serial/by-id/...` và bind LAN có
chủ ý:

```bash
./.venv/bin/python -m robonose_s3 \
  --port /dev/serial/by-id/usb-THIET_BI_DA_XAC_MINH \
  --serial-kind native-cdc \
  --web --web-host 0.0.0.0 --web-port 8000
```

Chỉ mở web trong mạng tin cậy. Bản hiện tại chưa có đăng nhập/TLS; mặc định
bind `127.0.0.1` để không vô tình công khai điều khiển.

## Năm chức năng

1. **Tín hiệu & thiết bị:** đúng 5 cảm biến vật lý: TGS2602, MQ3 #1,
   MQ135 #2, MQ3 #2 và BME688. Tám đại lượng A0–A3, Gas, nhiệt độ, độ ẩm và
   áp suất được tách thành tám biểu đồ riêng, có màu/đơn vị/thang chia rõ ràng.
   Biểu đồ realtime chỉ vẽ đường tín hiệu, không chèn đường dọc chuyển pha.
2. **Điều khiển thu mẫu:** các nút state-aware cho start/expose/recover/
   finish/next/abort, name/notes, marker và log xác nhận. Trang thu mẫu cũng
   hiển thị đủ tám biểu đồ riêng. Web cho chỉnh baseline/exposure/recovery ở
   `MONITOR`; firmware xác nhận lệnh `CONFIG` trước khi giao diện báo đã lưu.
   Firmware cũ không công bố các trường duration sẽ làm form bị khóa. PWM 80%
   vẫn cố định. Các nút sao chép/lưu tên/lưu ghi chú/lưu mẫu có phản hồi ngay
   dưới thao tác, không chỉ đổi chữ trên nút.
3. **Dự đoán danh tính:** mặc định dùng `MockPredictor`. Khi chọn artifact
   ResCNN64, backend đọc trial `COMPLETE`, tạo embedding 64 chiều và so gallery.
   Artifact hiện tại chưa có ngưỡng Unknown nên trả `RANKED_ONLY`, không tự
   xác nhận người dù top-1 có điểm cao.
4. **Đối sánh** dùng encoder ResCNN64 để xếp hạng cosine giữa mẫu tham chiếu
   và các mẫu đã lưu lựa chọn ở mục 05. Mẫu tham chiếu được loại khỏi tập đối sánh.
   Mẫu thiếu dữ liệu để chạy model được ghi kèm lý do. Chỉ vùng xếp hạng cuộn.
5. **Danh sách mẫu:** quét đệ quy các phiên trong `data/hardware`, kể cả layout
   ngày lồng cũ, khử trùng theo trial UUID và ưu tiên hardware trước nguồn khác.
   Tick các mẫu đã lưu hoàn chỉnh rồi bấm **Lưu lựa chọn** để giữ danh sách trong
   trình duyệt. Thanh lọc và tiêu đề bảng giữ nguyên vị trí khi cuộn các dòng mẫu.
Model ResCNN64 hiện tại được train với đúng 60 điểm baseline và 120 điểm
exposure. Web vẫn cho đổi thời lượng để thí nghiệm/thu dữ liệu mới, nhưng sẽ
cảnh báo khi cấu hình khác 60/120 vì mẫu đó chưa tương thích đầu vào model này.

Worker inference có queue riêng; event log đi qua Recorder hiện có và không giữ
acquisition/USB/heartbeat. Raw chỉ được đọc và kiểm hash, không bị model/web sửa.
Trong hardware mode, mỗi scan được flush ngay vào `session/raw.csv`; từ lúc
nhấn Start, dữ liệu của lượt cũng được flush vào `trials/<mẫu>/raw.csv`.
Catalog web refresh hai giây một lần, còn COMPLETE chỉ được gán sau khi lượt
đã đi đủ pha và người dùng chốt lưu.

## API cục bộ

| Endpoint | Tác dụng |
| --- | --- |
| `GET /api/snapshot?window=600` | Snapshot bounded cho dashboard |
| `POST /api/commands` | Gửi action vào command queue hiện có |
| `GET /api/messages` | Xác nhận queue/engine/MCU dạng message |
| `GET /api/trials` | Catalog chỉ đọc của trial export |
| `POST /api/inference/identity` | Tạo identity job cho backend đang chọn |
| `POST /api/inference/compare` | Tạo comparison job cho backend đang chọn |
| `GET /api/inference/results` | Trạng thái/kết quả job |

Backend kiểm whitelist và độ dài lệnh. Nút bị disable chỉ là presentation;
state machine/MCU vẫn kiểm lại lệnh và có thể từ chối với lý do.

## Chạy model ResCNN64 đã nhập

Artifact được lưu tại `models/rescnn64/20261119_053351_6b8717`. PyTorch là
dependency tùy chọn và hiện chưa có trong `.venv` Windows đã chốt cho bước
firmware; không đổi interpreter/core chỉ để chạy model. Sau khi một môi trường
đích đã được cài và pin bản PyTorch CPU tương thích, chạy:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo --web `
  --model-dir models\rescnn64\20261119_053351_6b8717
```

Để kiểm tra một trial hardware đã thu mà không cần mở COM, thêm nguồn mẫu chỉ
đọc. Session vẫn là SIMULATED, nhưng catalog và model được phép đọc thêm
`data/hardware`; dữ liệu không bị chép hoặc sửa:

```powershell
.\.venv\Scripts\python.exe -m robonose_s3 --demo --web `
  --model-dir models\rescnn64\20261119_053351_6b8717 `
  --model-sample-root data\hardware
```

`--model-sample-root` có thể lặp lại. Đường dẫn phải tồn tại, chỉ có hiệu lực
khi đã chọn `--model-dir`, và không thay đổi thư mục mà Session đang ghi.

Lệnh trên cố ý chỉ xếp hạng danh tính. Chỉ thêm hai tham số sau khi các giá trị
đã được hiệu chuẩn độc lập trên người không đăng ký và dữ liệu holdout theo
ngày/phiên:

```text
--model-similarity-threshold <cosine> --model-margin-threshold <margin>
```

Nếu người dùng chọn `--model-dir` mà artifact/hash/PyTorch không hợp lệ, host
dừng trước khi tạo Session thay vì âm thầm quay lại mock. Chi tiết artifact,
preprocessing và bằng chứng smoke nằm trong `docs/MODEL_RESCNN64_INTEGRATION.md`.
