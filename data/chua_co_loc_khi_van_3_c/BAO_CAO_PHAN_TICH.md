# Phân tích lô dữ liệu nhận diện người `chua_co_loc_khi_van_3_c`

README này tổng hợp trực tiếp các phương pháp đã dùng, biểu đồ chính và kết quả thu được trên lô dữ liệu mới. Phần môi trường và kiểm toán chi tiết vẫn được lưu trong CSV, nhưng chỉ những kết quả ảnh hưởng đến kết luận nhận diện mùi mới được đưa vào luồng chính.

## 1. Kết luận nhanh

Lô dữ liệu có **16 run chính** của 4 người và một mẫu chưa rõ nhãn:

| Người/nhãn | Số run | Điều kiện chính |
|---|---:|---|
| Tài | 5 | Ngực có/không áo, bụng không áo × 3 |
| Minh | 4 | Ngực không áo × 2, bụng không áo × 2 |
| Quy | 4 | Ngực không áo, bụng không áo × 3 |
| Dũng | 2 | Đầu gối, sau tắm không rõ vị trí |
| `hihi` | 1 | Không rõ nhãn |

Các kết quả chính:

- 16 run chứa **10.478 dòng raw** và **3.840 dòng pha lõi**.
- Mỗi run có đúng 60 mẫu baseline, 120 mẫu exposure và 60 mẫu recovery.
- Không có timestamp/sequence trùng, không bão hòa ADC và timing 1 Hz ổn định.
- BME688 và MQ3 có baseline ổn định; MQ135 bị trôi và dao động rất mạnh.
- Chỉ có **8 run bụng–không áo** của Minh, Quy và Tài đủ gần nhau về điều kiện để thử nhận diện người.
- BME688 riêng đạt balanced accuracy cao nhất **33,3%**.
- Kết hợp ba giá trị mean của ba cảm biến đạt **61,1%**.
- MQ3 riêng đạt kết quả thăm dò tốt nhất: **6/8 run**, balanced accuracy **72,2%**.
- Median khoảng cách khác người chỉ lớn hơn cùng người **1,12 lần**, nên fingerprint chưa tách rõ.
- Nhiệt độ/độ ẩm thay đổi ít trong một run, nhưng mức nền khác đáng kể giữa các ngày. Chúng được bỏ khỏi fingerprint chính nhưng vẫn giữ làm biến kiểm soát.

**Kết luận:** MQ3 đang có tín hiệu hứa hẹn nhất cho bài toán phân biệt người. BME688 ổn định nhưng chưa tách được người. MQ135 ở trạng thái hiện tại chưa đáng tin để làm fingerprint.

## 2. Phạm vi dữ liệu được sử dụng

Thư mục mang tên bằng chữ là run chính. Sáu thư mục chỉ gồm timestamp và UUID là phiên warm-up/phần cứng.

Toàn bộ dòng của run chính đã xuất hiện lại trong thư mục phiên tương ứng, vì vậy thư mục số không được tính thành mẫu độc lập. Nếu đưa cả hai loại thư mục vào train/test sẽ gây đếm trùng và rò rỉ dữ liệu.

![Thiết kế thu dữ liệu](report_outputs/figures/01_dataset_design.png)

Ba pha được dùng để phân tích:

| Pha | Thời gian | Vai trò |
|---|---:|---|
| Baseline | 60 giây | Xác định mức nền từng cảm biến |
| Exposure | 120 giây | Quan sát đáp ứng khi đưa mẫu vào |
| Recovery | 60 giây | Kiểm tra khả năng trở lại nền |

`MONITOR` và `WAIT_*` chỉ dùng để kiểm tra warm-up và thao tác, không dùng tạo fingerprint.

## 3. Pipeline phân tích

### 3.1. Lọc dữ liệu hợp lệ

BME688 chỉ được giữ khi:

```text
bme_status == "OK"
bme_fresh == True
gas_valid == True
heater_stable == True
new_data == True
```

