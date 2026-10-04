# Báo cáo phân tích bộ dữ liệu thử nghiệm RoboNose

## 1. Tóm tắt

Bộ dữ liệu này là lần thử nghiệm đầu tiên của hệ thống RoboNose nhằm thu nhận fingerprint mùi bằng ba kênh cảm biến khí:

- BME688: gas resistance, nhiệt độ, độ ẩm và áp suất;
- MQ135: kênh phản ứng bổ sung với VOC và một số loại khí;
- MQ3: nhạy với alcohol, ethanol và một số hơi hữu cơ;
- ADS1115: bộ chuyển đổi ADC 16-bit dùng để đọc MQ135 và MQ3.

Dữ liệu chính gồm 10 lần đo: 5 loại mẫu, mỗi loại được đo trong 2 trial. Các loại mẫu gồm không khí, áo, nách, nước hoa và mắm tôm.

Kết quả ban đầu cho thấy thiết bị tạo được tín hiệu có khả năng phân biệt một số loại mùi, đặc biệt là nước hoa và mùi nách. Tuy nhiên, bộ dữ liệu còn quá nhỏ để kết luận về hiệu năng mô hình. Dữ liệu hiện tại cũng chưa thể dùng để đánh giá khả năng nhận diện người qua mùi vì chỉ có dữ liệu của một người và trường `person_code` chưa được gán.

Các kết quả nổi bật:

- Tỷ lệ dữ liệu hợp lệ của các cảm biến đạt 99,9–100%.
- Nước hoa làm gas resistance của BME688 giảm khoảng 77–83% và điện áp MQ3 tăng trung bình khoảng 8–12%.
- Mùi nách làm gas resistance giảm khoảng 5,5–5,8% ở cả hai trial.
- Khoảng cách fingerprint khác nhãn lớn hơn khoảng 1,81 lần so với khoảng cách giữa hai lần đo cùng nhãn.
- Phép ghép nearest-neighbour chéo trial đạt độ chính xác mô tả 70% trên 10 truy vấn.
- Hai lần đo nước hoa có baseline không ổn định; tín hiệu BME688 sau recovery còn lệch tối đa khoảng 16,5% so với baseline.

Nhìn chung, kết quả đủ tích cực để tiếp tục thu một bộ dữ liệu lớn và được kiểm soát tốt hơn, nhưng chưa đủ để tuyên bố hệ thống đã phân loại mùi hoặc nhận diện người một cách đáng tin cậy.

## 2. Mục tiêu phân tích

Báo cáo tập trung trả lời các câu hỏi sau:

1. Bộ dữ liệu hiện tại có đầy đủ và hợp lệ về mặt kỹ thuật hay không?
2. Các cảm biến có tạo ra phản ứng rõ khi chuyển từ baseline sang exposure hay không?
3. Fingerprint của cùng một loại mẫu có lặp lại giữa `trial01` và `trial02` hay không?
4. Có tín hiệu ban đầu cho thấy mùi A có thể được phân biệt với mùi B hay không?
5. Dữ liệu hiện tại có đủ để đánh giá nhận diện người qua mùi hay không?

Đơn vị mẫu độc lập trong phân tích là **một lần đo hoàn chỉnh**, không phải từng dòng dữ liệu 1 Hz. Các dòng trong cùng một lần đo có tương quan rất cao theo thời gian; chia ngẫu nhiên chúng vào train và test sẽ gây rò rỉ dữ liệu và tạo ra độ chính xác ảo.

## 3. Thiết kế hệ thống thu nhận

Theo báo cáo phần cứng, luồng lấy mẫu dự kiến là:

```text
Sampling cup
    ↓
Sensor chamber
    ↓
Pump
    ↓
Exhaust
```

Bơm được đặt sau buồng cảm biến nhằm hạn chế hơi nhựa, dầu, nhiệt hoặc contamination từ bơm đi qua cảm biến trước khi đo. Giữa các mẫu, hệ thống được purge bằng không khí sạch nhằm đưa tín hiệu trở về baseline.

Các rủi ro phần cứng quan trọng đã được xác định:

