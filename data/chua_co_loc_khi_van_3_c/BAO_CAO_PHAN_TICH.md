# Báo cáo phân tích lô dữ liệu `chua_co_loc_khi_van_3_c`

## 1. Kết luận ngắn

Lô dữ liệu này cho thấy hệ thống **đã ghi nhận được sự thay đổi tín hiệu khi đo**, dữ liệu gần như đầy đủ và các pha đo được lưu đúng cấu trúc. Tuy nhiên, với số mẫu hiện tại, **chưa thể kết luận hệ thống nhận diện người ổn định chỉ dựa vào mùi**.

Kết quả quan trọng nhất:

- Có **22 thư mục**, gồm **16 lần đo chính** mang tên bằng chữ và **6 thư mục số** là phiên chạy/warm-up.
- Các dòng trong 16 lần đo chính đã xuất hiện lại trong file `raw.csv` của thư mục phiên tương ứng. Vì vậy, 6 thư mục số **không được tính là mẫu độc lập**.
- Có 4 người đã xác định: Dũng, Minh, Quy, Tài; ngoài ra có một mẫu `hihi` chưa rõ nhãn.
- Tổng cộng có 10.478 dòng trong 16 thư mục đo chính. Phần chuẩn hóa giống nhau giữa các run gồm 60 mẫu baseline, 120 mẫu exposure và 60 mẫu recovery, tức **240 mẫu/run và 3.840 mẫu lõi**.
- Tỷ lệ dữ liệu cảm biến hợp lệ thấp nhất vẫn đạt **99,80%**; không phát hiện file JSON/CSV/PNG bị thiếu hoặc hỏng.
- Khi chỉ so sánh điều kiện tương đối đồng nhất `bụng – không áo – bình thường`, còn **8 run của Minh, Quy và Tài**. Mô hình tốt nhất đúng **5/8 run (62,5%)**, balanced accuracy **61,1%**, cao hơn mức ngẫu nhiên 3 lớp khoảng 33,3% nhưng tập kiểm tra quá nhỏ.
- Khoảng cách fingerprint trung vị của các mẫu cùng người là **5,12**, khác người là **5,71**, chỉ cách nhau khoảng **11,6%** và còn chồng lấn nhiều.
- Cảm biến **MQ135 là vấn đề chính**: 8/16 run có cảnh báo trôi baseline và 10/16 run chưa hồi phục về nền. Baseline CV của MQ135 có trung vị 25,87% và cao nhất 47,16%, trong khi BME688 và MQ3 ổn định hơn nhiều.

**Đánh giá khả thi hiện tại:** có tín hiệu ban đầu cho bài toán phân biệt mùi/người, nhưng bằng chứng còn yếu và bị ảnh hưởng bởi phiên đo, thời gian, vị trí, áo và độ trôi cảm biến. Chưa nên công bố độ chính xác nhận diện người từ lô này.

---

## 2. Cách đọc và tổ chức dữ liệu

Theo quy ước của đợt thu:

- Thư mục mang tên bằng chữ là một lần đo chính, ví dụ `Tai_bung_khongao_...`.
- Thư mục chỉ có thời gian và mã UUID là phiên chạy/warm-up.
- Tên thư mục chính được tách thành: **người → vị trí đo → có/không áo → thời gian đo**.
- `aDung_moitamxonggg_...` là trường hợp vừa tắm xong nên không có vị trí đo.
- `hihi_...` chưa chứa đủ thông tin để gán người, vị trí và tình trạng áo, do đó chỉ được giữ như một mẫu chưa rõ nhãn.

Phân bố 16 run chính:

| Người/nhãn | Số run | Điều kiện có trong dữ liệu |
|---|---:|---|
| Tài | 5 | Ngực có áo, ngực không áo, bụng không áo × 3 |
| Minh | 4 | Ngực không áo × 2, bụng không áo × 2 |
| Quy | 4 | Ngực không áo, bụng không áo × 3 |
| Dũng | 2 | Đầu gối, vừa tắm xong không ghi vị trí |
| `hihi` | 1 | Chưa rõ người/vị trí/áo |