MQ135 và MQ3 được giữ khi trạng thái đọc là `OK` và `fresh`.

### 3.2. Chuẩn hóa baseline

Mỗi run được chuẩn hóa độc lập bằng median baseline:

```text
response_pct = 100 × (signal / median_baseline - 1)
```

- Giá trị âm: tín hiệu giảm so với nền.
- Giá trị dương: tín hiệu tăng so với nền.
- Gần 0: đáp ứng nhỏ.

### 3.3. Fingerprint

Mỗi kênh cảm biến tạo 5 đặc trưng:

| Đặc trưng | Ý nghĩa |
|---|---|
| `mean` | Trung bình trong 120 giây exposure |
| `late20` | Trung bình 20 giây cuối exposure |
| `min` | Giá trị thấp nhất |
| `max` | Giá trị cao nhất |
| `slope` | Tốc độ thay đổi trong exposure |

BME688 + MQ135 + MQ3 tạo 15 đặc trưng. Nhiệt độ, độ ẩm và áp suất không được đưa vào fingerprint nhận diện người; chúng chỉ dùng để kiểm tra biến gây nhiễu.

### 3.4. Nguyên tắc đánh giá

Một run hoàn chỉnh là một mẫu độc lập. Không chia ngẫu nhiên 240 dòng của một run vào train/test.

Đánh giá dùng leave-one-session-out: giữ toàn bộ một phiên làm test, chỉ fit scaler và mô hình trên các phiên còn lại.

## 4. Timing và thao tác chuyển pha

**Phương pháp:** kiểm tra loop interval và thời gian chờ giữa các lệnh `start`, `expose`, `recover`, `finish`.

![Timing và thời gian chờ](report_outputs/figures/14_timing_and_manual_steps.png)

**Kết quả:**

- Loop interval lớn nhất: **1,012 giây**.
- Loop duration lớn nhất: **0,284 giây**.
- Schedule lag lớn nhất: **0,015 giây**.
- `WAIT_EXPOSURE`: **6,13–63,33 giây**.
- `WAIT_RECOVERY`: **2,40–43,08 giây**.

Phần lấy mẫu tự động ổn định. Điểm chưa ổn định là thao tác chuyển nguồn khí bằng tay và không có feedback vật lý từ bơm. Các trường pump hiện đều là `DISABLED/unknown/not_reported`.

## 5. Đường đáp ứng BME688 trong subset kiểm soát

**Phương pháp:** chỉ dùng 8 run bụng–không áo của Minh, Quy, Tài; căn exposure về 0–120 giây và recovery về 120–180 giây.

![BME688 theo từng người](report_outputs/figures/19_bme_controlled_curves.png)

**Kết quả:**

- Minh có mean tương đối gần nhau, nhưng hình dạng hai đường chưa giống hoàn toàn.
- Quy có một run dương và hai run âm; độ lặp lại thấp.
- Tài có mean khá gần nhau, nhưng run 21:32 xuất hiện transient giảm mạnh khoảng giữa exposure.
- BME688 không tạo ba vùng riêng rõ ràng cho Minh, Quy và Tài.

BME688 là kênh ổn định về chất lượng đo, nhưng chưa đủ thông tin để nhận diện người ở lô hiện tại.

## 6. Đường đáp ứng MQ135

**Phương pháp:** chuẩn hóa điện áp MQ135 giống BME688 và vẽ riêng từng người.

![MQ135 theo từng người](report_outputs/figures/20_mq135_controlled_curves.png)

**Kết quả:**

- Tín hiệu dao động chu kỳ rất lớn, thường khoảng -60% đến +80% baseline.
- Hai run của cùng người không giữ được mức hoặc hình dạng giống nhau.
- 8/16 run có cảnh báo baseline drift.
- 10/16 run chưa hồi phục về nền sau recovery.
- Baseline CV trung vị là **25,87%**, cao nhất **47,16%**.