- VOC có thể bám vào ống và thành buồng, gây memory effect;
- ống silicon dài có thể hấp thụ và giải phóng VOC chậm;
- MQ135 và MQ3 có heater, có thể ảnh hưởng nhiệt độ buồng;
- thời gian purge cố định có thể không đủ với mẫu mạnh như nước hoa hoặc mắm tôm;
- sampling cup, khoảng cách lấy mẫu và lưu lượng bơm cần được giữ ổn định.

Trong dữ liệu hiện tại, BME688 được vận hành với heater cố định ở 320 °C trong khoảng 150 ms. Đây chưa phải là heater profile nhiều mức nhiệt. Việc bổ sung nhiều mức nhiệt có thể làm fingerprint giàu thông tin hơn trong các vòng thử nghiệm tiếp theo.

## 4. Quy trình đo

Mỗi lần đo chính có ba pha:

| Pha | Thời gian thiết kế | Ý nghĩa |
|---|---:|---|
| Baseline | 60 giây | Đo trạng thái nền trước khi đưa mẫu vào |
| Exposure | 120 giây | Cho cảm biến tiếp xúc với mẫu |
| Recovery | 60 giây | Purge và theo dõi tín hiệu trở về nền |

Ngoài ba pha trên, dữ liệu còn có các pha `MONITOR`, `WAIT_EXPOSURE`, `WAIT_RECOVERY` và `WAIT_FINISH`. Thời gian các pha chờ chưa đồng nhất giữa các lần đo nên chúng không được dùng để xây dựng fingerprint chính.

Thứ tự đo của hai trial:

| Trial | Thứ tự mẫu |
|---|---|
| Trial 01 | Không khí → Áo → Nách → Nước hoa → Mắm tôm |
| Trial 02 | Không khí → Mắm tôm → Áo → Nước hoa → Nách |

Trial 01 được warm-up khoảng 10 phút. Trial 02 được warm-up khoảng 15 phút vì nhiệt độ và độ ẩm ở trial đầu chưa ổn định như mong muốn. Hai trial cách nhau khoảng 15 phút; hệ thống được tắt sau trial 01 rồi warm-up lại trước trial 02.

Việc thay đổi thứ tự giữa hai trial là một điểm tốt vì làm giảm một phần sự trùng khớp hoàn toàn giữa nhãn và thứ tự đo. Tuy nhiên, số trial còn quá ít và recovery chưa hoàn toàn nên ảnh hưởng của carry-over chưa được loại bỏ.

## 5. Thành phần bộ dữ liệu

Toàn bộ thư mục `data/` đã được kiểm tra gồm:

| Loại file | Số lượng | Nội dung |
|---|---:|---|
| CSV | 36 | Dữ liệu thô và sự kiện |
| JSON | 36 | Metadata và thống kê tóm tắt |
| PNG | 36 | Biểu đồ tín hiệu và tín hiệu chuẩn hóa |
| TXT | 2 | Ghi chú quá trình đo và báo cáo phần cứng |

Tổng cộng có 18 thư mục run:

- 10 run chính có tiền tố `trial01_` hoặc `trial02_`;
- 8 run test/monitor dùng trong quá trình tối ưu hệ thống.

Một số run test/monitor chạy cùng thời điểm và chứa tín hiệu trùng hoặc chồng lấp với run chính. Vì vậy, chúng không được coi là các mẫu độc lập và không được đưa vào đánh giá phân loại. Nếu đưa các run này vào mô hình, kết quả có thể bị phóng đại do rò rỉ dữ liệu.

Mỗi thư mục run thường chứa:

| File | Vai trò |
|---|---|
| `raw.csv` | Toàn bộ chuỗi thời gian từ cảm biến |
| `events.csv` | Các mốc bắt đầu, chuyển pha và kết thúc |
| `metadata.json` | Cấu hình phần cứng, thời gian, thông tin mẫu và chất lượng baseline |
| `summary.json` | Thống kê baseline, exposure, recovery và các cảnh báo |
| `signals.png` | Biểu đồ tín hiệu thô |
| `normalized.png` | Biểu đồ tín hiệu đã chuẩn hóa |

Tất cả 36 file CSV và 36 file JSON đều đọc được; 36 file PNG đều hợp lệ. Không phát hiện file hỏng hoặc lỗi định dạng.

## 6. Cấu trúc dữ liệu thô

