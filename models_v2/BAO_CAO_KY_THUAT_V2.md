# Báo cáo kỹ thuật ResCNN64 V2

**Trạng thái ngày 27/11/2026** · Bản đang dùng ở mục 04 là `v2-grouped`.

## 1. Phạm vi thay đổi so với model gốc

`models/` chứa ResCNN64 gốc cùng trọng số, tham số chuẩn hóa và kho embedding tham chiếu. `models_v2/` bổ sung bộ hiệu chỉnh exposure dựa trên toàn bộ baseline. Bộ hiệu chỉnh có checkpoint riêng, đặt trước ResCNN64 khi chọn V2 trong dashboard. Cả hai đường chạy tạo embedding 64 chiều và xếp hạng theo cosine.

| Thành phần | `models/` · ResCNN64 gốc | `models_v2/` · `v2-grouped` |
| --- | --- | --- |
| Kiểm tra và chuẩn hóa dữ liệu | Kiểm tra schema, cấu hình, timing và cờ tín hiệu. Dùng trung vị 30 điểm cuối baseline để tạo tensor exposure rồi chuẩn hóa theo artifact. | Dùng lại toàn bộ quy trình này và đọc thêm 60 điểm baseline để tạo đầu vào cho bộ hiệu chỉnh. |
| Xử lý exposure | Chuyển tensor đã chuẩn hóa thẳng vào CNN. | Mạng nhỏ học mức bù và độ dốc cho từng kênh, áp dụng trên tensor đã chuẩn hóa trước khi qua CNN. |
| Trọng số | `model.pt` của ResCNN64 gốc, báo cáo ghi 77 lượt huấn luyện thuộc 9 nhãn. | Chỉ học trọng số bộ hiệu chỉnh trên 93 lượt thuộc 9 nhãn. Encoder và classifier của ResCNN64 được khóa khi huấn luyện. |
| Dashboard | **Model mặc định** ở mục 04 và đường dự đoán hiện có ở mục 03. | **ResCNN64 V2 · Bộ hiệu chỉnh đã học** ở mục 04. Áp dụng cùng bộ hiệu chỉnh cho mẫu tham chiếu và từng mẫu ứng viên. |

SHA-256 của checkpoint CNN gốc vẫn là `50e0d6ee1c2a3edd3c0b1f2cd794e83adffe6202395789190d7bb5a3c3d2ea4a`. Bộ nạp V2 kiểm tra hash của cả `model.pt` và `model.json` trước khi dùng checkpoint hiệu chỉnh. [Artifact gốc](../models/rescnn64/20261119_053351_6b8717/artifact.json) · [Báo cáo huấn luyện CNN gốc](../models/rescnn64/20261119_053351_6b8717/report.json)

## 2. Kiến trúc và luồng dữ liệu

```text
raw.csv + metadata.json
  |
  +-- BASELINE 6 × 60 ------> trung bình mỗi 10 giây, 36 giá trị
  |                             |
  |                             +--> chuẩn hóa baseline theo tập train
  |                             +--> MLP 36 → 16 → 12
  |                             +--> mức bù và độ dốc cho 6 kênh
  |
  +-- EXPOSURE 6 × 120 -----> hiệu chỉnh mốc bằng 30 điểm cuối baseline
                                +--> chuẩn hóa theo model.json gốc
                                +--> cộng đường hiệu chỉnh đã học
                                +--> ResCNN64 gốc
                                +--> embedding 64 chiều, chuẩn L2
                                +--> cosine và xếp hạng
```

Sáu kênh theo thứ tự của artifact là **TGS2602 A0, MQ3 #1 A1, MQ135 #2 A2, MQ3 #2 A3, điện trở gas BME688 và độ ẩm tương đối BME688**. Đầu vào CNN có dạng `[batch, 6, 120]`. Đầu vào riêng của bộ hiệu chỉnh có dạng `[batch, 36]`.

### ResCNN64 dùng chung cho hai đường chạy

