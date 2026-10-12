# Trạng thái hoàn thiện 10/10/2026

## Đã triển khai trong update này

- Phối nhiều lớp bằng prompt LLM, chọn media/đồng ý riêng, kiểm tra schema, nguồn,
  mốc thời gian và revision; duyệt trước áp dụng, có Hoàn tác, giữ track cũ.
- Cài/Gỡ MuseTalk theo nhu cầu; NVIDIA preflight, runtime riêng, source/model ghim
  revision/checksum; không kèm runtime/model trong gói Lite.
- Gia hạn bản quyền nền bằng phiên Windows DPAPI; server có `/v1/refresh`, token
  chỉ lưu hash ở DB. Client cũ/server cũ tương thích kích hoạt cơ bản.
- Khôi phục khả năng tìm bản sao chuyển dự án bị ngắt do mất điện: vào danh sách
  đã xóa, file giữ nguyên; có thể khôi phục rồi kiểm tra thủ công.
- Gói update cộng dồn gồm cả sửa dự án tách tab, chuyển bản sao giữa tab và màu
  nền chữ/tiêu đề, cùng các thay đổi sau setup 0.5.1 Lite trước đó.

## Chưa thể coi là nghiệm thu đầy đủ

- Forced alignment cần kiểm audio/model thật, đặc biệt tiếng Việt; ReID cần video
  đổi cảnh/che khuất và model ONNX thật. Unit/mock không thay thế đánh giá chất lượng.
- MuseTalk cần cài và chạy inference trên máy NVIDIA thật. Profile Windows đã tích
  hợp nhưng dependency/upstream có thể cần điều chỉnh theo GPU/driver thực tế.
- Đạo diễn AI cần thử API/model thực tế. Hiện chỉ đề xuất thêm lớp tối đa 60s từ
  metadata, không phân tích cảnh, không sinh media hoặc dựng phim dài tự động.
- Avatar theo nhiều người nói tự động chưa có; hiện tạo từng clip chân dung/audio.
- Auto-update sản xuất cần nguồn phát hành HTTPS, manifest/chữ ký và public key;
  license cần server/domain thật. Không có bí mật hoặc server sản xuất trong update.
- Chưa có GUI quản trị license hoặc ký số EXE/setup. Update là source overlay,
  không mã hóa source; không thay thế cơ chế bảo vệ quyền sử dụng bằng server.

## Kiểm tra trên máy sử dụng

Đóng app, sao lưu, giải nén đè vào thư mục có ReupVoiceStudio.exe, không vào data.
Thử mở dự án cũ/lưu/khôi phục; tạo đề xuất chữ bằng LLM, duyệt rồi Hoàn tác.
Chỉ cài MuseTalk khi cần và đủ phần cứng; chạy clip ngắn để nghiệm thu trước xử lý dài.
Backend gia hạn phải được cập nhật riêng; không gộp admin hoặc secret vào client.
