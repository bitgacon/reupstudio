# TTS đa ngôn ngữ và diễn xuất — bản phát triển 08/10/2026

Chưa đóng gói bộ cài mới. Đóng/mở lại app đang chạy từ thư mục mã nguồn để nhận giao diện mới; không cần xóa dữ liệu cũ.

## Thử theo thứ tự

1. Vào **Văn bản → Giọng nói**, mở **Bộ TTS · ngôn ngữ & diễn xuất**. VieNeu vẫn giữ các giọng tiếng Việt đã có.
2. Vào **⚙ → Thư viện tùy chọn**, chọn thư mục cài và bấm **Tải / cài TTS Kokoro**. Cần khoảng 2 GB trống (model và giọng khoảng 354 MB, phần còn lại là runtime). Chỉ khi bấm cài mới tải; cài xong tự nối danh sách giọng. Chọn English US/UK, nhập một câu tiếng Anh và bấm **Nghe thử đoạn đầu**.
3. Muốn đa ngôn ngữ/biểu cảm mạnh, cài **Chatterbox** (cần khoảng 12 GB trống). Chọn CPU hoặc NVIDIA CUDA ở **TTS đa ngôn ngữ · API & thiết bị** trước khi cài. Chatterbox hiện chọn Bình thường/Biểu cảm mạnh, không hứa điều khiển chính xác vui/buồn.
4. Muốn **ElevenLabs**, nhập key riêng tại **⚙ → TTS đa ngôn ngữ**, lưu, chọn ElevenLabs rồi bấm **Nạp giọng**. Đây là API chính thức, không phải miễn phí vô hạn. Chỉ gửi lời đọc khi bạn tích cho phép và bấm tạo/nghe thử; mỗi yêu cầu có thể tốn credit. Không tự thử lại/đổi key khi hết quota. Eleven v3 nhận thẻ diễn xuất; Multilingual v2 chỉ dùng Bình thường trong tích hợp này.
5. Cài **Qwen3-TTS CustomVoice 1.7B** (cần khoảng 15 GB trống), chọn giọng, cảm xúc hoặc mô tả cách đọc. Nên dùng GPU NVIDIA phù hợp; CPU có thể rất chậm. Cảm xúc là hướng dẫn cho model, không bảo đảm mọi câu đạt sắc thái giống nhau.

Không tự tải model khi chọn một bộ TTS hoặc mở dự án. Runtime local tách khỏi VieNeu, inference đặt chế độ offline. Bộ cài chỉ được đăng ký sau khi tạo câu thử thật và kiểm tra lại trong tiến trình offline riêng; thiếu DLL/model/dependency sẽ báo lỗi thay vì ghi nhận cài thành công. Tải lại tạo runtime ứng viên mới, không sửa bộ đang hoạt động trước khi ứng viên vượt kiểm tra.

## Ngôn ngữ hiện có trong giao diện

| Bộ | Ngôn ngữ |
|---|---|
| VieNeu | Việt |
| Kokoro | Anh US/UK, Tây Ban Nha, Pháp, Hindi, Ý, Nhật, Bồ Đào Nha, Trung |
| Chatterbox | Anh, Trung, Nhật, Hàn, Pháp, Đức, Tây Ban Nha, Bồ Đào Nha, Ý, Nga, Hindi (tập ngôn ngữ phổ biến đang đưa vào UI) |
| ElevenLabs | Việt và nhóm phổ biến trên; còn phụ thuộc giọng/model/tài khoản |
| Qwen3 | Anh, Trung, Nhật, Hàn, Pháp, Đức, Tây Ban Nha, Bồ Đào Nha, Ý, Nga |

Chọn ngôn ngữ TTS không tự dịch văn bản. Nhập lời đọc đúng ngôn ngữ; tiếng Việt vẫn ưu tiên VieNeu. Kokoro không có nút điều khiển cảm xúc thật nên tùy chọn diễn xuất bị khóa.

## Lồng tiếng từng cue

