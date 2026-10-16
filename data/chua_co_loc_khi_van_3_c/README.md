# Báo cáo và hướng dẫn phân tích `chua_co_loc_khi_van_3_c`

Tài liệu này mô tả toàn bộ cấu trúc dữ liệu, kết quả audit hiện tại, cách chạy notebook và quy trình đề xuất để thu dữ liệu mới. Kết quả được tạo bởi [`phan_tich_toan_bo.ipynb`](./phan_tich_toan_bo.ipynb) trên dữ liệu gốc trong các folder ngày `2026-10-13` đến `2026-10-15`.

## 1. Kết luận nhanh

- File được lưu đầy đủ, toàn bộ run có trạng thái `COMPLETE`, CSV/JSON/PNG hợp lệ.
- Có 22 run: 16 `collect` có nhãn và 6 `session` tổng.
- Có 10.478 dòng trong các folder `collect`, nhưng đơn vị thí nghiệm thực tế chỉ là 16 trial độc lập.
- Ba pha chính có 3.840 dòng: 960 baseline, 1.920 exposure và 960 recovery.
- Toàn bộ dòng trong `collect` xuất hiện lại trong các folder `session`; không được gộp hai nguồn khi huấn luyện.
- MQ135 có 10/16 trial chưa hồi phục và 8/16 trial có baseline drift.
- Ngày, khung giờ, độ ẩm và vị trí cơ thể bị confound mạnh.
- Chỉ có một trial có áo, nên chưa thể đánh giá có áo/không áo.
- Dữ liệu phù hợp làm pilot và kiểm tra hệ thống, chưa đủ để xây dựng mô hình đáng tin cậy.

## 2. Cấu trúc thư mục

```text
chua_co_loc_khi_van_3_c/
├── 2026-10-13/
│   ├── <folder session số>/
│   └── <folder collect có tên>/
├── 2026-10-14/
├── 2026-10-15/
├── analysis_outputs/
├── phan_tich_toan_bo.ipynb
├── README.txt
└── README.md
```

Mỗi run có 6 file:

| File | Mục đích |
|---|---|
| `raw.csv` | Dữ liệu cảm biến và chẩn đoán ở khoảng 1 Hz |
| `events.csv` | Lệnh, đổi pha, bắt đầu/kết thúc và đánh giá stability |
| `metadata.json` | Cấu hình, thông tin phần cứng, thời gian, phase interval |
| `summary.json` | Thống kê baseline/exposure/recovery và cảnh báo |
| `signals.png` | Biểu đồ tín hiệu gốc |
| `normalized.png` | Biểu đồ tín hiệu chuẩn hóa |

Folder `kind=session` là log tổng của một phiên chạy. Folder `kind=collect` là một trial có tên. Dữ liệu vật lý của trial được lưu đồng thời trong cả hai loại folder.

## 3. Quy mô dữ liệu hiện có

| Chỉ số | Giá trị |
|---|---:|
| Ngày thu | 3 |
| Session vật lý | 6 |
| Collect/trial có tên | 16 |
| Tổng dòng collect | 10.478 |
| Dòng thuộc pha đo chính | 3.840 |
| Baseline | 60 giây/trial |
| Exposure | 120 giây/trial |
| Recovery | 60 giây/trial |
| Tần số mục tiêu | 1 Hz |
| Gap lớn nhất | khoảng 1,09 giây |
| Gap trên 3 giây | 0 |

Phân bố trial:

| Nhóm | Số lượt |
|---|---:|
| Tài | 5 |
| Minh | 4 |
| Quy | 4 |
| Dũng | 2 |
| Không rõ | 1 |
| Bụng | 8 |
| Ngực | 5 |
| Đầu gối | 1 |
| Vị trí không rõ | 2 |
| Không áo | 12 |
| Có áo | 1 |
| Áo không rõ | 3 |

Ba tên đặc biệt cần xử lý thủ công:

- `hihi`: không rõ người, vị trí và áo.
- `anhdung_daugoi`: có người/vị trí nhưng không ghi áo.
- `aDung_moitamxonggg`: trạng thái sau tắm, không ghi vị trí và áo.

## 4. Timeline thu dữ liệu

