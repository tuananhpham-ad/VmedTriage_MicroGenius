# Hướng dẫn cập nhật code từ P-141 sang MicroGenius để Render tự động deploy

Tài liệu này dành cho người mới, giải thích **từng bước** cách đưa code mới nhất từ repo team
(`P-141`) sang thư mục `MicroGenius` và đẩy lên đúng remote để Render build & deploy bản mới.

## 0. Vì sao có 2 thư mục / 2 remote?

Trên máy bạn đang có **2 thư mục làm việc** cho cùng một dự án:

| Thư mục | Vai trò | Remote `origin` (fetch) | Remote push thực tế |
|---|---|---|---|
| `P-141/` | Repo team, nơi cả nhóm code, review PR | `AI20K-Build-Phase-Cohort-3/P-141` | `AI20K-Build-Phase-Cohort-3/P-141` |
| `MicroGenius/` | Bản clone dùng riêng để **deploy lên Render** | `AI20K-Build-Phase-Cohort-3/P-141` (chỉ để fetch) | `tuananhpham-vnu/VmedTriage_MicroGenius` (push) |

Nói cách khác: `MicroGenius/` **kéo code mới** từ repo team `P-141`, nhưng khi **đẩy code lên** thì
lại đẩy sang một repo cá nhân khác tên `VmedTriage_MicroGenius`. Render đang theo dõi nhánh `dev`
của repo `VmedTriage_MicroGenius` này (`render.yaml` → `branch: dev`, `autoDeployTrigger: commit`),
nên **chỉ khi bạn push vào `VmedTriage_MicroGenius`, Render mới tự build lại**.

Bạn có thể kiểm tra cấu hình remote đặc biệt này bằng:

```bash
cd MicroGenius
git remote -v
```

Kết quả sẽ giống:

```text
origin  https://github.com/AI20K-Build-Phase-Cohort-3/P-141.git (fetch)
origin  https://github.com/tuananhpham-vnu/VmedTriage_MicroGenius.git (push)
```

## 1. Quy trình tổng quát (nhìn nhanh)

```text
P-141 (branch của bạn, vd: tuananhpham)
   │  git push  → PR → merge vào
   ▼
P-141 origin/dev  (nhánh dev chung của team)
   │  git fetch/pull (từ MicroGenius, remote origin trỏ tới P-141)
   ▼
MicroGenius local "dev"
   │  git push origin dev  (thực chất đẩy sang VmedTriage_MicroGenius)
   ▼
VmedTriage_MicroGenius/dev  →  Render tự động phát hiện commit mới → build → deploy
```

Tóm lại: **code phải nằm trên nhánh `dev` của repo team `P-141` trước**, sau đó mới đồng bộ
sang `MicroGenius`, rồi mới push để Render deploy.

## 2. Bước 1 — Đưa code mới nhất lên `P-141/dev`

Làm việc bình thường trong thư mục `P-141`:

```bash
cd "P-141"
git status                     # kiểm tra không còn thay đổi chưa commit
git add <file thay đổi>
git commit -m "mô tả thay đổi"
git push origin <branch-cua-ban>   # vd: git push origin tuananhpham
```

Sau đó tạo Pull Request từ nhánh của bạn vào `dev` trên GitHub và merge (hoặc nếu bạn có quyền,
merge trực tiếp). Mục tiêu cuối bước này: **`origin/dev` trên repo `AI20K-Build-Phase-Cohort-3/P-141`
đã có commit mới nhất bạn muốn deploy**.

> Nếu bạn chỉ cần fix nhanh 1 file để deploy (hotfix), vẫn nên qua PR vào `dev` để lịch sử rõ ràng,
> tránh việc `MicroGenius` và `P-141` bị lệch nhau về sau.

## 3. Bước 2 — Đồng bộ nhánh `dev` từ `P-141` sang `MicroGenius`

Chuyển sang thư mục `MicroGenius`:

```bash
cd "../MicroGenius"
git checkout dev
git fetch origin
git merge origin/dev
```

- `git fetch origin` sẽ lấy dữ liệu từ `P-141` (vì remote `origin` fetch trỏ tới repo team).
- `git merge origin/dev` gộp các commit mới nhất của team vào nhánh `dev` local trong `MicroGenius`.

Nếu có xung đột (conflict), xử lý như merge bình thường: mở file bị đánh dấu `<<<<<<<`, sửa, rồi:

```bash
git add <file đã xử lý xung đột>
git commit
```

