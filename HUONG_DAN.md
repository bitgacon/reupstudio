# Reup Voice Studio 0.3.4

Bản hiện tại **0.3.4** bổ sung [ngắt nghỉ, từ điển phát âm và khai triển viết tắt](CAP_NHAT_0.3.4.md). Mở app và kiểm tra nhãn v0.3.4. Nội dung 0.3.3 dưới đây vẫn áp dụng cho dựng video.

Nhánh ứng dụng riêng dành cho đọc và lồng tiếng Việt bằng VieNeu v3 Turbo, giao diện sáng/tối với 5 mục chính. Không phải CIT Voice Studio, không phải bản cập nhật thay thế MPT. Bản hiện tại **0.3.4**; xem [timeline vùng mờ, lớp phủ, hòa trộn và nền](CAP_NHAT_0.3.3.md), [chọn giọng, nhiều vùng mờ và mở lại app](CAP_NHAT_0.3.2.md), [video cố định](CAP_NHAT_0.3.1.md), [khung đầu ra và dịch không key](CAP_NHAT_0.3.md), [tính năng dựng 0.2](CAP_NHAT_0.2.md).

## Mở ngay trên PC hiện tại

1. Bấm **Lưu thay đổi** và chờ tác vụ xong, rồi đóng cửa sổ Reup Voice Studio cũ để dùng mã mới; không cần đóng hoặc gỡ MPT.
2. Chạy **MO_REUP_VOICE_STUDIO.bat** trong thư mục này. Kiểm tra **v0.3.4** cạnh tên ứng dụng. Cửa sổ desktop mở bằng Qt WebEngine; nếu không thấy số phiên bản này, bạn đang mở cửa sổ hoặc thư mục mã cũ. Bản đầu dùng CPU và FP32 để ưu tiên tương thích.
3. Thư viện giọng được nạp nền khi mở lần đầu. Chờ danh sách hiện rồi chọn giọng. Có thể bấm **Nạp giọng** trong TTS để thử lại.
4. Nếu cửa sổ desktop không mở được, dùng **MO_BANG_TRINH_DUYET.bat**. Địa chỉ mặc định `http://127.0.0.1:18765`; giữ tiến trình máy chủ khi sử dụng.

Từ 0.3.2, mở lại app sẽ kết nối máy chủ đang chạy nếu đúng thư mục, kho dữ liệu và cùng bản mã. Đóng Chrome không tự dừng máy chủ Python. Khi nâng từ bản cũ, lưu thay đổi/chờ tác vụ xong rồi đóng cửa sổ máy chủ Reup cũ (Ctrl+C) một lần. Không tắt hàng loạt Python, không đổi cổng để chạy hai máy chủ cùng kho `data`. Xem hướng dẫn 0.3.2 cho vòng đời app/web.

### Độc lập ở mức nào?

Mã ứng dụng và dữ liệu nằm riêng tại `ReupVoiceStudio`; **không import mã MPT và không thay Project/giọng MPT**. Hiện tại launcher dùng Python đã có tại `../release/MPT/MoneyPrinterTurbo/runtime` hoặc `../MoneyPrinterTurbo/.venv`, FFmpeg trong bộ portable cũ và model trong `../VieNeuLocal` để tránh sao chép/tải lại nhiều GB.

**Chép riêng thư mục mã nguồn này sang PC trống chưa đủ chạy.** Muốn chuyển máy ngay, có thể đặt thư mục này cạnh `MoneyPrinterTurbo`, `VieNeuLocal`, `tools` đã giải nén từ bộ portable MPT: sao chép `MoneyPrinterTurbo/runtime` vào `ReupVoiceStudio/runtime`, đặt `tools` vào `ReupVoiceStudio/tools`, giữ `VieNeuLocal` ở cùng cấp với ReupVoiceStudio. Dùng bản sao, không di chuyển môi trường đang dùng. Lúc đó ứng dụng không cần MPT chạy. Chưa có bộ ZIP portable riêng đã nghiệm thu cho nhánh Reup.

