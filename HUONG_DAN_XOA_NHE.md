# Xóa phụ đề / logo — các lựa chọn mới

Không dùng EXE/mã nguồn của DeLogo, không yêu cầu đăng nhập Sonzim. Các chế độ này chạy trên máy bằng FFmpeg hoặc OpenCV; giữ nguyên nguồn và tạo kết quả riêng.

## Test nhanh

1. Chọn video và vẽ vùng. Chọn `Nhanh · FFmpeg delogo`, nguồn SRT `Không cần SRT gốc` nếu chỉ thử xóa hình.
2. Nhập mốc xem (giây), bấm **Xem kết quả tại mốc**. Ảnh xử lý thật hiện ngay trong khung video. Bấm **Xem gốc** để đối chiếu. Đây không phải bản xem video chuyển động.
3. Đổi vùng/tham số thì ảnh kết quả cũ được ẩn; bấm xem lại. Thử video ngắn trước khi xử lý cả tập.
4. Telea, Navier–Stokes hoặc Telea + làm mịn là nội suy cổ điển, có thể nhòe/xấu hơn và rất chậm trên CPU. Không phải model AI hay khẳng định tương đương thuật toán “cao cấp” của DeLogo. Nền phức tạp cần thử VSR AI, không chỉ tăng bán kính.
5. Bấm **Xóa phụ đề/logo** để chạy toàn video. Chọn giữ/tắt audio. Nếu cần dịch, chọn SRT nhập/trích/Whisper trước; lấy SRT thất bại thì chưa xóa.

## Các chế độ

- FFmpeg delogo: nội suy vùng chữ nhật, chạy ngay với bộ FFmpeg của ứng dụng. Cần viền ảnh quanh vùng; vùng sát mép hãy thu nhỏ/giảm nới vùng hoặc dùng Telea.
- Telea / Navier–Stokes: OpenCV xử lý từng khung. Telea + làm mịn bổ sung làm mịn bên trong mặt nạ. Dùng chung mặt nạ cho nhiều vùng trong một lượt.
- Che mờ, mosaic, tô đen: che thông tin, không phục hồi nền.
- Chèn logo mới: chọn ảnh PNG/JPG/WebP bằng **+ Ảnh logo**; logo giữ tỷ lệ trong vùng vẽ. Hỗ trợ nhiều vùng, không phải xóa logo cũ trước.
- Cắt khung: vẽ đúng một vùng **GIỮ LẠI**. Video xuất có kích thước vùng cắt, làm tròn xuống số chẵn để tương thích mã hóa. Không dùng “nới vùng” cho cắt/logo.
- AI VSR: vẫn giữ các lựa chọn cũ, cần runtime/model riêng. Nút xem ảnh xóa nhẹ không chạy AI VSR.

**Nới vùng** tính bằng pixel nguồn, 0–64. **Bán kính** 1–32 dùng cho OpenCV và che mờ; không tác động FFmpeg delogo/mosaic/tô đen. Video xuất MP4, mã hóa CPU x264. Chưa thêm tự chọn encoder GPU.

## Thư viện theo nhu cầu

FFmpeg không cần cài thêm. Telea/Navier–Stokes tự tìm OpenCV trong bộ Xóa nhẹ, AI hình hoặc VSR đã kết nối. Nếu chưa có, vào **Cài đặt → Thư viện → Xóa nhẹ OpenCV** và bấm cài. Bộ mới chỉ có OpenCV + NumPy, không tải model AI; có nút gỡ giống các thư viện khác. Chỉ tải khi người dùng bấm cài.

Video OpenCV hiện cần FPS cố định, tối đa 120 FPS; video có metadata xoay cần render chuẩn qua Biên tập trước. Không đảm bảo khôi phục hoàn hảo vùng mặt/tóc/cảnh nhiều chi tiết; hãy so sánh với VSR.

## Hàng loạt

- Nút **+ Ảnh / video** nhận nhiều file; **+ Thư mục** nhận cả thư mục con. Hỗ trợ video MP4/MOV/MKV/AVI/WebM và ảnh PNG/JPG/WebP. Danh sách tối đa 1000 file, mặc định file mới chưa tích để tránh chạy nhầm cả thư mục.
- Bấm tên file để xem trực tiếp từ nguồn trên máy; không tạo WebM khi thêm file. File chỉ tải vào dữ liệu ứng dụng khi xử lý/xem kết quả. Nguồn chưa tải cần chọn lại sau khi mở app. Codec không hỗ trợ có thể cần ảnh khung hình hoặc bấm Tạo bản xem WebM; không bảo đảm mọi codec mở tức thì.
- Ảnh không cần SRT/model VSR, xuất PNG riêng. Chọn phương pháp nhẹ và vẽ vùng như video; ảnh nguồn giữ nguyên.
- **Tất cả video:** vùng phần trăm co giãn theo kích thước từng video.
- **Riêng từng video:** chuyển từng tên và vẽ vùng riêng.
- **Dùng chung, video có vùng riêng ghi đè:** tạo vùng chung trước, chuyển sang chế độ này rồi sửa file cần khác.
- SRT nhập gắn với từng video; không tự dùng một SRT cho tất cả. Whisper tạo SRT riêng theo audio mỗi video.
- **Xử lý file đã tích:** đưa vào hàng đợi tuần tự, tối đa 20 tác vụ đang chờ/chạy. Một tác vụ lỗi không làm hỏng nguồn hoặc ngăn tác vụ tiếp theo. Có thể dừng từ Lịch sử.
- **Bỏ qua kết quả cùng nguồn và cấu hình:** chỉ bỏ qua khi có mục kết quả hợp lệ, khớp dấu vân tay nguồn/tham số. Không chỉ so tên file.

Vùng, lựa chọn và danh sách file đã tải được giữ trong cấu hình giao diện trên máy. Nút × chỉ bỏ khỏi danh sách, không xóa nguồn. Chưa có tự dò logo. Lựa chọn OpenCV cũ tự đổi sang Telea, không gọi CLI VSR portable 1.1.1.

## Giao diện và lưu kết quả

Tab đổi tên thành **Xóa logo/phụ đề**. Kết nối, check CLI, thiết bị VSR và cài thư viện ở **Cài đặt → Thư viện**. Giải thích dài được gom vào **Hướng dẫn** mặc định đóng.

Kết quả mới tập trung vào `outputs/RemoveSRT`: `tên_gốc_clean.mp4`, `tên_gốc_clean.png`, `tên_gốc_clean.srt`. SRT giữ nội dung gốc, chỉ thêm hậu tố theo yêu cầu đặt tên; không dịch hay sửa nội dung. Tên trùng thêm `_2`, `_3`…; cùng job dùng cùng tiền tố cho video/ảnh/SRT. Nhật ký/file tạm ở `RemoveSRT/.jobs/Job1`, `Job2`…; bản sạch tạm được bỏ sau khi công bố thành công.

Các chức năng khác dùng `TextSpeech/TextSpeech1`, `VoiceClone/VoiceClone1`, `VideoDubbing/VideoDubbing1`, `VideoEditor/VideoEditor1`, `Downloads/Downloads1`, `Podcast/Podcast1`, `Documents/Documents1`… Dự án mới đặt thư mục `Tên dự án-1`, `Tên dự án-2`…, ID nội bộ không đổi. Thư mục đã chọn trong Cài đặt là thư mục cha của nhóm chức năng. Kết quả/dự án cũ giữ nguyên, không tự di chuyển hay đổi tên.
