# BÁO CÁO XỬ LÝ DỮ LIỆU VÀ THỬ NGHIỆM PHÁT HIỆN MÙI CÀ PHÊ

## 1. Mục tiêu

Mục tiêu của thử nghiệm là xây dựng một pipeline có khả năng nhận biết liệu tín hiệu mùi thu từ một người có mang đặc trưng của cà phê hay không. Đầu vào của hệ thống là file `raw.csv` chứa chuỗi thời gian từ mảng cảm biến khí; đầu ra thuộc một trong các trạng thái:

- `COFFEE_ODOR_LIKELY`: có khả năng có mùi cà phê;
- `NO_COFFEE_ODOR_LIKELY`: có khả năng không có mùi cà phê;
- `UNCERTAIN`: dữ liệu hợp lệ nhưng hai mô hình chưa đủ đồng thuận để kết luận;
- `OUT_OF_DOMAIN`: mẫu nằm ngoài miền dữ liệu đã dùng để huấn luyện;
- `INVALID_MEASUREMENT`: phép đo không đạt yêu cầu chất lượng.

Pipeline hiện tại là một **proof-of-concept**, phục vụ đánh giá phương pháp và xác định vấn đề trong quy trình thu dữ liệu. Kết quả chưa đủ cơ sở để xem là một hệ thống nhận diện mùi cà phê hoàn chỉnh.

## 2. Dữ liệu sử dụng

### 2.1. Cấu trúc một phiên đo

Một phiên đo chuẩn gồm các pha chính:

```text
BASELINE 60 giây → EXPOSURE 120 giây → RECOVERY 60 giây
```

Trong bài toán phát hiện cà phê hiện tại, đặc trưng được trích chủ yếu từ hai pha `BASELINE` và `EXPOSURE`. Pha `BASELINE` dùng làm mức tham chiếu riêng cho từng phiên, giúp giảm ảnh hưởng của sai khác điện áp nền, nhiệt độ cảm biến và độ trôi giữa các lần đo.

Mảng cảm biến gồm năm kênh:

1. BME688 gas resistance;
2. MQ135-1;
3. MQ3-1;
4. MQ135-2;
5. MQ3-2.

### 2.2. Tập huấn luyện

Pipeline tự động thu thập các phiên đã gán nhãn từ các ngày 25, 28 và 29/10/2026. Sau khi qua kiểm tra chất lượng, tập dùng cho đánh giá hiện tại có:

| Lớp | Số phiên |
|---|---:|
| Không có cà phê | 20 |
| Có cà phê | 4 |
| **Tổng** | **24** |

Tập dữ liệu bị mất cân bằng mạnh, đồng thời toàn bộ bốn mẫu dương đều được thu trong ngày 28/10. Đây là hạn chế quan trọng nhất vì mô hình chưa được quan sát mẫu cà phê trên nhiều ngày, nhiều người và nhiều điều kiện môi trường độc lập.

### 2.3. Tập kiểm tra ngày 28/10/2026

Thư mục ngày 28/10 có 17 phiên và 17 file `raw.csv`. Manifest chia dữ liệu thành:

| Nhóm | Vai trò |
|---|---|
| `HUMAN_ONLY` | Người không mang cà phê, nhãn 0 |
| `HUMAN_COFFEE` | Người có mang cà phê, nhãn 1 |
| `AIR` | Không khí, không thuộc bài toán nhị phân trên người |
| `COFFEE_ONLY` | Cà phê riêng, không thuộc bài toán nhị phân trên người |
| `PAIRED` | Baseline và exposure khác điều kiện, không xem là một mẫu nhị phân độc lập |

Trong 17 phiên có 11 phiên được đánh dấu `ELIGIBLE` và có nhãn 0/1, gồm 7 mẫu âm và 4 mẫu dương. Sáu phiên còn lại vẫn được chạy qua hệ thống để tham khảo nhưng không được dùng khi tính accuracy.

