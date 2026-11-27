# Ứng dụng AI trong hệ thống RoboNose

Tài liệu báo cáo PBL6 · Số liệu đối chiếu với mã nguồn và kết quả thực nghiệm đến 27/11/2026.

## 1. Bài toán và phương án được chọn

RoboNose dùng chuỗi đo từ mảng cảm biến để giải quyết hai bài toán độc lập. Cùng một lượt thu có thể được đưa vào cả hai bài toán.

| Bài toán | Model được chọn | Kết quả trả về | Lý do lựa chọn |
| --- | --- | --- | --- |
| Nhận diện và đối sánh người | ResCNN64, một CNN tích chập một chiều với các khối residual. Mục 04 có thêm tùy chọn V2 hiệu chỉnh exposure trước CNN. | Mục 03 xếp hạng các nhãn trong kho tham chiếu. Mục 04 xếp hạng các lượt được chọn theo điểm cosine với một lượt tham chiếu. | CNN học được hình dạng đáp ứng theo thời gian của nhiều kênh. Embedding 64 chiều dùng được cho cả nhận diện theo kho mẫu và đối sánh từng lượt. |
| Phát hiện cà phê | Logistic Regression V2 trên ba kênh **MQ3 #1 A1, MQ135 #2 A2, MQ3 #2 A3**. | Mục 06 báo có mùi cà phê, không có mùi cà phê hoặc chưa đủ dữ liệu để dự đoán. | Đây là bản có kết quả cân bằng cao nhất trong các phương án đã thử trên tập 09–20/11. Model nhỏ, dễ triển khai và truy vết đóng góp của từng kênh. |

Mục 03 và mục 06 dùng API và kết quả riêng. Cà phê có thể được kiểm tra ngay cả khi một job nhận diện người thất bại. [Điểm vào API](robonose_s3/web_server.py) · [Job suy luận](robonose_s3/inference.py)

## 2. Kiến trúc hệ thống và công nghệ

```text
TGS2602 + MQ3 #1 + MQ135 #2 + MQ3 #2 → ADS1115 ┐
                                             ├─ ESP32-S3 → USB native CDC
BME688 (điện trở gas, nhiệt độ, RH, áp suất) ────┘
          → host Python ghi raw.csv và metadata.json theo UUID lượt đo
          → dashboard chọn mẫu đã lưu → hàng đợi inference
               ├─ Mục 03 → ResCNN64 → embedding → kho tham chiếu → xếp hạng nhãn
               ├─ Mục 04 → tùy chọn hiệu chỉnh V2 → ResCNN64 → cosine giữa các lượt
               └─ Mục 06 → đặc trưng đáp ứng → Logistic Regression → có/không cà phê
```

| Lớp | Công nghệ và vai trò |
| --- | --- |
| Thiết bị | ESP32-S3 chạy firmware C++, lấy mẫu danh định 1 Hz và điều khiển bơm/van theo pha. ADS1115 số hóa bốn điện áp analog. BME688 cung cấp điện trở gas và dữ liệu môi trường. |
| Thu và lưu | Host Python trên Windows nhận dữ liệu USB, lưu CSV và metadata. UUID theo từng lượt giúp phân biệt các mẫu trùng tên và đối chiếu dữ liệu giữa các lần chạy. |
| Huấn luyện | NumPy xử lý tensor và đặc trưng. PyTorch dùng cho ResCNN64, bộ hiệu chỉnh V2 và CNN cà phê thử nghiệm. scikit-learn dùng để fit Logistic Regression, Extra Trees, SVM và LDA. |
| Suy luận | ResCNN64 dùng PyTorch, có thể chạy qua một tiến trình Python riêng. Logistic dùng hệ số xuất dưới dạng JSON và tính điểm bằng Python tiêu chuẩn. Hàng đợi inference tách việc chấm mẫu khỏi thu dữ liệu. |
| Giao diện | HTTP server Python cục bộ và HTML/CSS/JavaScript. Dashboard có danh sách mẫu, xếp hạng danh tính, đối sánh và kiểm tra cà phê. |

[Firmware và thông số thiết bị](firmware/RoboNose_Dataset_S3/config.h) · [Worker ResCNN64](robonose_s3/rescnn_worker.py)

## 3. Dataset và nhãn

### 3.1. Đơn vị dữ liệu

