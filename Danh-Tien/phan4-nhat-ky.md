# Nhật ký làm bài

**Họ tên:** Danh Tiến

**Nhận đề lúc:** 14:50

**Nộp bài lúc:** ...

**Tổng thời gian làm thật (ước tính):** ...

## Các phiên làm việc

| Thời điểm | Thời lượng | Làm phần nào                                     | Ghi chú (kẹt ở đâu, đã thử gì)   |
| --------- | ---------- | ------------------------------------------------ | -------------------------------- |
| 15:00     | 16:40      | Phần 1: Timeline Sự Cố                           |                                  |
| 16:40     | 17:25      | Phần 1: Phân tích nguyên nhân gốc & chuỗi hệ quả |                                  |
| 17:25     | 17:43      | Phần 1: Các giả thuyết đã loại trừ               |                                  |
| 17:43     | 18:48      | Phần 1: Khắc phục tức thời                       | Dùng AI để nêu ra bước khắc phục |
| 18:48     | 18:55      | Phần 1: Phương án Phòng ngừa                     |                                  |
| 18:55     | 19:00      | Phần 1: Timeline Sự Cố                           | Dùng AI để tóm tắt phần 1        |

## Giả định đã đặt ra

- 

## Câu hỏi đã gửi cho người ra đề

- (Nếu có)

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

| Bước | Công cụ     | Dùng để làm gì                        | Bạn đã kiểm tra, sửa lại gì                                                    |
| ---- | ----------- | ------------------------------------- | ------------------------------------------------------------------------------ |
| 1    | tail + gzip | Giữ 1 GB cuối `access.log`            | `tail -c 1G access.log \| gzip -1 > /dev/shm/access-tail.gz` — ghi vào RAM vì đĩa còn 0 byte |
| 2    | truncate    | Đưa `access.log` về 0 byte, giữ inode | Thu lại 37 GB; **không** truncate `error.log` (641 MB, cần giữ làm chứng cứ)    |
| 3    | install/mv  | Tạo thư mục incident, cất mẫu log     | `install -d -m 700 /root/incident-20261020`, rồi `mv` file `.gz` từ `/dev/shm` |
| 4    | cp          | Sao chép `error.log` làm chứng cứ     | `cp -a` sang `/root/incident-20261020/`, giữ nguyên file gốc                   |
| 5    | sed         | Sửa lỗi `dailly` → `daily`            | Sửa nguyên nhân gốc; thiếu bước này thì 00:00 đêm sau tái diễn                 |
| 6    | logrotate   | `-d` dry-run kiểm tra lại config      | Xác nhận không còn `unknown option 'dailly'`                                   |

- Xả worker từ PHP-FPM

| Bước | Công cụ    | Dùng để làm gì              | Bạn đã kiểm tra, sửa lại gì                   |
| ---- | ---------- | --------------------------- | --------------------------------------------- |
| 1    | systemctl  | reload/restart `php8.1-fpm` | kiểm tra backlog vẫn 511/511, thì mới restart |
| 1    | mysqladmin | `ping`, `processlist`       | Đếm 49 thread "Waiting for"                   |
| 1    | ss         | `-xl` xem backlog socket    | Thấy `511/511`                                |

#### Dùng AI
| Bước | Công cụ  | Dùng để làm gì                              | Bạn đã kiểm tra, sửa lại gì                                                                            |
| ---- | -------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 1    | DeepSeek | Tìm hiểu phần mềm Logrotate                 | Kiểm tra được là mấu chốt do phần mềm ứng dụng Logrotate                                               |
| 2    | DeepSeek | Tìm hiểu syntax của Logrotate config        | Kiểm tra được config option bị sai và sửa lại config option                                            |
| 3    | DeepSeek | Hỏi `kill -USR1` có cần khi truncate log    | Kiểm tra nginx ghi log bằng `O_APPEND`, truncate tại chỗ là đủ; chỉ `nginx -s reopen` khi đã `mv` file |
| 4    | DeepSeek | Hỏi inode: `: > access.log` khác `mv` ở đâu | Truncate giữ nguyên inode nên `df` giảm ngay; `mv` vẫn giữ inode cũ đang mở nên chưa thu hồi được      |

### Phần 2
#### Công Cụ Sử Dụng

## Phần chưa xong hoặc chưa hài lòng

- (Phần nào, vì sao, nếu có thêm thời gian sẽ làm thế nào)

## Nếu làm lại, bạn sẽ làm khác điều gì?