> Không dùng `git pull --rebase` hay `git reset --hard` ở bước này nếu bạn không chắc, vì `MicroGenius`
> có thể có commit riêng (ví dụ sửa `render.yaml`) chưa có ở `P-141`.

## 4. Bước 3 — Kiểm tra nhanh trước khi đẩy lên Render

Trước khi push, nên kiểm tra sơ các file quan trọng ảnh hưởng tới deploy:

```bash
git diff origin/dev -- render.yaml requirements.txt Dockerfile
```

- `render.yaml`: xác nhận `branch: dev` (đúng nhánh Render đang theo dõi) và biến môi trường
  (`envVars`) vẫn đầy đủ, không bị thiếu key nào so với `P-141`.
- `requirements.txt`: đảm bảo không thiếu dependency mới mà `P-141` vừa thêm.
- `.env`: **không commit** file `.env` thật (đã có trong `.gitignore`), chỉ cần đối chiếu
  `.env.example` xem có biến mới cần khai báo thủ công trên Render Dashboard hay không.

(Xem thêm quy ước biến môi trường ở [`deploy_render.md`](deploy_render.md).)

## 5. Bước 4 — Push sang repo Render đang theo dõi

```bash
git push origin dev
```

Vì remote `origin` trong `MicroGenius` có `pushurl` trỏ về `VmedTriage_MicroGenius`, lệnh này sẽ
tự động đẩy vào đúng repo mà Render Blueprint đang lắng nghe. Bạn **không cần** gõ thêm URL nào khác.

Nếu Git báo `Permission denied` hoặc yêu cầu đăng nhập, nghĩa là tài khoản GitHub hiện tại chưa có
quyền push vào `tuananhpham-vnu/VmedTriage_MicroGenius` — cần xin quyền collaborator hoặc dùng đúng
tài khoản/token đã được cấp.

## 6. Bước 5 — Theo dõi Render deploy

1. Vào <https://dashboard.render.com/> → chọn service `vmedtriage`.
2. Vào tab **Events** hoặc **Logs**, kiểm tra Render đã nhận commit mới (`autoDeployTrigger: commit`
   nghĩa là mỗi commit trên `dev` sẽ tự trigger build).
3. Đợi build xong (trạng thái chuyển từ `Building` → `Live`).
4. Kiểm tra health check:

```text
https://vmedtriage.onrender.com/health
https://vmedtriage.onrender.com/api/v1/status
```

5. Mở `https://vmedtriage.onrender.com/` để test nhanh flow demo (nhập triệu chứng mẫu như mô tả
   trong [`deploy_render.md`](deploy_render.md) mục 4).

Nếu build fail, xem log lỗi trên Render — thường do thiếu package trong `requirements.txt`, thiếu
biến môi trường, hoặc lỗi cú pháp `render.yaml`.

## 7. Tóm tắt lệnh (copy-paste nhanh)

```bash
# 1) Trong P-141: đảm bảo code đã merge vào origin/dev qua PR
cd "P-141"
git push origin <branch-cua-ban>
# ... merge PR vào dev trên GitHub ...

# 2) Trong MicroGenius: kéo code mới từ P-141
cd "../MicroGenius"
git checkout dev
git fetch origin
git merge origin/dev

# 3) Kiểm tra nhanh
git diff origin/dev -- render.yaml requirements.txt Dockerfile

# 4) Đẩy sang repo Render theo dõi → tự động deploy
git push origin dev
```

## 8. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Render không build sau khi push | Push nhầm remote/branch khác `dev` | Kiểm tra `git remote -v` trong `MicroGenius`, đảm bảo push đúng `origin dev` |
| Merge conflict liên tục ở `render.yaml` | `MicroGenius` từng sửa riêng `render.yaml` (khác `P-141`) | Ưu tiên giữ cấu hình đang chạy tốt trên Render, merge thủ công, sau đó cân nhắc đồng bộ lại `P-141/render.yaml` |
| Build fail vì thiếu package | Quên đồng bộ `requirements.txt` mới từ `P-141` | Merge lại `origin/dev`, kiểm tra `pip install -r requirements.txt` chạy local trước khi push |
| App live nhưng thiếu biến môi trường | Biến mới trong `.env.example` chưa được thêm trên Render Dashboard | Vào Render → service `vmedtriage` → **Environment** → thêm biến thủ công |
| `git push origin dev` báo permission denied | Chưa có quyền trên `VmedTriage_MicroGenius` | Liên hệ chủ repo (`tuananhpham-vnu`) để được thêm collaborator |