Trên máy có Python 3.11 có thể tạo môi trường từ `requirements.txt`, cài FFmpeg và VieNeu riêng. Bản yêu cầu model VieNeu được cache trước; ứng dụng không tự tải model TTS khi chạy. Whisper là ngoại lệ: người dùng phải bật cho phép tải lần đầu.

## 1. Văn bản → Giọng nói

- Nhập/dán văn bản, chọn giọng bên phải; tìm theo tên, vùng miền, lọc nam/nữ/giọng đã clone.
- Nút ▶ ở từng giọng tạo câu nghe thử. Chọn tốc độ 0,5–2,0× rồi bấm **Tạo giọng nói**.
- Audio lưu ngay trong `data/outputs/<mã tác vụ>`. Thanh phát dưới cùng có tải WAV, MP3 và SRT. Lịch sử mở lại kết quả cũ.
- Văn bản dài được chia đoạn. SRT căn theo thời lượng **đoạn đã tạo**, không phải nhận dạng căn từng từ. Tối đa 100.000 ký tự mỗi tác vụ.
- `[nghỉ 1s]` được biến thành khoảng lặng thật. `[cười]`, `[hắng giọng]`, `[thở dài]` gửi tới VieNeu; hiệu quả phụ thuộc model/giọng, không bảo đảm biểu cảm giống nhau ở mọi lần đọc.
- Đổi tốc độ dùng FFmpeg, vì trường `speed` trên API VieNeu hiện không đổi tốc độ tổng hợp.

## 2. Voice Clone

1. Chọn WAV/MP3/M4A/OGG/FLAC, hoặc thu micro tối đa 8 giây. Micro cần quyền thiết bị của bạn; chưa nghiệm thu trên micro vật lý ở lần bàn giao này.
2. Nên dùng một người nói rõ, 3–8 giây, ít nhạc/nhiễu; file dài lấy 8 giây đầu. Đặt tên mới, xác nhận quyền sử dụng mẫu rồi bấm **Clone & lưu**.
3. Chờ xong, chọn giọng bên phải và tạo audio thử. Giọng mới cũng có ở TTS, podcast và từng cue lồng tiếng.
4. Có thể nhập MP3/WAV do OmniVoice tạo. Không chuyển trực tiếp embedding `voice.pt`; VieNeu cần **mẫu âm thanh**. Giọng clone riêng nằm trong `data/voices`, tự đăng ký lại khi engine khởi động.

Tên trùng bị từ chối để không phá giọng đang có. Lần clone đầu có thể lâu hơn đọc giọng sẵn do nạp speaker encoder. Không bấm lặp lại. Ứng dụng mở VieNeu riêng trên cổng nội bộ ngẫu nhiên, không đăng ký giọng hoặc dừng server MPT cổng 8000.

## 3. Lồng tiếng video

1. **Dự án lồng tiếng** → chọn video hoặc chỉ nhập `.srt`. Nhập file không tự dịch, không tự tạo lời đọc. File gốc không bị sửa.
2. Nếu chưa có SRT, mở **Nhận dạng bằng Whisper**, chọn ngôn ngữ. Lần đầu cần Internet và tích **Cho phép tải model**. Model mặc định `small`, chạy CPU; chưa tự phân vai người nói.
3. SRT đã Việt: bỏ qua dịch. Nếu cần dịch, chọn **Google V1 · giống Subtitle Edit · không key** (mặc định), ngôn ngữ nguyên văn/đích và cho phép gửi văn bản qua Internet; bấm **Dịch / Tiếp tục phụ đề**. Có thêm **Google Web · giống subviet**. Hai cách này không cần Google API key, nhưng có thể bị Google giới hạn (lần thử 30/09/2026 cả hai trả HTTP 429). Chỉ văn bản được gửi, không upload video. Lưu sau từng cue; bấm tiếp tục sẽ giữ câu đã dịch và phần sửa tay. **Dịch lại** cho phép dịch riêng cue. Rút gọn theo thời lượng cần sửa tay hoặc chọn **API tương thích** và cấu hình ở ⚙; có thể phát sinh phí. Có thể bật **Dịch ngay sau Whisper**; timeline được lưu trước khi dịch.
4. Chọn giọng chung; có thể đổi giọng và tốc độ từng câu. Sửa lời đọc, mốc bắt đầu/kết thúc theo **giây**, bấm **Lưu thay đổi / Kiểm tra SRT**.
5. Thời lượng bằng 0/âm và sai thứ tự bị chặn; không tự chia cho 0 hoặc âm thầm đổi timeline. Khối SRT sai định dạng cần sửa file rồi nhập lại; cảnh báo chồng lấn nghĩa là có thể nghe hai câu cùng lúc.
6. **Tạo / Tiếp tục** xử lý lần lượt và lưu sau mỗi cue. Câu đã xong, còn đúng văn bản/giọng/timing, được bỏ qua. Đổi lời đọc/giọng/timing sẽ làm audio cũ không còn hợp lệ để xuất.
7. Tích câu rồi **Tạo lại câu đã chọn**, hoặc bấm **Tạo lại** ngay trên cue. Cue tăng tốc trên 1,8× được đánh dấu **Cần xem lại**; rút gọn lời đọc để tự nhiên hơn. Đây không phải lỗi tạo audio.
8. **Xuất kết quả**: chỉ SRT, WAV+MP3+SRT, video lồng tiếng+SRT rời, hoặc video có phụ đề dính hình. Phải tạo đủ audio hợp lệ trước khi xuất audio/video; không tự chèn im lặng để che cue lỗi.

