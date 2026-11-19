# RoboNose — web workflow và inference versioned

Ngày 19/11/2026, Asia/Saigon. Đây là phần bổ sung local vào host 0.4.0;
firmware ESP32-S3, protocol USB, raw schema và state machine thu giữ nguyên.

## Đã triển khai

- Web buildless tại `robonose_s3/web`, không cần Node/runtime frontend.
- HTTP adapter dependency-free tại `robonose_s3/web_server.py`; chỉ gọi
  `Session.post()` và đọc snapshot bounded.
- Năm cảm biến vật lý: bốn card analog và một card BME688 gộp Gas/T/RH/P;
  API/biểu đồ vẫn giữ tám đại lượng, hai canvas chart, quality và cảnh báo.
- Nút state-aware cho start/expose/recover/finish/next/abort,
  name/notes/mark/quit. Web bỏ `extend` gây nhầm lẫn; cấu hình 60/120/60 và PWM
  80% hiển thị chỉ đọc. Terminal/protocol cũ vẫn giữ `extend`.
- `MockPredictor` deterministic có nhánh `UNKNOWN` và comparison X với tối đa
  A-E; worker/queue riêng, output `robonose.prediction.v1`, luôn ghi
  `model_backend=MOCK` và `synthetic_prediction=true`.
- Adapter ResCNN64 thật dùng chung cho identity và so X với A-E, kiểm hash
  artifact, preprocessing 6×120 và chỉ resolve UUID bên trong sample root.
- Artifact `20261119_053351_6b8717` đã được nhập. Vì báo cáo train không có
  holdout/ngưỡng, identity thật trả `RANKED_ONLY`; không tự nhận người/Unknown.
- Trial catalog chỉ đọc và event inference đi qua Recorder hiện có. Raw không bị
  model/web sửa.
- `--web` không import Qt; trên Linux không áp đường dẫn Python Windows. Mặc
  định chỉ bind `127.0.0.1`; LAN phải chọn rõ `--web-host 0.0.0.0`.

## Kiểm chứng thực

- `node --check robonose_s3/web/app.js`: exit 0.
- `python -m py_compile` cho entry point/inference/web server: exit 0.
- Ba test web/API loopback: đạt.
- Suite trước khi nhập model: **145 passed trong 36.09 s**.
- Test bổ sung preprocessor/artifact/web: **8 passed trong 3.10 s**.
- Suite hồi quy cuối sau sửa dashboard 5 cảm biến/cấu hình: **153 passed trong 95.14 s**.
- Smoke checkpoint thật: top Phúc `0.928494`; Phúc↔Phúc `0.892075`,
  Phúc↔Dương `-0.149132`; chỉ là kiểm chức năng trên mẫu train.
- Smoke HTTP thật: job `QUEUED` → `SUCCEEDED`, backend
  `RESCNN64_TORCH`, status `RANKED_ONLY`, top `Phúc`.
- Bổ sung `--model-sample-root`: smoke demo đọc-only `data/hardware` với UUID
  `ade1a38e-...` đạt `QUEUED` → `SUCCEEDED`, top `Dương`, cosine `0.854266`,
  margin `0.587633`; Session demo vẫn ghi riêng trong `data/simulation`.
- Entry point `--demo --web --web-port 8765 --auto-close-s 2`: exit 0, session
  CLOSED, PWM cuối 0%. Lần smoke đầu phát hiện CP1258 không in được chữ Việt;
  entry point đã chuyển stdout/stderr sang UTF-8 và smoke lại đạt.

Một test emulator/Qt cũ có một lần latch/timeout ngẫu nhiên trong lượt full và
một lần timeout khi chạy riêng; chạy riêng lại đạt, full suite cuối đạt 145.
Không sửa USB policy hoặc nới test để che flake timing này.

## Giới hạn bằng chứng

- Chưa mở COM, nạp firmware hoặc tác động bơm/van trong đợt web.
- Mock inference không đọc đặc trưng. Model thật chưa có đánh giá holdout hoặc
  ngưỡng Unknown nên chưa có độ chính xác nhận diện triển khai.
- Chưa có authentication/TLS; không expose khỏi mạng tin cậy.
- Không có browser preview tool trong môi trường hiện tại; đã kiểm HTTP/static
  response, JS syntax, API/integration và entry point nhưng chưa tuyên bố QA
  trực quan trên Chrome/điện thoại/Raspberry Pi.
- PyTorch chưa được thêm vào `.venv` Windows đã chốt; `requirements-pi.txt`,
  hiệu chuẩn Unknown, systemd và kiểm USB trên Pi vẫn là các bước sau.

Hướng dẫn vận hành: `docs/WEB_DASHBOARD.md`.