MQ135 hiện không chỉ bị thay đổi mức nền mà còn có dao động mạnh theo thời gian. Mean có thể tình cờ triệt tiêu phần dao động, nhưng không thể xem đó là fingerprint ổn định.

**Đánh giá:** giữ MQ135 để kiểm tra phần cứng và thử nghiệm, nhưng không nên dùng làm kênh chính cho mô hình hiện tại.

## 7. Đường đáp ứng MQ3

**Phương pháp:** chuẩn hóa điện áp MQ3 và so sánh các ngày đo của từng người trong subset kiểm soát.

![MQ3 theo từng người](report_outputs/figures/21_mq3_controlled_curves.png)

**Kết quả:**

- Minh có mức đáp ứng cao nhất, mean khoảng **2,37–3,20%**.
- Quy nằm ở giữa, mean khoảng **0,28–0,69%**.
- Tài thấp nhất, mean khoảng **0,10–0,27%**.
- Baseline MQ3 ổn định: CV trung vị **0,19%**, cao nhất **0,35%**.
- Hình dạng giữa các run chưa hoàn toàn giống nhau, nhưng mức đáp ứng tạo ra thứ tự tương đối rõ hơn BME688 và MQ135.

MQ3 là cảm biến hứa hẹn nhất trong lô này. Tuy nhiên, Minh chỉ có hai run và kết quả vẫn cần lặp lại qua nhiều ngày.

## 8. So sánh đáp ứng trung bình theo người và ngày

**Phương pháp:** tính mean của toàn bộ 120 giây exposure trong 8 run kiểm soát.

![Đáp ứng trung bình subset](report_outputs/figures/07_controlled_mean_responses.png)

| Người | Phiên | BME688 | MQ135 | MQ3 |
|---|---|---:|---:|---:|
| Quy | 14/10 23:52 | +0,78% | +10,48% | +0,28% |
| Tài | 15/10 00:11 | -0,62% | +6,44% | +0,27% |
| Tài | 15/10 11:27 | -0,76% | +1,50% | +0,25% |
| Minh | 15/10 11:49 | -0,56% | -4,65% | +3,20% |
| Quy | 15/10 11:56 | -0,68% | -1,77% | +0,69% |
| Quy | 15/10 21:19 | -1,10% | -0,32% | +0,48% |
| Minh | 15/10 21:25 | -0,17% | +12,90% | +2,37% |
| Tài | 15/10 21:32 | -0,95% | +5,04% | +0,10% |

**Diễn giải:**

- MQ3 giữ thứ tự Minh > Quy > Tài trong các run kiểm soát.
- BME của Tài tương đối ổn định về mean nhưng động học vẫn có run bất thường.
- MQ135 đổi rất mạnh giữa phiên, kể cả đổi dấu ở Minh và Quy.

## 9. Các run khác ngày/vị trí

Các run ngoài subset vẫn có giá trị mô tả nhưng không dùng để huấn luyện nhận diện:

- Minh đo ngực ngày 13/10 và 14/10 thay đổi rất mạnh trên cả ba kênh; riêng MQ135 từ -0,04% xuống -22,26%.
- Dũng chỉ có một run đầu gối và một run sau tắm không rõ vị trí, nên không thể so sánh lặp lại cá nhân.
- Tài có một run ngực mặc áo nhưng không có mẫu đối chứng không áo trong cùng phiên.
- `hihi` không có nhãn người/vị trí/áo.

![Các run đặc biệt](report_outputs/figures/12_special_runs.png)

## 10. Kiểm tra baseline và recovery

**Phương pháp:** baseline noise được đo bằng `CV = std / |mean| × 100%`; recovery được đo bằng mức lệch ở 10 giây cuối.

![Chất lượng cảm biến](report_outputs/figures/04_quality_control.png)

| Cảm biến | CV trung vị | CV lớn nhất | Đánh giá |
|---|---:|---:|---|
| BME688 | 0,33% | 0,86% | Tốt |
| MQ135 | 25,87% | 47,16% | Không đạt ở nhiều run |
| MQ3 | 0,19% | 0,35% | Tốt |