### Biểu đồ 1 – Thiết kế và phân bố lần đo

![Thiết kế thu dữ liệu](report_outputs/figures/01_dataset_design.png)

**Phương pháp:** sắp xếp 16 run theo thời gian bắt đầu, sau đó đếm số run theo người, vị trí đo và tình trạng áo.

**Kết quả:** dữ liệu không cân bằng. Tài có 5 run, Minh và Quy có 4 run, Dũng chỉ có 2 run với điều kiện khác hẳn. Dữ liệu bụng–không áo tập trung ở Minh, Quy và Tài; đây là nhóm duy nhất đủ gần nhau về điều kiện để thử phân tích nhận diện người.

**Ý nghĩa:** không thể đưa toàn bộ 16 run vào một phép so sánh người với người rồi coi kết quả là do mùi cá nhân, vì mô hình có thể học nhầm vị trí đo, áo, ngày đo hoặc điều kiện vừa tắm.

---

## 3. Phương pháp phân tích

Quy trình sử dụng trong báo cáo:

1. Kiểm tra đủ 6 file chuẩn trong từng thư mục: `metadata.json`, `summary.json`, `raw.csv`, `events.csv`, `signals.png`, `normalized.png`.
2. Tách thư mục đo chính khỏi thư mục số dùng cho warm-up/phiên đo.
3. Đối chiếu timestamp và phát hiện 100% dòng của mỗi run chính đã được lưu lặp trong thư mục phiên; loại phần lặp khỏi số mẫu độc lập.
4. Chỉ giữ giá trị cảm biến có cờ trạng thái hợp lệ.
5. Với từng run và từng cảm biến, lấy trung vị pha baseline làm mốc rồi chuẩn hóa:

   `response (%) = 100 × (giá trị / baseline_median - 1)`

6. Trích xuất 5 đặc trưng động học cho mỗi cảm biến: trung bình exposure, trung bình 20 giây cuối exposure, cực tiểu, cực đại và hệ số dốc. Ba cảm biến tạo thành 15 đặc trưng.
7. Dùng PCA để quan sát cấu trúc dữ liệu; dùng khoảng cách Euclid sau chuẩn hóa z-score để so sánh fingerprint cùng người/khác người.
8. Thử nhận diện người bằng 1-NN và nearest centroid. Đánh giá theo **leave-one-session-out**: giữ toàn bộ một phiên làm test và chỉ huấn luyện bằng các phiên còn lại, tránh việc các mẫu cùng phiên xuất hiện ở cả train lẫn test.

---

## 4. Phân tích toàn bộ 16 run

### Biểu đồ 2 – Đường đáp ứng của ba cảm biến

![Đường tín hiệu toàn bộ run](report_outputs/figures/02_all_signal_traces.png)

**Phương pháp:** căn thẳng tất cả run theo thời gian; 0–120 giây là exposure, 120–180 giây là recovery. Mỗi đường đã được đưa về phần trăm thay đổi so với baseline riêng của run đó.

**Kết quả:** BME688 và MQ3 có biên độ nhìn chung gọn hơn. MQ135 dao động rất lớn giữa các run, nhiều đường không quay về mức 0% sau recovery và có biên độ lớn hơn hẳn hai cảm biến còn lại.

**Ý nghĩa:** các run thật sự tạo ra đáp ứng động theo thời gian, nhưng riêng MQ135 đang mang nhiều thành phần trôi/nhiễu. Nếu dùng trực tiếp đường MQ135 để phân loại, mô hình rất dễ học trạng thái phiên đo thay vì mùi.

### Biểu đồ 3 – Heatmap đáp ứng exposure và recovery

![Heatmap đáp ứng](report_outputs/figures/03_response_heatmap.png)

**Phương pháp:** với mỗi run, tính đáp ứng trung bình trong 120 giây exposure và mức tín hiệu trung bình ở 10 giây cuối recovery cho BME688, MQ135 và MQ3.

