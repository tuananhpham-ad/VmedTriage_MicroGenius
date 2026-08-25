"""Render cut-scene "chạy qua thay áo" của hai linh vật thành ảnh động WebP.

Chạy TAY, không phải bước build: `python scripts/build_mascot_cutscene.py`. Đầu ra được commit như
một asset bình thường - dựng lại chỉ cần khi ảnh nguồn đổi.

**Vì sao render sẵn thay vì để CSS làm hết.** CSS animate được vị trí, xoay, co giãn - và bản CSS
vẫn còn nguyên, nó là đường dự phòng. Thứ CSS KHÔNG làm được là mấy thứ khiến một cú chuyển đọc ra
như phim: vệt nhoè chuyển động thật (ghost nhiều lớp theo hướng chạy), bụi tung ở chân lúc phanh, và
một quầng sáng ở đúng khoảnh khắc giao ca. Ba thứ đó phải vẽ theo TỪNG KHUNG HÌNH, nên chúng được
nướng sẵn ở đây.

**Vì sao WebP động chứ không phải video.** Video có alpha là ngõ cụt tương thích: WebM/VP9 alpha
không chạy trên Safari, còn HEVC alpha thì chỉ chạy trên Safari - hai file cho một hiệu ứng trang
trí. WebP động có alpha chạy trên mọi trình duyệt đang hỗ trợ, và `<img>` thì không kéo theo bộ giải
mã video nào.

**Vì sao render ở 1x chứ không 2x.** Cut-scene chỉ xuất hiện lúc ĐANG chuyển động, còn lúc đứng yên
trang dùng lại đúng file PNG sắc nét. Mắt không đọc được chi tiết trên một vật đang chạy ngang màn
hình trong bốn phần mười giây, nên 2x chỉ mua thêm dung lượng gấp bốn.
"""

from __future__ import annotations

import math
import shutil
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "src" / "ui" / "new" / "assets"

SOURCES = {
    # Ảnh bác sĩ dùng chung với landing page nên đọc THẲNG từ đó chứ không giữ một bản sao đã cắt:
    # hai bản sao của cùng một hình là hai thứ sẽ lệch nhau ở lần ai đó thay ảnh.
    "doctor": ASSETS / "triage-ai-doctor-looking-left.png",
    "engineer": ROOT / "figures" / "engineer_testing.png",
}

W, H = 430, 540
"""Khung hình bằng đúng vùng linh vật đứng trên trang. Robot chạy ra khỏi mép là bị CẮT ở đây - đúng
thứ ta muốn: nó biến mất sau mép tấm thẻ, không bay lơ lửng ra ngoài."""

ROBOT_H = 436
GROUND = 494
"""Đáy chân robot. Chừa 48px phía dưới cho bụi tung, và để cả hai con được nâng khỏi mép dưới - một
linh vật dính sát đáy khung trông như bị cắt chân."""

FRAMES = 30
FPS = 25

EXIT_END = 0.40
ENTER_START = 0.30
BURST = (0.20, 0.66)
"""Ba mốc, và khoảng CHỒNG LẤN mới là phần quan trọng: con mới bắt đầu vào (0.30) TRƯỚC khi con cũ
khuất hẳn (0.40), nên có mấy khung hình thấy cả hai cùng chạy - đọc ra như một cú trao ca. Bản đầu
để hai mốc rời nhau và kết quả là ba khung hình trống trơn giữa cú chuyển: khoảng trống biến một cú
chạy thành một lần ảnh biến mất."""


def ease_in(t: float) -> float:
    """Bậc HAI, không phải bậc ba. Bậc ba giữ robot đứng gần như tại chỗ suốt nửa đầu rồi mới vụt
    biến mất - nhìn ra thành "đứng im rồi bị xoá" chứ không thành "chạy đi"."""
    return t * t


def ease_out(t: float) -> float:
    return 1 - (1 - t) ** 3


def span(t: float, start: float, end: float) -> float:
    """`t` quy về [0,1] trong khoảng [start,end], kẹp hai đầu."""
    return min(max((t - start) / (end - start), 0.0), 1.0)


def load(key: str, scale: float = 1) -> Image.Image:
    """Ảnh nguồn, CẮT SÁT THÂN rồi kéo về cùng chiều cao.

    Cắt theo `alpha.getbbox()` là bước không được bỏ: hai ảnh gốc có lượng nền trong suốt thừa khác
    nhau (thân bác sĩ chiếm 79% chiều cao canvas, thân kỹ sư chỉ 70%), nên đưa thẳng vào cùng một
    khung CSS vẫn ra hai con robot to nhỏ khác nhau. Chuẩn hoá ở đây, một lần, thay vì bù bằng hai
    con số magic trong stylesheet."""
    robot = Image.open(SOURCES[key]).convert("RGBA")
    robot = robot.crop(robot.getchannel("A").getbbox())
    height = round(ROBOT_H * scale)
    return robot.resize((round(robot.width * height / robot.height), height), Image.LANCZOS)