`raw.csv` được lấy mẫu với tần số mục tiêu 1 Hz. Các nhóm cột quan trọng gồm:

### 6.1. Định danh và thời gian

- `run_id`, `seq`, `timestamp`;
- `elapsed_s`, `phase_elapsed_s`, `phase`;
- `sensor_uptime_s`, `loop_interval_s`, `schedule_lag_s`.

### 6.2. BME688

- `temperature_c`;
- `humidity_pct`;
- `pressure_hpa`;
- `gas_resistance_ohm`;
- `gas_valid`, `heater_stable`, `new_data`, `bme_status`, `bme_fresh`.

### 6.3. MQ135 và MQ3

- `mq135_adc_count`, `mq135_voltage_v`;
- `mq3_adc_count`, `mq3_voltage_v`;
- các trường status, error, fresh và thời gian đọc.

Hệ số voltage divider của MQ135 và MQ3 chưa được xác nhận trong metadata. Vì vậy, phân tích hiện tại sử dụng điện áp ADC và phần trăm thay đổi so với baseline của từng run, không diễn giải thành nồng độ ppm hay điện áp AO tuyệt đối.

## 7. Lựa chọn và tiền xử lý dữ liệu

Ba tín hiệu chính dùng để tạo fingerprint là:

- `gas_resistance_ohm` của BME688;
- `mq135_voltage_v`;
- `mq3_voltage_v`.

Một mẫu BME688 chỉ được giữ lại khi:

- `bme_status == "OK"`;
- `bme_fresh == True`;
- `gas_valid == True`;
- `heater_stable == True`;
- `new_data == True`.

Một mẫu MQ chỉ được giữ lại khi trạng thái tương ứng là `OK` và dữ liệu được đánh dấu `fresh`.

Mỗi tín hiệu được chuẩn hóa theo median baseline của chính run đó:

```text
response_pct = 100 × (signal / baseline_median - 1)
```

Cách chuẩn hóa này giúp giảm ảnh hưởng của chênh lệch mức nền giữa các lần đo, nhưng không loại bỏ hoàn toàn drift, thay đổi môi trường hoặc memory effect.

Các đặc trưng cấp run được trích từ exposure và recovery gồm:

- trung bình exposure;
- trung bình 20 giây cuối exposure;
- giá trị nhỏ nhất và lớn nhất;
- diện tích tuyệt đối dưới đường cong;
- slope theo thời gian;
- trung bình 10 giây cuối recovery.

## 8. Chất lượng dữ liệu

Mười run chính chứa tổng cộng 5.082 dòng dữ liệu. Chu kỳ lấy mẫu median là khoảng 1 giây và khoảng trống lớn nhất chỉ khoảng 1,01 giây.

Tỷ lệ dữ liệu hợp lệ:

| Tín hiệu | Tỷ lệ hợp lệ |
|---|---:|
| BME688 gas resistance | 99,9–100% |
| MQ135 voltage | 100% |
| MQ3 voltage | 100% |

Chất lượng từng run:

| Trial | Mẫu | Số dòng | Baseline ổn định | Nhiệt độ baseline (°C) | Độ ẩm baseline (%) | BME recovery cuối (%) |
|---:|---|---:|:---:|---:|---:|---:|
| 1 | Không khí | 1.076 | Có | 36,68 | 53,34 | -1,31 |
| 1 | Áo | 306 | Có | 36,61 | 53,59 | -1,42 |
| 1 | Nách | 314 | Có | 36,61 | 54,00 | -2,06 |
| 1 | Nước hoa | 369 | Không | 36,65 | 54,28 | -7,60 |
| 1 | Mắm tôm | 322 | Có | 36,65 | 54,72 | -1,85 |
| 2 | Không khí | 1.191 | Có | 36,64 | 54,57 | -0,58 |
| 2 | Mắm tôm | 303 | Có | 36,61 | 54,70 | -0,28 |
| 2 | Áo | 425 | Có | 36,60 | 54,76 | +0,01 |
| 2 | Nước hoa | 332 | Không | 36,59 | 54,71 | -16,54 |
| 2 | Nách | 444 | Có | 36,59 | 54,64 | -1,92 |