**Kết quả:**

- Trung bình exposure của BME688 nằm trong khoảng **-2,98% đến +4,25%**, trung vị **-0,76%**.
- MQ135 trải rất rộng, từ **-22,26% đến +16,82%**, trung vị chỉ **+0,09%**.
- MQ3 nằm trong khoảng **-7,85% đến +3,20%**, trung vị **+0,26%**.
- Màu của cùng một người chưa lặp lại thành mẫu ổn định giữa các phiên, rõ nhất ở MQ135.

**Ý nghĩa:** dữ liệu có độ tương phản giữa các run, nhưng độ tương phản lớn chưa đồng nghĩa với đặc trưng người. Ví dụ MQ135 thay đổi rất mạnh nhưng phần lớn đi kèm độ trôi baseline và hồi phục kém.

### Biểu đồ 4 – Chất lượng baseline và khả năng hồi phục

![Kiểm soát chất lượng](report_outputs/figures/04_quality_control.png)

**Phương pháp:** dùng hệ số biến thiên `CV = độ lệch chuẩn / giá trị trung bình` để đo độ ổn định baseline; đồng thời đo phần trăm lệch khỏi baseline ở cuối recovery.

**Kết quả:**

| Cảm biến | Baseline CV nhỏ nhất | Trung vị | Lớn nhất |
|---|---:|---:|---:|
| BME688 | 0,21% | 0,33% | 0,86% |
| MQ135 | 0,38% | 25,87% | 47,16% |
| MQ3 | 0,10% | 0,19% | 0,35% |

MQ135 có 8 run bị cảnh báo baseline drift và 10 run chưa hồi phục về nền. Một số run bụng ngày 14–15/10 có baseline CV của MQ135 khoảng 25–47%. Trong khi đó, BME688 và MQ3 ổn định hơn rõ rệt.

**Ý nghĩa:** chỉ số `baseline_stable` chung trong metadata vẫn có thể là `true`, nhưng kiểm tra riêng từng cảm biến cho thấy MQ135 không ổn định. Cần kiểm tra tiêu chí tạo cờ ổn định trong code thu dữ liệu và không nên dựa hoàn toàn vào cờ chung này.

### Biểu đồ 5 – Trôi theo thời gian và môi trường nền

![Trôi theo thời gian](report_outputs/figures/05_temporal_drift.png)

**Phương pháp:** biểu diễn nhiệt độ, độ ẩm, áp suất baseline và đáp ứng trung bình của ba cảm biến theo thời điểm thu.

**Kết quả:** điều kiện nền thay đổi đáng kể giữa các phiên:

- Nhiệt độ baseline: **32,57–34,67°C**.
- Độ ẩm baseline: **55,01–68,02%**.
- Áp suất baseline: **1.010,83–1.013,49 hPa**.

Đáp ứng MQ135 cũng đổi mạnh theo thời gian, đặc biệt ở các phiên muộn. Các lần đo của cùng người ở hai buổi khác nhau chưa giữ được cùng một mức đáp ứng.

**Ý nghĩa:** ngày/giờ và trạng thái cảm biến là biến gây nhiễu đáng kể. Chuẩn hóa theo baseline từng run giúp giảm độ lệch mức DC nhưng chưa loại được sự thay đổi hình dạng đáp ứng và độ trôi theo phiên.

### Biểu đồ 6 – PCA trên toàn bộ run

![PCA toàn bộ run](report_outputs/figures/06_pca_all_runs.png)

**Phương pháp:** chuẩn hóa z-score 15 đặc trưng động học rồi giảm còn 2 chiều bằng PCA. PC1 giải thích **45,7%**, PC2 giải thích **25,7%**, tổng cộng **71,4%** phương sai.

**Kết quả:** các điểm không tạo thành cụm riêng rõ ràng theo người. Mẫu `hihi` và một số run khác điều kiện nằm xa phần còn lại; vị trí đo và phiên đo có ảnh hưởng trực quan lớn.