| Session | Trial chính |
|---|---|
| 13/10 20:49–20:58 | Một trial `hihi` chưa rõ nhãn |
| 13/10 21:03–21:49 | Dũng–đầu gối, Tài–ngực–có áo, Minh–ngực–không áo, Quy–ngực–không áo |
| 14/10 11:03–11:42 | Minh và Tài đo ngực–không áo |
| 14/10 23:52–15/10 00:16 | Quy và Tài đo bụng–không áo |
| 15/10 11:27–12:01 | Tài, Minh, Quy đo bụng–không áo |
| 15/10 21:03–21:38 | Dũng sau tắm; Quy, Minh, Tài đo bụng |

Các trial tập trung vào lúc nửa đêm, 11–12 giờ và 20:49–21:49. Không có dữ liệu buổi chiều. Ngực chủ yếu được đo ngày 13–14, trong khi bụng chủ yếu được đo ngày 15. Do đó, chưa thể tách ảnh hưởng của vị trí khỏi ngày, giờ và môi trường.

Các khoảng thao tác chưa chuẩn hóa:

- `MONITOR`: 9–1.615 giây.
- `WAIT_EXPOSURE`: 6–63 giây.
- `WAIT_RECOVERY`: 2–43 giây.
- Tổng thời gian một collect: khoảng 288–1.947 giây.

## 5. Thống kê cảm biến trong pha chính

Chỉ dùng `BASELINE`, `EXPOSURE`, `RECOVERY`; không dùng warm-up và pha chờ.

| Chỉ số | Min | Trung bình | Trung vị | Max |
|---|---:|---:|---:|---:|
| Nhiệt độ BME | 32,53°C | 34,15°C | 34,28°C | 34,86°C |
| Độ ẩm | 54,84% | 60,84% | 60,06% | 68,09% |
| Áp suất | 1010,73 hPa | 1012,14 hPa | 1012,35 hPa | 1013,58 hPa |
| BME gas resistance | 78,77 kΩ | 100,62 kΩ | 100,43 kΩ | 108,68 kΩ |
| MQ135 ADC | 381 | 987 | 889 | 2.254 |
| MQ135 voltage | 0,0476 V | 0,1234 V | 0,1111 V | 0,2818 V |
| MQ3 ADC | 2.110 | 2.581 | 2.459 | 3.247 |
| MQ3 voltage | 0,2638 V | 0,3226 V | 0,3074 V | 0,4059 V |

Không có ADC nào gần ngưỡng saturation 32.700.

### Trung bình theo pha

| Chỉ số | Baseline | Exposure | Recovery |
|---|---:|---:|---:|
| Nhiệt độ | 34,061°C | 34,149°C | 34,230°C |
| Độ ẩm | 60,794% | 61,046% | 60,457% |
| Áp suất | 1012,144 hPa | 1012,136 hPa | 1012,136 hPa |
| BME gas resistance | 100,933 kΩ | 100,355 kΩ | 100,834 kΩ |
| MQ135 | 0,12258 V | 0,12522 V | 0,12071 V |
| MQ3 | 0,32230 V | 0,32263 V | 0,32283 V |

### Đáp ứng cấp trial

| Chỉ số | Trung bình exposure so với baseline | Phạm vi 16 trial | Nhận xét |
|---|---:|---:|---|
| Nhiệt độ | +0,088°C | −0,113 đến +0,255°C | 15/16 trial tăng; recovery còn nóng hơn baseline |
| Độ ẩm | +0,252 điểm % | −0,397 đến +0,939 | 13/16 trial tăng |
| Áp suất | −0,008 hPa | −0,054 đến +0,027 | Hầu như không phản ứng |
| BME gas | −0,51% | −3,01% đến +4,35% | 13/16 trial giảm |
| MQ135 | +1,92%; trung vị +0,60% | −22,28% đến +17,68% | Biến thiên rất lớn |
| MQ3 | +0,04%; trung vị +0,26% | −7,86% đến +3,28% | Đa số thay đổi nhỏ, có ngoại lệ |

Nhiệt độ BME nằm gần heater và không nên được coi là nhiệt độ phòng. Cần một cảm biến nhiệt độ/độ ẩm môi trường riêng ở ngoài buồng.

## 6. Drift theo ngày