Các nhãn trong manifest hiện có trường `label_verification = PROVISIONAL_NAME_ONLY`, nghĩa là phần lớn nhãn được suy ra từ tên phiên. Vì vậy, kết quả đánh giá phải được xem là thăm dò; cần xác nhận nhãn bằng nhật ký thí nghiệm độc lập trong các lần thu tiếp theo.

## 3. Kiểm tra chất lượng dữ liệu

Trước khi trích đặc trưng, pipeline thực hiện quality gate. Một mẫu không đạt sẽ trả về `INVALID_MEASUREMENT` và không được đưa vào mô hình.

### 3.1. Kiểm tra cấu trúc phiên

- File chỉ được chứa một `run_id`;
- phải có đủ pha `BASELINE` và `EXPOSURE`;
- mỗi pha phải là một đoạn liên tục, không bị lặp hoặc tách thành nhiều chu kỳ;
- `phase_elapsed_s` không được quay ngược;
- `BASELINE` phải phủ ít nhất 50 giây;
- `EXPOSURE` phải phủ ít nhất 105 giây;
- khoảng trống lấy mẫu lớn nhất không vượt quá 3 giây.

Các kiểm tra này ngăn việc vô tình ghép nhiều chu kỳ đo vào cùng một file. Nếu hai chu kỳ bị nối với nhau, thời gian pha thường quay về gần 0 và hệ thống sẽ từ chối mẫu.

### 3.2. Kiểm tra từng cảm biến

Một dòng dữ liệu chỉ được xem là hợp lệ khi:

- giá trị cảm biến là số hữu hạn;
- `status = OK`;
- `fresh = true`;
- với MQ, trường `quality` phải rỗng hoặc bằng `OK`;
- với BME688, các cờ `gas_valid`, `heater_stable` và `new_data` đều phải hợp lệ.

Mỗi cảm biến phải có ít nhất 90% số mẫu hợp lệ trong từng pha. Cửa sổ giữa exposure từ giây 40 đến dưới 80 cũng phải có tối thiểu 90% dữ liệu. Cách kiểm tra này tránh trường hợp cảm biến lỗi nhưng vẫn tạo ra một vector đặc trưng có vẻ hợp lệ.

### 3.3. Chống trùng và rò rỉ dữ liệu

Mỗi file được tính SHA-256. Khi kiểm tra một phiên đã có nhãn, pipeline loại khỏi tập train:

- chính đường dẫn của file đang kiểm tra;
- mọi file khác có nội dung SHA-256 giống hệt.

Nếu hai file trùng nội dung nhưng có nhãn khác nhau, pipeline báo lỗi xung đột nhãn. Cơ chế này hạn chế việc một bản sao của mẫu test xuất hiện trong tập train.

## 4. Chuẩn hóa tín hiệu

Với mỗi cảm biến, median của các giá trị hợp lệ trong `BASELINE` được chọn làm mức tham chiếu:

```text
baseline = median(signal trong BASELINE)
```

Tín hiệu trong từng pha được chuyển thành phần trăm thay đổi so với baseline:

```text
response_pct = 100 × (signal - baseline) / |baseline|
```

Ý nghĩa của phép biến đổi:

- giá trị dương: tín hiệu lớn hơn baseline;
- giá trị âm: tín hiệu nhỏ hơn baseline;
- đây là phần trăm thay đổi tương đối, không phải điện áp hay điện trở vật lý âm.

Chuẩn hóa theo baseline riêng của từng phiên giúp giảm sai lệch DC giữa các lần đo. Tuy nhiên, nó không loại bỏ hoàn toàn ảnh hưởng của nhiệt độ, độ ẩm, vị trí đặt mẫu, thời gian làm nóng cảm biến hoặc mùi tồn dư từ phiên trước.

## 5. Trích xuất đặc trưng

Mỗi cảm biến tạo ra năm đặc trưng từ pha `EXPOSURE`:

| Đặc trưng | Ý nghĩa |
|---|---|
| `exposure_mean` | Trung bình toàn bộ exposure |
| `exposure_middle_mean` | Trung bình trong cửa sổ 40–80 giây |
| `q10` | Phân vị 10% của đáp ứng exposure |
| `q90` | Phân vị 90% của đáp ứng exposure |
| `slope_pct_per_min` | Độ dốc tuyến tính theo %/phút |

Với năm cảm biến, mô hình chính sử dụng tổng cộng:

```text
5 cảm biến × 5 đặc trưng = 25 đặc trưng
```

Việc dùng mean, phân vị và slope giúp biểu diễn cả mức đáp ứng, biên độ biến thiên và xu hướng theo thời gian mà không đưa toàn bộ chuỗi thô vào mô hình.

## 6. Mô hình phân loại

### 6.1. Mô hình chính

Mô hình chính là pipeline:

```text
StandardScaler → RBF-SVM
```

Thông số hiện tại:

| Thông số | Giá trị |
|---|---:|
| Kernel | RBF |
| C | 30 |
| Gamma | 0,1 |
| Class weight | Balanced |
| Số đặc trưng | 25 |

`StandardScaler` chỉ được fit trên tập train của từng fold. `class_weight="balanced"` giảm ảnh hưởng của mất cân bằng 20 mẫu âm và 4 mẫu dương.

### 6.2. Mô hình tập trung MQ135/MQ3

Một RBF-SVM phụ chỉ sử dụng hai kênh:

- MQ135-1;
- MQ3-1.

Mô hình phụ có 10 đặc trưng, `C = 10` và `gamma = 0,1`. Mục đích là kiểm tra riêng nhóm cảm biến MQ thay vì để quyết định chỉ phụ thuộc mô hình 25 đặc trưng.

### 6.3. Quy tắc đồng thuận

Phiên bản đang sử dụng là:

```text
coffee-rbf-ensemble-v4-consensus
```

Quy tắc quyết định:

```text
CÓ CÀ PHÊ:
    main_score >= 0,25
    VÀ mq_score >= 0,60

KHÔNG CÓ CÀ PHÊ:
    main_score < 0
    VÀ mq_score < 0

NGƯỢC LẠI:
    UNCERTAIN
```

Quy tắc bất đối xứng được chọn vì số mẫu dương quá ít. Để kết luận có cà phê, hệ thống yêu cầu cả hai mô hình cùng vượt ngưỡng dương tương đối cao. Để kết luận không có cà phê, cả hai mô hình phải cùng nghiêng âm. Nếu hai mô hình trái dấu, hệ thống từ chối kết luận.

So với phiên bản trước, quy tắc đồng thuận âm giúp giảm số mẫu bị từ chối mà không tạo thêm false positive trên tập hiện có.

### 6.4. Phát hiện ngoài miền

Sau khi chuẩn hóa bằng scaler của tập train, khoảng cách RMS từ mẫu test đến mẫu train gần nhất được tính trong không gian đặc trưng. Ngưỡng ngoài miền được ước lượng từ phân vị 95% của khoảng cách láng giềng gần nhất trong tập train, nhân hệ số 1,5. Mẫu cũng bị đánh dấu ngoài miền nếu có đặc trưng chuẩn hóa với trị tuyệt đối lớn hơn 5.

Nếu không đạt kiểm tra này, hệ thống trả `OUT_OF_DOMAIN` thay vì ép thành có hoặc không có cà phê.

## 7. Phương pháp đánh giá

### 7.1. Leave-one-out

Với mỗi phiên có nhãn:

1. loại phiên đó và mọi bản sao trùng nội dung khỏi tập train;
2. fit lại scaler và hai RBF-SVM trên các phiên còn lại;
3. tính lại miền dữ liệu từ tập train của fold;
4. dự đoán phiên bị loại;
5. lặp lại cho tất cả các phiên.

Cách đánh giá này hạn chế việc mô hình nhìn thấy chính mẫu đang kiểm tra. Tuy nhiên, do chỉ có bốn mẫu dương và tất cả thuộc cùng một ngày, kết quả vẫn có độ không chắc chắn cao.

