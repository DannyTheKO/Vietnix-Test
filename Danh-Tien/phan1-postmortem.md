# Executive Summary

# Timeline sự cố
## Load balancer (phan1-su-co\lb)
- Lấy log bên load balancer (phan1-su-co\lb) và tìm thời gian bắt đầu lỗi 502/504 trả về client
- Dùng "ripgrep" để tìm string lỗi và ghi vào log 
    - `rg -w "502|504" phan1-su-co\lb\access-lb-hcm-01.log > phan1-su-co\lb\502-504-error.log`
- Sau khi dùng dụng cụ "ripgrep"
    - thời gian xảy ra lỗi là từ `20/Oct/2026:01:33:05 +0700`
    - lỗi kết thúc vào `20/Oct/2026:02:25:01 +0700`
