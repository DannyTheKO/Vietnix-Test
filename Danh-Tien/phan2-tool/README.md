# Phần 2 - Tool phân tích tải cluster Proxmox VE

Tool đọc snapshot `cluster-pve-hcm-c3.json` (xuất từ `/cluster/resources`), tính mức tải
từng node, đánh dấu node quá tải và đề xuất kế hoạch live-migrate. Output có 2 dạng:
bảng cho người đọc và JSON cho script/cron.

Chỉ dùng thư viện chuẩn của Python, không cần `pip install` gì.

## Yêu cầu

- Python 3.10 trở lên (đã chạy thử với 3.14).
- Không có dependency ngoài.

## Cấu trúc

```
phan2-tool/
  data/
    cluster-pve-hcm-c3.json    # snapshot của đề
  pve_balance/
    loader.py                  # đọc JSON, kiểm tra và chuẩn hoá bản ghi
    models.py                  # Node, VM, NodeLoad, Thresholds...
    metrics.py                 # tính tải node + kiểm tra ngưỡng
    planner.py                 # lập kế hoạch migrate
    report.py                  # xuất bảng / JSON
    cli.py                     # tham số dòng lệnh
    __main__.py                # python -m pve_balance
  tests/                       # unit test + test tích hợp
  README.md
```

## Cách dùng

```bash
cd phan2-tool

# Bảng trên terminal (mặc định đọc data/cluster-pve-hcm-c3.json)
python -m pve_balance

# JSON để pipe sang tool khác
python -m pve_balance -f json

# Đổi ngưỡng
python -m pve_balance --cpu-threshold 75 --mem-threshold 80 --overcommit-threshold 1.8

# Dùng cho cron/CI: exit 1 nếu có node quá tải
python -m pve_balance --fail-on-overload

# Đọc file khác
python -m pve_balance -i /duong/dan/snapshot.json
```

| Tham số | Ý nghĩa | Mặc định |
| --- | --- | --- |
| `-i, --input` | File JSON đầu vào | `data/cluster-pve-hcm-c3.json` |
| `-f, --format` | `table` hoặc `json` | `table` |
| `--cpu-threshold` | % CPU coi là quá tải | `80` |
| `--mem-threshold` | % RAM coi là quá tải | `85` |
| `--overcommit-threshold` | Tỷ lệ vCPU/core coi là rủi ro | `2.0` |
| `--fail-on-overload` | Exit code 1 nếu có node quá tải | tắt |
| `-v, --verbose` | In cảnh báo dữ liệu ra stderr | tắt |

### Exit code

| Code | Ý nghĩa |
| --- | --- |
| `0` | Báo cáo tạo thành công |
| `1` | Có `--fail-on-overload` và có node quá tải |
| `2` | Dữ liệu không hợp lệ (thiếu file, JSON hỏng, thiếu `nodes`/`vms`) |

## Output mẫu (dữ liệu của đề)

```
Proxmox VE cluster load report
Cluster  : pve-hcm-c3
Snapshot : 2026-10-27T09:00:00+07:00
Thresholds: CPU >= 80.0% | RAM >= 85.0% | vCPU overcommit >= 2.00

+------------+---------+-------+------+------+----------------+----------------+------+
|    Node    |  Status | Cores | vCPU |  OC  |      CPU       |      RAM       | Flag |
+------------+---------+-------+------+------+----------------+----------------+------+
| hcm-c3-n01 | online  |    64 |  110 | 1.72 | 85.9% #######- | 93.0% #######- | OVER |
| hcm-c3-n02 | online  |    64 |   80 | 1.25 | 39.1% ###----- | 55.0% ####---- |  ok  |
| hcm-c3-n03 | online  |    48 |   80 | 1.67 | 38.0% ###----- | 47.0% ####---- |  ok  |
| hcm-c3-n04 | offline |    48 |    0 | 0.00 | 0.0% --------  | 0.0% --------  | off  |
| hcm-c3-n05 | online  |    64 |   72 | 1.12 | 78.9% ######-- | 71.9% ######-- | risk |
| hcm-c3-n06 | online  |    32 |   94 | 2.94 | 30.0% ##------ | n/a --------   | risk |
+------------+---------+-------+------+------+----------------+----------------+------+

OVERLOADED NODES
  hcm-c3-n01: CPU 85.9% >= 80.0%; RAM 93.0% >= 85.0%

MIGRATION PLAN (greedy, dry-run)
  #1 vmid 2054 (cloud-std-657): hcm-c3-n01 -> hcm-c3-n03 [8 vCPU, 62.0 GiB]
     hcm-c3-n01: CPU 85.9% | RAM 93.0% | OC 1.72  =>  CPU 74.1% | RAM 80.9% | OC 1.59
     hcm-c3-n03: CPU 38.0% | RAM 47.0% | OC 1.67  =>  CPU 53.8% | RAM 63.1% | OC 1.83
```