### 7.2. Các chỉ số có vùng từ chối

Vì hệ thống có `UNCERTAIN` và `OUT_OF_DOMAIN`, không nên chỉ báo cáo một con số accuracy. Báo cáo sử dụng:

- **Coverage**: tỷ lệ mẫu được hệ thống đưa ra kết luận có/không;
- **Accuracy khi có kết luận**: tỷ lệ đúng trong các mẫu mà hệ thống đã kết luận;
- **Đúng trên toàn bộ eligible**: số dự đoán đúng chia cho toàn bộ mẫu hợp lệ, xem mẫu từ chối là chưa giải quyết;
- số mẫu dương phát hiện được;
- số false negative;
- số false positive.

## 8. Kết quả trên dữ liệu ngày 28/10/2026

### 8.1. Ma trận kết quả có vùng từ chối

| Nhãn thật | Dự đoán CÓ | Dự đoán KHÔNG | Từ chối | Tổng |
|---|---:|---:|---:|---:|
| Có cà phê | 1 | 2 | 1 | 4 |
| Không cà phê | 0 | 4 | 3 | 7 |
| **Tổng** | **1** | **6** | **4** | **11** |

### 8.2. Chỉ số tổng hợp

| Chỉ số | Kết quả |
|---|---:|
| Tổng mẫu eligible | 11 |
| Số mẫu được kết luận | 7 |
| Số kết luận đúng | 5 |
| Số kết luận sai | 2 |
| Số mẫu từ chối | 4 |
| Coverage | 63,6% |
| Accuracy khi có kết luận | 71,4% |
| Đúng trên toàn bộ eligible | 45,5% |
| Phát hiện mẫu có cà phê | 1/4 = 25% |
| False negative | 2/4 = 50% |
| False positive | 0/7 = 0% |

Kết quả cho thấy hệ thống đang ưu tiên hạn chế báo nhầm có cà phê. Không có mẫu âm nào bị kết luận là có cà phê, nhưng khả năng phát hiện mẫu dương còn thấp.

### 8.3. Các mẫu bị từ chối

Bốn mẫu còn `UNCERTAIN` đều có hai mô hình không đồng thuận:

| Phiên | Nhãn | Main | MQ | Nhận xét |
|---|---:|---:|---:|---|
| `Tai_133044` | 0 | +0,303 | -0,556 | Main nghiêng dương, MQ nghiêng âm |
| `TaivsCF_140100` | 1 | -0,379 | +0,350 | Main nghiêng âm, MQ nghiêng dương |
| `aMinh_220050` | 0 | -0,629 | +0,470 | Main nghiêng âm, MQ nghiêng dương |
| `Tai_221033` | 0 | -0,344 | +0,326 | Main nghiêng âm, MQ nghiêng dương |

Trước khi áp dụng quy tắc đồng thuận v4, phiên âm `Tai_132052` cũng bị từ chối. Hai score của phiên này đều âm (`main = -0,006`, `MQ = -0,203`), nên v4 đã chuyển nó thành kết luận KHÔNG và kết quả đúng. Bốn mẫu trong bảng vẫn không thể được giải quyết an toàn chỉ bằng cách đổi dấu hoặc hạ một ngưỡng, vì mẫu dương `TaivsCF_140100` có cùng kiểu bất đồng với hai mẫu âm buổi tối.

### 8.4. Hai mẫu dương bị phân loại sai

Hai phiên sau bị cả hai mô hình kết luận mạnh về phía âm:

| Phiên | Main | MQ | Kết quả |
|---|---:|---:|---|
| `TaivsCF_nhieu_225757` | -1,336 | -2,289 | Sai: dự đoán KHÔNG |
| `TaivsCF_it_230521` | -1,734 | -1,875 | Sai: dự đoán KHÔNG |

