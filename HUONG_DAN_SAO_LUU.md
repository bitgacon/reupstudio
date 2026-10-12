# Sao lưu / khôi phục

Mở **Cài đặt → Lưu trữ → Sao lưu / Khôi phục**.

## Sao lưu

1. Lưu thay đổi trong dự án, chờ các job chạy xong.
2. Tích dự án muốn sao lưu hoặc chỉ chọn **Kèm cài đặt**.
3. Bấm **Sao lưu dự án đã chọn**, sau đó **Tải bản sao lưu**. Gói `.rvbackup` được tạo trong thư mục dữ liệu `outputs/Backups`; nên chép sang ổ khác để tránh mất cùng ổ máy.

Gói gồm metadata/cue, timeline biên tập, nguồn video/ảnh/audio, mẫu audio TTS tham chiếu, audio cue đã tạo và stems đã tách. Nguồn dự án bên ngoài hoặc bản lưu trong assets của dự án cũng được mang theo. Không kèm runtime/model, thư viện, giọng VieNeu clone, lịch sử job, proxy/cache editor hay file render cũ. Giọng clone cần chép/cài riêng trước khi tạo lại audio. Dự án không đủ nguồn sẽ báo lỗi, không tạo gói thiếu dữ liệu.

Cài đặt gồm giao diện/ngôn ngữ, FP32/INT8, model Whisper đã chọn, quy tắc đọc/ngắt nghỉ, cấu hình dịch/LLM và TTS CPU/CUDA. Không kèm đường dẫn thư viện/đầu ra/dự án trên máy cũ, bản quyền, preset bố cục hoặc bản nháp chưa lưu trong trình duyệt.

Tối đa 100 dự án, 10000 file, 2 GB mỗi gói; chia thành nhiều gói nếu lớn. Khi nhập, nên để trống ít nhất 3 lần dung lượng gói cho file nhập, vùng kiểm tra tạm và dự án mới. Không nén lại video/audio để tránh tốn CPU. Việc sao lưu/kiểm tra file lớn có thể mất thời gian; chưa có hủy hoặc % tiến độ chi tiết.

**API key mặc định không được đóng kèm.** Nếu chủ động tích kèm key, file là ZIP dữ liệu không mã hóa, người có file có thể đọc key. Không chia sẻ gói chứa key. SHA256 giúp phát hiện file hỏng, không phải chữ ký xác thực người gửi; chỉ nhập gói từ nguồn tin cậy.

## Khôi phục

1. Chọn file `.rvbackup`; ứng dụng kiểm tra đường dẫn, metadata và checksum mọi file trước khi cho nhập.
2. **Thêm thành dự án mới** mặc định bật, **Khôi phục cài đặt** và **Khôi phục API key** mặc định tắt.
3. Xác nhận khôi phục. Dự án được cấp mã mới, nguồn được nối lại; dự án cũ không bị ghi đè. Có thể nhập nhiều lần, mỗi lần tạo bản riêng.
4. Nếu khôi phục cài đặt, giao diện cập nhật theo ngôn ngữ đã lưu. Bấm **Tải lại giao diện** sau khi xong.

Trước khi thay cài đặt, bản cũ được giữ trong thư mục dữ liệu `backups/settings-before-...`. API key hiện có được giữ nếu không chọn nhập key. Để không gắn key hiện có với nhà cung cấp khác, URL/model dịch hiện tại được giữ trong trường hợp này; các cấu hình LLM nhập thêm có key trống để bạn bổ sung/chọn sau. Các cấu hình LLM hiện có không bị xóa. Gói chứa key chỉ áp dụng key khi tích cả khôi phục cài đặt và khôi phục key.

Không tự tải model/cài thư viện hoặc chạy job sau khôi phục. Quyền gửi phụ đề/lời đọc qua Internet cần xác nhận lại. Audio cache vẫn được kiểm tra theo giọng/model/quy tắc hiện tại trước khi xuất; có thể cần tạo lại nếu khác máy.

File hỏng/thiếu nguồn/đường dẫn thoát gói/file thực thi bị từ chối. Khi gặp lỗi xử lý bình thường, các bản mới đang nhập được thu hồi và cài đặt trước đó được khôi phục; dữ liệu hiện có giữ nguyên. File JSON ghi theo cách atomic; dự án chỉ hiển thị khi đã sao chép xong nguồn. Chưa kiểm chứng mất điện thật trong quá trình khôi phục nhiều dự án/cài đặt: một số bản mới đã hoàn tất có thể còn lại, và nên dùng bản cài đặt trước trong `backups` nếu cần.

## Chọn nhanh file xóa logo/phụ đề

Tab **Xóa logo/phụ đề** → danh sách **Ảnh / video hàng loạt** có **Chọn tất cả** và **Bỏ chọn tất cả**, áp dụng cả ảnh và video đang có trong danh sách, không thay vùng xóa. Danh sách có thể hơn 20 file nhưng hàng đợi vẫn tối đa 20 tác vụ mỗi lượt; chọn ít hơn khi xử lý.

## Lỗi cài VSR trên máy Lite chưa có 7-Zip

Gói VSR portable 1.1.1 dùng bộ lọc ARM64 (mã `0x0A`, thông báo cũ có `b'\n'`) và BCJ2. `py7zr==1.0.0` trong `extractor-env` không giải nén được bộ lọc ARM64. Bản update dùng console 7-Zip native: nếu máy chưa có, khi bấm cài VSR sẽ tải `7zr.exe` 26.04 chính thức (~603 KB), xác minh SHA256 trước khi chạy. Không cài vào runtime Lite, không yêu cầu bạn cài 7-Zip thủ công; không đóng kèm thư viện vào setup/update.

Sau khi áp dụng update: **Cài đặt → Thư viện → VSR → Tải/cài** lại. Gói VSR đã tải nằm trong thư mục thư viện `downloads` được dùng lại nếu size/checksum đúng, không tải lại 1,7 GB. Cần tối thiểu 10 GB trống; thư mục giải nén lỗi trước đây được giữ nguyên, không tự xóa dữ liệu trên máy bạn. Nếu ổ gần đầy, kiểm tra các bộ VSR chưa kích hoạt trước khi dọn thủ công. Sau khi giải nén, app còn kiểm tra runtime/model trước khi kết nối tự động; lỗi runtime khác (nếu có) cần xem log mới.