Một mẫu đưa vào model là **một lượt đo đã lưu hoàn chỉnh**. Mỗi lượt gồm `raw.csv` và `metadata.json`. Raw giữ các giá trị đo, thời gian monotonic, pha, cờ hợp lệ, trạng thái cảm biến, đường khí và PWM. Metadata ghi UUID, phiên, tên mẫu, trạng thái và cấu hình thiết bị. Luồng thu có baseline danh định 60 giây, exposure 120 giây và recovery 60 giây. Baseline và exposure qua đầu lấy mẫu, recovery qua khí lọc. Các pha chờ có nhãn riêng.

Lượt `COMPLETE` thể hiện đã đi hết quy trình. Chất lượng tín hiệu được kiểm tra riêng trước khi vào model. Những bản xuất trùng UUID hoặc nội dung raw trùng hash được lọc ở các thử nghiệm có kiểm tra chống trùng. Các tập sau phục vụ mục đích khác nhau, có thể dùng lại một phần lượt đo. [Cấu trúc lưu trữ](data/README.md)

### 3.2. Tập theo từng bài toán

| Tập | Quy mô và cách dùng |
| --- | --- |
| ResCNN64 gốc | **77 lượt huấn luyện, 9 nhãn**. Báo cáo artifact ghi `full_fit`, các ngày train nằm trong 06–18/11/2026. Báo cáo gốc không có ngày test độc lập. |
| Bộ hiệu chỉnh người V2 | **93 lượt thuộc 9 nhãn**, ngày **09–20/11/2026**, tách khỏi cây `data/hardware`. Loại **60 lượt không xác nhận được nhãn danh tính** và **3 lượt chưa hoàn chỉnh**. |
| Kiểm tra người khác phiên | **13 lượt từ 4 phiên** trong `data/hardware`, gồm 8 lượt Phúc Lưu và 5 lượt Tài. Khi chấm một truy vấn, ứng viên chỉ đến từ phiên khác. Loại trùng theo UUID, hash hoặc phiên theo quy tắc của script. |
| Cà phê, chọn và huấn luyện model | **141 lượt ngày 09–20/11** gồm **32 lượt tên có cà phê**, **16 đối chứng không khí**, và **93 lượt chỉ mang tên người** được dùng làm nhãn âm quy ước. Nhóm cuối chưa có xác nhận thực nghiệm rằng từng lượt đều không có cà phê. |
| Cà phê, kiểm tra ngoài khoảng huấn luyện V2 | **8 lượt ghi nhãn cà phê ngày 07/11**. Tập này chỉ có mẫu dương đủ điều kiện trong phép kiểm tra, nên dùng để báo tỷ lệ phát hiện. |
| Cà phê, kiểm tra `data/hardware` | Có **13 lượt có tên người** trong tập so sánh có nhãn quy ước. Tập đã dùng trong báo cáo chưa có mẫu cà phê được xác nhận, nên chỉ báo số lượt model dự đoán có cà phê. |

[Báo cáo ResCNN64 gốc](models/rescnn64/20261119_053351_6b8717/report.json) · [Tập V2 nhận diện người](models_v2/grouped_training_report.json) · [Tập cà phê](models_v2/coffee_sensor_report.json)

## 4. Tiền xử lý và làm giàu tín hiệu

### 4.1. Nhận diện người

1. **Kiểm tra đầu vào.** ResCNN64 xác thực schema, cấu hình và miền giá trị. Yêu cầu đúng **60 điểm baseline, 120 điểm exposure**, khoảng cách danh định 1 giây giữa các điểm trong mỗi pha và timestamp tăng. Mẫu có kênh điện áp hoặc gas đứng yên suốt exposure bị loại. Độ trôi baseline lớn có thể được ghi cảnh báo theo cấu hình artifact.
2. **Quy về nền.** Với bốn điện áp analog và độ ẩm, lấy exposure trừ trung vị 30 điểm cuối baseline. Với BME688 gas, lấy `ln(R_exposure / R_baseline)`. Chuẩn hóa 6 kênh bằng mean/scale lưu trong checkpoint cấu hình. Đầu vào CNN là tensor **6 × 120**. Nhiệt độ, áp suất và recovery nằm ngoài tensor này.
3. **Làm giàu ở V2.** Dùng thêm toàn bộ 60 điểm baseline, chia thành sáu cửa sổ 10 giây cho mỗi kênh, tạo **36 đặc trưng**. Mỗi cửa sổ lấy trung bình, riêng điện trở gas chuyển sang log trước. Bộ hiệu chỉnh dự đoán mức bù và độ dốc rồi cộng đường hiệu chỉnh lên exposure chuẩn hóa. Kết quả vẫn giữ kích thước **6 × 120**.