Timeline lấy mốc đã duyệt, cắt lặng và căn tốc độ trong từng cue, không dồn câu gây trôi. Bấm cue trên timeline để tua video. Sau xuất audio, **Xem với audio lồng tiếng đã xuất** đồng bộ phát bản lồng tiếng với video. Nếu codec video không được cửa sổ Qt/trình duyệt hỗ trợ, bấm **Tạo bản xem WebM**; bản xem nhẹ giữ thời lượng, xuất vẫn dùng video gốc.

Khung phát video được cố định ở đầu cột trái; cuộn phần tùy chỉnh bên dưới không làm video trôi mất. Tại **Khung đầu ra** bên dưới video, chọn tỷ lệ 9:16, 16:9, 1:1, 4:5, 4:3, theo gốc hoặc kích thước riêng. Khung xem đổi ngay. **Giữ đủ hình** có viền; **Phủ kín** cắt phần thừa. Kéo hình để đổi vị trí, dùng mục **Khung hình** để zoom/xoay. Bấm ⛶ để phóng lớn bản xem. Cỡ phụ đề/tiêu đề tính theo pixel đầu ra. Lưu dự án hoặc lưu cấu hình dùng lại để giữ các lựa chọn này; file video nguồn không thay đổi.

**Vẽ vùng mờ** ngay dưới video → kéo chuột trên hình để chọn vùng. Kéo trong vùng để di chuyển, kéo bốn góc để đổi kích thước; Esc hủy thao tác đang kéo. **Bỏ vùng mờ** trả về giữ nguyên. Mục **Xử lý phụ đề gốc** có độ mờ, vùng theo phần trăm và tùy chọn che đen. Vùng áp dụng lên hình gốc trước zoom/xoay và chạy suốt video, không tự theo dõi vật thể/người. Khi xuất dùng làm mờ thật bằng FFmpeg; hiệu ứng trình duyệt chỉ là bản xem gần đúng, không khôi phục chữ/hình đã bị che.

Giới hạn: video tải vào tối đa 2 GB, timeline xuất tối đa 60 phút. Bản 0.2 bổ sung zoom/xoay, phụ đề, logo/tiêu đề, nhạc nền, tách giọng Demucs tùy chọn và ducking; hướng dẫn trong `CAP_NHAT_0.2.md`. Chưa có lip-sync, tự phân vai, OCR, kéo/thả mốc cue hoặc xuất soft-sub gắn trong container. Mốc SRT đúng không bảo đảm lời đọc sau tăng tốc luôn tự nhiên.

## 4. Hội thoại / Podcast

Mỗi lượt viết theo mẫu:

```text
[Host]: Xin chào các bạn!
[Khách mời]: Rất vui được tham gia.
[Host]: Chúng ta bắt đầu nhé. [nghỉ 1s]
```