- Mục **Giọng đa ngôn ngữ / diễn xuất dự án** đặt bộ/giọng mặc định cho cue kế thừa.
- Nút **Giọng / diễn xuất** trên từng cue đặt riêng; có thể trở về mặc định dự án.
- Bấm **Áp dụng**, rồi **Lưu thay đổi**. Lựa chọn đi cùng dự án, không sửa chữ phụ đề.
- Đổi bộ/giọng/diễn xuất làm audio cũ của cue đó hết hiệu lực; **Tạo / Tiếp tục** tái sử dụng cue còn đúng phiên bản. **Tạo lại** chủ động yêu cầu tạo mới.
- Nút **Nghe tốc độ xuất** dùng audio đã căn thực tế. Ước tính trước khi tạo vẫn là ước tính theo luật, không phải thời lượng chính xác của từng model/ngôn ngữ.

## Hội thoại / Podcast nhiều ngôn ngữ

Trong **Hội thoại / Podcast**, nhập kịch bản dạng `[Alice]: Hello` / `[Khách]: Xin chào`, rồi bấm **Giọng / ngôn ngữ** cạnh từng nhân vật. Mỗi người có thể chọn VieNeu, Kokoro, Chatterbox, ElevenLabs hoặc Qwen3 với ngôn ngữ, giọng và diễn xuất riêng. Bấm **Lưu giọng nhân vật** để giữ lựa chọn trên trình duyệt/app đang dùng; các gán giọng VieNeu cũ vẫn được giữ. Đây là cấu hình podcast lưu cùng kịch bản trên trình duyệt, không phải dự án lồng tiếng.

Nút **▶** cạnh nhân vật nghe thử tối đa 120 ký tự từ lượt thoại đầu của người đó. **Tạo audio hội thoại** ghép toàn bộ lượt đọc, giữ nguyên chữ SRT, tốc độ và khoảng nghỉ. Một bộ TTS local được nạp/reuse trong tác vụ, không nạp lại cho mỗi nhân vật cùng bộ. Khi dùng nhiều bộ nặng có thể tốn thêm RAM. Qwen3 CPU vẫn chậm; tích hợp podcast không tự làm model nhanh hơn.

Văn bản không tự dịch khi đổi ngôn ngữ: nhập lời thoại đúng ngôn ngữ của nhân vật. App kiểm tra cấu hình các nhân vật có lời thoại trước khi nạp model/gửi API; không bắt cấu hình nhân vật không có trong kịch bản. ElevenLabs cần key và cho phép gửi lời đọc riêng cho người dùng bộ cloud; nghe thử cũng có thể tính credit. Không tự tải/cài khi tạo podcast.

Hiện các bộ mới nối vào tab TTS, các cue lồng tiếng và từng nhân vật podcast. Voice Clone/Đọc tài liệu vẫn giữ luồng VieNeu; chưa có clone đa engine trong các tab này.

## Quyền riêng tư / giấy phép / trạng thái kiểm thử

Key ElevenLabs chỉ lưu trong `data/tts-provider-settings.json`, không trả về trình duyệt, không ghi vào dự án hoặc payload worker. Giọng cloud chỉ gọi endpoint chính thức ElevenLabs. Không tích hợp endpoint riêng của CapCut; có thể nhập file audio được phép sử dụng do CapCut xuất vào tab biên tập.

Kokoro model Apache-2.0, các dependency có giấy phép riêng (đặc biệt eSpeak-NG). Chatterbox giữ watermark của upstream. ElevenLabs free có hạn mức và điều kiện thương mại riêng; không đồng nghĩa free có quyền thương mại. Kiểm tra giấy phép và quyền sử dụng giọng/mẫu trước khi phát hành nội dung.

Đã kiểm tra hợp đồng provider bằng model giả, luồng WAV/MP3/SRT bằng FFmpeg thật, lưu/mở lại cue và điều khiển UI trong Qt. **Chưa tải/cài các model mới trên máy này, chưa nghe xác nhận chất lượng local, chưa gọi tạo audio ElevenLabs bằng tài khoản thật.** Các vấn đề tương thích Windows/GPU hoặc biểu cảm cần kiểm tra khi người dùng bấm cài/thử. Không coi kiểm thử mock là nghiệm thu chất lượng AI.

## Nguồn chính thức

- Kokoro ONNX: https://github.com/thewh1teagle/kokoro-onnx ; model: https://huggingface.co/hexgrad/Kokoro-82M
- Chatterbox: https://github.com/resemble-ai/chatterbox
- ElevenLabs API: https://elevenlabs.io/docs/api-reference/text-to-speech/convert ; giá/hạn mức: https://elevenlabs.io/pricing
- Qwen3-TTS: https://github.com/QwenLM/Qwen3-TTS ; model: https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