### 4.2. Phát hiện cà phê

1. **Lọc chất lượng theo từng kênh.** Dùng các điểm có trạng thái hợp lệ. Mỗi pha cần tối thiểu 90% điểm hợp lệ và không có khoảng trống giữa các điểm hợp lệ quá 3 giây. Độ phủ thời gian tối thiểu là 50 giây cho baseline và 105 giây cho exposure. Thiếu dữ liệu bắt buộc sẽ trả trạng thái chưa dự đoán được.
2. **Đổi về phần trăm so với nền.** Từ trung vị baseline `b`, mỗi điểm exposure `x` được đổi thành `100 × (x − b) / |b|`.
3. **Rút đặc trưng.** Mỗi kênh đóng góp 5 giá trị gồm trung bình toàn exposure, trung bình cửa sổ 40–80 giây, P10, P90 và độ dốc tính theo phút. Logistic V2 dùng ba kênh nên có **15 đặc trưng**. Scaler được fit trên dữ liệu train, riêng từng fold khi đánh giá.
4. **Các cách làm giàu đã thử.** Thêm phản ứng đầu và cuối pha, chênh lệch đầu–cuối và độ dao động baseline. Thử Logistic học thêm từ hiệu giữa các cặp cà phê và tên người cùng ngày. CNN thử nghiệm dùng 12 cửa sổ exposure, tăng/giảm biên độ nhẹ và thêm nhiễu nhỏ trong train. Tăng cường CNN chỉ thực hiện ở các fold huấn luyện. Những thử nghiệm này chưa được đưa vào model mặc định.

