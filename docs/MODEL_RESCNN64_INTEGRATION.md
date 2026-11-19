# ResCNN64 — hợp đồng tích hợp model

## Quy tắc validity dùng chung

`robonose_s3/signals.py` giữ hợp đồng tương thích với
`processing/core/signals.py` của source model: danh mục kênh, số hữu hạn,
boolean ba trạng thái và `validity(row, key, sensor, modern)`. Preprocessing
ResCNN64 gọi trực tiếp module này; `False` và `UNKNOWN` không được coi như nhau,
không fill, clip hoặc sửa raw. Modern BME dùng prefix `bme688`; legacy dùng
`bme`. Gas còn yêu cầu `gas_valid`, `heater_stable` và `new_data`.

## Artifact được bàn giao

Nguồn là `C:\Users\nguye\Downloads\odor_embed (1).zip`, SHA-256
`B390598ABF58F32C539397E6B57B82E1343438829252508E56ED76F0EDC5ACC1`.
Bản runtime được chọn là `20261119_053351_6b8717`; thư mục versioned trong
workspace chứa `model.pt`, `model.json`, `report.json`, `training_history.json`
và `artifact.json`. Adapter kiểm hash trước khi gọi `torch.load` và bắt buộc
`weights_only=True`.

`curated_raw.zip` có SHA-256
`FA25AC0D2B375F6B96766D45B1F27107EA652EB159E5602FA75DED1E1A1902FA`.
Bản giải nén kiểm tra chỉ nằm dưới `runtime/` bị gitignore; không chép vào
`data/`, không sửa raw và không trộn với dataset thu mới.

## Tiền xử lý cố định

- Chỉ nhận schema `robonose.dataset.v1`, metadata `COMPLETE` và UUID đầy đủ.
- Đúng 60 dòng BASELINE và 120 dòng EXPOSURE ở 1 Hz, sai số khoảng cách tối đa
  0,1 giây.
- Sáu kênh theo đúng thứ tự: TGS2602, MQ3 #1, MQ135 #2, MQ3 #2, BME gas và độ
  ẩm.
- Mọi điểm phải có giá trị hữu hạn và cờ status/fresh/valid hợp lệ. Không fill
  0, không nội suy và không forward-fill.
- Reference là median 30 giây cuối baseline. Năm kênh thông thường dùng delta;
  BME gas dùng `log(exposure/reference)`.
- Chuẩn hóa bằng median/IQR đã lưu trong `model.json`; encoder trả vector đơn vị
  64 chiều.
- Trước suy luận, adapter còn đối chiếu 1 Hz, PWM 80%, map A0–A3, ADS LSB/hệ số
  chia và BME profile `s3_bringup_300_100_t2h2p4.v1`. Thiếu hoặc khác cấu hình
  sẽ bị từ chối; không trộn âm thầm profile Pi 320°C/150 ms.

## Hai chế độ dùng chung model

1. Identity: embedding mẫu mới nhân cosine với gallery 9 người. Khi chưa có cả
   ngưỡng similarity và margin, output là `RANKED_ONLY`, `predicted_id=null`.
2. Reference retrieval: embedding X so trực tiếp với A–E, sắp giảm dần theo
   cosine. Chế độ này không dùng ngưỡng nhận diện danh tính.

Resolver chỉ tìm UUID trong các sample root do host cấp; chuỗi đường dẫn hoặc
UUID trùng bị từ chối. Inference chạy ở worker hữu hạn, tách khỏi acquisition.

## Giới hạn model hiện tại

`report.json` cho biết 77 lượt của 9 người được fit bằng chế độ `full_fit`, không
có test group, `heldout_top1=null` và `threshold=null`. Vì vậy 100% trên train
hoặc pair AUC trên các mẫu đã thấy không phải bằng chứng tổng quát hóa và không
được dùng để tự đặt ngưỡng Unknown.

Cần đánh giá lại với `ALL_DATA=False`/holdout theo ngày hoặc phiên và thêm người
thật sự không đăng ký. Sau đó mới chốt hai ngưỡng, phiên bản hóa chúng cùng model
và cho phép trạng thái `MATCHED`/`UNKNOWN`.

## Kiểm chứng đã thực hiện

- Checkpoint tải thành công bằng Python 3.10, PyTorch 2.11.0 CPU; gallery `9×64`
  và state dict khớp ResCNN64.
- Mẫu Phúc trong tập bàn giao: top Phúc, cosine `0.928494`, margin `0.654228`,
  trạng thái an toàn `RANKED_ONLY`.
- So mẫu Phúc tham chiếu với một Phúc khác và một Dương: cosine lần lượt
  `0.892075` và `-0.149132`.
- Đây là smoke chức năng trên mẫu train, không phải phép đo accuracy độc lập.
- Không mở COM, không nạp firmware và không tác động tải khi kiểm model.