Đây không phải lỗi chỉ do ngưỡng. Trong không gian 25 đặc trưng và không gian MQ135/MQ3, hai mẫu này đều giống lớp âm hơn các mẫu dương đã học.

Một dấu hiệu cần kiểm tra trong quy trình thí nghiệm là phiên `CF_nhieu_225145` ngay trước đó được mô hình nhận là có cà phê rất mạnh (`main = +0,780`, `MQ = +1,263`), nhưng phiên người mang cà phê mức nhiều lúc 22:57 lại chuyển sang rất âm. Điều này có thể liên quan đến:

- mùi cà phê chưa thực sự đi vào luồng khí khi đo trên người;
- vị trí, khoảng cách hoặc hướng đặt mẫu thay đổi;
- baseline bị nhiễm mùi từ phiên trước;
- cảm biến chưa recovery đủ;
- điều kiện nhiệt độ, độ ẩm hoặc lưu lượng khí thay đổi;
- nhãn tên phiên đúng về thao tác nhưng không phản ánh nồng độ mùi thực tế tại buồng đo.

## 9. Vì sao chưa dùng PCA hoặc 1D-CNN làm mô hình chính

### 9.1. PCA

PCA phù hợp để trực quan hóa và giảm chiều, nhưng là phương pháp không giám sát: nó giữ các hướng có phương sai lớn nhất chứ không đảm bảo giữ hướng phân biệt cà phê. Với chỉ bốn mẫu dương, việc chọn số thành phần PCA dễ phụ thuộc mạnh vào một vài phiên. Vì vậy PCA nên được dùng để khảo sát cụm và phát hiện ngoại lệ, chưa nên dùng làm bước bắt buộc của classifier hiện tại.

### 9.2. 1D-CNN

1D-CNN có thể học trực tiếp hình dạng chuỗi thời gian, nhưng số mẫu hiện quá nhỏ:

- chỉ có 24 phiên hợp lệ;
- chỉ có 4 phiên dương;
- toàn bộ phiên dương thuộc cùng một ngày và chủ yếu cùng một người;
- các điểm thời gian trong cùng phiên không phải các mẫu độc lập.

Nếu cắt một phiên thành nhiều cửa sổ rồi chia ngẫu nhiên train/test, các cửa sổ từ cùng một phép đo có thể xuất hiện ở cả hai phía và tạo accuracy ảo. CNN chỉ phù hợp sau khi có thêm nhiều phiên dương độc lập và chia dữ liệu theo `session_id`, người và ngày.

RBF-SVM trên đặc trưng tóm tắt được chọn vì phù hợp hơn với tập nhỏ, vẫn biểu diễn quan hệ phi tuyến và dễ kiểm soát rò rỉ dữ liệu hơn.

## 10. Hạn chế

1. Chỉ có bốn mẫu dương, không đủ đại diện cho biến thiên thực tế.
2. Các mẫu dương đều thuộc ngày 28/10 và chủ yếu từ một người.
3. Nhãn hiện được suy ra từ tên phiên, chưa có xác nhận độc lập bằng nhật ký thao tác hoặc nồng độ chuẩn.
4. Dữ liệu âm nhiều hơn dữ liệu dương năm lần.
5. Hai mẫu dương buổi tối có đặc trưng đảo chiều so với mẫu dương buổi chiều.
6. Ngưỡng được lựa chọn thăm dò trên tập nhỏ, chưa có validation set độc lập.
7. `COFFEE_ONLY`, `AIR` và `PAIRED` khác miền bài toán “cà phê trên người”, nên không được dùng trực tiếp để tính accuracy nhị phân.
8. Kết quả leave-one-out vẫn có thể lạc quan nếu các phiên gần nhau chịu cùng điều kiện môi trường hoặc cùng một lần chuẩn bị mẫu.

## 11. Hướng cải tiến đề xuất

### 11.1. Ưu tiên cải thiện dữ liệu

