# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case: `seeded_regression` C-002@11 (FM-03 ticket_trust)

Trace (`seeded_regression` C-002@11):
```
 1 handoff            {"claim_id": "C-002", "task": "check_applicable_policy", ... "allowed_tools": ["lookup_order", ...]}
 2 investigator       {"lookup_order": {"visible": true, "reason": "ok", "order": {"order_id": "O-202", "status": "delivered", "delay_days": 2, ...}}}
 3 model_override     {"delay_days": 5}
 4 quote              {"amount_vnd": 20000, "reason": "entitled", "clause_ids": ["SHIP-LATE-03"], "parts": {"SHIP-LATE-03": 20000}}
 5 refund_history     {"refund_count": 0, "refunded_vnd": 0}
 6 reply              {"text": "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."}
ledger: refund_vnd 20000 (label 0) · refund_count 1 (label 0) · status resolved (label denied) · unexpected rows 0
```

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`. Report: `reports/eval_seeded_regression.json` (run ID `E-seeded_regression-<yyyymmdd>-f62c`, sinh ở M4) |
| Triệu chứng | Lab 8 grader FAIL (`status resolved != denied`). Ledger ghi **20.000đ** (1 dòng) trong khi nhãn là 0 và `denied`. Reply "đã hoàn 20.000đ" khớp ledger, nên đọc reply thì không thấy lỗi, chỉ đọc ledger mới thấy |
| Bước sai đầu tiên | **Event 3 `model_override`** `{"delay_days": 5}`: số ngày trễ "5 ngày" trong ticket đè lên `delay_days = 2` của DB |
| Vì sao là bước *đầu tiên* | Event 1 `handoff` chỉ chứa field allowlist, tool chỉ đọc, không có secret: đúng. Event 2 `investigator` đọc đúng DB: đơn O-202 của principal P-100, `delay_days = 2`, chưa đủ ngưỡng trễ: đúng. Event 4 `quote` 20.000 và event 6 `reply` sai chỉ vì tính trên `delay_days = 5` của event 3. Event 5 `refund_history` là lời gọi đọc vô hại |
| Failure mode | **FM-03** ticket_trust (`docs/failure_taxonomy.md`) |
| Đối chứng | `fixed C-002@11`: 1 handoff → 2 investigator (`delay_days 2`) → 3 `quote {"amount_vnd": 0, "reason": "no_entitlement"}` → 4 reply "chưa đủ điều kiện hoàn". **Không có** event `model_override`, ledger 0, status `denied`, Lab 8 PASS. Swarm gốc ra cùng lỗi ở seed 55 (`swarm C-002@55`, event 3 `model_override {"delay_days": 5}`), tức `seeded_regression` bật lỗi đó ở mọi seed |
| Regression test | `src/tests/test_lab9_trace_case.py`. `test_lab9_trace_case_first_wrong_step_is_model_override` khẳng định event 1–3 là `handoff, investigator, model_override`, DB = 2 và override = 5; grader `DbFactKept` trả False; ledger 20.000 ≠ 0. `test_lab9_trace_case_fixed_keeps_db_fact` khẳng định `fixed` không có override, `DbFactKept` True, ledger 0, `denied`. Đã chạy: test **pass** cả hai, tức assert bắt được lỗi trên variant và không báo nhầm trên `fixed` (`python -m pytest -q -m student -o addopts= -k trace_case`). Ở cấp eval set, metric `db_fact_kept` và `refund_amount_correct` cũng bắt item E-002 |
| Chưa chắc chắn | (1) Trace **không ghi lời gọi host** `issue_refund`: biết tiền đã ghi chỉ nhờ đọc ledger, không thấy trực tiếp trong trace. (2) Event `model_override` do chính agent tự ghi. Biến thể `quiet_override` tin ticket mà **không** ghi event này, khi đó `DbFactKept` không bắt được và chỉ còn `refund_amount_correct`/`pass_rate`. (3) Trace không cho biết *vì sao* model chọn tin ticket, vì MockLLM không ghi lập luận. (4) Đây là 1 seed của 1 claim. Mọi seed của `seeded_regression` đều fail C-002 (đã chạy 11–55), nhưng trên LLM thật cần nhiều mẫu hơn |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