Hai run nước hoa đều bị hệ thống đánh dấu baseline không ổn định do gas resistance còn trôi. Đây là vấn đề quan trọng vì nước hoa cũng tạo ra phản ứng mạnh nhất và cần thời gian purge lâu nhất.

Nhiệt độ BME688 ở baseline khoảng 36,6 °C, cao hơn nhiệt độ phòng thông thường. Giá trị này chịu ảnh hưởng của heater và vị trí trong buồng cảm biến, vì vậy không nên được diễn giải trực tiếp là nhiệt độ môi trường đã bù.

## 9. Mức phản ứng của các mẫu

### 9.1. BME688 gas resistance

Phần trăm thay đổi trung bình trong exposure:

| Mẫu | Trial 01 | Trial 02 | Nhận xét |
|---|---:|---:|---|
| Không khí | -0,53% | -0,21% | Thay đổi nhỏ, gần baseline |
| Áo | -0,78% | -1,12% | Phản ứng yếu |
| Nách | -5,79% | -5,48% | Phản ứng khá rõ và lặp lại tốt |
| Nước hoa | -76,58% | -82,90% | Phản ứng rất mạnh |
| Mắm tôm | -3,44% | -2,75% | Có phản ứng, hình dạng mang tính transient |

Nước hoa là mẫu tách biệt rõ nhất. Mùi nách cũng có độ lặp lại đáng chú ý giữa hai trial. Áo và không khí gần nhau hơn nhiều nên sẽ là cặp khó phân biệt.

Mắm tôm có giá trị BME688 thấp nhất tức thời khoảng -13,5% ở cả hai trial, nhưng giá trị trung bình chỉ khoảng -3%. Điều này cho thấy phản ứng mạnh ở đầu exposure rồi hồi phục một phần, vì vậy các đặc trưng động học như peak, slope và AUC quan trọng hơn chỉ dùng giá trị trung bình.

### 9.2. MQ135

MQ135 thay đổi trung bình trong exposure chủ yếu nằm trong khoảng -0,2% đến +1,1%. Nước hoa tạo phản ứng dương khoảng 0,87–1,07%, nhưng độ lớn vẫn khá gần mức nhiễu/ngắn hạn của nhiều mẫu khác.

Trong bộ dữ liệu hiện tại, MQ135 chưa cho thấy khả năng phân biệt mạnh khi dùng riêng. Cần thêm nhiều lần lặp để xác định tín hiệu nhỏ này có ổn định hay không.

### 9.3. MQ3

Phần trăm thay đổi trung bình trong exposure:

| Mẫu | Trial 01 | Trial 02 | Nhận xét |
|---|---:|---:|---|
| Không khí | -0,05% | -0,08% | Gần baseline |
| Áo | +0,04% | -0,01% | Gần baseline |
| Nách | +0,71% | +0,31% | Phản ứng nhỏ |
| Nước hoa | +8,16% | +11,57% | Phản ứng mạnh, phù hợp độ nhạy với alcohol |
| Mắm tôm | -0,88% | +0,37% | Không lặp lại về dấu |

MQ3 có đóng góp rõ nhất đối với nước hoa. Với các lớp còn lại, phản ứng nhỏ và chưa ổn định. Kết quả này phù hợp với đặc tính nhạy với alcohol của MQ3.

## 10. Recovery và carry-over

Recovery 60 giây chưa đủ cho một số mẫu:

- BME688 sau nước hoa trial 01 còn lệch khoảng -7,6%;
- BME688 sau nước hoa trial 02 còn lệch khoảng -16,5%;
- MQ3 sau nước hoa còn lệch khoảng +2,9% và +4,5%;
- các mẫu còn lại thường gần baseline hơn, nhưng vẫn có sai lệch khoảng 1–2% ở một số run.

Điều này xác nhận nhận xét trong ghi chú thí nghiệm rằng cảm biến chưa luôn trở về mức cũ sau recovery. Nếu run kế tiếp được bắt đầu quá sớm, mô hình có thể học mùi còn sót lại hoặc thứ tự đo thay vì học fingerprint thật của mẫu hiện tại.