1. Lớp đầu `Conv1d(6 → 32, kernel=7)`, sau đó `GroupNorm(8)` và GELU.
2. Ba khối residual lần lượt là `32 → 32` với kernel 5 và stride 1, `32 → 64` với kernel 5 và stride 2, rồi `64 → 128` với kernel 3 và stride 2. Mỗi khối có hai lớp tích chập. Nhánh skip dùng identity hoặc tích chập kernel 1 khi đổi kích thước.
3. Tính trung bình và cực đại theo trục thời gian, nối lại thành 256 giá trị. Đầu embedding gồm `Linear(256 → 128)`, GELU, Dropout 0,2 và `Linear(128 → 64)`, sau đó chuẩn hóa L2. Dropout tắt ở chế độ `eval`.
4. Classifier gốc có 9 lớp. Khi huấn luyện bộ hiệu chỉnh, logits được tính từ cosine với trọng số lớp đã chuẩn hóa, nhân hệ số 12. Khi đối sánh trên web, dùng embedding 64 chiều để tính cosine trực tiếp.

### Bộ hiệu chỉnh mới nằm trước CNN

Mạng gồm `Linear(36 → 16)`, Tanh và `Linear(16 → 12)`, tổng cộng **796 tham số học được**. Mười hai số đầu ra gồm 6 hệ số mức bù và 6 hệ số độ dốc. Lớp cuối khởi tạo bằng 0, vì vậy lúc bắt đầu huấn luyện tensor đi qua đúng như ở đường chạy gốc. [Kiến trúc CNN](../robonose_s3/rescnn64.py#L217) · [Bộ hiệu chỉnh](learned.py)

## 3. Tiền xử lý chi tiết

### Bước dùng chung với model gốc

- Đọc `raw.csv` và `metadata.json` của lượt `COMPLETE`. Đối chiếu schema `robonose.dataset.v1` và cấu hình với artifact, gồm map kênh, profile BME, hệ số ADC, tần số lấy mẫu và PWM.
- Lấy đúng **60 điểm BASELINE và 120 điểm EXPOSURE**. Mỗi pha gần 1 Hz, cho phép sai lệch tối đa 0,1 giây giữa hai điểm liên tiếp. Đồng hồ monotonic của toàn lượt phải tăng nghiêm ngặt.
- Kiểm tra cờ trạng thái, độ mới, tính hợp lệ và miền giá trị của sáu kênh. Tín hiệu gas hoặc điện áp không biến thiên trong cả pha EXPOSURE bị từ chối. Drift hoặc độ dao động vượt 5% trong 30 giây cuối baseline được ghi cảnh báo theo cấu hình `baseline_warn=true` của artifact hiện tại. `WAIT_EXPOSURE` có thể hỗ trợ cảnh báo chất lượng trước exposure. `RECOVERY` nằm ngoài tensor dự đoán.
- Với bốn kênh điện áp và độ ẩm, lấy exposure trừ trung vị của 30 điểm cuối baseline. Với điện trở gas, tính `ln(R_exposure / R_baseline)`. Chuẩn hóa từng kênh bằng `(delta − center) / scale` lưu trong `model.json`.

### Bước bổ sung của V2 đã học

1. Đọc toàn bộ baseline hợp lệ của sáu kênh. Chuyển điện trở gas sang log trước khi tạo đặc trưng. Chia mỗi kênh thành 6 cửa sổ liên tiếp, mỗi cửa sổ 10 điểm, rồi lấy trung bình. Cách này dùng cả 60 điểm và giữ thứ tự các cửa sổ để mạng thấy nền thay đổi theo thời gian.
2. Chuẩn hóa 36 đặc trưng bằng mean và độ lệch chuẩn học từ tập train của từng fold. Giới hạn giá trị chuẩn hóa trong `[-4, 4]` trước MLP. Bản được chọn giữ thông tin mức nền tuyệt đối của từng cửa sổ.
3. Gọi `X` là exposure đã chuẩn hóa, `d` và `s` lần lượt là vector mức bù và độ dốc sau `0,5 × tanh`. Với mỗi kênh `c` và thời điểm `t`, áp dụng:

   `X_v2[c,t] = X[c,t] + 0,5 × (d[c] + s[c] × u[t])`

   `u` là 120 điểm chạy đều từ −1 đến 1. Mức hiệu chỉnh tuyệt đối bị chặn ở **0,5 đơn vị chuẩn hóa** trên mỗi kênh và thời điểm, bằng một nửa biên tối đa của V2 đã học lần đầu. Đường bù vừa có thể nâng hoặc hạ mức tín hiệu, vừa có thể đổi xu hướng tuyến tính. Đường raw trên đĩa chỉ được đọc.

Bản V2 đã học dùng nhãn danh tính làm mục tiêu. Nó chưa được huấn luyện để tái tạo nền vật lý hoặc tách chính xác dư âm của mẫu trước. Tùy chọn thử nghiệm bù theo công thức trong `baseline.py` là một đường chạy riêng, có thể dùng blank cùng phiên và cấu hình khi dữ liệu đáp ứng điều kiện. [Tiền xử lý gốc](../robonose_s3/rescnn64.py#L117) · [Tiền xử lý V2](learned.py) · [Bản công thức](baseline.py)

## 4. Dữ liệu và cách huấn luyện

Tập train lấy từ dữ liệu lưu theo phiên trong `data/`, giới hạn **09–20/11/2026**, loại riêng cây `data/hardware`. Lần chạy giữ **93 lượt thuộc 9 nhãn**. Trong 63 lượt bị loại, **60 lượt có tên chưa xác nhận nhãn danh tính** và **3 lượt chưa hoàn chỉnh**. Pipeline cũng có kiểm tra trùng UUID/SHA-256 và kiểm tra chất lượng đầu vào của CNN. Một lượt có cảnh báo baseline vẫn có thể được giữ nếu đáp ứng các điều kiện bắt buộc.

| Nhãn | Số lượt train |
| --- | ---: |
| Dương | 14 |
| Phúc | 29 |
| Tài | 5 |
| chau | 7 |
| lam | 5 |
| son | 10 |
| tan | 11 |
| toan | 7 |
| tuan | 5 |

- **Thiết lập huấn luyện** dùng AdamW, learning rate 0,003, batch tối đa 24 lượt, 20 epoch và seed 42. ResCNN64 gốc ở chế độ `eval`, toàn bộ tham số khóa gradient. Gradient truyền qua CNN về bộ hiệu chỉnh.
- **Hàm mất mát** gồm cross-entropy theo nhãn, có trọng số lớp tỷ lệ nghịch căn bậc hai số mẫu, cộng phạt bình phương mức chỉnh exposure. Cấu hình được chọn dùng hệ số phạt 0,25 và hệ số contrastive 0,5.
- **Thành phần contrastive** dùng embedding gốc của các lượt train khác ngày làm mốc. Nó khuyến khích embedding sau hiệu chỉnh có cosine cao với mẫu cùng nhãn và thấp hơn tương đối với mẫu khác nhãn. Chỉ tính khi có cả mẫu cùng nhãn và khác nhãn ở ngày khác. Temperature là 0,15.
- **Chọn cấu hình** bằng cách lần lượt giữ riêng từng ngày trong tập 09–20/11. Thử bốn tổ hợp giữa baseline giữ mức tuyệt đối hoặc đã trừ trung bình riêng, và có hoặc không có contrastive. Ưu tiên top 1 trung bình theo lớp, dùng MRR để phân xử khi bằng. Có 76 truy vấn hợp lệ ở 6 nhãn có lượt cùng nhãn ở ngày khác. Sau khi chọn, huấn luyện lại bộ hiệu chỉnh trên cả 93 lượt.

### Kết quả giữ riêng từng ngày trong tập 09–20/11

| Cấu hình | Đúng hạng 1 | Top 1 trung bình theo lớp | MRR |
| --- | ---: | ---: | ---: |
| ResCNN64 gốc | 48/76 | 60,70% | 0,7243 |
| Giữ mức baseline, chỉ CE và phạt mức chỉnh | 49/76 | 63,33% | 0,7329 |
| Baseline trừ trung bình, chỉ CE và phạt mức chỉnh | 45/76 | 63,79% | 0,6774 |
| **Giữ mức baseline và thêm contrastive** | **50/76** | **66,09%** | **0,7409** |
| Baseline trừ trung bình và thêm contrastive | 44/76 | 62,60% | 0,6668 |

MRR là trung bình của `1 / hạng` của ứng viên cùng nhãn đầu tiên. Điểm càng cao thì mẫu đúng thường xuất hiện càng sớm. Các fold giữ riêng ngày để chọn bộ hiệu chỉnh. CNN gốc đã được huấn luyện trước đó trên một số ngày trùng với giai đoạn này, nên bảng được dùng để chọn cấu hình V2. [Mã huấn luyện và đánh giá](improve.py)

## 5. Đánh giá trên `data/hardware`

Tập hardware được đưa vào đánh giá sau khi chốt cấu hình V2. Có **13 lượt từ 4 phiên**, gồm 8 lượt Phúc Lưu và 5 lượt Tài. Mỗi lượt được dùng một lần làm truy vấn, ứng viên chỉ lấy từ các phiên khác. Bộ lọc kiểm tra UUID, SHA-256 và phiên trùng với dữ liệu huấn luyện, đồng thời loại UUID/SHA-256 trùng danh sách tham chiếu gốc.

| Phiên bản | Phúc Lưu đúng hạng 1 | Tài đúng hạng 1 | Tổng đúng hạng 1 | MRR |
| --- | ---: | ---: | ---: | ---: |
| ResCNN64 gốc | 5/8 | 2/5 | 7/13 (53,8%) | 0,6692 |
| V2 đã học lần đầu | 6/8 | 0/5 | 6/13 (46,2%) | 0,5788 |
| **V2 hiện tại `v2-grouped`** | **6/8** | **2/5** | **8/13 (61,5%)** | **0,7333** |

So với CNN gốc, V2 mới đúng thêm một lượt Phúc Lưu theo tổng số lượt đúng từng nhãn. So với V2 đã học lần đầu, số lượt đúng tăng ở nhãn Tài. Test qua API dashboard cũng xác nhận `v2-grouped` chạy thành công với đủ **17 ứng viên** trong một lần chạy. Kiểm thử API xác nhận đường chạy web và khả năng xử lý mẫu. Bảng độ chính xác ở trên dùng riêng tập 13 lượt có nhãn xác nhận.

Mức tăng một lượt trên hai nhãn là kết quả thử nghiệm ban đầu. Tập hardware này đã dùng trong các lần đánh giá trước. Để xác nhận tổng quát, cần đợt đo mới, nhiều phiên và nhiều nhãn hơn. [Số liệu theo lớp và lý do loại mẫu](grouped_training_report.json)

## 6. File và cách chạy lại

| File | Vai trò |
| --- | --- |
| `learned.py` | Đọc tín hiệu, tạo đặc trưng baseline, nạp checkpoint và chạy đối sánh với CNN. |
| `improve.py` | Lọc dữ liệu, chọn cấu hình bằng quy trình giữ riêng từng ngày, huấn luyện và đánh giá hardware. |
| `baseline_corrector_grouped.pt` | Checkpoint V2 hiện tại. |
| `grouped_training_report.json` | Kết quả từng cấu hình, dữ liệu loại và điểm trên hardware. |
| `train.py`, `baseline_corrector.pt`, `training_report.json` | Quy trình và artifact của lần huấn luyện V2 đầu tiên. |
| `baseline.py` | Thử nghiệm bù xu hướng theo công thức và bù bằng blank. |

Chạy lại từ thư mục gốc bằng môi trường có PyTorch. Script sẽ ghi lại checkpoint và báo cáo hiện tại trong `models_v2/`.

```powershell
& D:/PBL6/.venv/Scripts/python.exe -m models_v2.improve
```

Để chạy trên web, lưu lựa chọn ở **05 · Danh sách mẫu**, rồi vào **04 · Đối sánh** và chọn **ResCNN64 V2 · Bộ hiệu chỉnh đã học**. Kết quả bản hiện tại có `corrector_version = v2-grouped`. Có thể giữ nguyên mẫu tham chiếu và ứng viên, rồi chạy lại bằng **Model mặc định** để so thứ hạng. [Hướng dẫn sử dụng](../huongdan.md)