**Ý nghĩa:** PCA toàn bộ dữ liệu chỉ dùng để mô tả. Không thể xem khoảng cách trên biểu đồ này là bằng chứng nhận diện người vì các điều kiện thu chưa được kiểm soát đồng đều.

---

## 5. Phân tích subset kiểm soát để thử nhận diện người

Subset được chọn gồm các run thỏa cả ba điều kiện:

- Đo ở bụng.
- Không áo.
- Điều kiện bình thường, không phải vừa tắm.

Subset có 8 run: Quy 3, Tài 3 và Minh 2, thuộc 3 phiên S4, S5 và S6.

### Biểu đồ 7 – Đáp ứng trung bình trong subset kiểm soát

![Đáp ứng subset kiểm soát](report_outputs/figures/07_controlled_mean_responses.png)

**Phương pháp:** so sánh đáp ứng exposure trung bình của từng cảm biến, đồng thời giữ ký hiệu phiên đo để nhìn ảnh hưởng giữa các buổi.

**Kết quả:**

- BME688 của cả ba người chủ yếu nằm phía âm và khá gần nhau; không có ranh giới người rõ.
- MQ3 của Minh cao hơn ở hai run bụng (**2,37% và 3,20%**) so với phần lớn run của Quy và Tài, tạo ra một dấu hiệu có thể nghiên cứu thêm.
- MQ135 của cùng một người thay đổi rất mạnh theo phiên. Ví dụ Minh từ **-4,65%** ở S5 lên **+12,90%** ở S6; Quy từ **+10,48%** ở S4 xuống gần 0 hoặc âm ở S5–S6.

**Ý nghĩa:** MQ3 đang cho tín hiệu cá nhân đáng chú ý hơn trong subset này, nhưng mới chỉ có hai mẫu Minh. MQ135 thể hiện ảnh hưởng phiên lớn hơn ảnh hưởng người.

### Biểu đồ 8 – PCA của subset kiểm soát

![PCA subset kiểm soát](report_outputs/figures/08_controlled_pca.png)

**Phương pháp:** PCA trên 15 đặc trưng của 8 run bụng–không áo. PC1 giải thích **36,8%**, PC2 giải thích **30,4%**, tổng cộng **67,2%** phương sai.

**Kết quả:** các điểm cùng người chưa gom thành cụm kín; một số điểm khác người gần nhau hơn các điểm cùng người. Hình dạng marker theo phiên cũng cho thấy hiệu ứng phiên vẫn còn.

**Ý nghĩa:** chưa có fingerprint hình học tách biệt bền vững cho từng người. Nếu tăng dữ liệu mà các cụm vẫn phân theo phiên thay vì theo người, phải ưu tiên hiệu chỉnh cảm biến và quy trình thu trước khi tăng độ phức tạp mô hình.

### Biểu đồ 9 – Khoảng cách fingerprint cùng người và khác người

![Khoảng cách fingerprint](report_outputs/figures/09_controlled_distances.png)

**Phương pháp:** chuẩn hóa 15 đặc trưng rồi tính khoảng cách Euclid cho mọi cặp run. Chia cặp thành cùng người và khác người; màu điểm cho biết hai run có cùng phiên hay không.

**Kết quả:**

- Trung vị khoảng cách cùng người: **5,12**.
- Trung vị khoảng cách khác người: **5,71**.
- Tỷ lệ tách biệt: **5,71 / 5,12 = 1,12**.

Hai phân bố chồng lấn mạnh. Khoảng cách khác người chỉ lớn hơn cùng người khoảng 11,6% ở trung vị.

**Ý nghĩa:** tồn tại một xu hướng đúng hướng nhưng còn yếu. Một fingerprint tốt cần các lần đo cùng người gần nhau rõ rệt và các người khác nhau xa nhau rõ rệt; lô này chưa đạt điều đó.

### Biểu đồ 10 – Kết quả nhận diện người theo phiên chưa thấy

![So sánh mô hình](report_outputs/figures/10_controlled_classification.png)