Không nên dùng recovery cố định 60 giây cho mọi loại mẫu. Một tiêu chí tốt hơn là tiếp tục purge cho đến khi các tín hiệu chính trở về trong một ngưỡng xác định, ví dụ ±2–5% so với baseline và slope trong cửa sổ 30 giây đủ nhỏ.

## 11. Đánh giá sơ bộ khả năng phân biệt mùi

Fingerprint cấp run được chuẩn hóa theo từng đặc trưng rồi đánh giá bằng:

- PCA để quan sát cấu trúc dữ liệu;
- khoảng cách Euclidean giữa trial 01 và trial 02;
- nearest-neighbour, dùng một trial làm tập tham chiếu và trial còn lại làm truy vấn;
- đánh giá riêng BME688, hai cảm biến MQ và toàn bộ cảm biến khí.

### 11.1. PCA

Hai thành phần PCA đầu giải thích:

- PC1: 80,9% phương sai;
- PC2: 9,3% phương sai.

Phần lớn PC1 bị chi phối bởi phản ứng rất mạnh của nước hoa. Do đó, việc các điểm tách xa nhau trên PCA không có nghĩa là tất cả năm loại mẫu đều đã phân tách tốt. Cần kiểm tra riêng các lớp yếu như áo và không khí.

### 11.2. Khoảng cách fingerprint

Median khoảng cách giữa hai trial cùng nhãn là 2,314, trong khi median khoảng cách khác nhãn là 4,194.

```text
separation ratio = 4,194 / 2,314 ≈ 1,81
```

Tỷ lệ lớn hơn 1 là tín hiệu tích cực: trung bình các mẫu khác loại xa nhau hơn hai lần đo của cùng loại. Tuy nhiên, chỉ có một cặp lặp lại cho mỗi nhãn nên chưa thể ước lượng phân phối khoảng cách nội lớp một cách đáng tin cậy.

### 11.3. Nearest-neighbour chéo trial

| Nhóm đặc trưng | Trial 01 tham chiếu, Trial 02 truy vấn | Trial 02 tham chiếu, Trial 01 truy vấn | Trung bình |
|---|---:|---:|---:|
| BME688 gas | 100% | 60% | 80% |
| MQ135 + MQ3 | 40% | 60% | 50% |
| Tất cả cảm biến khí | 80% | 60% | 70% |

Khi sử dụng tất cả cảm biến khí, độ đúng theo nhãn là:

| Nhãn | Số lần đúng | Tổng truy vấn | Độ đúng mô tả |
|---|---:|---:|---:|
| Không khí | 2 | 2 | 100% |
| Áo | 0 | 2 | 0% |
| Nách | 2 | 2 | 100% |
| Nước hoa | 2 | 2 | 100% |
| Mắm tôm | 1 | 2 | 50% |

Kết quả 70% cao hơn mức ngẫu nhiên danh nghĩa 20% của bài toán 5 lớp, nhưng không được xem là accuracy triển khai vì:

- chỉ có 10 run;
- chỉ có 2 run mỗi nhãn;
- không có ngày đo độc lập;
- không có người độc lập;
- các mẫu được thu liên tiếp trên cùng một thiết bị;
- carry-over và drift chưa được kiểm soát hoàn toàn;
- một lớp rất mạnh là nước hoa có thể làm kết quả tổng thể trông tốt hơn các lớp còn lại.

BME688 hiện mang phần lớn thông tin phân biệt. Hai cảm biến MQ có thể bổ sung thông tin cho một số chất, đặc biệt MQ3 với nước hoa, nhưng chưa chứng minh được đóng góp ổn định trên tất cả các lớp.

## 12. Khả năng nhận diện người qua mùi

Bộ dữ liệu hiện tại không thể trả lời câu hỏi nhận diện người vì:

- chỉ có dữ liệu của một người;
- `person_code` đang để trống;
- áo và nách là nhãn nguồn mẫu, không phải nhãn danh tính;
- không có nhiều ngày đo để đánh giá sự ổn định mùi của cùng người;
- không có dữ liệu giữa nhiều người để ước lượng khác biệt liên cá nhân;
- không có các biến kiểm soát như mỹ phẩm, nước hoa, chế độ ăn và vận động.