| Ngày exposure | Baseline nhiệt độ | Baseline RH | Baseline BME gas | Baseline MQ135 | Baseline MQ3 |
|---|---:|---:|---:|---:|---:|
| 13/10 | 34,44°C | 66,30% | 93,77 kΩ | 0,0766 V | 0,2685 V |
| 14/10 | 33,63°C | 60,55% | 104,99 kΩ | 0,1358 V | 0,3013 V |
| 15/10 | 33,98°C | 57,44% | 103,89 kΩ | 0,1463 V | 0,3638 V |

Từ ngày 13 sang 15:

- Độ ẩm giảm gần 9 điểm phần trăm.
- MQ135 baseline tăng gần gấp đôi.
- MQ3 baseline tăng khoảng 36%.
- BME gas resistance tăng khoảng 10%.

Tương quan thăm dò ở cấp trial:

- Baseline độ ẩm với MQ135: khoảng −0,81.
- Baseline độ ẩm với MQ3: khoảng −0,89.
- Baseline độ ẩm với BME gas: khoảng −0,72.

Các hệ số này không chứng minh quan hệ nhân quả vì n=16 và ngày/vị trí bị confound, nhưng cho thấy bắt buộc phải kiểm soát hoặc bù nhiệt độ–độ ẩm.

## 7. Cảnh báo chất lượng

| Cảnh báo | Số trial |
|---|---:|
| MQ135 chưa hồi phục về baseline | 10/16 |
| MQ135 baseline drift | 8/16 |
| Baseline bắt đầu khi chưa ổn định | 1/16 |
| `prebaseline evaluated_at` vượt tổng elapsed | 10/16 |
| Gap trên 3 giây | 0 |
| ADC gần saturation | 0 |
| Dòng core không hợp lệ | 0 |

Cảnh báo theo ngày:

- 13/10: 0/5 trial.
- 14/10: 2/3 trial.
- 15/10: 8/8 trial.

`measurement_quality.pre_baseline.evaluated_at_elapsed_s` có vẻ dùng thời gian session/sensor uptime ở 10 collect, trong khi tên trường hàm ý elapsed của collect. Không sử dụng trực tiếp trường này để căn chỉnh tín hiệu.

## 8. Data dictionary đầy đủ của `raw.csv`

### Định danh và thời gian

| Trường | Ý nghĩa |
|---|---|
| `run_id` | ID duy nhất của run |
| `seq` | Số thứ tự dòng, bắt đầu từ 1 |
| `timestamp` | Thời gian ISO 8601 có timezone +07:00 |
| `elapsed_s` | Giây từ đầu collect/session |
| `phase_elapsed_s` | Giây từ đầu pha hiện tại |
| `phase` | MONITOR, BASELINE, WAIT_EXPOSURE, EXPOSURE, WAIT_RECOVERY, RECOVERY, WAIT_FINISH |
| `sensor_uptime_s` | Thời gian sensor/session đã chạy |
| `loop_interval_s` | Khoảng thời gian từ vòng đọc trước |
| `loop_duration_s` | Thời gian xử lý một vòng đọc |
| `schedule_lag_s` | Độ trễ so với lịch 1 Hz |

Sáu giá trị `loop_interval_s` trống là dòng đầu của sáu session và được xem là hợp lệ.

### Bơm

| Trường | Ý nghĩa | Hiện trạng |
|---|---|---|
| `pump_command` | Lệnh bơm do phần mềm gửi | Toàn bộ `DISABLED` |
| `external_pump_state` | Trạng thái bơm ngoài | Toàn bộ `unknown` |
| `external_pump_source` | Nguồn thông tin bơm | Toàn bộ `not_reported` |

Không có cảm biến lưu lượng hoặc phản hồi vật lý xác nhận khí thực sự di chuyển.

### BME68x

| Trường | Ý nghĩa |
|---|---|
| `temperature_c` | Nhiệt độ tại BME, °C |
| `humidity_pct` | Độ ẩm tương đối, %RH |
| `pressure_hpa` | Áp suất, hPa |
| `gas_resistance_ohm` | Điện trở khí không đặc hiệu, Ω |
| `gas_valid` | Phép đo gas hợp lệ |
| `heater_stable` | Heater đã ổn định |
| `new_data` | Có dữ liệu mới |
| `bme_status_bits` | Bit trạng thái driver; 160 ở mẫu đầu chưa ổn định, 176 khi ổn định |
| `bme_meas_index` | Chỉ số phép đo; hiện luôn 0 |
| `bme_gas_index` | Heater profile index; hiện luôn 0 |
| `bme_res_heat` | Thanh ghi heater resistance; hiện 109 |
| `bme_idac` | Giá trị IDAC heater, chủ yếu 178–180 |
| `bme_gas_wait` | Thanh ghi gas wait; hiện 101 |
| `bme_read_started_at` | Thời gian bắt đầu đọc |
| `bme_read_elapsed_s` | Elapsed tại lúc bắt đầu đọc |
| `bme_read_duration_s` | Thời gian đọc BME |
| `bme_status` | Trạng thái đọc; toàn bộ `OK` |
| `bme_error` | Lỗi; trống nghĩa là không lỗi |
| `bme_fresh` | Dữ liệu mới; toàn bộ `True` |

