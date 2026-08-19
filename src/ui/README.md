# Thu muc `src/ui`

Thu muc nay chua frontend static theo feature. FastAPI mount thu muc `new/` tai route `/`, nen mo `http://localhost:8000/` se thay UI.

Giao dien dang chay theo goi thiet ke `docs/design_handoff_vmedtriage/` (ap dung 2026-08-19). Hai file `.dc.html` trong goi do la BAN THAM CHIEU (prototype), khong phai code de copy — moi thay doi giao dien phai sua trong `new/` chu khong sua prototype.

## File va folder

| Duong dan | Lam gi |
|---|---|
| `__init__.py` | Danh dau package `src.ui`. |
| `static_files.py` | Ham `build_demo_static_app()` tra ve `StaticFiles(directory=new, html=True)` de `main.py` mount UI. |
| `new/index.html` | Vo trang: nap IBM Plex Sans, `styles.css` va module `app.js`. |
| `new/app.js` | Router: anh xa ten view sang ham render cua tung feature. |
| `new/state.js` | State toan cuc + luu/xoa phien dang nhap. |
| `new/api.js` | Goi REST (`api`) va SSE (`apiStream`), dich loi backend sang tieng Viet. |
| `new/shared.js` | Nhan tieng Viet, bo icon net, `appHeader`, thang do tin cay AI (`aiConfidence`). |
| `new/styles.css` | Token mau/chu/bo goc + toan bo component theo handoff. Khong viet mau cung trong feature. |
| `new/features/auth.js` | W-00P trang gioi thieu cong khai, W-01 dang nhap/dang ky, xac thuc email, dat lai mat khau. |
| `new/features/patient.js` | W-00 trang chu, W-02 disclaimer, W-03 khai bao, W-04 red-flag, W-05 ket qua. |
| `new/features/nurse.js` | W-06 hang doi, W-07 duyet ca (diem chot HITL). |
| `new/features/account.js` | Menu tai khoan, ho so, cai dat. |

## Hai bat bien khong duoc lam mat khi sua giao dien

- **G1 — noi ro pham vi cua AI.** Hang `AI_SCOPE_VI` trong `patient.js` xuat hien o CA W-02 (muc 1) va dai nang luc (`.capability-strip`) tren W-03. Khong rut gon thanh "AI ho tro".
- **G2 — noi ro do tin cay.** Moi cho dieu duong thay muc uu tien AI de xuat (dong hang doi W-06, the de xuat W-07) deu phai hien kem do tin cay Cao/Trung binh/Thap, dung thang mau RIENG (`--conf-*`), khong dung do/ho phach/xanh cua thang muc uu tien.

## Ghi chu

`new/support.js` va hai file `new/*.dc.html` la ban prototype con sot lai, KHONG duoc `index.html` nap. Co the xoa khi don dep — ban goc nam o `docs/design_handoff_vmedtriage/`.