Kết quả hiện tại chỉ cho thấy hệ thống có thể phản ứng khác nhau với các nguồn mùi có cường độ và thành phần rất khác nhau. Điều đó chưa đồng nghĩa với khả năng phân biệt hai người có mùi cơ thể gần nhau.

Cần xác định rõ hai bài toán nhận diện người:

1. **Closed-set identification:** dự đoán một mẫu thuộc về người nào trong danh sách những người đã biết.
2. **Verification:** xác định hai mẫu có thuộc cùng một người hay không.

Với identification, train và test phải là các ngày hoặc session khác nhau của cùng nhóm người. Với verification, nên báo cáo ROC-AUC, Equal Error Rate và khoảng tin cậy, thay vì chỉ dùng accuracy.

## 13. Các yếu tố gây nhiễu và hạn chế

### 13.1. Cỡ mẫu

Hai lần lặp mỗi nhãn không đủ để ước lượng phương sai nội lớp, kiểm định thống kê hoặc xây dựng mô hình machine learning có khả năng tổng quát hóa.

### 13.2. Carry-over

Nước hoa không recovery hoàn toàn. Mắm tôm cũng là mẫu có nguy cơ bám mùi cao. Tín hiệu run sau có thể chứa thành phần của run trước.

### 13.3. Drift theo thời gian

Một số đặc trưng, đặc biệt slope của MQ135, có tương quan đáng kể với thứ tự thu. Điều này cho thấy một phần fingerprint có thể liên quan đến quá trình warm-up hoặc drift chứ không chỉ do mẫu.

### 13.4. Nhiệt độ và độ ẩm

Độ ẩm baseline thay đổi giữa các run. Cảm biến MOX nhạy với điều kiện môi trường nên cần ghi và kiểm soát nhiệt độ/độ ẩm phòng, đồng thời kiểm tra liệu mô hình có đang dự đoán từ các biến này hay không.

### 13.5. Thứ tự mẫu

Hai trial có đổi thứ tự, nhưng mỗi thứ tự chỉ xuất hiện một lần. Chưa thể tách hoàn toàn hiệu ứng nhãn khỏi hiệu ứng thứ tự.

### 13.6. Chưa xác nhận voltage divider

Hệ số chia áp MQ135/MQ3 chưa được xác nhận nên không thể diễn giải điện áp AO tuyệt đối hay chuyển đổi sang đại lượng vật lý đáng tin cậy.

### 13.7. Mẫu có độ mạnh rất khác nhau

Nước hoa là mẫu rất mạnh, trong khi áo và không khí có phản ứng gần baseline. Accuracy tổng thể có thể bị chi phối bởi các lớp dễ.

## 14. Đề xuất vòng thu tiếp theo

### 14.1. Thử nghiệm phân biệt loại mùi

- Thu ít nhất 10–20 run độc lập cho mỗi loại mùi;
- trải dữ liệu trên ít nhất 3 ngày;
- random hóa thứ tự mẫu trong từng block;
- dùng blank không khí trước và sau mẫu mạnh;
- chuẩn hóa khoảng cách sampling cup, lưu lượng bơm, thời gian exposure và lượng mẫu;
- purge cho đến khi tín hiệu trở về ngưỡng thay vì chỉ purge cố định 60 giây;
- cân nhắc cup hoặc tubing riêng cho nước hoa và mắm tôm;
- ghi lại thời điểm thay/vệ sinh cup và tubing;
- nếu có thể, đo lưu lượng khí thực tế;
- thử heater profile nhiều mức nhiệt cho BME688.

### 14.2. Thử nghiệm nhận diện người

Một pilot hợp lý nên có:

- tối thiểu 10 người, tốt hơn là 20–30 người;
- mỗi người ít nhất 5 lần đo mỗi ngày;
- ít nhất 3 ngày khác nhau;
- cùng vị trí lấy mẫu, ví dụ chỉ nách hoặc chỉ vùng sau tai;
- một protocol thống nhất về thời gian không dùng nước hoa/mỹ phẩm trước khi đo;
- ghi lại `person_code`, ngày, session, vị trí cơ thể, mỹ phẩm, vận động, chế độ ăn và tình trạng môi trường;
- có blank và mẫu kiểm soát trong mỗi session.

### 14.3. Chia tập dữ liệu

