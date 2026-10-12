# Khôi phục job — đợt ổn định 1

Mở **Lịch sử**, bấm **Chạy lại** ở job lỗi, đã dừng hoặc gián đoạn có lưu yêu cầu. Job mới có ID/thư mục mới; job cũ và file kết quả cũ được giữ nguyên. Một job cũ chỉ tạo một lượt chạy lại; nếu lượt mới lỗi thì chạy lại từ lượt mới.

- Sau đóng app/mất điện, job đang chạy/chờ trở thành gián đoạn, không tự chạy hay gọi API.
- Dịch/lồng tiếng dùng dữ liệu dự án hiện tại, bỏ chế độ force, tận dụng cue/cache còn hợp lệ. Đây không phải tiếp tục FFmpeg từ đúng khung hình đang render: render cần chạy lại.
- Tác vụ dịch, tải hoặc dùng ElevenLabs cần xác nhận Internet/phí/quota trước khi chạy lại. Không tự đổi key, tự cài thư viện hay tải model.
- Xóa logo/phụ đề bật bỏ qua kết quả hợp lệ cùng nguồn/cấu hình. Tải video bỏ các URL đã công bố thành công còn trong thư viện; URL lỗi tiếp tục ở job mới.
- Thiếu file nguồn/cookie/SRT, dự án đã xóa hoặc cue đã đổi thì cần sửa/chọn lại trước. Giới hạn 20 job và khóa dự án đang chạy vẫn áp dụng.
- Job trước bản update chưa lưu yêu cầu không có nút chạy lại; mở tab gốc/dự án để tiếp tục. Các tác vụ thay toàn bộ cue (ASR/nhập SRT), clone mới, cài thư viện/AI chưa cho phát lại từ Lịch sử.
- Yêu cầu riêng nằm trong data/jobs/requests, không trả trong state/history/job API và không được phục vụ qua /files. Không lưu các key API inline để phát lại. Khi xóa lịch sử, yêu cầu được chuyển vào kho lịch sử đã bỏ cùng bản ghi, không xóa kết quả.
- Bản ghi lịch sử lỗi được giữ nguyên để khôi phục; các job còn tốt vẫn nạp. Đây chưa phải bản sao lưu toàn bộ dữ liệu lên ổ khác.

Đợt tiếp theo: giao diện sao lưu/khôi phục dự án+cài đặt và báo cáo tổng cho hàng đợi. Chưa có tiếp tục render theo từng đoạn/checkpoint hay khôi phục toàn bộ file khi ổ đĩa bị hỏng.