Metadata hiện có thể đánh dấu baseline chung là ổn định dù MQ135 đang drift. Quality gate phải được tính riêng cho từng cảm biến.

## 11. Heatmap đáp ứng

**Phương pháp:** so sánh mean exposure và mức còn lại cuối recovery của ba cảm biến trên từng run.

![Heatmap đáp ứng và recovery](report_outputs/figures/03_response_heatmap.png)

**Kết quả:**

- Cùng một người chưa tạo hàng màu lặp lại trên cả ba cảm biến.
- MQ135 có biên độ lớn nhất nhưng cũng không ổn định nhất.
- Hai run bụng của Minh có MQ3 nổi bật hơn phần lớn run của Quy và Tài.
- Các run khác điều kiện tạo outlier, vì vậy không được dùng chung để đánh giá danh tính.

## 12. PCA của fingerprint

**Phương pháp:** StandardScaler trên 15 đặc trưng rồi PCA xuống hai chiều. Chỉ dùng subset bụng–không áo.

![PCA subset kiểm soát](report_outputs/figures/08_controlled_pca.png)

PC1 và PC2 giải thích tổng cộng **67,2%** phương sai. Các điểm cùng người chưa tạo cụm kín; một số điểm khác người gần nhau hơn hai điểm cùng người.

PCA cho thấy fingerprint chưa tách rõ. Kết quả phân loại tốt của MQ3 chủ yếu đến từ một số mức đáp ứng, chưa phải cấu trúc đa cảm biến ổn định.

## 13. Khoảng cách cùng người và khác người

**Phương pháp:** chuẩn hóa 15 đặc trưng rồi tính khoảng cách Euclidean cho mọi cặp run trong subset.

![Khoảng cách fingerprint](report_outputs/figures/09_controlled_distances.png)

| Chỉ số | Giá trị |
|---|---:|
| Median cùng người | 5,12 |
| Median khác người | 5,71 |
| Separation ratio | 1,12 |

Khoảng cách khác người chỉ lớn hơn cùng người khoảng 11,6% và hai phân bố còn chồng lấn mạnh. Đây là bằng chứng rằng fingerprint đa cảm biến hiện chưa ổn định.

## 14. Ablation theo cảm biến

**Phương pháp:** chạy 1-NN và nearest centroid với từng nhóm đặc trưng, đánh giá leave-one-session-out.

![Ablation cảm biến](report_outputs/figures/10_controlled_classification.png)

| Nhóm cảm biến | Mô hình tốt nhất | Đúng | Balanced accuracy |
|---|---|---:|---:|
| BME688 gas | 1-NN | 3/8 | 33,3% |
| MQ3 | Nearest centroid | **6/8** | **72,2%** |
| MQ135 | Cả hai mô hình | 3/8 | 33,3% |
| BME688 + MQ3 | Cả hai mô hình | 4/8 | 50,0% |
| BME688 + MQ135 | Tốt nhất | 2/8 | 22,2% |
| Cả ba, 15 đặc trưng | 1-NN | 3/8 | 33,3% |
| Cả ba, chỉ mean | Nearest centroid | 5/8 | 61,1% |

**Diễn giải:**

- MQ3 đang mang nhiều thông tin phân biệt nhất.
- MQ135 không tạo giá trị độc lập ổn định và làm kết quả BME688 + MQ135 giảm.
- Ghép toàn bộ 15 đặc trưng không tốt hơn mô hình đơn giản.
- Không nên tăng độ phức tạp mô hình trước khi tăng số run và sửa MQ135.

## 15. Kết quả nhận diện tốt nhất

**Phương pháp:** nearest centroid trên 5 đặc trưng MQ3, đánh giá theo phiên chưa thấy.

![Ma trận nhầm lẫn](report_outputs/figures/11_controlled_confusion.png)

