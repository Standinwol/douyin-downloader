# Douyin Cookie Exporter

Extension Chrome/Edge nho de lay cookie `douyin.com` theo dung format cho Douyin Downloader.

Extension nay chi doc cookie trong trinh duyet cua ban va hien thi trong popup. Khong co server, khong gui cookie ra ngoai.

## Cai dat

1. Mo Chrome hoac Edge.
2. Vao `chrome://extensions` hoac `edge://extensions`.
3. Bat `Developer mode`.
4. Bam `Load unpacked`.
5. Chon thu muc nay:

   ```text
   tools/douyin-cookie-extension
   ```

## Cach lay cookie

1. Mo `https://www.douyin.com/`.
2. Dang nhap tai khoan Douyin.
3. Refresh trang sau khi da dang nhap.
4. Bam icon `Douyin Cookie Exporter` tren thanh extension.
5. Bam `Recommended`.
6. Bam `Copy header`.
7. Dan vao o `Cookies` trong GUI Douyin Downloader.

Neu app van bao thieu cookie hoac tai profile bi chan, bam `All` roi `Copy header` de lay them cookie phu.

## Format xuat ra

Dang header:

```text
ttwid=...; odin_tt=...; passport_csrf_token=...; sid_guard=...; sessionid=...; sid_tt=...; msToken=...
```

Dang JSON:

```json
{
  "ttwid": "...",
  "odin_tt": "...",
  "passport_csrf_token": "...",
  "sid_guard": "...",
  "sessionid": "...",
  "sid_tt": "...",
  "msToken": "..."
}
```

Cookie quan trong:

- `ttwid`
- `odin_tt`
- `passport_csrf_token`
- `sid_guard`
- `sessionid`
- `sid_tt`
- `msToken`

## Bao mat

Cookie tuong duong phien dang nhap. Khong gui cookie cho nguoi khac, khong upload len web, khong commit vao git.