**Phương pháp:** thử hai mô hình đơn giản là 1-NN và nearest centroid trên bốn nhóm đặc trưng:

- 5 đặc trưng BME688.
- 10 đặc trưng MQ135 + MQ3.
- Toàn bộ 15 đặc trưng động học.
- Chỉ 3 giá trị mean exposure.

Mỗi lượt giữ hẳn một phiên làm test; scaler, median điền thiếu và tâm lớp đều chỉ được học từ các phiên train.

**Kết quả:**

| Đặc trưng | Mô hình | Đúng | Balanced accuracy |
|---|---|---:|---:|
| BME688 (5) | 1-NN | 3/8 | 33,3% |
| BME688 (5) | Nearest centroid | 2/8 | 22,2% |
| MQ135 + MQ3 (10) | 1-NN | 3/8 | 33,3% |
| MQ135 + MQ3 (10) | Nearest centroid | 3/8 | 33,3% |
| Tất cả động học (15) | 1-NN | 3/8 | 33,3% |
| Tất cả động học (15) | Nearest centroid | 2/8 | 22,2% |
| Chỉ mean (3) | 1-NN | 3/8 | 33,3% |
| **Chỉ mean (3)** | **Nearest centroid** | **5/8** | **61,1%** |

Mô hình tốt nhất có accuracy 62,5%, balanced accuracy 61,1% và macro-F1 58,6%.

**Ý nghĩa:** kết quả 5/8 cho thấy tín hiệu có thể chứa thông tin về người, nhưng các đặc trưng động học nhiều hơn lại không cải thiện khả năng tổng quát. Điều này thường xảy ra khi số mẫu quá ít hoặc đặc trưng đang học nhiễu. Không nên chọn mô hình tốt nhất rồi coi 62,5% là độ chính xác thật của hệ thống.

### Biểu đồ 11 – Ma trận nhầm lẫn của mô hình tốt nhất

![Ma trận nhầm lẫn](report_outputs/figures/11_controlled_confusion.png)

**Phương pháp:** tổng hợp dự đoán từ ba lượt leave-one-session-out của nearest centroid dùng ba mean exposure.

**Kết quả:**

- Tài: đúng 3/3 run.
- Minh: đúng 1/2 run; một run bị nhầm thành Quy.
- Quy: đúng 1/3 run; hai run bị nhầm lần lượt thành Minh và Tài.

**Ý nghĩa:** phần lớn kết quả tốt hiện tại đến từ việc nhận đúng Tài. Dữ liệu chưa chứng minh mô hình nhận đồng đều cả ba người. Với Minh chỉ có hai lần đo, một lần sai đã làm thay đổi kết quả rất lớn.

---

## 6. Các run đặc biệt

### Biểu đồ 12 – Mẫu chưa đủ điều kiện đối chứng

![Các run đặc biệt](report_outputs/figures/12_special_runs.png)

**Phương pháp:** tách riêng các run không cùng điều kiện với subset chính: `hihi`, Dũng–đầu gối, Tài–ngực–có áo và Dũng–vừa tắm xong.

**Kết quả:**

| Run | BME688 mean | MQ135 mean | MQ3 mean |
|---|---:|---:|---:|
| `hihi` chưa rõ nhãn | +4,25% | +0,04% | -0,35% |
| Dũng – đầu gối | -2,13% | -0,35% | -0,11% |
| Tài – ngực – có áo | -1,18% | +0,17% | -0,05% |
| Dũng – vừa tắm xong | +0,73% | +16,82% | +0,65% |

Mẫu vừa tắm có MQ135 tăng mạnh, nhưng baseline CV của MQ135 ở run này lên tới **47,16%**. Vì chỉ có một mẫu sau tắm và không có mẫu trước tắm cùng người, cùng vị trí, cùng phiên, chưa thể nói mức tăng đó là do vừa tắm.

Tương tự, chỉ có một run Tài mặc áo và run đối chiếu không áo không được thu cặp ngay cùng phiên, nên chưa tách được ảnh hưởng của áo.

