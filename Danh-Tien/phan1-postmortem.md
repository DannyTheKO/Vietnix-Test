# Executive Summary


# Timeline sự cố
## Ngày 14/10/2026 - 20/10/2026 (syslog)
- Người dùng `hieunv` đăng nhập vào máy chủ `web-hcm-07`, sửa config bên dịch vụ nginx `/etc/logrotate.d/nginx` và khởi động lại dịch vụ
- Vào ngày `14/10/2026` cron chạy task vào lúc `00:00:01` với lệnh `test -x /usr/sbin/logrotate && /usr/sbin/logrotate /etc/logrotate.conf`, thì xuất ra 2 lỗi của phần mềm chạy deamon `logrotate`
```console
Oct 14 00:00:02 web-hcm-07 logrotate[5199]: error: /etc/logrotate.d/nginx:3 unknown option 'dailly' -- ignoring line
Oct 14 00:00:02 web-hcm-07 logrotate[5199]: error: found error in /var/log/nginx/*.log , skipping
```
- Nginx không thấy được option của `dailly`, phần này là do phía người dùng typo, nên phải ghi là `daily`
- Lỗi này lặp lại 7 lần tới `20/10/2026`

## Ngày 14/10/2026 (Logorate)
- Bên phần `logrotate-nginx.conf` config không hợp lệ nên phần mềm skip qua conf cài đặt.

## Ngày 20/10/2026 (LoadBalancer)
- Lấy log bên load balancer (phan1-su-co\lb) và tìm thời gian bắt đầu lỗi 502/504 trả về client
- Dùng "ripgrep" để tìm string lỗi và ghi vào log 
    - `rg -w "502|504" phan1-su-co\lb\access-lb-hcm-01.log > phan1-su-co\lb\502-504-error.log`
- Sau khi dùng dụng cụ "ripgrep"
    - thời gian xảy ra lỗi là từ `20/Oct/2026:01:33:05 +0700` (20/10/2026 01:33:05)
    - lỗi kết thúc vào `20/Oct/2026:02:25:01 +0700` (20/10/2026 02:25:01)

## Ngày 20/10/2026 (MySQL)
- Khi vào mysql/error.log thì thấy lỗi output "đầy dung lượng" và chờ sau 1 phút để user tự giải phóng dung lượng
    - thời gian bắt đầu từ `2026-10-20T01:33:04` (20/10/2026 1:33:04)
    - thời gian kết thúc từ `2026-10-20T02:23:04` (20/10/2026 2:23:04)

## Ngày 20/10/2026 (Nginx)
- Lỗi loại "Critical" xảy ra với thông tin là "không còn dung lượng" vào `2026/10/20 01:32:59`
- Dẫn đến thông tin loại "Alert" về lỗi không ghi được log cho dịch vụ Nginx vào `2026/10/20 01:33:01`
- Từ thời gian `2026/10/20 01:33:16` trở đi client bị timeout bởi và `php8.1-fpm.sock` chạy thất bại vì không có tài nguyên máy

# Phân tích nguyên nhân gốc & chuỗi hệ quả
- Nguyên nhân ban đầu là do người dùng ghi sai config, dẫn tới không hợp lệ và ứng dụng skip config đó
```conf
# root@web-hcm-07:~# cat /etc/logrotate.d/nginx
/var/log/nginx/*.log {
	dailly # << sai option
	missingok
	rotate 14
	compress
	delaycompress
	notifempty
	create 0640 www-data adm
	sharedscripts
	postrotate
		invoke-rc.d nginx rotate >/dev/null 2>&1
	endscript
}
```

- Từ nguyên nhân dẫn đến hậu quả tới dung lượng file log nhiều tới 37GB
```conf
# root@web-hcm-07:~# ls -lh /var/log/nginx/ /var/backups/
/var/log/nginx/:
-rw-r----- 1 www-data adm  37G Oct 20 01:33 access.log
-rw-r----- 1 www-data adm 212M Oct 13 23:59 access.log.1
-rw-r----- 1 www-data adm  19M Oct 13 00:00 access.log.2.gz
-rw-r----- 1 www-data adm 641M Oct 20 02:23 error.log
-rw-r----- 1 www-data adm 1.1M Oct 13 23:58 error.log.1
```

- Dẫn tới hệ quả tiếp theo là backup site fail là tại vì dung lượng đầy và backup được 1 phần của website
```console
Oct 20 01:00:01 web-hcm-07 CRON[16887]: (root) CMD (/usr/local/bin/backup-sites.sh >> /var/log/backup-sites.log 2>&1)
Oct 20 01:00:02 web-hcm-07 backup-sites: start backup /home -> /var/backups/sites-20261020.tar.gz
Oct 20 01:02:04 web-hcm-07 sshd[16570]: Invalid user ubuntu from 185.5.159.96 port 32248
Oct 20 01:32:57 web-hcm-07 backup-sites: tar: /var/backups/sites-20261020.tar.gz: Wrote only 4096 of 10240 bytes
Oct 20 01:32:57 web-hcm-07 backup-sites: tar: Error is not recoverable: exiting now
Oct 20 01:32:58 web-hcm-07 backup-sites: ERROR backup failed exit=2, keep old backups
```