### MQ135

| Trường | Ý nghĩa |
|---|---|
| `mq135_read_started_at` | Thời gian bắt đầu đọc ADS1115 |
| `mq135_read_elapsed_s` | Elapsed tại lúc đọc |
| `mq135_read_duration_s` | Thời gian đọc |
| `mq135_status` | Trạng thái; toàn bộ `OK` |
| `mq135_error` | Lỗi; trống nghĩa là không lỗi |
| `mq135_fresh` | Dữ liệu mới; toàn bộ `True` |
| `mq135_adc_count` | Mã ADC thô |
| `mq135_voltage_v` | Điện áp tại đầu vào ADS1115 |
| `mq135_ao_voltage_v` | Điện áp AO sau bù cầu chia; đang trống 100% |

### MQ3

| Trường | Ý nghĩa |
|---|---|
| `mq3_read_started_at` | Thời gian bắt đầu đọc ADS1115 |
| `mq3_read_elapsed_s` | Elapsed tại lúc đọc |
| `mq3_read_duration_s` | Thời gian đọc |
| `mq3_status` | Trạng thái; toàn bộ `OK` |
| `mq3_error` | Lỗi; trống nghĩa là không lỗi |
| `mq3_fresh` | Dữ liệu mới; toàn bộ `True` |
| `mq3_adc_count` | Mã ADC thô |
| `mq3_voltage_v` | Điện áp tại đầu vào ADS1115 |
| `mq3_ao_voltage_v` | Điện áp AO sau bù cầu chia; đang trống 100% |

Hai cột AO trống vì divider factor chưa được xác nhận. Chưa có R0, RL hoặc khí chuẩn nên không được diễn giải điện áp MQ thành ppm.

## 9. Schema `events.csv`

| Trường | Ý nghĩa |
|---|---|
| `run_id` | ID run |
| `timestamp` | Thời gian sự kiện |
| `elapsed_s` | Elapsed từ đầu run |
| `phase_elapsed_s` | Elapsed trong pha |
| `phase` | Pha hiện tại |
| `event` | Loại sự kiện |
| `details_json` | Payload JSON chi tiết |

Các event gồm `run_start`, `run_end`, `session_end`, `phase_change`, `command_received`, `pump_command`, `external_pump_report`, `baseline_quality_at_start`.

## 10. Cấu trúc `metadata.json`

- Thông tin run: `schema_version`, `program_version`, `run_id`, `kind`, `status`, `started_at`, `ended_at`, `rows`, `elapsed_s`, `end_reason`.
- `config`: sample rate, fsync, baseline/exposure/recovery, hardware, pump, stability và analysis threshold.
- `applied`: cấu hình thực sự được driver áp dụng cho BME68x và ADS1115.
- `sample`: mô tả mẫu, người, nguồn, phương pháp lấy mẫu, purge, nắp, khoảng cách.
- `phase_intervals`: thời gian bắt đầu/kết thúc và planned/actual của từng pha.
- `adc_inputs`: kênh MQ, vị trí điện áp và divider factor.
- `software`: Python, hệ điều hành và phiên bản dependency.
- `external_pump`: báo cáo bơm ngoài và mức độ xác nhận.

Thông số chính hiện tại:

- BME68x hardware, forced mode.
- Heater target 320°C, yêu cầu 150 ms, lập trình 148 ms.
- ADS1115 gain 1, 128 SPS, single-shot.
- MQ135 ở channel 0; MQ3 ở channel 1.
- Divider factor chưa xác nhận.
- Pump phần mềm tắt và không có feedback.
- Cách đổi khí bằng tay trong buồng đóng.
- `person_code`, `source`, `distance_cm`, `notes` hiện trống.

