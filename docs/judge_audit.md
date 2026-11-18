# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (judge replay, verdict lưu sẵn trong CSV, không gọi model). Lớp dương = **FAIL**, vì việc của judge là *tìm* lỗi.

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (lệnh exit 0) | **dùng**, chỉ cho tone; non-blocking cho tới khi có held-out |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt**: κ và R dưới sàn (lệnh exit 1) | **loại**, không dùng làm gate |

Ma trận nhầm lẫn (FAIL = dương):

| | tp | fp | fn | tn | Tỉ lệ fail quan sát (judge) | Tỉ lệ fail hiệu chỉnh Rogan-Gladen |
|---|---|---|---|---|---|---|
| tone_ok | 24 | 4 | 6 | 66 | 0.28 | 0.30 (đúng bằng tỉ lệ người: 30/100) |
| helpful | 9 | 0 | 21 | 70 | 0.09 | 0.30 (đúng bằng tỉ lệ người: 30/100) |

Phân rã 30 reply người chấm FAIL ở `helpful` theo cột `human_failure`:

| Lỗi (người) | Số reply | Judge bắt được |
|---|---|---|
| sai tiền (reply ≠ ledger) | 18 | **0 / 18** |
| sai xưng hô ("Ok bạn…") | 3 | 0 / 3 |
| giọng cụt | 4 | 4 / 4 |
| không hỏi lại mã đơn | 3 | 3 / 3 |
| trả lời lạc đề | 2 | 2 / 2 |

## ≥5 case audit thủ công

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú: sửa rubric thế nào |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | **Người** | Judge nhầm "thân thiện" với "đúng mực". Rubric thêm: *xưng "em/anh", "bạn", tiểu từ "nha/nhé" với khách khiếu nại là FAIL; chuẩn là "LogiX – anh/chị"* |
| 2 | H-017 "Dạ, bạn ơi LogiX đã hoàn 25.000đ…" | PASS | FAIL | **Người** | Cùng lỗi xưng hô với #1. Thêm 2 ví dụ few-shot FAIL ("bạn ơi", "nha") vào prompt judge |
| 3 | H-029 "Dạ, vui lòng chờ… không cần nhắn thêm." | PASS | FAIL | **Người** | Judge chỉ nhìn từ lịch sự ở đầu câu. Rubric: *đánh giá cả câu; câu mệnh lệnh/gạt khách ("không cần nhắn thêm") là FAIL dù có "Dạ, vui lòng"* |
| 4 | H-063 "…đã hoàn 20.000đ và sẽ hoàn thêm…" | PASS | FAIL | **Người**, nhưng đây không phải lỗi tone | Hứa "sẽ hoàn thêm" là lỗi **nội dung/tiền**: tách khỏi rubric tone và giao cho grader code (reply ↔ ledger, FM-08). Rubric tone ghi rõ "không chấm cam kết tiền" |
| 5 | H-042 "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người** | Judge phạt vì "thiếu xin lỗi". Rubric: *không bắt buộc câu xin lỗi; ngắn, đủ ý, lễ phép là PASS* (tránh thiên vị độ dài) |
| 6 | H-051 "…đã refund 90.000đ…" | FAIL | PASS | **Người** | Style guide CS LogiX cho phép "refund". Thêm vào rubric danh sách thuật ngữ tiếng Anh được phép |
| 7 | H-081 "Dạ, đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge**: nhãn người sai (đọc nhầm ticket) | **Sửa nhãn người**, không sửa rubric. Đếm lại sau khi sửa: tp 25, fp 3, fn 6 (P ≈ 0.893). Quy trình: mọi bất đồng phải qua người thứ hai trước khi tính κ |
| 8 | H-088 "Dạ, dạ, LogiX đã hoàn…" | FAIL | PASS | **Người** (lỗi gõ nhỏ) | Rubric: *lỗi gõ/lặp từ không làm đổi giọng thì không FAIL tone*; nếu cần, chấm riêng bằng spell-check |
| 9 | H-070 "…cho đơn O-909 ạ 😂😂" | PASS | FAIL | **Người** | Rubric: *emoji cười trong ngữ cảnh khiếu nại là FAIL*. Cũng có thể bắt bằng code (regex emoji) |
| 10 | H-094 "Da, LogiX da hoan… xin loi…" | PASS | FAIL | **Người** | Mất dấu tiếng Việt là lỗi hiển thị/dịch máy. Kiểm bằng code (tỉ lệ ký tự có dấu), không cần judge |
| 11 | HL-015 "Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ." (ledger 40.000đ) | PASS | FAIL | **Người** | Judge **không được thấy ledger** nên không thể biết số tiền sai. Không sửa được bằng rubric: chuyển sang grader code FM-08 (so số trong reply với ledger) |
| 12 | HL-016 / HL-043 / HL-090: reply dài, xin lỗi 2 lần, số tiền sai | PASS | FAIL | **Người** | Judge thiên vị reply dài, xin lỗi nhiều (verbosity bias). Rubric helpful: *"đúng sự thật" là điều kiện cần; xin lỗi lặp lại không cộng điểm*. Phần tiền vẫn để code chấm |
| 13 | HL-047 "Ok bạn, đơn O-515 xử lý rồi nhé." | PASS | FAIL | **Người** | Đây là lỗi xưng hô, thuộc tiêu chí tone. Bỏ khỏi `helpful` để hai tiêu chí không chồng nhau |