Không được chia ngẫu nhiên các dòng hoặc các cửa sổ từ cùng một run vào cả train và test.

Nên sử dụng:

- GroupKFold theo session hoặc ngày;
- leave-one-day-out để kiểm tra độ bền theo thời gian;
- tập test cuối cùng được khóa và chỉ đánh giá một lần;
- preprocessing và StandardScaler chỉ được fit trên tập train.

### 14.4. Lộ trình mô hình

Thứ tự nên thử:

1. nearest centroid hoặc nearest-neighbour;
2. logistic regression có regularization;
3. Linear/Kernel SVM;
4. Random Forest hoặc gradient boosting;
5. chỉ cân nhắc deep learning khi đã có hàng trăm đến hàng nghìn run độc lập.

Cần thực hiện ablation test:

- chỉ BME688;
- chỉ MQ135;
- chỉ MQ3;
- BME688 + MQ135;
- BME688 + MQ3;
- toàn bộ cảm biến.

Việc này giúp xác định MQ135 và MQ3 có thực sự tăng khả năng phân loại hay chỉ tăng số chiều và nhiễu.

## 15. Tiêu chí go/no-go đề xuất

Có thể tiếp tục sang giai đoạn mô hình hóa nghiêm túc khi:

- baseline ổn định ở phần lớn run;
- ít nhất 90% run recovery về trong ±5% baseline;
- khoảng cách cùng nhãn nhỏ hơn khoảng cách khác nhãn một cách nhất quán;
- hiệu năng group cross-validation vượt baseline ngẫu nhiên với khoảng tin cậy rõ;
- kết quả vẫn tốt khi loại bỏ nhiệt độ, độ ẩm và thứ tự thu;
- kết quả giữ được trên ngày hoặc session chưa xuất hiện trong train.

Cần quay lại tối ưu phần cứng/protocol nếu:

- tín hiệu chủ yếu phụ thuộc vào thứ tự đo hoặc thời gian warm-up;
- carry-over vẫn lớn sau purge;
- độ lệch giữa các ngày lớn hơn độ lệch giữa các nhãn;
- các lớp yếu như áo và không khí không lặp lại sau khi tăng số lần đo;
- các cảm biến MQ không đóng góp ngoài mức nhiễu.

## 16. Kết luận

Bộ dữ liệu thử nghiệm đầu tiên có chất lượng ghi nhận tốt, gần như không mất mẫu và có metadata tương đối đầy đủ. Thiết bị phản ứng rõ với nước hoa và tạo được đáp ứng BME688 khá lặp lại đối với mùi nách. Đây là bằng chứng ban đầu rằng hệ thống có khả năng tạo fingerprint khác nhau giữa một số loại mùi.

Tuy nhiên, kết quả phân loại 70% chỉ có giá trị thăm dò. Cỡ mẫu quá nhỏ, nước hoa chi phối phần lớn phương sai, áo chưa được nhận dạng đúng, và recovery sau nước hoa chưa đủ. Chưa có cơ sở để đánh giá nhận diện người.

Bước tiếp theo phù hợp không phải là tối ưu một mô hình phức tạp trên 10 run hiện tại, mà là chuẩn hóa protocol, giảm carry-over, random hóa thứ tự và thu thêm nhiều run độc lập trên nhiều ngày và nhiều người. Khi đó mới có thể đánh giá khách quan liệu fingerprint mùi có ổn định và đủ đặc trưng cho phân biệt mùi hoặc nhận diện người hay không.

## 17. Tài liệu và mã phân tích

- Báo cáo phần cứng: [`data/phần cứng.txt`](data/phần%20cứng.txt)
- Ghi chú lần thử: [`data/first_trial/note.txt`](data/first_trial/note.txt)
- Notebook chưa chạy: [`odor_data_feasibility.ipynb`](odor_data_feasibility.ipynb)
- Notebook đã chạy, có biểu đồ và kết quả: [`odor_data_feasibility.executed.ipynb`](odor_data_feasibility.executed.ipynb)
- Danh sách thư viện: [`requirements.txt`](requirements.txt)

Notebook là nguồn tính toán chính cho các bảng thống kê, fingerprint, PCA, ma trận khoảng cách và phép ghép nearest-neighbour được trình bày trong báo cáo này.
