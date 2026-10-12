# AI nâng cao — tích hợp ngày 07/10/2026

Chưa đóng gói. Lượt phát triển này không tải/cài model, không sửa/xóa dự án đang sử dụng.
Mở lại app để nạp nguồn mới. Trong Biên tập video → Phòng sáng tạo → AI nâng cao / phối nhiều lớp.

## Forced alignment CTC

- Chọn clip có audio, tối đa 30 giây, tốc độ cố định. Muốn căn lời dịch phải chọn **audio lồng tiếng** tương ứng, không căn lời Việt vào tiếng Trung gốc.
- Cài đặt → Thư viện tùy chọn → Forced alignment: bấm cài mới tải runtime CPU riêng và model MMS 300M. Cần vài GB và Internet. Bộ này chưa được thử tải/cài model thật trong lượt này.
- **Model mặc định CC-BY-NC-4.0, chỉ phi thương mại**. Nút cài yêu cầu xác nhận riêng. Không đưa model này vào bộ cài thương mại.
- Có thể nối Python/model CTC đã tải riêng trong Cài đặt → AI nâng cao. Model dùng Transformers AutoModelForCTC + tokenizer ký tự + feature extractor, không chạy `trust_remote_code`. Chọn mã ISO 639-3 (`vie`, `eng`, `zho`) và Romanize theo vocabulary model; MMS cần Romanize.
- Engine đọc audio offline, tính emission và đường CTC Viterbi cho toàn bộ văn bản. Không dùng SequenceMatcher/Whisper để bịa mốc từ thiếu. Có giới hạn frame/token để tránh đầy RAM.
- Kết quả hiển thị mốc có thể sửa và số từ confidence dưới 0.50. Confidence **không** chứng minh lời nhập đúng nội dung audio; CTC vẫn có thể ép lời sai vào audio. Nghe và duyệt trước khi thêm karaoke. Có Hoàn tác.
- Thuật toán đã thử với emission tổng hợp (kể cả ký tự lặp/ngắt nghỉ); chưa nghiệm thu chất lượng tiếng Việt của model thật.

Nguồn model/giấy phép: https://github.com/MahmoudAshraf97/ctc-forced-aligner

## Tracking tái tìm / ReID

- Chọn video và vùng có chi tiết như trước; đoạn còn lại tối đa 12s, tối đa 64 mẫu.
- Tích **Tracking tái tìm mẫu toàn khung** trước khi chọn vùng. Không tích thì giữ chế độ tracking local cũ.
- Mặc định dùng OpenCV so khớp ngoại hình toàn khung: đây là thuật toán cổ điển, **không phải neural ReID hay nhận diện danh tính**.
- Có thể nối model ReID ONNX local trong AI nâng cao. Hợp đồng: một input float NCHW `[1,3,256,128]`, RGB, ImageNet mean/std; output embedding vector 16–4096 phần tử. Model phải đúng loại, có quyền sử dụng và không cần tải ngầm. Chưa cung cấp/chứng nhận model ReID mặc định.
- Encoder ONNX so cosine ngoại hình với mẫu đầu trên tối đa 12 ứng viên template mỗi frame. Không bảo đảm tìm được vật thể sau biến dạng lớn, đổi kích thước hay đổi góc hoàn toàn; không phải detector/long-term identity tracker đầy đủ.
- Cần score ≥0.88, hơn ứng viên thứ hai ≥0.06. Sau mất dấu/đổi cảnh phải có hai mẫu nhất quán. Đoạn mất dấu **không tạo vùng mờ/sticker**, các đoạn hiện lớp tách clip riêng; không nối qua gap.
- Không dùng tính năng này như bảo đảm che thông tin nhạy cảm. Duyệt từng đoạn. OpenCV đã thử video tổng hợp mất dấu/đổi cảnh rồi xuất hiện lại; ONNX model thật chưa thử.

## Avatar MuseTalk v1.5 — đầu nối, chưa có trình cài tự động