## 11. Cấu trúc `summary.json`

- `signals`: BME gas, MQ135, MQ3.
- `baseline`: n, mean, median, std, min, max, slope, drift và drift percentage.
- `exposure.metrics`: min/max, thời điểm cực trị, delta, delta percentage, slope và AUC.
- `recovery.metrics`: các metric tương tự cùng end deviation và xu hướng quay về baseline.
- `environment_baseline`: nhiệt độ, độ ẩm, áp suất baseline.
- `warnings`: drift và recovery warning.
- `measurement_quality`: stability trước baseline, stability của baseline và lý do.
- `filter_rule`: chỉ dùng mẫu status OK/fresh; BME gas còn yêu cầu gas valid, heater stable và new data.

Summary của folder `session` cố ý để nhiều metric `null` vì session chứa nhiều lượt. Chỉ dùng summary của `collect` để đánh giá trial.

## 12. Quy trình thu dữ liệu đề xuất

### 12.1 Thiết kế tối thiểu cân bằng

Cho bài toán ngực/bụng và áo/không áo:

```text
4 người × 2 vị trí × 2 trạng thái áo × 5 lần lặp = 80 trial chính
```

- Thu trên ít nhất 5 ngày.
- Mỗi ngày cần có đại diện của cả hai vị trí và hai trạng thái áo.
- Random hóa thứ tự hoặc dùng Latin square.
- Đầu gối và sau tắm là thí nghiệm riêng.
- Thêm khoảng 30 blank/control; tổng kế hoạch khoảng 110 lượt.

Nếu mục tiêu là mô hình tổng quát cho người mới, sau pilot nên mở rộng tối thiểu 10 người:

```text
10 người × 2 vị trí × 2 trạng thái áo × 5 lần lặp = 200 trial chính
```

### 12.2 Chuẩn bị session

1. Bật toàn bộ cảm biến và heater ít nhất 30 phút.
2. Ghi `device_id`, tuổi cảm biến, ngày burn-in và nguồn cấp.
3. Xác nhận divider factor, RL/R0 của MQ và ADC không saturation.
4. Kiểm tra buồng, ống, van và lưu lượng.
5. Đặt cảm biến môi trường riêng ngoài buồng.
6. Chạy blank không khí phòng và blank buồng rỗng.

### 12.3 Quy trình một trial

1. Purge tối thiểu 180 giây.
2. Chờ stability của BME gas, MQ135, MQ3, nhiệt độ và độ ẩm.
3. Baseline 120 giây.
4. Chuyển mẫu trong đúng 10 giây bằng thao tác cố định hoặc van tự động.
5. Exposure 120 giây.
6. Recovery tối thiểu 180 giây, tối đa 600 giây.
7. Chỉ chuyển trial khi ba tín hiệu khí nằm trong ±5% baseline liên tục 60 giây.
8. Nếu không hồi phục sau 600 giây, gắn `recovery_failed`, không chạy tiếp như bình thường.

### 12.4 Stability gate đề xuất

Trong cửa sổ 60 giây trước exposure:

| Tiêu chí | Ngưỡng |
|---|---:|
| Mẫu hợp lệ | ≥95% |
| Gap | Không quá 2 giây |
| ADC | Không saturation |
| BME gas/MQ135/MQ3 slope | <2%/phút |
| BME gas/MQ135/MQ3 range | <3% |
| Nhiệt độ slope | <0,1°C/phút |
| Nhiệt độ range | <0,2°C |
| Độ ẩm slope | <0,5 điểm %/phút |
| Độ ẩm range | <1 điểm % |

Không đạt gate thì không bắt đầu exposure. Hệ thống hiện mới kiểm tra chủ yếu BME gas, nhiệt độ và độ ẩm; phải bổ sung MQ135 và MQ3.

### 12.5 Yếu tố cần cố định

- Khoảng cách đầu hút, đề xuất 2 cm nếu phù hợp thiết bị.
- Điểm giải phẫu chính xác và diện tích lấy mẫu.
- Hướng đầu hút.
- Thể tích buồng.
- Lưu lượng bơm.
- Loại ống và chiều dài ống.
- Trạng thái nắp.
- Thời gian chuyển mẫu.
- Loại/chất liệu áo và thời gian mặc.
- Thời gian sau tắm, vận động, ăn uống, rượu, nước hoa.
- Điều hòa, quạt, cửa sổ và `room_id`.
- Người thao tác.