Bấm **Thêm nhân vật**, hoặc **Cập nhật** để nhận tên trong kịch bản. Bôi đen lời thoại rồi bấm tên nhân vật để gán; chọn giọng từng người (có thể dùng giọng clone), chỉnh khoảng nghỉ/tốc độ rồi tạo. Không giới hạn ở hai người trong kịch bản mẫu. Audio/SRT được ghép theo thời lượng từng lượt đọc thực tế. Cần nạp giọng trước nếu danh sách còn trống.

## 5. Đọc tài liệu

Nhập TXT, DOCX hoặc PDF có lớp chữ; sửa văn bản trích xuất rồi bấm **Chuyển sang Văn bản → Giọng nói**. Khi TTS đang có nội dung, ứng dụng hỏi trước khi thay. Word `.doc` cũ phải lưu thành `.docx`. PDF có mật khẩu cần mở khóa bản sao; PDF scan/ảnh cần OCR bên ngoài. Bảng Word đọc theo thứ tự đoạn; tài liệu nhiều cột cần kiểm tra lại thứ tự câu.

## Lưu trữ, riêng tư, dừng và sao lưu

- `data/projects` hoặc thư mục dự án đã chọn: dự án, bản sao nguồn, cue WAV, snapshot và `exports`; `data/voices`: mẫu clone và metadata; `data/outputs`: kết quả TTS/podcast; `data/jobs`: lịch sử; `data/uploads`: bản sao file nhập. `data/project-index.json` liên kết các dự án lưu ngoài; `data/presets.json` chứa cấu hình dùng lại.
- `data/settings.json` chứa cấu hình, **API key lưu dạng văn bản trên máy**. Không gửi thư mục `data` cho người khác nếu chưa loại bỏ khóa, giọng, video và nội dung riêng. Sao lưu vào nơi bạn kiểm soát.
- **Dừng sau bước hiện tại** không ngắt giữa dòng ghi cue. Đóng desktop lúc đang làm sẽ hỏi và chờ dừng an toàn. Tác vụ gián đoạn được đánh dấu; mở lại dự án để tiếp tục cue. TTS/podcast dài chưa có resume từng đoạn như luồng SRT.
- Giao diện chỉ lắng nghe `127.0.0.1`, có kiểm tra phiên/yêu cầu cùng nguồn. Không phải dịch vụ để đưa lên Internet; không mở port ra ngoài.
- `data/vieneu.log` ghi log engine riêng. Nếu thiếu model/encoder, xem log và kiểm tra VieNeuLocal, không tự xóa cache hoặc môi trường MPT.
- Chỉ dùng nội dung và mẫu giọng bạn sở hữu/được phép sử dụng. Công cụ không tải lại video từ nền tảng và không xử lý quyền xuất bản thay bạn.

## Kiểm thử và mã nguồn

Xem `QA_REPORT.md`. Chạy test bằng `python -m pytest tests`; kiểm thử end-to-end cục bộ bằng `QA_LIVE.py` với server dùng kho `REUP_DATA` riêng. Không chạy script QA lên dữ liệu thật. Mã frontend trong `web`, backend trong `reup`, launcher trong `run.py`. Phần xử lý SRT/audio kế thừa thuật toán đã kiểm thử của MPT, nhưng không kéo toàn bộ giao diện MPT sang.
# Biên tập video nhiều clip (0.5.0 — bản thử)

Tab mới **Biên tập video** có timeline riêng, nhập nhiều media, cắt/chia/ghép,
track hình/tiếng, Undo/Redo và tự lưu. Không tự thay đổi dự án lồng tiếng cũ.
Xem [CAP_NHAT_0.5.md](CAP_NHAT_0.5.md) để biết cách dùng và giới hạn.

## Bản nguồn bổ sung editor ngày 03/10/2026 — chưa đóng gói

Cập nhật 06/10/2026: **Công cụ dựng → Căn khung thông minh · theo mặt** tạo đề xuất cho các clip đã chọn ở tỷ lệ 9:16/1:1/16:9/4:5. Có xem thử realtime không lưu, duyệt từng clip, áp dụng một lượt và Hoàn tác. Hướng dẫn/giới hạn: [TEST_CAN_KHUNG_THONG_MINH.md](TEST_CAN_KHUNG_THONG_MINH.md).