Phần `DATA WARNINGS` ở cuối báo các bản ghi bất thường (xem mục dưới).
`-f json` cho ra cùng dữ liệu ở dạng máy đọc; cảnh báo nằm trong `data_warnings`
để stdout vẫn là JSON hợp lệ khi pipe.

## Công thức

Chỉ VM `status = running` được tính vào tải hiện tại.

```
node CPU %      = sum(vcpus * cpu_usage) / cpu_cores * 100
node RAM %      = sum(mem_used) / mem_total * 100
vCPU overcommit = sum(vcpus) / cpu_cores
```

Vì sao nhân `vcpus`? `cpu_usage` là tỷ lệ trên **số vCPU được cấp**, không phải trên
toàn bộ core của node. Một VM 8 vCPU dùng `0.25` tức là chiếm 2 core vật lý.

## Ngưỡng mặc định và lý do

| Ngưỡng | Giá trị | Lý do |
| --- | --- | --- |
| CPU | 80% | Trên 80% hàng đợi scheduler bắt đầu dài, live-migrate cũng cần CPU để copy RAM |
| RAM | 85% | Proxmox/KVM cần chỗ cho page cache, ballooning và bộ nhớ đệm khi migrate |
| Overcommit | 2.0 | vCPU là tài nguyên chia sẻ; cấp quá 2x core thì khi tải thật tăng sẽ tranh chấp mạnh |

Đây là **giả định**, không phải chân lý. Có thể đổi bằng tham số dòng lệnh; khi nộp bài
nên nêu rõ ngưỡng đã chọn.

Cách đánh dấu:

- **OVER**: vượt ngưỡng CPU hoặc RAM -> node quá tải thật.
- **risk**: chưa vượt CPU/RAM nhưng overcommit >= 2.0, hoặc thiếu dữ liệu RAM.
- **off**: node offline.
- Overcommit **một mình không** làm node bị coi là quá tải, vì overcommit cao nhưng
  CPU/RAM thấp thì chưa ảnh hưởng ngay. Tuy vậy tool **không chọn node đó làm đích**
  nếu sau khi nhận VM sẽ vượt ngưỡng overcommit.

## Dữ liệu bẩn trong snapshot và cách xử lý

| Bản ghi | Vấn đề | Cách xử lý |
| --- | --- | --- |
| vmid 2067, 2073, 2065 | `cpu_usage` = 31.0 / 98.0 / 20.8, vượt thang 0-1 | Hiểu là %, chia 100, có cảnh báo (tiếng Anh: "normalised to ...") |
| node `hcm-c3-n06` | `mem_total` = 262144 byte (quá nhỏ) | Bỏ trống, không tính % RAM, không cho làm đích migrate |
| vmid 2001 | Xuất hiện ở cả n01 và n02 | Giữ bản ghi đầu, bỏ bản ghi sau, có cảnh báo |
| VM 2390 | Thuộc node `hcm-c3-n07` không tồn tại | Cảnh báo, không cộng vào tải node nào |
| vmid 2199 | `mem_used = null` | Coi là chưa biết, không cộng RAM, không chọn để migrate |
| node `hcm-c3-n04` | `offline` | Không làm đích migrate |
| VM `stopped` | Không dùng tài nguyên | Không tính vào tải, nhưng đếm riêng vCPU/RAM đã cấp |

