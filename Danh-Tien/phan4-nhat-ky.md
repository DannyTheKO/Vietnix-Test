# Nhật ký làm bài

**Họ tên:** Danh Tiến

**Nhận đề lúc:** 14:50

**Nộp bài lúc:** 30/10/2026 12:00

**Tổng thời gian làm thật (ước tính):** 8h06p (~8 tiếng) — 5h45p ngày 29/10 + 2h21p ngày 30/10

## Các phiên làm việc

### Ngày 29/10/2026

| Thời điểm | Thời lượng | Làm phần nào                                     | Ghi chú (kẹt ở đâu, đã thử gì)                                                                                                                                        |
| --------- | ---------- | ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 15:00     | 1h40p      | Phần 1: Timeline Sự Cố                           | Xem tất cả file log dịch vụ `nginx`, `logrotate`, `logrotate_config` và `syslog`, lọc ra kết quả 502 và 504                                                           |
| 16:40     | 0h45p      | Phần 1: Phân tích nguyên nhân gốc & chuỗi hệ quả | Tìm nguyên nhân kèm theo bằng chứng của những dịch vụ chuổi đi theo                                                                                                   |
| 17:25     | 0h18p      | Phần 1: Các giả thuyết đã loại trừ               | Loại trừ CPU/RAM quá tải (uptime load 1.84, idle 94.9%); loại trừ backup script (script đúng quy trình, lỗi do disk full)                                             |
| 17:43     | 1h05p      | Phần 1: Khắc phục tức thời                       | Sử dụng công cụ AI để đưa ra cách khắc phục hậu quả tức thời với tâm trí dung lượng hiện tại đầy và bảo tồn lịch sử của `access.log` và `error.log` để làm bằng chứng |
| 18:48     | 0h07p      | Phần 1: Phương án Phòng ngừa                     | Thêm `maxsize 100M`; thêm `logrotate -d` dry-run trước reload; đề xuất cảnh báo disk > 80%                                                                            |
| 18:55     | 0h05p      | Phần 1: Summary                                  | Sử dụng AI để tóm tắt lại bài làm                                                                                                                                     |
| 19:00     | 0h15p      | Phần 2: Tìm hiểu Proxmox VE & đọc file JSON      | Chưa rõ Proxmox là gì, hỏi AI và đọc lại đề; xác nhận chỉ cần đọc JSON không cần lab thật                                                                             |
| 19:15     | 1h30p      | Phần 2: Thống kê và hiển thị mức tải             | Sử dụng AI để thiết kế giao diện CLI cho người dùng trực tiếp và thiết lập hàm xuất ra dạng json để các phần mềm khác sử dụng.                                        |


### Ngày 30/10/2026

| Thời điểm | Thời lượng | Làm phần nào                                               | Ghi chú (kẹt ở đâu, đã thử gì)                                     |
| --------- | ---------- | ---------------------------------------------------------- | ------------------------------------------------------------------ |
| 9:07      | 1h6p       | Phần 2: Unit Test                                          |                                                                    |
| 10:07     | 0h45p      | Phần 3: Nghiên cứu ngắn Đề B (nftables vs Nginx limit_req) | So sánh L4/L7, đề xuất mô hình defense in depth cho shared hosting |
| 10:52     | 0h36p      | Phần 3: Viết dẫn chứng tài liệu chính thức       | Chép số liệu Nginx docs (~16.000 trạng thái/1MB zone) và kernel netfilter từ tài liệu chính thức; kiểm chứng lại thuật ngữ |
| 11:28     | 0h25p      | Phần 2: Chạy test + kiểm tra README              | `python -m unittest discover -s tests`; kiểm tra CLI chạy đúng; sửa lỗi chính tả nhỏ |
| 11:53     | 0h29p      | Phần 3: Hoàn thiện `phan3-nghien-cuu.md` + Part 4 | Viết khuyến nghị defense in depth; hoàn thiện bảng so sánh; cập nhật nhật ký phiên cuối |

## Giả định đã đặt ra

**Phần 1 – Điều tra sự cố**
- Giả định không có dữ liệu/database của khách bị mất do sự cố: incident chỉ gây disk full (MySQL không ghi binlog, PHP không ghi session), không có lệnh xóa/sửa data của khách.
- Giả định máy chủ không có hệ thống monitoring/cảnh báo disk full đang hoạt động trước sự cố, nếu có sẽ phát hiện sớm hơn.

**Phần 2 – Tool Proxmox**
- Giả định chỉ cần đọc file JSON snapshot (`cluster-pve-hcm-c3.json`), không cần kết nối API Proxmox VE thực tế khi chạy tool.
- Giả định ngưỡng "quá tải" được tự đặt: CPU thực dùng > 80%, RAM thực dùng > 85%, overcommit vCPU > 1.5× core vật lý (có thể điều chỉnh trong config/tool).
- Giả định chỉ tính các VM có trạng thái `running` trong kế hoạch migrate; VM `stopped` không được xét migrate.
- Giả định node có `status: offline` không được chọn làm node đích nhận VM migrate.