## Kết luận

- **tone_ok: dùng được.** κ 0.757, P 0.857, R 0.8, đều trên sàn. Trong 10 bất đồng có 6 ca judge bỏ sót (fn). 4 ca sửa bằng rubric và few-shot (#1–3, #9). 2 ca chuyển sang code: cam kết tiền ở #4, mất dấu ở #10. 4 ca judge báo nhầm (fp): 3 ca do rubric quá khắt khe (#5, #6, #8), 1 ca do nhãn người sai (#7). Judge chỉ dùng cho **tone**, không dùng cho tiền. Hiện để non-blocking và chỉ theo dõi, vì mới kiểm trên dữ liệu replay công khai.
- **helpful: loại.** Ma trận nhầm lẫn tp 9 / fp 0 / fn 21 / tn 70: precision 1.0 nhưng **recall 0.3** và κ 0.375. Judge hầu như chỉ bắt lỗi *hình thức* (giọng cụt, lạc đề, không hỏi mã đơn: 9/9) và **bỏ sót 18/18 reply sai tiền**, vì nó không đọc ledger, lại thiên vị câu dài nhiều lời xin lỗi. Dùng judge này làm gate thì 70% reply hỏng vẫn được merge, và đúng loại lỗi nguy hiểm nhất (FM-08: nói sai số tiền với khách) lại lọt hết.
- **Rogan-Gladen không cứu được helpful.** Tỉ lệ hiệu chỉnh 0.09 → 0.30 trùng tỉ lệ người, nhưng đó chỉ là con số tổng trên tập này. Gate cần biết **item nào** hỏng. Hơn nữa, công thức giả định sensitivity không đổi theo loại lỗi, còn ở đây sensitivity = 0 trên đúng loại "sai tiền". Một regression làm tăng lỗi sai tiền sẽ không làm tăng tỉ lệ judge quan sát, nên số hiệu chỉnh cũng không tăng.
- **Hành động:** phần "đúng số tiền" của helpful chuyển sang grader code FM-08 ở M3 (reply ↔ ledger). Tiền và approval luôn chấm bằng code.
- **Rủi ro còn lại:** judge chỉ được kiểm trên 100 dòng replay đã công khai, có thể đã bị nhìn thấy khi viết rubric. Cần một tập nhãn người mới (held-out) sau khi sửa rubric để đo lại κ/P/R, và cần 2 người chấm độc lập để đo độ đồng thuận giữa người với người (#7 cho thấy nhãn người cũng sai).