- Mở **Biên tập video**, chọn dự án và bấm **Mở**. Bấm clip sẽ tua đến đầu clip. Nhập file rồi bấm media để thêm; clip mới được chọn và hiện tại đúng thời gian của nó.
- Video không tương thích với bộ hiển thị được tạo bản xem WebM riêng một lần, lưu dưới `editor-media` của dự án. Đây là chuyển mã nguồn để xem, không phải render lại timeline. Lần đầu có thể phải chờ tùy thời lượng video/CPU. Audio/video nguồn vẫn được dùng khi xuất để giữ chất lượng.
- **↩ Xem realtime** trở về khung dựng trực tiếp nếu trước đó đã bấm **Xem chính xác**. Chỉnh vị trí, phóng to/thu nhỏ, xoay và độ hiện trong **Thuộc tính clip**; có thể kéo lớp trên video. **Đưa lớp lên/xuống** thay đổi thứ tự cả track; ảnh trên track video có thể dùng làm logo.
- **＋ Chữ** tạo chữ có thời gian riêng. Sửa nội dung, font, màu, cỡ chữ và nền hộp trong bảng thuộc tính. Chữ hiện ngay khi gõ.
- **＋ Vùng mờ** thêm mỗi vùng trên một track riêng, không ghi đè vùng trước. Kéo vùng trên hình để đặt vị trí; chỉnh rộng/cao/độ mờ trong thuộc tính. Kéo clip hoặc hai đầu clip trên timeline để chỉnh thời gian xuất hiện. Khóa/ẩn track nếu cần.
- **Nhập phụ đề dự án** sao chép trường lời đọc tiếng Việt từ các cue trong tab Lồng tiếng của cùng dự án, giữ thời gian; không sửa cue gốc. Cue chồng nhau được phân vào track khác. Kiểm tra cue trống, dưới 100 ms, vượt 60 phút trước khi nhập. Tổng giới hạn 500 clip, trong đó tối đa 100 clip media; tối đa 64 track.
- Preview realtime dùng trình duyệt; kiểu chữ/ngắt dòng và mức mờ có thể khác nhẹ so với FFmpeg. **Xem chính xác** vẫn dùng để đối chiếu cuối cùng, không cần dùng cho mỗi chỉnh sửa.
- Đây chỉ là sửa mã nguồn. Đóng và mở lại app **trong thư mục nguồn này** để nạp backend mới; bản đã cài từ bộ cài cũ không tự có thay đổi. Không có bộ cài hay ZIP phát hành mới trong đợt này.

### UI thu gọn và thao tác trực tiếp — bổ sung 03/10/2026

- Thư mục đầu ra không hiện ở đầu mỗi tab nữa. Vào **Cài đặt → Thư mục lưu trữ · mặc định và theo chức năng**, mở nhóm rồi chọn/nhập đường dẫn và bấm **Lưu** trên đúng hàng. Các đường dẫn đã đặt vẫn giữ nguyên; không di chuyển file cũ.
- Chọn clip trên timeline hoặc bấm lớp trên video. Bốn tay nắm vàng ở góc dùng zoom; nút tròn xanh dùng xoay. Giữ **Shift** khi kéo xoay để bắt góc 15°. Con lăn trên khung xem zoom lớp đang chọn; **Shift + con lăn** xoay. Không thao tác được với track đang khóa; tay nắm ẩn khi phát để không che video.
- Vùng mờ có tay nắm góc để đổi rộng/cao, không có xoay. Bấm **Vẽ vùng mờ**, kéo một hình chữ nhật trên khung xem rồi thả. Mỗi lần vẽ tạo một vùng/track mới, giữ các vùng trước đó. Thời gian mặc định bắt đầu tại con trỏ, dài 5 giây; kéo/trim clip vùng mờ trên timeline để đổi.
- Các nhóm **Thời gian & audio**, **Bố cục**, **Chữ / phụ đề**, **Vùng mờ** ở bảng thuộc tính có thể mở/thu gọn. Trạng thái thu gọn được nhớ trên máy.
- Kéo thanh phân cách ngay phía trên thanh công cụ timeline để chia lại chiều cao timeline/khung xem. Có thể dùng phím ↑/↓ khi thanh phân cách đang được chọn. Chiều cao được nhớ trên máy và giới hạn theo kích thước cửa sổ.
- Hàng timeline đã giảm từ 64 xuống 42 px. Waveform audio hiển thị phần tương ứng với điểm cắt nguồn, không kéo giãn toàn bộ waveform nguồn vào mọi đoạn cắt.