### 12.6 Thí nghiệm sau tắm

Không trộn một mẫu sau tắm vào dữ liệu bình thường. Thiết kế riêng theo cặp:

- Trước tắm.
- 15 phút sau tắm.
- 60 phút sau tắm.
- Cùng người, vị trí, áo, giờ, phòng và quy trình.

## 13. Manifest bắt buộc cho lần thu tiếp theo

Mỗi trial cần một dòng manifest:

```text
trial_id
session_id
subject_id
device_id
date
time_block
room_id
body_location
clothing_state
clothing_material
shower_state
minutes_since_shower
minutes_since_exercise
distance_cm
chamber_volume_ml
pump_flow_lpm
ambient_temperature_c
ambient_humidity_pct
baseline_s
exposure_s
recovery_s
sample_order
operator
quality_status
quality_reasons
notes
```

Nhãn không nên chỉ tồn tại trong tên folder.

## 14. Quy tắc dùng cho machine learning

- Đơn vị độc lập là trial, không phải dòng 1 Hz.
- Không đưa folder `session` và `collect` của cùng phép đo vào hai tập khác nhau.
- Không random split theo dòng.
- Với bài toán nhận diện người đã biết: group split theo session/ngày.
- Với bài toán tổng quát cho người mới: group split theo `subject_id`.
- Fit scaler/normalizer chỉ trên train.
- Ưu tiên đặc trưng tương đối với baseline, slope, AUC, thời điểm cực trị và recovery.
- Luôn chạy sensitivity analysis có/không có trial MQ135 warning.
- Không dùng `mq*_ao_voltage_v` hoặc suy ppm trước khi xác nhận divider/RL/R0/calibration.

## 15. Chạy notebook

Từ repo root:

```powershell
py -3.11 -m pip install -r requirements.txt
py -3.11 -m jupyter lab data/chua_co_loc_khi_van_3_c/phan_tich_toan_bo.ipynb
```

Hoặc chạy headless:

```powershell
py -3.11 -m jupyter nbconvert `
  --to notebook `
  --execute `
  --inplace `
  data/chua_co_loc_khi_van_3_c/phan_tich_toan_bo.ipynb
```

Notebook tự tìm dataset khi chạy từ repo root hoặc chính folder dataset.

## 16. Kết quả do notebook xuất

Trong `analysis_outputs/`:

| File | Nội dung |
|---|---|
| `analysis_summary.json` | Tóm tắt máy đọc được |
| `run_inventory.csv` | Danh sách 22 run |
| `integrity_report.csv` | Kiểm tra file/schema/run ID |
| `raw_field_dictionary.csv` | Từ điển 50 trường raw |
| `raw_field_quality.csv` | Missingness, unique, min/median/max |
| `duplicate_report.csv` | Mức lặp collect-session |
| `trial_manifest_inferred.csv` | Manifest suy luận của 16 trial |
| `phase_counts.csv` | Số mẫu theo pha |
| `timing_statistics.csv` | Hiệu năng vòng đọc |
| `phase_statistics.csv` | Thống kê tín hiệu theo pha |
| `trial_response_features.csv` | Đặc trưng cấp trial |
| `response_summary.csv` | Tổng hợp đáp ứng |
| `group_statistics.csv` | Thống kê theo ngày/người/vị trí/áo/giờ |
| `quality_flags.csv` | Cờ chất lượng từng trial |

Các hình trong `analysis_outputs/figures/`:

- `design_balance.png`
- `phase_distributions.png`
- `response_heatmap.png`
- `baseline_by_day.png`
- `trial_correlations.png`
- `aligned_signal_traces.png`

## 17. Trạng thái sử dụng hiện tại

| Mục đích | Đánh giá |
|---|---|
| Kiểm tra phần mềm/file | Đạt |
| Kiểm tra lịch lấy mẫu 1 Hz | Đạt |
| Khảo sát response sơ bộ | Có thể dùng |
| So sánh vị trí cơ thể | Chưa đáng tin cậy |
| So sánh áo/không áo | Chưa đủ dữ liệu |
| Phân tích sau tắm | Chưa đủ dữ liệu |
| Huấn luyện mô hình chính thức | Chưa sẵn sàng |
| Thiết kế đợt thu tiếp theo | Đủ thông tin để triển khai |