**Phần 3 – Nghiên cứu ngắn (Đề B)**
- Giả định bot crawl không giả mạo IP (spoof IP), nên rate-limit theo IP có hiệu lực đối với phần lớn trường hợp.
- Giả định chấp nhận rủi ro nhiều khách hàng khác nhau chia sẻ cùng IP công khai (NAT/CGNAT); rate-limit theo IP có thể ảnh hưởng nhầm, nhưng được giảm nhẹ bằng cách chia quota theo vhost (`$server_name`).
- Giả định Nginx là điểm dừng TLS và reverse proxy trực tiếp trước PHP-FPM, không có CDN/WAF phía trước che giấu IP khách hàng thật.
- Giả định mỗi khách hàng trên shared hosting có vhost/domain riêng biệt, nên có thể rate-limit riêng theo `$server_name` mà không ảnh hưởng lẫn nhau.

## Câu hỏi đã gửi cho người ra đề


## Dùng AI và công cụ
### Phần 1
#### Công Cụ Sử Dụng

| Bước | Công cụ                | Dùng để làm gì              | Bạn đã kiểm tra, sửa lại gì                                             |
| ---- | ---------------------- | --------------------------- | ----------------------------------------------------------------------- |
| 1    | cd                     | Dùng để chuyển thư mục      |                                                                         |
| 1    | vim                    | Công cụ chỉnh sửa tệp tin   | Dùng để kiểm tra và thay đổi tệp tin                                    |

- Kiểm tra và lọc kết quả

| Bước | Công cụ                | Dùng để làm gì           | Bạn đã kiểm tra, sửa lại gì                       |
| ---- | ---------------------- | ------------------------ | ------------------------------------------------- |
| 1    | ripgrep (rg) hoặc grep | Lọc và tìm string cụ thể | Lọc những String tồn tại riêng ở "502" và "504"   |
| 2    | > 502-504-error.log    | Ghi log vào 1 file khác  | Từ ripgrep output, ghi vào file 502-504-error.log |

- Giải phóng dung lượng và sao chép lịch sử log

| Bước | Công cụ     | Dùng để làm gì                        | Bạn đã kiểm tra, sửa lại gì                                                                  |
| ---- | ----------- | ------------------------------------- | -------------------------------------------------------------------------------------------- |
| 1    | tail + gzip | Giữ 1 GB cuối `access.log`            | `tail -c 1G access.log \| gzip -1 > /dev/shm/access-tail.gz` — ghi vào RAM vì đĩa còn 0 byte |
| 2    | truncate    | Đưa `access.log` về 0 byte, giữ inode | Thu lại 37 GB; giữ `error.log` (641 MB, cần giữ làm chứng cứ)                                |
| 3    | install/mv  | Tạo thư mục incident, cất mẫu log     | `install -d -m 700 /root/incident-20261020`, rồi `mv` file `.gz` từ `/dev/shm`               |
| 4    | cp          | Sao chép `error.log` làm chứng cứ     | `cp -a` sang `/root/incident-20261020/`, giữ nguyên file gốc                                 |
| 5    | sed         | Sửa lỗi `dailly` → `daily`            | Sửa nguyên nhân gốc; thiếu bước này thì 00:00 đêm sau tái diễn                               |
| 6    | logrotate   | `-d` dry-run kiểm tra lại config      | Xác nhận không còn `unknown option 'dailly'`                                                 |

- Xả worker từ PHP-FPM

| Bước | Công cụ    | Dùng để làm gì              | Bạn đã kiểm tra, sửa lại gì                   |
| ---- | ---------- | --------------------------- | --------------------------------------------- |
| 1    | systemctl  | reload/restart `php8.1-fpm` | kiểm tra backlog vẫn 511/511, thì mới restart |
| 1    | mysqladmin | `ping`, `processlist`       | Đếm 49 thread "Waiting for"                   |
| 1    | ss         | `-xl` xem backlog socket    | Thấy `511/511`                                |

#### Dùng AI
| Bước | Công cụ       | Dùng để làm gì                              | Bạn đã kiểm tra, sửa lại gì                                                                            |
| ---- | ------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1    | DeepSeek / AI | Tìm hiểu phần mềm Logrotate                 | Kiểm tra được là mấu chốt do phần mềm ứng dụng Logrotate                                               |
| 2    | DeepSeek / AI | Tìm hiểu syntax của Logrotate config        | Kiểm tra được config option bị sai và sửa lại config option                                            |
| 3    | DeepSeek / AI | Hỏi `kill -USR1` có cần khi truncate log    | Kiểm tra nginx ghi log bằng `O_APPEND`, truncate tại chỗ là đủ; chỉ `nginx -s reopen` khi đã `mv` file |
| 4    | DeepSeek / AI | Hỏi inode: `: > access.log` khác `mv` ở đâu | Truncate giữ nguyên inode nên `df` giảm ngay; `mv` vẫn giữ inode cũ đang mở nên chưa thu hồi được      |

### Phần 2
#### Công Cụ Sử Dụng