def stamp(canvas: Image.Image, robot: Image.Image, *, x: float, bob: float, tilt: float, squash: float, alpha: int) -> None:
    """Dán robot vào khung: co giãn theo `squash`, nghiêng `tilt`, nhấc `bob`, mờ theo `alpha`.

    `squash` là bảo toàn thể tích (rộng ra thì thấp xuống) - co giãn một chiều thôi thì robot lúc
    phanh trông như bị kéo dãn chứ không như bị nén."""
    if alpha <= 0:
        return
    width = max(1, round(robot.width * squash))
    height = max(1, round(robot.height / squash))
    piece = robot.resize((width, height), Image.LANCZOS)
    if tilt:
        piece = piece.rotate(tilt, resample=Image.BICUBIC, expand=True)
    if alpha < 255:
        piece.putalpha(piece.getchannel("A").point(lambda value: value * alpha // 255))
    canvas.alpha_composite(piece, (round(x - piece.width / 2), round(GROUND - bob - piece.height)))


def run_pose(progress: float, *, steps: float = 3.5) -> tuple[float, float]:
    """Nhịp chạy: chân nhún và thân nghiêng theo cùng một pha.

    Nhún dùng `abs(sin)` chứ không `sin`: bước chạy là chuỗi cú nảy LÊN rồi chạm đất, không phải một
    dao động lên-xuống đều quanh trục - dùng `sin` thì robot chìm xuống dưới mặt đất nửa chu kỳ."""
    phase = progress * steps * math.pi
    return abs(math.sin(phase)) * 26, math.sin(phase * 2) * 4.5


def dust(draw: ImageDraw.ImageDraw, x: float, progress: float, direction: int) -> None:
    """Bụi tung ở chân: mấy vòng tròn nở ra và mờ dần, bay NGƯỢC hướng chạy."""
    for index in range(5):
        seed = 0.18 * index
        life = span(progress, seed, seed + 0.55)
        if life <= 0 or life >= 1:
            continue
        radius = 5 + life * (16 + index * 4)
        offset = -direction * life * (34 + index * 18)
        alpha = int(90 * (1 - life))
        cx, cy = x + offset, GROUND - 6 - life * (10 + index * 5)
        draw.ellipse((cx - radius, cy - radius * .6, cx + radius, cy + radius * .6), fill=(120, 152, 190, alpha))


def speed_lines(draw: ImageDraw.ImageDraw, x: float, strength: float, direction: int) -> None:
    """Vệt tốc độ BÁM THEO robot đang chạy, không đứng yên giữa khung.

    Bản đầu vẽ chúng cố định ở giữa cộng một quầng sáng lớn: cả hai đứng im trong lúc robot lao qua,
    nên chúng đọc ra như một vệt bẩn trên nền chứ không như tốc độ của một vật đang chuyển động."""
    if strength <= 0:
        return
    for index in range(7):
        y = GROUND - 110 - index * 46
        length = 48 + (index % 3) * 62
        tail = x - direction * (26 + (index % 4) * 30)
        draw.line((tail, y, tail - direction * length, y), fill=(37, 99, 235, int(85 * strength)), width=2)



def publish(write, out_name: str) -> None:
    """Ghi ra thư mục TẠM rồi mới copy vào `assets/`.

    Không phải cầu kỳ thừa: ghi thẳng vào `src/ui/new/assets/` thì file `.webp` VỪA ghi xong bị cắt
    còn 0 byte ngay khi file `.webp` thứ hai được ghi - lặp lại được, và chỉ xảy ra trong thư mục
    này (thư mục tạm thì không). Thủ phạm gần như chắc chắn là một trình quét file đang theo dõi thư
    mục dự án. Copy một file đã hoàn chỉnh thì không kích hoạt được lỗi đó.

    `write(path)` phải là hàm ghi ra đúng `path` được truyền vào."""
    with tempfile.TemporaryDirectory() as workspace:
        staged = Path(workspace) / out_name
        write(staged)
        shutil.copyfile(staged, ASSETS / out_name)
    size_kb = round((ASSETS / out_name).stat().st_size / 1024)
    if size_kb == 0:
        raise RuntimeError(f"{out_name} ra 0 byte sau khi copy - xem lại trình quét file đang theo dõi assets/")
    print(f"{out_name}: {size_kb} KB")


def build(leaving_key: str, entering_key: str, direction: int, out_name: str) -> None:
    """`direction` = hướng con cũ chạy đi (-1 trái, +1 phải). Con mới luôn vào từ phía đối diện."""
    leaving, entering = load(leaving_key), load(entering_key)
    off_screen = W / 2 + max(leaving.width, entering.width) / 2 + 20
    frames: list[Image.Image] = []

    for index in range(FRAMES):
        t = index / (FRAMES - 1)
        canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        exit_p = span(t, 0.0, EXIT_END)
        if exit_p < 1:
            bob, tilt = run_pose(exit_p)
            speed = ease_in(exit_p)
            x = W / 2 + direction * speed * off_screen
            # Ngả người theo hướng chạy: một vật đang tăng tốc mà thân vẫn thẳng đứng trông như bị
            # kéo trên ray. Ngả tăng dần theo tốc độ, không phải một góc cố định.
            lean = -direction * 7 * speed
            fade = int(255 * (1 - span(exit_p, .80, 1.0)))
            speed_lines(draw, x, speed * (1 - span(exit_p, .8, 1)), direction)
            # Vệt nhoè: ba bản sao mờ dần TỤT LẠI phía sau hướng chạy. Đây là thứ CSS không có, và
            # là thứ khiến khung hình đọc ra "đang chạy nhanh" thay vì "đang ở vị trí khác".
            for ghost in (3, 2, 1):
                stamp(canvas, leaving, x=x - direction * ghost * 30 * speed, bob=bob, tilt=tilt + lean,
                      squash=1 + .05 * speed, alpha=int(fade * .11 * ghost * speed))
            stamp(canvas, leaving, x=x, bob=bob, tilt=tilt + lean, squash=1 + .05 * speed, alpha=fade)

        enter_p = span(t, ENTER_START, 1.0)
        if enter_p > 0:
            eased = ease_out(enter_p)
            bob, tilt = run_pose(1 - enter_p)
            # Vượt đích rồi lùi về: nhịp phanh. Không có nó thì con mới dừng đúng vạch như một hộp
            # trượt trên ray.
            overshoot = math.sin(enter_p * math.pi) * -direction * 18
            x = W / 2 - direction * (1 - eased) * off_screen + overshoot
            lean = direction * 7 * (1 - eased)
            settle = span(enter_p, .74, 1.0)
            squash = 1 + .13 * math.sin(settle * math.pi)  # nén người lúc chạm vạch
            fade = int(255 * span(enter_p, 0, .18))
            speed_lines(draw, x, (1 - eased) * .9, -direction)
            for ghost in (3, 2, 1):
                stamp(canvas, entering, x=x + direction * ghost * 28 * (1 - eased), bob=bob, tilt=tilt + lean,
                      squash=squash, alpha=int(fade * .11 * ghost * (1 - eased)))
            stamp(canvas, entering, x=x, bob=bob, tilt=tilt + lean, squash=squash, alpha=fade)
            if settle > 0:
                dust(ImageDraw.Draw(canvas), x, settle, direction)

        frames.append(canvas)

    publish(lambda path: frames[0].save(
        path, save_all=True, append_images=frames[1:],
        duration=round(1000 / FPS), loop=1, quality=62, method=6,
    ), out_name)


def build_still(key: str, out_name: str, scale: float = 2) -> None:
    """Ảnh ĐỨNG YÊN, dựng trên ĐÚNG khung hình của cut-scene (`W`x`H`, chân ở `GROUND`).

    Đây là thứ khiến cú chuyển liền mạch: khung hình cuối của cut-scene và ảnh tĩnh thay nó có cùng
    kích thước, cùng tâm, cùng vạch chân - nên khoảnh khắc trang gỡ ảnh động ra và trả ảnh tĩnh vào,
    robot không nhích một pixel nào. Căn hai hệ toạ độ khác nhau bằng vài phép nhân trong CSS là chỗ
    chắc chắn sẽ lệch khi ai đó đổi một con số ở một bên.

    Đổi lại: ảnh tĩnh mang theo phần nền trong suốt của khung. Không tốn mấy - vùng rỗng nén gần như
    bằng không - và nó mua lại đúng thứ đắt nhất ở đây là sự khớp nhau.

    `scale=2` vì ảnh tĩnh là thứ người dùng NHÌN LÂU: nó phải nét trên màn Retina. Cut-scene giữ 1x
    vì mắt không đọc được chi tiết trên một vật đang lao ngang màn hình trong bốn phần mười giây.
    Cùng tỉ lệ nên chỉ cần một dòng `height` trong CSS là hai bên khớp nhau."""
    robot = load(key, scale)
    canvas = Image.new("RGBA", (round(W * scale), round(H * scale)), (0, 0, 0, 0))
    canvas.alpha_composite(robot, (round(W * scale / 2 - robot.width / 2), round(GROUND * scale) - robot.height))
    publish(lambda path: canvas.save(path, optimize=True), out_name)


if __name__ == "__main__":
    build("doctor", "engineer", -1, "mascot-swap-to-engineer.webp")
    build("engineer", "doctor", 1, "mascot-swap-to-doctor.webp")
    build_still("doctor", "mascot-doctor.png")
    build_still("engineer", "mascot-engineer.png")