| Người | Đúng/Tổng | Độ đúng mô tả |
|---|---:|---:|
| Minh | 1/2 | 50,0% |
| Quy | 2/3 | 66,7% |
| Tài | 3/3 | 100% |
| **Tổng** | **6/8** | **75,0%** |

Balanced accuracy là 72,2%, macro-F1 là 73,0%. Đây chỉ là kết quả thăm dò vì Minh có đúng hai run và tổng tập kiểm tra chỉ có tám run.

## 16. Nhiệt độ và độ ẩm có ảnh hưởng nhiều không?

**Có ảnh hưởng như biến gây nhiễu giữa ngày, nhưng không cần đưa vào fingerprint chính ở giai đoạn này.**

Trong một lần exposure, thay đổi môi trường khá nhỏ:

- Nhiệt độ: trung vị +0,086°C.
- Độ ẩm: trung vị +0,210 điểm phần trăm.

Nhưng baseline giữa các run thay đổi lớn hơn:

- Nhiệt độ nền: 32,57–34,67°C.
- Độ ẩm nền: 55,01–68,02%.
- Áp suất nền: 1.010,83–1.013,49 hPa.

![Tương quan biến môi trường](report_outputs/figures/17_environment_sensor_correlation.png)

Kết quả đáng chú ý:

- MQ3 mean tương quan với độ ẩm nền: **ρ = -0,72**.
- MQ3 mean tương quan với áp suất nền: **ρ = -0,74**.
- BME mean chỉ tương quan nhẹ/vừa với nhiệt độ, độ ẩm và áp suất: khoảng -0,22 đến -0,39.

Với n=16, chưa thể kết luận môi trường gây ra đáp ứng. Tuy nhiên, không được bỏ hẳn các trường này khỏi dữ liệu. Quyết định sử dụng là:

1. không đưa nhiệt độ/độ ẩm/áp suất vào mô hình nhận diện người;
2. vẫn lưu và vẽ chúng để kiểm tra drift giữa ngày;
3. các phiên train/test phải trải trên nhiều điều kiện môi trường;
4. nếu MQ3 tiếp tục phân biệt tốt sau khi cân bằng ngày/độ ẩm thì mới coi đó là tín hiệu người.

## 17. Dữ liệu chưa sạch hoặc còn thiếu

| Vấn đề | Mức độ | Cách xử lý |
|---|---|---|
| `person_code`, `source`, `distance_cm`, `notes` trống 16/16 run | Nghiêm trọng | Ghi trực tiếp vào metadata, không chỉ đặt tên folder |
| `hihi` không rõ nhãn | Nghiêm trọng cho supervised learning | Chỉ dùng QC, loại khỏi phân loại |
| Trạng thái bơm luôn unknown | Nghiêm trọng cho timing exposure | Thêm feedback hoặc đồng bộ event với thao tác thật |
| MQ135 drift/dao động lớn | Nghiêm trọng | Sửa phần cứng/đọc ADC; quality gate riêng |
| `mq135_ao_voltage_v`, `mq3_ao_voltage_v` trống | Cấu hình thiếu | Xác nhận hệ số chia áp |
| Điều kiện người/vị trí/áo không cân bằng | Nghiêm trọng cho kết luận người | Thu cùng protocol cho mọi người |
| Recovery cố định 60 giây | Chưa phù hợp MQ135 | Recovery thích ứng đến khi về nền |
| Sáu `loop_interval_s` trống | Không nghiêm trọng | Mẫu đầu phiên không có khoảng trước đó |
| Ba cột `*_error` trống | Không phải lỗi | Trống vì mọi trạng thái đọc là `OK` |

Chi tiết đủ 50 trường nằm trong [`field_audit_all_50_fields.csv`](report_outputs/tables/field_audit_all_50_fields.csv).

## 18. Trả lời câu hỏi nghiên cứu

### Có tìm được đặc trưng người dựa vào mùi không?

**Có tín hiệu ban đầu ở MQ3, nhưng chưa đủ để khẳng định.**