### Mở thư mục, chọn nhóm và preset bố cục — bổ sung 03/10/2026

- **📂 Mở thư mục lưu** nằm cạnh thanh phát của TTS, Clone, Lồng tiếng, Podcast, Đọc tài liệu; trong Biên tập video nằm dưới khung xem. Ưu tiên thư mục chứa kết quả đang hiển thị/vừa tạo của tab và dự án đang mở. Chưa có kết quả thì mở thư mục dự án (video) hoặc thư mục đầu ra đã cấu hình; mặc định là `data/outputs`. Kết quả cũ vẫn mở đúng nơi đã lưu, kể cả sau khi đổi mặc định.
- **Ctrl/Shift + bấm clip** để thêm/bỏ một clip khỏi nhóm. **Ctrl+A** chọn toàn bộ, **Esc** bỏ chọn khi không nhập văn bản. Viền vàng đậm và số clip cho biết nhóm đang chọn. Kéo thân một clip đã chọn để dịch cả nhóm giữ khoảng cách; kéo mép vẫn chỉ trim clip đó. Chỉnh bố cục trên canvas/thuộc tính vẫn áp dụng clip chính đang hiển thị, không tự đổi cả nhóm.
- **Dịch nhóm…** nhập số giây (âm để lùi) để căn chính xác. Không vượt mốc 0 hoặc 60 phút. Nếu vướng clip khác cùng track, thao tác bị chặn; có track khóa thì cả nhóm bị chặn. **Xóa clip** xóa cả nhóm; **Xóa dồn track** chỉ đóng các khoảng của clip đã xóa trên từng track, không tự dồn track khác. Một thao tác nhóm tương ứng một lần Hoàn tác.
- Mở **Preset bố cục** ở cột thuộc tính: chọn một clip video/chữ/vùng mờ, bấm **Lưu bố cục clip**, đặt tên. Chọn preset rồi **Áp dụng cho nhóm chọn**; nhóm phải cùng loại với preset và không khóa. Preset chỉ lưu vị trí, kích thước/scale, xoay, độ hiện hoặc kiểu chữ/độ mờ, không lưu nội dung, nguồn media hay thời gian. Các preset được lưu trên máy để dùng ở dự án khác; đặt cùng tên tạo mục mới, không ghi đè mục cũ.
- Đóng/mở lại launcher trong thư mục source để nạp backend mới. Không dùng bộ cài cũ để thử các thay đổi này.

### Video dài, nền và hòa trộn — bổ sung đợt tiếp theo 03/10/2026