- Thu tối thiểu 20–30 phiên dương và 20–30 phiên âm độc lập;
- thu trên ít nhất 3–5 ngày và nhiều người;
- mỗi người cần có cả phiên có cà phê và không cà phê;
- xáo trộn thứ tự đo âm/dương để tránh thời gian trong ngày trở thành đặc trưng ngầm;
- ghi rõ `session_id`, `person_id`, loại cà phê, khối lượng, khoảng cách, thời gian đặt mẫu và người thao tác;
- dùng mã nhãn được ghi trước khi chạy, không suy nhãn từ tên thư mục sau thí nghiệm;
- thêm một mẫu chuẩn coffee-only trước và sau mỗi nhóm đo để kiểm tra độ nhạy cảm biến;
- quy định thời gian recovery hoặc điều kiện trở về baseline trước phiên tiếp theo.

### 11.2. Cải thiện feature sau khi có thêm dữ liệu

- mean ở các cửa sổ 0–20, 20–40, 40–80, 80–120 giây;
- initial slope và late slope;
- peak amplitude và thời gian đạt peak;
- diện tích dưới đường đáp ứng;
- độ lệch early–late;
- đặc trưng recovery như thời gian trở về 50% và 90%;
- nhiệt độ, độ ẩm và áp suất dưới dạng biến hiệu chỉnh hoặc điều kiện miền.

Các feature mới phải được lựa chọn trong tập train của từng fold; không chọn feature bằng toàn bộ dữ liệu rồi mới đánh giá.

### 11.3. Cải thiện mô hình

Sau khi dữ liệu đủ lớn, nên so sánh trên cùng một cách chia theo session/ngày/người:

1. Logistic Regression có regularization;
2. Linear SVM;
3. RBF-SVM;
4. Random Forest hoặc Extra Trees;
5. XGBoost/LightGBM nếu số phiên đủ lớn;
6. 1D-CNN hoặc temporal convolution khi có đủ chuỗi độc lập.

Ngưỡng quyết định phải được chọn bằng validation nội bộ trong tập train, sau đó mới đánh giá một lần trên test độc lập.

## 12. Kết luận

Pipeline hiện tại đã thực hiện đầy đủ các bước: kiểm tra chất lượng, chống trùng dữ liệu, chuẩn hóa theo baseline, trích 25 đặc trưng, chuẩn hóa z-score, phân loại bằng hai RBF-SVM, phát hiện ngoài miền và đưa ra vùng từ chối.

Trên 11 mẫu có nhãn ngày 28/10, hệ thống đạt coverage 63,6% và accuracy 71,4% trong các trường hợp dám kết luận. Không có false positive trên bảy mẫu âm, nhưng chỉ phát hiện được một trong bốn mẫu dương. Do đó, ưu điểm hiện tại là tính thận trọng; nhược điểm chính là độ nhạy với cà phê còn thấp.

Kết quả cho thấy nút thắt lớn nhất chưa nằm ở việc chọn thêm một thuật toán phức tạp, mà nằm ở số lượng, độ đa dạng và độ tin cậy của dữ liệu dương. Việc ưu tiên chuẩn hóa quy trình thu mẫu và bổ sung các phiên dương độc lập sẽ có giá trị hơn việc tiếp tục hạ ngưỡng hoặc chuyển ngay sang 1D-CNN.

## 13. Tệp chương trình và kết quả

| Tệp | Vai trò |
|---|---|
| `analysis/check_coffee_odor.py` | Kiểm tra một file `raw.csv` |
| `analysis/test_all_coffee_odor.py` | Chạy toàn bộ phiên trong một thư mục ngày |
| `data/2026-10-28/label_manifest.csv` | Manifest và nhãn ngày 28/10 |
| `data/2026-10-28/coffee_odor_batch_test/coffee_odor_batch_results.csv` | Kết quả batch dạng bảng |
| `data/2026-10-28/coffee_odor_batch_test/coffee_odor_batch_results.json` | Kết quả batch đầy đủ |

Lệnh chạy lại:

```powershell
python analysis\test_all_coffee_odor.py
```