Nguyên tắc chung: **không bịa số**. Thiếu dữ liệu thì để `null`/bỏ trống và cảnh báo,
không tự thay bằng 0 rồi coi như sự thật. Riêng tổng RAM đã dùng thì cộng 0 cho VM
`null` (để vẫn có số tối thiểu) nhưng đánh dấu `unknown_mem_vms` để người đọc biết.

Lưu ý: cảnh báo trong code và JSON được viết bằng tiếng Anh (ví dụ
`"cpu_usage=31 outside 0..1 range, interpreted as 31% and normalised to 0.31"`),
để tool dùng được trong môi trường quốc tế.

## Thuật toán migrate

Greedy, chạy từng bước, không tối ưu toàn cục:

1. Tính tải tất cả node; lấy các node đang quá tải, xử lý node nặng nhất trước.
2. Với node nguồn, thử từng VM đang chạy x từng node đích.
3. Nước đi hợp lệ khi:
   - đích đang `online`,
   - đích có `cpu_cores` và `mem_total` hợp lệ,
   - sau khi nhận VM, đích vẫn dưới **cả ba** ngưỡng (CPU, RAM, overcommit),
   - nguồn giảm tải.
4. Ưu tiên: gỡ quá tải ngay -> giảm tải nguồn nhiều nhất -> đích nhẹ nhất.
5. Lặp tới khi hết node quá tải hoặc không còn nước đi an toàn.

Kết quả in kèm before/after của cả nguồn và đích để người vận hành kiểm tra.

Hạn chế đã biết:

- Không phải lời giải tối ưu (bin-packing là bài toán NP-hard). Greedy đủ nhanh và dễ giải thích.
- Chưa tính affinity/anti-affinity, ổ đĩa local, băng thông migrate, giờ cao điểm.
- Live-migrate thật cần shared storage hoặc
  `qm migrate <vmid> <node> --online --with-local-disks`; tool chỉ đề xuất, không gọi API.
- Nếu dữ liệu RAM của VM là `null`, hoặc node thiếu `mem_total`, tool không migrate vì
  không chứng minh được đích an toàn.

## Chạy test

```bash
cd phan2-tool
python -m unittest discover -s tests -t . -v
```

37 test, gồm:

- `test_loader.py`: chuẩn hoá %, trùng vmid, `mem_total` lỗi, `mem_used` null, JSON hỏng...
- `test_metrics.py`: công thức CPU/RAM/overcommit, VM stopped, node offline, đúng ngưỡng.
- `test_planner.py`: gỡ quá tải, không đẩy đích quá tải, đích offline, overcommit, tính lặp lại được.
- `test_report.py`: cấu trúc JSON, nội dung bảng.
- `test_integration.py`: chạy trên chính snapshot của đề + chạy CLI thật.

## Đọc code theo thứ tự (nếu muốn học)

1. `models.py` - các kiểu dữ liệu, `NodeLoad` tính % bằng property.
2. `loader.py` - kiểm tra dữ liệu từng bản ghi và ghi cảnh báo thay vì crash.
3. `metrics.py` - công thức tải; để ý chỉ VM `running` được tính.
4. `planner.py` - mô phỏng bằng `_NodeState`, hàm `_can_host` là điều kiện an toàn.
5. `report.py` - tách dữ liệu (`to_json_dict`) khỏi trình bày (`render_text`).
6. `cli.py` - ghép các bước, xử lý lỗi và exit code.

## Dùng với cluster thật

Snapshot này tương đương `GET /api2/json/cluster/resources`. Trên cluster thật:

```bash
pvesh get /cluster/resources --output-format json > snapshot.json
```

API trả các trường `maxcpu`, `maxmem`, `mem`, `cpu`, `status`, `vmid`, `node`; loader đã
chấp nhận cả tên này. Cần quyền đọc tối thiểu (`PVEAuditor`) và nên chạy qua token API
thay vì mật khẩu root.