Các đặc trưng và biến thể tăng cường được tính cho model. CSV gốc chỉ được đọc. [Tiền xử lý ResCNN64](robonose_s3/rescnn64.py#L117) · [Tiền xử lý cà phê](robonose_s3/coffee_detection/__init__.py) · [CNN cà phê thử nghiệm](models_v2/benchmark_coffee_cnn.py)

## 5. Kiến trúc model

### 5.1. ResCNN64 cho người

| Khối | Cấu hình |
| --- | --- |
| Đầu vào | Chuỗi `[batch, 6, 120]`, bốn kênh điện áp, điện trở gas và độ ẩm. |
| Trích xuất theo thời gian | `Conv1d 6 → 32`, kernel 7, GroupNorm, GELU. |
| Khối residual | `32 → 32`, kernel 5, stride 1. Tiếp theo `32 → 64`, kernel 5, stride 2 và `64 → 128`, kernel 3, stride 2. Mỗi khối gồm hai lớp tích chập và một nhánh nối tắt. |
| Gộp theo thời gian | Nối trung bình và cực đại của từng kênh đặc trưng để được vector 256 chiều. |
| Đầu embedding | `Linear 256 → 128 → 64`, GELU, dropout 0,2 trong train và chuẩn L2 ở đầu ra. |
| Đầu phân lớp | Học 9 nhãn. Lúc chạy dashboard, hệ thống dùng embedding để tính cosine. Mục 03 lấy ứng viên tốt nhất của từng nhãn trong kho, bỏ lượt có UUID hoặc raw hash trùng truy vấn. |

CNN 1D phù hợp vì mỗi lượt là chuỗi nhiều kênh đồng bộ. Tích chập học đặc trưng biến thiên cục bộ theo thời gian. Embedding cho phép mục 04 xếp hạng các mẫu do người dùng chọn, kể cả khi tên mẫu khác tên lớp trong kho. Ngưỡng xác nhận danh tính chưa được hiệu chuẩn, nên giao diện trình bày thứ hạng thay vì khẳng định danh tính. [Kiến trúc ResCNN64](robonose_s3/rescnn64.py#L217) · [Trạng thái hiệu chuẩn](models/rescnn64/20261119_053351_6b8717/artifact.json)

### 5.2. Bộ hiệu chỉnh trước CNN trong V2

Từ 36 đặc trưng baseline, MLP `36 → 16 → 12` với Tanh tạo 6 mức bù và 6 độ dốc. Model giới hạn độ lớn của đường hiệu chỉnh. **Trọng số ResCNN64 được khóa**, còn gradient đi qua CNN để học bộ hiệu chỉnh. Hàm mất mát ghép cross-entropy có trọng số lớp, phạt hiệu chỉnh lớn và thành phần contrastive giữa các lượt khác ngày. Mục tiêu contrastive giúp kéo gần các embedding cùng nhãn từ ngày khác. [Chi tiết kiến trúc V2](models_v2/BAO_CAO_KY_THUAT_V2.md) · [Nguồn gốc supervised contrastive learning](https://proceedings.neurips.cc/paper_files/paper/2020/hash/d89a66c7c80a29b1bdbab0f2a1a94af8-Abstract.html)

### 5.3. Model Logistic Regression cho cà phê

Với vector 15 đặc trưng sau chuẩn hóa `z`, model tính logit `b + w · z`. Logit lớn hơn 0 thì model trả có cà phê. Logistic dùng L2 với `C = 0,1` và cân bằng trọng số lớp khi train. Có thể so chuẩn L2 của hệ số theo nhóm kênh để diễn giải mức đóng góp trong model này. Thứ tự đo được là **MQ3 #2**, **MQ3 #1**, rồi **MQ135 #2**. Đây là độ lớn hệ số trong mô hình đã fit, còn đáp ứng từng cảm biến có thể thay đổi theo điều kiện đo. [Artifact Logistic V2](robonose_s3/coffee_detection/model_sensor_v2.json) · [Kết quả chọn kênh](models_v2/coffee_sensor_report.json)

## 6. Thử nghiệm và tiêu chí chọn model

### 6.1. Đối sánh danh tính

Trên archive, bộ hiệu chỉnh được chọn bằng cách lần lượt giữ riêng một ngày. Trong bốn cấu hình, phép thử dùng **top 1 trung bình theo lớp** làm chỉ số chính để mỗi nhãn có trọng số ngang nhau. MRR là trung bình nghịch đảo thứ hạng của ứng viên cùng nhãn đầu tiên, dùng để so khi điểm chính bằng nhau. Sau khi chốt cấu hình mới đánh giá 13 lượt hardware.

| Model | Top 1 trên 13 lượt hardware khác phiên | MRR hardware | Kết luận sử dụng |
| --- | ---: | ---: | --- |
| ResCNN64 gốc | 7/13 (53,8%) | 0,6692 | Giữ cho mục 03 và lựa chọn mặc định ở mục 04. |
| V2 bù theo công thức | 4/13 (30,8%) | 0,5231 | Giữ dưới dạng thử nghiệm. |
| V2 bộ hiệu chỉnh đã học lần đầu | 6/13 (46,2%) | 0,5788 | Bản thử trước khi chọn cấu hình theo ngày. |
| **V2 hiện tại, `v2-grouped`** | **8/13 (61,5%)** | **0,7333** | Tùy chọn **Bộ hiệu chỉnh đã học** ở mục 04. |
| V2 thử thêm trọng số cảm biến | 8/13 (61,5%) | 0,7418 | Top 1 trung bình theo lớp trên archive giảm từ 66,09% xuống 65,15%. Mục 04 tiếp tục dùng `v2-grouped`. |

Trên archive, V2 hiện tại đạt **50/76** truy vấn đúng hạng 1, so với **48/76** của CNN gốc. Trên hardware, V2 cải thiện tổng cộng một lượt đúng so với CNN gốc. Tập hardware chỉ có hai nhãn và đã dùng qua nhiều lần đánh giá, nên cần phiên mới để xác nhận khả năng tổng quát. [Báo cáo V2](models_v2/grouped_training_report.json) · [Thử nghiệm trọng số](models_v2/identity_sensor_report.json) · [Kết quả các bản V2](models_v2/BAO_CAO_KY_THUAT_V2.md)

### 6.2. Phát hiện cà phê

Mỗi fold giữ riêng toàn bộ một ngày. Model và scaler được fit trên các ngày còn lại. Báo cáo dùng **balanced accuracy** = trung bình của tỷ lệ bắt đúng cà phê và tỷ lệ nhận đúng nhóm âm. Chỉ số này giúp đánh giá khi mẫu âm nhiều hơn mẫu dương. Kiểm tra riêng ngày 07/11 cho thấy khả năng phát hiện ngoài khoảng ngày train. Với phép thử tối ưu Logistic, vòng trong chọn cấu hình và ngưỡng, vòng ngoài chấm trên ngày được giữ riêng. [Nghiên cứu về kiểm định lồng](https://pubmed.ncbi.nlm.nih.gov/16504092/)

| Phương án | Balanced accuracy trên tập 09–20/11 | Bắt đúng lượt cà phê | Ghi chú |
| --- | ---: | ---: | --- |
| Logistic cũ, BME688 gas và MQ3 #1 | 54,6% | 10/32 | Chạy lại checkpoint cũ để tham chiếu. Phạm vi trùng tập train cũ chưa xác minh. |
| **Logistic V2, ba kênh analog** | **71,8%** | **21/32** | Bản được chọn. Nhận đúng 85/109 lượt âm theo quy ước. |
| Logistic bổ sung đặc trưng đầu/cuối exposure tốt nhất | 71,6% | 20/32 | Trên hardware mang tên người, báo dương 5/13 so với 1/13 của V2. |
| Extra Trees tốt nhất | 59,9% | 14/32 | Ensemble cây chưa vượt Logistic trên dữ liệu này. |
| LDA có shrinkage tốt nhất | 70,2% | 20/32 | Ngày 07/11 bắt được 1/8, bằng V2. |
| SVM RBF tốt nhất | 65,2% | 20/32 | Báo dương 35/109 lượt âm theo quy ước khi kiểm tra khác ngày. |
| Logistic tinh chỉnh bằng kiểm định lồng | 62,3% | 17/32 | Thử 36 cấu hình và 9 ngưỡng. Dùng kết quả vòng ngoài để báo cáo. |
| Logistic học thêm từ cặp cùng ngày | 68,2% | 19/32 | Chưa cải thiện so với V2. |
| CNN 1D ba kênh | 61,9% | 22/32 | Bắt 4/8 ngày 07/11, đồng thời báo dương 49/109 lượt âm theo quy ước. |
| Kết hợp Logistic và CNN | 70,9% | 21/32 | Bản kết hợp được chọn vẫn bắt 1/8 ngày 07/11. |

**Căn cứ chọn Logistic V2.** Bản này đạt 71,8% balanced accuracy, bắt **21/32** lượt cà phê, báo dương **0/16** đối chứng không khí trong kiểm tra theo ngày và **1/13** lượt hardware mang tên người. Accuracy thông thường là **106/141 (75,2%)**, còn recall cà phê là **65,6%**. Balanced accuracy vẫn dưới 75%, và đợt 07/11 chỉ phát hiện **1/8**. Vì vậy có thể trình bày bản demo và đo lường kết quả, còn khả năng nhận diện ổn định qua nhiều đợt đo vẫn cần xác nhận.

[Logistic cũ và V2](models_v2/coffee_sensor_report.json) · [Logistic thêm đặc trưng và Extra Trees](models_v2/coffee_v3_report.json) · [SVM và LDA](models_v2/coffee_ml_report.json) · [Kiểm định lồng](models_v2/coffee_logistic_tuned_report.json) · [Học cặp](models_v2/coffee_pairs_report.json) · [CNN và kết hợp](models_v2/coffee_cnn_report.json)

## 7. Điểm cần nêu khi bảo vệ

1. **Hai tác vụ, hai mục tiêu.** Nhận diện người cần xếp hạng hình dạng mùi giữa nhiều lượt; phát hiện cà phê là phân loại nhị phân. Hai bài toán dùng bộ đặc trưng và tiêu chí đánh giá riêng.
2. **Chọn model bằng dữ liệu khác phiên hoặc khác ngày.** Tách theo ngày hạn chế việc mẫu cùng điều kiện đo rơi vào cả train và test. Báo riêng kết quả chọn cấu hình, kết quả hardware và các tập chỉ có một lớp.
3. **Đánh giá theo ngữ cảnh mẫu.** Một mẫu chỉ mang tên người là nhãn âm quy ước. Muốn đo báo nhầm chắc chắn, cần ghi rõ có hay không có cà phê khi thu. Lượt cà phê riêng và lượt người kèm cà phê cũng nên được báo cáo riêng.
4. **Hướng kiểm chứng tiếp.** Thu xen kẽ cùng người có và không có cà phê trong cùng phiên, thêm đối chứng không khí và mùi dễ nhầm. Giữ riêng các phiên mới để chấm đồng thời recall, tỷ lệ báo nhầm và balanced accuracy.