---

## 7. Trả lời câu hỏi nghiên cứu

### Có tìm được đặc trưng của người dựa vào mùi không?

**Có dấu hiệu ban đầu nhưng chưa đủ mạnh để khẳng định.** Ba mean exposure cho kết quả 5/8 khi kiểm tra theo phiên chưa thấy, và khoảng cách khác người lớn hơn cùng người khoảng 11,6%. Tuy vậy, PCA chưa tạo cụm người rõ, phân bố khoảng cách còn chồng lấn và MQ135 bị trôi mạnh.

### Có phân biệt được mùi A với mùi B không?

Lô này chưa có nhãn A/B độc lập; tên người hiện đang đóng vai trò nhãn lớp. Vì vậy, báo cáo chỉ thử bài toán phân biệt Minh–Quy–Tài trong một điều kiện tương đối giống nhau. Muốn kết luận phân biệt mùi A/B, cần thu nhiều lần lặp cho A và B trong cùng quy trình, luân phiên thứ tự đo và có mẫu blank giữa các lần.

### Lô dữ liệu có dùng được không?

**Dùng được cho thăm dò, kiểm tra pipeline và phát hiện lỗi quy trình; chưa đủ để huấn luyện mô hình cuối.** BME688 và MQ3 có chất lượng baseline tốt. MQ135 cần được xử lý trước khi tin vào các đặc trưng của nó.

---

## 8. Đề xuất cho đợt thu tiếp theo

1. Chọn một cấu hình cố định, ví dụ `bụng – không áo – khoảng cách đầu dò cố định`, áp dụng cho mọi người.
2. Thu tối thiểu **10–20 run/người**, trải trên ít nhất 5 ngày; mỗi ngày mỗi người nên có từ 2 run trở lên.
3. Xáo trộn thứ tự người trong từng phiên để không làm nhãn người trùng với thời gian đo.
4. Giữa hai run cần có blank/recovery cho đến khi cả ba cảm biến về gần baseline; đặt ngưỡng tự động, ví dụ lệch dưới 3–5% trong một khoảng liên tục.
5. Theo dõi baseline CV riêng từng cảm biến. Nếu MQ135 vượt ngưỡng thì không bắt đầu run hoặc gắn cờ loại mẫu.
6. Ghi rõ các biến phụ: vừa tắm, xà phòng/nước hoa, ăn uống, vận động, nhiệt độ/độ ẩm, khoảng cách và thời gian kể từ lần đo trước.
7. Thu các cặp đối chứng riêng cho áo/không áo và trước/sau tắm; mỗi cặp phải cùng người, cùng vị trí và gần nhau về thời gian.
8. Khi đánh giá mô hình, tiếp tục chia train/test theo **ngày hoặc phiên**, không chia ngẫu nhiên từng dòng tín hiệu.

---

## 9. Tệp kết quả và khả năng tái tạo

- Script phân tích: [`../../analysis/analyze_new_batch.py`](../../analysis/analyze_new_batch.py)
- Tóm tắt máy đọc: [`report_outputs/summary.json`](report_outputs/summary.json)
- Danh sách 16 run: [`report_outputs/tables/run_manifest.csv`](report_outputs/tables/run_manifest.csv)
- Chỉ số chất lượng: [`report_outputs/tables/run_quality.csv`](report_outputs/tables/run_quality.csv)
- Đặc trưng từng run: [`report_outputs/tables/run_features.csv`](report_outputs/tables/run_features.csv)
- Subset kiểm soát: [`report_outputs/tables/controlled_subset.csv`](report_outputs/tables/controlled_subset.csv)
- Điểm các mô hình: [`report_outputs/tables/controlled_scores.csv`](report_outputs/tables/controlled_scores.csv)
- Dự đoán từng run: [`report_outputs/tables/controlled_predictions.csv`](report_outputs/tables/controlled_predictions.csv)

Chạy lại toàn bộ phân tích từ thư mục gốc dự án:

```powershell
python analysis/analyze_new_batch.py
```
