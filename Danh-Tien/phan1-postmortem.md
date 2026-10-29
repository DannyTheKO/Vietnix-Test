# Executive Summary

# Timeline sự cố
## Load balancer (phan1-su-co\lb)
- Lấy log bên load balancer (phan1-su-co\lb) và tìm thời gian bắt đầu lỗi 502/504 trả về client
- Dùng "ripgrep" để tìm string lỗi và ghi vào log 
    - `rg -w "502|504" phan1-su-co\lb\access-lb-hcm-01.log > phan1-su-co\lb\502-504-error.log`
- Sau khi dùng dụng cụ "ripgrep"
    - thời gian xảy ra lỗi là từ `20/Oct/2026:01:33:05 +0700` (20/10/2026 01:33:05)
    - lỗi kết thúc vào `20/Oct/2026:02:25:01 +0700` (20/10/2026 02:25:01)

## MySQL
- Khi vào mysql/error.log thì thấy lỗi output "đầy dung lượng" và chờ sau 1 phút để user tự giải phóng dung lượng
    - thời gian bắt đầu từ `2026-10-20T01:33:04` (20/10/2026 1:33:04)
    - thời gian kết thúc từ `2026-10-20T02:23:04` (20/10/2026 2:23:04)

## Nginx
- Lỗi loại "Critical" xảy ra với thông tin là "không còn dung lượng" vào `2026/10/20 01:32:59`
- Dẫn đến thông tin loại "Alert" về lỗi không ghi được log cho dịch vụ Nginx vào `2026/10/20 01:33:01`
- Từ thời gian `2026/10/20 01:33:16` trở đi client bị timeout bởi và `php8.1-fpm.sock` chạy thất bại vì không có tài nguyên máy