- Cài bộ MuseTalk theo hướng dẫn chính thức trước, với Python riêng, các model phụ thuộc và GPU NVIDIA CUDA. Chưa tải/chạy bộ này trong lượt phát triển này.
- Cài đặt → AI nâng cao: nối thư mục MuseTalk và Python. Thư mục MuseTalk/FFmpeg không có dấu, khoảng trắng hoặc ký tự shell (ví dụ `D:\AI\MuseTalk`). Upstream dùng lệnh FFmpeg chưa quote; đầu nối chỉ truyền tên file staging ASCII do app tạo.
- Nhập ảnh chân dung vào thư viện dự án. Chọn clip audio/video ≤30s, chọn ảnh và xác nhận quyền sử dụng hình/giọng. Audio trích đúng điểm cắt/tốc độ.
- Tác vụ kiểm tra CUDA và runtime riêng, chạy inference v1.5, giữ log/staging, kiểm tra MP4 rồi nhập thành media riêng. Duyệt video trước khi thêm track; không thay video nguồn.
- Còn cần hoàn thiện trình cài MuseTalk một nút (chọn bộ CUDA tương thích, tải model, xác minh runtime) và test GPU thật. Không hiển thị trạng thái “đã cài” chỉ vì có thư mục.

Nguồn: https://github.com/TMElyralab/MuseTalk

## Phối nhiều lớp tự động

- Ba bố cục Kể chuyện/Bản tin/Podcast; chọn nền, lớp phủ, nhạc, tiêu đề từ thư viện đã nhập. Bắt đầu tại con trỏ, tối đa 60s mỗi đề xuất.
- Nền nằm dưới các track cũ; lớp phủ và chữ nằm trên. Nhạc mặc định 15%, có fade. File ngắn thì rút đúng độ dài nguồn, không kéo vượt nguồn.
- Tạo đề xuất → duyệt danh sách → Áp dụng. Chưa duyệt thì không sửa timeline; kiểm tra revision và có Hoàn tác. Track cũ, kể cả track khóa, giữ nguyên.
- Đây là **phối theo quy tắc local**, chưa phải AI tự chọn cảnh/viết nội dung/điều khiển nhiều lớp bằng prompt. Phần AI director vẫn còn cần phát triển và nghiệm thu riêng.

## Trạng thái nghiệm thu

- Python/unit: CTC DP, cấu hình không tải ngầm, quyền avatar, hủy trước launch, giới hạn dữ liệu, bảo toàn track.
- JavaScript: proposal tracking tách gap, nguồn cũ không đổi; các hồi quy timeline hiện có.
- GUI Qt: mở bộ điều khiển, chạy job phối chữ, duyệt/lưu timeline, đọc cấu hình AI mà không tải model.
- Render FFmpeg: kiểm tra màu pixel xác nhận nền dưới, foreground giữa, overlay trên.
- Chưa nghiệm thu: tải/cài CTC thật, audio CTC tiếng Việt, ReID ONNX thật, avatar GPU, trình cài MuseTalk tự động và AI director bằng LLM.

## Cập nhật 10/10/2026 (thay thế trạng thái cũ ở trên)

Đạo diễn AI dùng model API đang chọn trong Cài đặt → Dịch & API. Nhập prompt,
chọn media được phép dùng, tích đồng ý gửi prompt và metadata (tên, loại, thời lượng,
kích thước). Không gửi file video/audio, đường dẫn hoặc nội dung cue của dự án.
Đề xuất tối đa 60 giây; chỉ thêm lớp mới, kiểm tra nguồn và thời gian, duyệt rồi
Áp dụng/Hoàn tác. Không phân tích hình ảnh/cảnh phim hoặc dựng tự động toàn bộ phim.

Thư viện MuseTalk có Cài/Gỡ. Cài chỉ bắt đầu khi xác nhận; kiểm tra NVIDIA trước tải lớn,
cần 25 GB trống và đường dẫn ASCII không dấu/không khoảng trắng. Source/model ghim
revision và kiểm checksum, runtime riêng; nối tự động chỉ sau khi kiểm tra thành công.
Tham khảo upstream: https://github.com/TMElyralab/MuseTalk . Kiểm tra giấy phép của
các thành phần/model và quyền sử dụng chân dung. Gỡ runtime ngoài chỉ ngắt kết nối.

Đã kiểm tra unit/mock và GUI cho luồng đề xuất; chưa gọi LLM thật trong QA.
Chưa tải model hoặc cài runtime GPU để nghiệm thu MuseTalk trên máy thực tế.
Forced alignment/ReID đã tích hợp nhưng vẫn cần audio/model thật để đo chất lượng.
Avatar nhiều nhân vật tự động theo lượt hội thoại chưa triển khai; hiện tạo clip riêng.