- Timeline chỉ dựng các clip/vạch thời gian gần vùng đang xem; cuộn sang phần khác để thấy các clip tiếp theo. Clip ngoài vùng xem vẫn được lưu, chọn bằng Ctrl+A và xuất đầy đủ. Không giới hạn nội dung xuất theo vùng đang nhìn.
- Khi tua qua nhiều clip, bộ hiển thị chỉ giữ tối đa 8 lớp không hoạt động gần con trỏ, cộng các lớp đang hoạt động. Tua lại có thể cần chờ nạp khung hình nhưng không tự render toàn timeline.
- Proxy nguồn dài hơn 5 phút dùng cạnh tối đa 640 px / 24 fps; nguồn ngắn dùng 960 px / 30 fps. Không phóng lớn nguồn nhỏ. Tối đa 2 luồng mã hóa proxy. Bản xuất vẫn dùng file gốc, canvas và FPS dự án. Cache mới có tên `proxy-v2-*`; bản xem cũ không bị xóa, có thể tạo lại một lần khi cần.
- Nhập video sẽ tạo 16 thumbnail lấy mẫu trên toàn nguồn và cache theo dấu nguồn. Thumbnail trên clip chọn mẫu gần thời điểm nguồn tương ứng với điểm cắt và vị trí trong clip. Đây là hình đại diện lấy mẫu, không phải mọi khung hình chính xác; video rất dài có thể có các mẫu cách xa nhau. Chọn clip/tua để xem khung thật. Nhập nguồn dài vẫn có thể cần thời gian để tạo waveform và bản xem.
- Chọn clip ảnh/video → mở **Nền / lớp phủ / hòa trộn**. **Giữ toàn hình** không cắt viền; **Lấp đầy / cắt viền** phủ kín canvas, hữu ích khi chuyển ngang sang dọc. Kéo/zoom/xoay như trước.
- **Đặt làm nền dưới cùng** đưa cả track xuống đáy và đặt clip chính lấp đầy canvas. Các clip khác cùng track cũng thay thứ tự lớp, nhưng giữ bố cục riêng. Nếu track chứa cả video gốc, tạo track riêng cho nền trước. Ảnh/video trên các track phía trên là lớp phủ.
- **Screen** thích hợp hiệu ứng nền đen; **Multiply** thích hợp hình nền trắng; **Cộng sáng** cộng sáng các lớp. Dùng **Độ hiện** để giảm mức hiệu ứng; tắt tiếng track nếu không muốn trộn âm thanh của video hiệu ứng. Các chế độ có tác dụng cả realtime và FFmpeg; khác biệt màu/alpha giữa trình duyệt và codec vẫn cần đối chiếu bằng **Xem chính xác** trước xuất cuối.
- Fit/hòa trộn được lưu cùng timeline và preset video. Chưa có keyframe, crossfade giữa hai clip hoặc tracking AI trong đợt này.

### Bổ sung keyframe và fade — bản nguồn tiếp theo cùng ngày

Đã thêm **Keyframe vị trí · X/Y** cho ảnh/video, dấu mốc trên timeline, kéo/sửa X/Y
tại con trỏ để ghi mốc khi đã bật chuyển động, nội suy realtime và xuất FFmpeg.
Thêm **Hiệu ứng vào / ra** cho ảnh/video/audio/chữ và **Mờ nối clip sau qua nền**
cho hai clip liền nhau cùng track. Lưu/mở lại, Undo/Redo, chia/trim có giữ/rebase mốc.
Xem [TEST_KEYFRAME_CHUYEN_CANH.md](TEST_KEYFRAME_CHUYEN_CANH.md) để thử từng bước.
Đây là fade qua nền, chưa phải crossfade chồng clip; keyframe zoom/xoay chưa có.
Chỉ sửa bản nguồn; chưa build bộ cài.

### Giao diện gọn và kiểu chuyển động X/Y

Bổ sung tiếp: bảng thuộc tính giữ vị trí cuộn khi chỉnh; có tốc độ video/audio
0,25–4× giữ cao độ, lật ngang/dọc cả clip hoặc theo đoạn. Hướng dẫn thử chi tiết:
[TEST_TOC_DO_LAT_HINH.md](TEST_TOC_DO_LAT_HINH.md). Chỉ sửa nguồn, chưa đóng gói.

- Thư viện media: bấm **＋** ở cạnh tiêu đề để chọn một hoặc nhiều file. Có thể dùng Tab rồi Enter/Space.
- Bảng thuộc tính đã giảm khoảng cách giữa các nhóm và trường; các nhóm vẫn mở/thu gọn như trước.
- Trong **Keyframe · bố cục**, chọn **Kiểu chuyển động**: **Đều**, **Mềm đầu/cuối**, hoặc **Giữ rồi đổi vị trí**. Realtime và bản xuất dùng cùng lựa chọn; mốc hỗ trợ X/Y/zoom/xoay/độ hiện.
- Với **Mềm đầu/cuối**, chia/trim giữ chính xác đoạn của đường cong cũ cho X/Y/zoom/xoay/độ hiện, có thể lưu/mở lại và cắt tiếp. Không cần đổi về Đều.

### Tải media, dựng 4K và preset nhiều track

