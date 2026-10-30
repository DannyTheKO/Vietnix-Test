# Phần 3: Nghiên cứu ngắn — Đề B

**Bài toán:** Một máy chủ shared hosting (~40 website, Nginx + PHP-FPM + MySQL) thường xuyên bị bot crawl dữ liệu dồn dập khiến toàn bộ hệ thống chậm. So sánh phương án chặn/rate-limit ở **tầng L4 (nftables)** và **tầng L7 (Nginx `limit_req` hoặc tương đương)**, rồi đề xuất mô hình triển khai phù hợp cho hosting.

## 1. Tiêu chí so sánh

| Tiêu chí | Ý nghĩa |
|----------|---------|
| Vị trí xử lý | Kernel (netfilter) hay userspace (Nginx worker) |
| Thông tin nhìn được | IP/TCP port hay toàn bộ HTTP (method, URL, UA, header, cookie, body) |
| Khả năng phân biệt khách hàng | Có thể gán quota riêng cho từng domain/vhost trên cùng máy hay không |
| Chi phí tài nguyên | CPU/RAM mỗi gói hay mỗi request |
| Trả lời client | Drop gói im lắng hay trả mã HTTP rõ ràng (429/503) |
| Khả năng évade | Spoof IP, NAT/CGNAT, TLS, HTTP/2, slowloris |
| Tác động đến khách khác | Blind drop có thể ảnh hưởng chung hay được hạn chế theo vhost |

## 2. Tầng L4 — nftables (netfilter kernel)

**Cách hoạt động:** Điều hành ở lớp mạng/vận chuyển, kiểm tra gói IP/TCP trước khi đến ứng dụng. Dùng `limit rate` kết hợp `conntrack` để giới hạn số kết nối/second từ một IP, hoặc drop trực tiếp IP blacklist.

**Ưu điểm:**
- Xử lý sớm nhất, tốn ít CPU, không tiêu thụ worker Nginx hay PHP-FPM.
- Bảo vệ máy trước flood kết nối (SYN flood, connection exhaustion) trước khi Nginx overload.
- Không cần terminate TLS, không cần parse HTTP.

**Nhược điểm:**
- Chỉ nhìn IP/port, **không biết** request là crawl trang sản phẩm hay truy cập bình thường, không phân biệt bot hay người dùng chân chính trên cùng một IP.
- Khó cấp quota riêng cho từng domain/vhost (quan trọng trên shared hosting).
- Drop gói im lắng, client không biết lý do (không có mã 429), khó debug và hỗ trợ khách hàng.
- Rate-limit theo IP bị sai lệch khi nhiều người dùng chung IP NAT/CGNAT.

## 3. Tầng L7 — Nginx `limit_req` (leaky bucket)

**Cách hoạt động:** Hoạt động sau khi TLS terminate và Nginx parse xong request HTTP. Dùng module `ngx_http_limit_req_module` với `limit_req_zone` (shared memory zone) và `limit_req` tại `server`/`location`; key có thể là `$binary_remote_addr`, `$server_name`, `$http_user_agent`, URI, v.v. Trả về `429 Too Many Requests` (hoặc `503` khi vượt burst).

**Ưu điểm:**
- Nhìn toàn bộ HTTP, có thể chặn theo UA bekannten bot, giới hạn từng đường dẫn (`/wp-admin/`, `xmlrpc.php`, search...).
- **Có thể rate-limit riêng cho từng domain/vhost** bằng cách tách zone theo `$server_name` — phù hợp shared hosting, không để một khách hàng bị ảnh hưởng bởi bot của khách khác.
- Trả mã HTTP rõ ràng (429/503), có `burst` + `nodelay` để không chặn ngang người dùng thật.
- Dễ tích hợp vào config hosting/panel và xem log truy vấn bị chặn.

**Nhược điểm:**
- Request đã đến Nginx mới xử lý -> tiêu thụ worker Nginx; flood lớn có thể hết worker trước khi limit_req hiệu lực.
- Zone dùng RAM (theo docs Nginx, một zone 1MB lưu khoảng 16.000 trạng thái IP).
- Rate-limit theo IP vẫn bị sai khi nhiều user chung IP.
- Không chặn được flood ở cấp TLS handshake / kết nối TCP trước HTTP.

## 4. Bằng chứng / số liệu tham khảo

- Nginx official docs (`ngx_http_limit_req_module`): triển khai **leaky bucket**, một zone 1MB có thể chứa ~16.000 trạng thái IP (64-bit state), khi zone đầy các request mới bị trả 503.
- nftables/`limit`: xử lý trong kernel/netfilter, giới hạn theo gói/packet và kết nối (conntrack), overhead thấp hơn nhiều so với xử lý userspace.

## 5. Khuyến nghị & mô hình triển khai

**Khuyến nghị chốt:** Không chọn một tầng duy nhất, mà kết hợp **defense in depth**:

1. **Tầng L4 (nftables) trên máy vật lý/firewall trước:** drop các IP ddos/blacklist đã biết, giới hạn tổng số kết nối mới/second từ một IP để bảo vệ kernel trước khi Nginx quá tải. Đây là hàng rào đầu, tốn ít tài nguyên và giúp máy không bị sập hoàn toàn bởi flood kết nối.
2. **Tầng L7 (Nginx `limit_req`) tại mỗi vhost:** rate-limit riêng cho từng domain, whitelist bot công khai (Googlebot, v.v.) bằng `geo`/`map`, giới hạn các đường dẫn dễ bị crawl (`wp-admin`, `xmlrpc.php`, search...), trả 429 với `Retry-After` và burst cho người dùng thật.

**Mô hình xử lý:**  
`Internet → nftables (L4: drop blacklist, limit kết nối) → Nginx (L7: limit_req theo vhost/UA/URI, 429 + burst) → PHP-FPM/MySQL`

Với shared hosting, L7 là lớp chính để phân chia công bằng tài nguyên giữa khách hàng, L4 là lớp hỗ trợ bảo vệ cơ sở hạ tầng.

## 6. Rủi ro kỹ thuật / đánh đổi (trade-offs)

- **L4:** Drop gói không phản hồi -> khó phân biệt bot và người dùng thật, không thể cấp quota theo domain, có nguy cơ chặn nhầm khi nhiều user chung IP NAT.
- **L7:** Tốn worker Nginx và RAM cho zone; nếu flood quá lớn, Nginx có thể hết worker trước khi `limit_req` có thời gian tác động; rate-limit theo IP vẫn sai lệch dưới CGNAT.
- **Khuyến nghị không nên:** Chỉ rate-limit cứng theo IP toàn cầu (không chia vhost) vì sẽ phạt toàn bộ khách hàng khi một ISP dùng NAT; cũng không nên chỉ để L4 vì không phân biệt được crawl dữ liệu và truy cập hợp pháp.

---