- Minh, Quy và Tài có ba khoảng mean MQ3 tương đối khác nhau.
- MQ3 nearest-centroid nhận đúng 6/8 run.
- Tuy nhiên, fingerprint 15 đặc trưng chưa tách rõ và separation ratio chỉ 1,12.
- MQ3 còn tương quan với môi trường nền.

### Có nên kết hợp cả ba cảm biến không?

**Chưa có lợi ở dữ liệu hiện tại.**

- Cả ba cảm biến với 15 đặc trưng chỉ đạt balanced accuracy 33,3%.
- Chỉ ba mean đạt 61,1%.
- MQ3 riêng đạt 72,2%.
- MQ135 đang làm giảm chất lượng fusion.

Trong đợt tiếp theo nên giữ hai baseline:

1. BME688 riêng để làm mốc ổn định;
2. BME688 + MQ3 làm nhánh fusion chính;
3. MQ135 là nhánh thử nghiệm, chỉ thêm vào khi đạt quality gate.

## 19. Pipeline thu thập đề xuất

1. Tạo `session_id`; warm-up đến khi từng cảm biến đạt baseline ổn định.
2. Ghi blank/khí phòng đầu phiên.
3. Ghi bắt buộc vào metadata: `person_code`, vị trí, áo, trạng thái sau tắm, `distance_cm`, thứ tự mẫu và lần lặp.
4. Chọn một vị trí chuẩn, ví dụ bụng–không áo, cho toàn bộ người trong bài toán nhận diện ban đầu.
5. Xáo trộn thứ tự người trong mỗi phiên.
6. Thu baseline 60 giây; kiểm tra CV riêng BME688, MQ135, MQ3.
7. Đồng bộ event exposure với thời điểm đổi nguồn khí thật.
8. Thu exposure 120 giây với khoảng cách và tư thế cố định.
9. Recovery đến khi tín hiệu trở về ngưỡng, không dừng cứng ở 60 giây.
10. Thu blank giữa hai người để kiểm tra carry-over.
11. Thu ít nhất 10–20 run/người trên tối thiểu 5 ngày.
12. Đánh giá theo ngày/phiên chưa thấy, không chia ngẫu nhiên từng dòng 1 Hz.

Quality gate khởi đầu:

| Tiêu chí | Ngưỡng đề xuất |
|---|---:|
| Dữ liệu hợp lệ | ≥95% |
| Gap lấy mẫu | ≤3 giây |
| BME688 baseline CV | ≤1% |
| MQ3 baseline CV | ≤1% |
| MQ135 drift/CV | ≤5% |
| Recovery cuối run | Trong ±5–10% baseline |
| ADC saturation | 0 dòng |

## 20. File tái lập phân tích

- Script: [`../../analysis/analyze_new_batch.py`](../../analysis/analyze_new_batch.py)
- Biểu đồ: [`report_outputs/figures/`](report_outputs/figures/)
- Bảng kết quả: [`report_outputs/tables/`](report_outputs/tables/)
- Audit từng run: [`report_outputs/tables/run_audit.csv`](report_outputs/tables/run_audit.csv)
- Biến đổi người/ngày: [`report_outputs/tables/person_day_changes.csv`](report_outputs/tables/person_day_changes.csv)
- Kết quả BME688: [`report_outputs/tables/model_table_main_bme688.csv`](report_outputs/tables/model_table_main_bme688.csv)
- Kết quả ba cảm biến: [`report_outputs/tables/model_table_all_3_sensors.csv`](report_outputs/tables/model_table_all_3_sensors.csv)
- Sensor ablation: [`report_outputs/tables/sensor_ablation_scores.csv`](report_outputs/tables/sensor_ablation_scores.csv)

Chạy lại pipeline:

```powershell
& 'C:\Users\ADMIN\AppData\Local\Programs\Python\Python311\python.exe' 'analysis\analyze_new_batch.py'
```