| Bước | Công cụ                 | Dùng để làm gì                                                                     | Bạn đã kiểm tra, sửa lại gì                                                        |
| ---- | ----------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 1    | Python                  | Viết tool phân tích tải cluster Proxmox (đọc JSON, thống kê node, đề xuất migrate) | Kiểm tra logic tính CPU/RAM thực dùng và overcommit vCPU                           |
| 2    | cluster-pve-hcv-c3.json | File snapshot cluster làm input cho tool                                           | Đối chiếu trường dữ liệu với mô tả trong đề bài (cpu_cores, mem_total, vcpus, vms) |
| 3    | pytest / unittest       | Viết unit test cho các hàm logic cốt lõi                                           | Chạy test tự động, kiểm tra trường hợp bị quá tải và migration hợp lệ              |
| 4    | vim                     | Chỉnh sửa mã nguồn tool                                                            | Kiểm tra và sửa lỗi cú pháp, định dạng code                                        |

#### Dùng AI

| Bước | Công cụ       | Dùng để làm gì                                                              | Bạn đã kiểm tra, sửa lại gì                                                                                       |
| ---- | ------------- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| 1    | DeepSeek / AI | Hỏi Proxmox VE là gì, kiến trúc cluster/node/VM và live-migrate             | Đối chiếu với đề bài phần 2 (cluster `pve-hcm-c3`, node, VM) để chắc chỉ cần đọc JSON, không phải dựng lab thật   |
| 2    | DeepSeek / AI | Hỏi cách tính tải node và cách dùng dữ liệu trong `cluster-pve-hcm-c3.json` | Tự tính lại thủ công cho node `hcm-c3-n01`, kiểm tra khớp công thức; rà các bản ghi bất thường (xem mục Giả định) |

### Phần 3
#### Công Cụ Sử Dụng

| Bước | Công cụ               | Dùng để làm gì                                     | Bạn đã kiểm tra, sửa lại gì                        |
| ---- | --------------------- | -------------------------------------------------- | -------------------------------------------------- |
| 1    | Nginx official docs   | Xác nhận triển khai leaky bucket của `limit_req`   | Kiểm tra dung lượng zone 1MB ~16.000 trạng thái IP |
| 2    | kernel netfilter docs | Xác nhận nftables `limit` xử lý ở kernel/userspace | Xác nhận overhead thấp hơn xử lý userspace         |

#### Dùng AI

| Bước | Công cụ       | Dùng để làm gì                                                                 | Bạn đã kiểm tra, sửa lại gì                                                                    |
| ---- | ------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- |
| 1    | DeepSeek / AI | So sánh nftables (L4) và Nginx `limit_req` (L7) cho bài toán bot crawl hosting | Kiểm tra lại số liệu zone Nginx, điều chỉnh các thuật ngữ và lỗi gõ trong bản nháp             |
| 2    | DeepSeek / AI | Lập đề xuất mô hình defense in depth (L4 + L7) cho shared hosting              | Rà lại khuyến nghị chốt, rủi ro kỹ thuật và trade-offs trước khi ghi vào `phan3-nghien-cuu.md` |

## Phần chưa xong hoặc chưa hài lòng

- Phần 3: Chưa có kết quả benchmark thực tế từ lab cá nhân (AB/wrk với kịch bản bot crawl), các số liệu hiện tại dựa trên tài liệu chính thức Nginx và kernel netfilter. Nếu có thêm thời gian sẽ chạy benchmark để xác định ngưỡng `rate` và `burst` phù hợp.

## Nếu làm lại, bạn sẽ làm khác điều gì?

**Phần 1 – Điều tra sự cố**
- Sửa lỗi chính tả `dailly` → `daily` và chạy `logrotate -d` dry-run ngay khi nhận thấy logrotate báo lỗi đầu tiên (14/10), chứ không đợi đến đêm 20/10 khi disk full mới xử lý.
- Thiết lập sẵn cảnh báo disk usage (ví dụ > 80% hoặc > 90%) và giám sát logrotate status, thay vì chỉ phát hiện sự cố khi khách hàng báo lỗi 502/504.
- Ghi lại mẫu log và chứng cứ ngay từ đầu sự cố, không chờ đến lúc can thiệp lúc 02:23.

**Phần 2 – Tool Proxmox**
- Thiết lập sẵn cấu trúc dự án (requirements.txt, entrypoint CLI với argparse, README) trước khi viết logic core, để tool dễ chạy, dễ mở rộng và dễ đưa vào Cron.
- Viết unit test song song với từng hàm tính tải và đề xuất migrate, chứ không để nhóm test sau cùng.
- Xác định ngưỡng quá tải (CPU, RAM, overcommit vCPU) rõ ràng trong config file thay vì hard-code trong code.

**Phần 3 – Nghiên cứu ngắn (Đề B)**
- Dành thời gian chạy benchmark thực tế (AB/wrk, siege) với kịch bản bot crawl đồng thời trên máy thử, để có con số `rate` và `burst` cụ thể cho Nginx `limit_req` thay vì chỉ dựa trên tài liệu chính thức.
- Lab mô hình defense in depth (nftables + Nginx) trên thiết bị thử để xác thực việc chặn bot không ảnh hưởng khách hàng thật trước khi khuyến nghị triển khai production.
