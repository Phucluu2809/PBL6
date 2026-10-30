# Kiểm tra 17 phiên và manifest nhãn

File máy đọc tương ứng: [`label_manifest.csv`](./label_manifest.csv).

## 1. Kết luận kiểm tra

- Có đúng **17 phiên**, tất cả có trạng thái `COMPLETE`.
- Tổng cộng **7.661 dòng**, khớp giữa `metadata.json` và `summary.json` của từng phiên.
- Mỗi phiên đều có đủ `metadata.json`, `summary.json`, `raw.csv`, `events.csv`, `signals.png` và `normalized.png`.
- Có **198 lỗi đọc cảm biến** đã được lưu trong `events.csv`; đây là vấn đề QC, không phải bằng chứng nhãn sai.
- Có **15 phiên đạt QC đầy đủ** và **2 phiên cần xem lại baseline**. Cả hai đều là `CF_nhieu`; nhãn mẫu vẫn được giữ nhưng không nên dùng làm bằng chứng chính.
- Cách chia **7 Human Only + 4 Human Coffee + 4 Coffee Only + 1 Air + 1 Paired = 17** là đúng với quy ước tên phiên hiện tại.

## 2. Điểm quan trọng về độ tin cậy của nhãn

Các trường `person_code`, `source` và `notes` trong metadata đều trống; `sample_description` của cả 17 phiên chỉ ghi chung là `thu tham do: khong khi va mau that`. Vì vậy không thể xác minh ground truth độc lập từ nội dung metadata.

Manifest hiện gắn `label_verification = PROVISIONAL_NAME_ONLY`, nghĩa là:

1. Nhãn được suy ra từ `original_name` và tên thư mục.
2. Cấu trúc dữ liệu và thứ tự pha khớp với tên phiên.
3. Người trực tiếp thu mẫu vẫn cần xác nhận điều kiện thực tế trước khi đổi thành `CONFIRMED_BY_COLLECTOR`.

Nói ngắn gọn: **logic gán nhãn hiện tại hợp lý và không có phiên bị xếp nhầm theo tên**, nhưng chưa thể gọi là nhãn ground truth đã xác minh.

## 3. Quy ước nhãn

| Tên phiên | Nhóm | `coffee_on_person_label` | Cách sử dụng |
|---|---|---:|---|
| `Tai`, `aMinh`, `aQuy` | `HUMAN_ONLY` | 0 | Mẫu người không mang cà phê |
| `TaivsCF*` | `HUMAN_COFFEE` | 1 | Mẫu Tài có cà phê trên người |
| `CF_it`, `CF_nhieu` | `COFFEE_ONLY` | NA | Đối chứng cà phê riêng, không đưa vào binary classifier |
| `khongkhi` | `AIR` | NA | Mẫu nền, không đưa vào binary classifier |
| `BaseTai_ExposeTaivsCF` | `PAIRED` | Theo pha | Phân tích trước–sau, không tách thành hai mẫu độc lập |

`coffee_level = unspecified` được giữ cho hai phiên `TaivsCF` và phiên paired vì tên phiên không ghi mức cà phê. Không được tự suy diễn chúng là “ít” hoặc “nhiều”.

## 4. Danh sách 17 phiên

| # | Giờ | `original_name` | Nhóm | Người | Mức CF | Nhãn | QC | Xác minh |
|---:|---|---|---|---|---|---:|---|---|
| 1 | 12:58:35 | `khongkhi` | AIR | NA | none | NA | PASS | Theo tên |
| 2 | 13:09:42 | `CF_it` | COFFEE_ONLY | NA | low | NA | PASS | Theo tên |
| 3 | 13:20:52 | `Tai` | HUMAN_ONLY | Tài | none | 0 | PASS | Theo tên |
| 4 | 13:30:44 | `Tai` | HUMAN_ONLY | Tài | none | 0 | PASS | Theo tên |
| 5 | 13:44:33 | `BaseTai_ExposeTaivsCF` | PAIRED | Tài | unspecified | Theo pha | PASS | Theo tên |
| 6 | 13:53:36 | `CF_nhieu` | COFFEE_ONLY | NA | high | NA | REVIEW_BASELINE | Theo tên |
| 7 | 14:01:00 | `TaivsCF` | HUMAN_COFFEE | Tài | unspecified | 1 | PASS | Theo tên |
| 8 | 14:07:32 | `TaivsCF` | HUMAN_COFFEE | Tài | unspecified | 1 | PASS | Theo tên |
| 9 | 22:00:50 | `aMinh` | HUMAN_ONLY | Minh | none | 0 | PASS | Theo tên |
| 10 | 22:10:33 | `Tai` | HUMAN_ONLY | Tài | none | 0 | PASS | Theo tên |
| 11 | 22:16:51 | `Tai` | HUMAN_ONLY | Tài | none | 0 | PASS | Theo tên |
| 12 | 22:24:30 | `Tai` | HUMAN_ONLY | Tài | none | 0 | PASS | Theo tên |
| 13 | 22:35:10 | `aQuy` | HUMAN_ONLY | Quy | none | 0 | PASS | Theo tên |
| 14 | 22:51:45 | `CF_nhieu` | COFFEE_ONLY | NA | high | NA | REVIEW_BASELINE | Theo tên |
| 15 | 22:57:57 | `TaivsCF_nhieu` | HUMAN_COFFEE | Tài | high | 1 | PASS | Theo tên |
| 16 | 23:05:21 | `TaivsCF_it` | HUMAN_COFFEE | Tài | low | 1 | PASS | Theo tên |
| 17 | 23:11:23 | `CF_it` | COFFEE_ONLY | NA | low | NA | PASS | Theo tên |

## 5. Tập dữ liệu dùng cho từng câu hỏi

### Phát hiện cà phê trên người

- Tập nhị phân tổng quát tạm thời: **7 nhãn 0 + 4 nhãn 1 = 11 phiên độc lập**.
- So sánh chính giảm nhiễu khác biệt cá nhân: **5 phiên Tài nhãn 0 + 4 phiên Tài nhãn 1 = 9 phiên**.
- Không đưa `AIR`, `COFFEE_ONLY` hoặc phiên `PAIRED` vào như các mẫu binary độc lập.
- Phiên paired chỉ dùng để tính chênh lệch trong cùng người giữa baseline Tài và exposure Tài+cà phê.

### Fingerprint cà phê riêng

- Dùng 2 phiên `CF_it` và 2 phiên `CF_nhieu`.
- Hai phiên `CF_nhieu` phải mang cờ QC và cần phân tích độ nhạy có/không có chúng.

## 6. Các xác nhận còn thiếu

Trước khi dùng manifest để huấn luyện hoặc báo cáo chính thức, người thu mẫu cần xác nhận:

- [ ] `Tai`, `aMinh`, `aQuy` thực sự không mang cà phê trong EXPOSURE.
- [ ] `TaivsCF*` là cà phê mang trên người Tài, không phải cốc cà phê đặt riêng gần đầu hút.
- [ ] Baseline của các phiên thông thường là không khí sạch; riêng phiên paired là Tài không cà phê.
- [ ] `it` và `nhieu` có định nghĩa định lượng hoặc quy trình bố trí mẫu nhất quán.

Sau khi xác nhận, cập nhật `label_verification` trong CSV từ `PROVISIONAL_NAME_ONLY` thành `CONFIRMED_BY_COLLECTOR`. Các đợt thu tiếp theo nên ghi trực tiếp `person_code`, `sample_type`, `coffee_present`, `coffee_level`, `baseline_condition` và `exposure_condition` vào metadata tại thời điểm đo.