Đã thêm tab **Tải video / audio**, danh sách tải và chuyển nhanh tạo dự án mới sang Lồng tiếng/Biên tập; video tải xong render MP4, audio MP3. Các tab dựng có lựa chọn xuất 2K/4K. Upscale không tạo chi tiết mới. Downloader dùng yt-dlp, có cookies Netscape tùy chọn; không vượt DRM.

Editor có crossfade/wipe chồng thật trên track riêng, speed curve mượt hoặc chế độ 5 đoạn riêng, preset nhiều track cục bộ và tách giọng/nhạc AI vào thư viện editor. Hướng dẫn thao tác/giới hạn/kiểm thử: [TEST_TAI_4K_KEYFRAME_PRESET.md](TEST_TAI_4K_KEYFRAME_PRESET.md), [TEST_CURVE_MUOT.md](TEST_CURVE_MUOT.md).

Đã thêm nhóm **AI · hình ảnh**: căn mặt/tracking theo mẫu (~1s, clip tối đa 60s) và tách nền PNG/WebM alpha vào thư viện riêng. Máy hiện tại đã cài vision-env/model; máy khác dùng INSTALL_VISION.bat. Tách nền video CPU giới hạn 15s nguồn/720px/12fps, không audio; ảnh tối đa 1536px. Xem [TEST_AI_HINH_SMOOTH.md](TEST_AI_HINH_SMOOTH.md) trước khi dùng. Chưa nghiệm thu tracking nhiều người/đổi cảnh, mask theo thời gian/video dài/GPU/Windows sạch. Chưa đóng gói.

### Kho sáng tạo trực quan

Trong Biên tập video, bấm **✦ Kho sáng tạo** tại thư viện media: 8 lựa chọn màu, 36 nhãn dán Twemoji/Fluent và 11 lớp phép thuật động. Bộ lọc đổi ngay clip đang chọn; chỉnh cường độ tại thuộc tính. Nhãn dán/phép thuật thêm track riêng ở con trỏ, kéo/zoom/xoay/trim và Hoàn tác. Tài nguyên dùng offline, không phải tài nguyên CapCut. Video có nhãn dán cần giữ thông tin ghi công trong ATTRIBUTION.txt cạnh bản xuất. Xem [TEST_KHO_SANG_TAO.md](TEST_KHO_SANG_TAO.md).

### Công cụ dựng — năm nhóm bản thử

Bấm **✦ Công cụ dựng** dưới thư viện để mở Phòng sáng tạo: phong cách chữ động, phân tích nhịp/cảnh và duyệt cắt, vẽ vùng bám vật thể rồi thêm vùng mờ/sticker, Comic Freeze, sóng âm podcast, xuất đa tỷ lệ, encoder CPU/GPU thử nghiệm, benchmark đoạn ngắn và xuất/nhập dự án dữ liệu .rvp. Hướng dẫn/checklist/giới hạn: [TEST_PHONG_SANG_TAO.md](TEST_PHONG_SANG_TAO.md). Chưa đóng gói, chưa nghiệm thu GPU/video dài trên máy thật, không coi phiên bản cơ bản là toàn bộ khả năng nâng cao.

### Cập nhật: karaoke theo mốc audio

Biên tập video → chọn clip có audio → ✦ Công cụ dựng → Nhận dạng & duyệt từng từ. Sau duyệt, chọn dùng lại track chữ có khoảng trống hoặc tạo track mới; không sửa phụ đề cũ. Hướng dẫn/test và giới hạn: [TEST_CAN_CHU_AUDIO.md](TEST_CAN_CHU_AUDIO.md).

### Xóa phụ đề gốc bằng VSR

Tab Xóa phụ đề gốc kết nối bộ VSR riêng, vẽ nhiều vùng trực tiếp trên video, giữ/tạo SRT trước khi xóa và chuyển video sạch + SRT sang dự án Lồng tiếng/Biên tập mới. Mục Tải video/audio có lựa chọn lấy SRT nền tảng trước render và chuyển một video đã chọn sang tab mới. Chưa cài VSR/model, chưa nghiệm thu chất lượng xóa AI. Xem [TEST_XOA_PHU_DE_GOC.md](TEST_XOA_PHU_DE_GOC.md).