- Sau đó những dịch vụ liên quan
- Nginx không buffer được request body và không ghi được access log
```console
2026/10/20 01:32:59 [crit] 2104#0: *5532190 pwrite() "/var/lib/nginx/body 0000183421" failed (28: No space left on device), client: 113.161.40.12, server: shop.anhduongfood.vn, request: "POST /wp-admin/admin-ajax.php HTTP/1.1"
```
```console
2026/10/20 01:33:01 [alert] 2112#0: 2104#0: *5532201 write() to "/var/log/nginx/access.log" failed (28: No space left on device) while logging request
```

- PHP không ghi được session
```console
[20-Oct-2026 01:33:06] WARNING: [pool www] child 90311 said into stderr: "PHP Warning:  session_start(): open(/var/lib/php/sessions/sess_9f2c1d, O_RDWR) failed: No space left on device (28) in /home/site42/public_html/wp-includes/class-wp-session.php on line 112"
```

- MySQL không ghi được binlog
```console
2026-10-20T01:33:04.118842+07:00 14 [ERROR] [MY-000035] [Server] Disk is full writing './binlog.000187' (OS errno 28 - No space left on device). Waiting for someone to free space... Retry in 60 secs.
```

- Dẫn đến lỗi 502 và 504 từ Nginx và LoadBalancer
```console
2026/10/20 01:33:16 [error] 2105#0: *5209440 connect() to unix:/run/php/php8.1-fpm.sock failed (11: Resource temporarily unavailable) while connecting to upstream, client: 14.218.58.164, server: site42.vn, request: "GET /tin-tuc/ HTTP/1.1"
```

# Các giả thuyết đã loại trừ
- Đầy dung lượng là do khu chứa backup sites do cron task làm việc hàng ngày. Sau khi kiểm tra log file `du-var.txt` thì cron task của backup hoạt động bình thường theo kế hoạch xoá file backup sau 1 ngày
```bash
#!/bin/bash
# /usr/local/bin/backup-sites.sh  (cron 01:00 hằng ngày)
set -o pipefail
DEST=/var/backups
TODAY=$(date +%Y%m%d)
OLD=$(date -d '1 day ago' +%Y%m%d)
logger -t backup-sites "start backup /home -> $DEST/sites-$TODAY.tar.gz"
if tar -czf "$DEST/sites-$TODAY.tar.gz" /home 2>&1 | logger -t backup-sites; then
    SIZE=$(du -h "$DEST/sites-$TODAY.tar.gz" | cut -f1)
    logger -t backup-sites "backup done size=$SIZE"
    rm -f "$DEST/sites-$OLD.tar.gz" && logger -t backup-sites "removed old backup sites-$OLD.tar.gz"
else
    logger -t backup-sites "ERROR backup failed exit=$?, keep old backups"
fi
```

- CPU/RAM quá tải nhưng sau khi kiểm tra thì uptime máy vẫn chạy bình thường
```console
# root@web-hcm-07:~# uptime
 02:23:52 up 41 days,  6:12,  1 user,  load average: 1.84, 2.10, 1.97

# root@web-hcm-07:~# top -b -n1 | head -15
top - 02:23:53 up 41 days,  6:12,  1 user,  load average: 1.84, 2.10, 1.97
Tasks: 312 total,   1 running, 311 sleeping,   0 stopped,   0 zombie
%Cpu(s):  3.1 us,  1.2 sy,  0.0 ni, 94.9 id,  0.6 wa,  0.0 hi,  0.2 si,  0.0 st
MiB Mem :  31994.0 total,    611.2 free,   9182.4 used,  22201.1 buff/cache
MiB Swap:   2048.0 total,   2035.4 free,     12.6 used.  22053.0 avail Mem

    PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
   1187 mysql     20   0 6912340   3.9g  38112 S   1.3  12.4   812:44.10 mysqld
   2104 www-data  20   0  178220  21004   9300 S   0.7   0.1  21:02.71 nginx
  90311 www-data  20   0  412880  88120  61204 S   0.0   0.3   0:04.11 php-fpm8.1
  90312 www-data  20   0  412880  86500  60812 S   0.0   0.3   0:03.92 php-fpm8.1
``` 

# Khắc phục tức thời
- Sửa conf daemon của logrotate
```conf
# root@web-hcm-07:~# cat /etc/logrotate.d/nginx
/var/log/nginx/*.log {
	daily # << sửa lại thành "daily"
	missingok
	rotate 14
	compress
	delaycompress
	notifempty
	create 0640 www-data adm
	sharedscripts
	postrotate
		invoke-rc.d nginx rotate >/dev/null 2>&1
	endscript
}
```

- Giữ mẫu 1G log rồi giải phóng 37 GB
```bash
# mẫu 1 GB cuối
tail -c 1G /var/log/nginx/access.log | gzip -1 > /dev/shm/access-tail.gz

# truncate tại chỗ, giữ inode
truncate -s 0 /var/log/nginx/access.log
df -h /

# rồi tới nginx/error.log
install -d -m 700 /root/incident-20261020
mv /dev/shm/access-tail.gz /root/incident-20261020/
cp -a /var/log/nginx/error.log /root/incident-20261020/
```

- Để MySQL tự hồi
```bash
mysqladmin ping
mysqladmin processlist | grep -c "Waiting for"   # 49 -> 0
```

- Xả worker PHP-FPM
```bash
systemctl reload php8.1-fpm
ss -xl | grep php                                 # còn 511/511 thì:
systemctl restart php8.1-fpm
```
