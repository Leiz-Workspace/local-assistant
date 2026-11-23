"""HAR-009-C summary v2 dev-plus cases: six dev tuning cases written after the held-out hash (protocol v2, dev set)."""

from benchmarks.context_budget import SHORT_FILLER, log_block
from benchmarks.context_summary import LONG_FROM, PAIRS
from benchmarks.context_summary_v2 import build_case

SUFFIX = dict(en=" Answer in one short line.", vi=" Trả lời ngắn gọn trong một dòng.")


def dialogue(identifier, language, explicit):
    """Return 16 (user, assistant) pairs: explicit pairs among 1-7, short fillers elsewhere before the long worker logs."""
    pool = SHORT_FILLER[language]
    offset = sum(map(ord, identifier)) % len(pool)
    pairs = []
    for number in range(1, PAIRS + 1):
        if number in explicit:
            pairs.append(explicit[number])
        elif number >= LONG_FROM:
            pairs.append(log_block(identifier, number, language))
        else:
            pairs.append(pool[(offset + number) % len(pool)])
    return pairs


def case(identifier, kind, language, explicit, targets, question, **fields):
    """Build one dev-plus case with the v1 question suffix."""
    return build_case(
        identifier,
        kind,
        language,
        dialogue(identifier, language, explicit),
        question + SUFFIX[language],
        targets=targets,
        **fields,
    )


def dev_plus():
    """Return the 6 dev-plus cases (3 EN, 3 VI): multi-fact (EN, VI), a late target at pair 7 (EN, VI), an entity-less correction (EN) and a negation in a medium message (VI)."""
    return [
        case(
            "dp-multi-quarrymoor",
            "identifier",
            "en",
            {
                2: (
                    "Quarrymoor staging runs on 9 hosts in rack R-117, and production runs on 23.",
                    "Understood.",
                ),
                4: (
                    "For the Quarrymoor rollout, the build host is bx-node-417, the artifact bucket is qm-art-0593, and the signing key id is KX-82-TD.",
                    "Noted.",
                ),
                5: (
                    "The Quarrymoor smoke suite should finish within 40 minutes.",
                    "The last Quarrymoor smoke run took 47 minutes and reported 3 flaky tests.",
                ),
                6: (
                    "The old Quarrymoor signing key KX-28-TD was revoked on 2026-03-09.",
                    "Got it.",
                ),
            },
            [4],
            "What is the signing key id for the Quarrymoor rollout?",
            required=[["KX-82-TD"]],
            forbidden=["KX-28-TD", "bx-node-417", "qm-art-0593"],
            evidence=["KX-82-TD"],
            gold=dict(
                pair=4,
                quote="the signing key id is KX-82-TD",
                text="Signing key id is KX-82-TD",
                value="kx-82-td",
            ),
        ),
        case(
            "dp-multi-trangquyt",
            "number",
            "vi",
            {
                2: (
                    "Kho Trảng Quýt mở cửa lúc 6 giờ 15 và đóng cửa lúc 22 giờ.",
                    "Đã rõ.",
                ),
                3: (
                    "Kho Trảng Quýt chứa được 8.465 pallet và dùng mã kho TQ-773; riêng khu xuất hàng của kho Trảng Quýt có 317 vị trí xếp dỡ.",
                    "Đã ghi.",
                ),
                5: (
                    "Xe tải chở hàng cho kho Trảng Quýt có tải trọng 15 tấn.",
                    "Theo bảng điều phối, xe tải 15 tấn đã chạy 27 chuyến tới kho Trảng Quýt trong tuần trước.",
                ),
                6: (
                    "Đội bốc xếp của kho Trảng Quýt có 41 người, chia làm 3 ca.",
                    "Đã ghi nhận.",
                ),
            },
            [3],
            "Khu xuất hàng của kho Trảng Quýt có bao nhiêu vị trí xếp dỡ?",
            required=[["317"]],
            forbidden=["8.465", "TQ-773"],
            evidence=["317 vị trí"],
            gold=dict(
                pair=3,
                quote="khu xuất hàng của kho Trảng Quýt có 317 vị trí xếp dỡ",
                text="Khu xuất hàng của kho Trảng Quýt có 317 vị trí xếp dỡ",
                value="317",
            ),
        ),
        case(
            "dp-late-tamarack",
            "number",
            "en",
            {
                3: (
                    "Tamarack ingest runs 12 worker pods during business hours.",
                    "Understood.",
                ),
                4: (
                    "The Tamarack retry queue is capped at 5.48 megabytes per partition.",
                    "Noted.",
                ),
                5: (
                    "Tamarack dashboards refresh every 45 seconds.",
                    "The last Tamarack load test peaked at 2,940 messages per second before throttling.",
                ),
                6: (
                    "The Tamarack nightly export starts at 01:40 UTC.",
                    "Will do.",
                ),
                7: (
                    "The Tamarack ingest queue is capped at 4.85 megabytes per partition.",
                    "Got it.",
                ),
            },
            [7],
            "What is the per-partition size cap of the Tamarack ingest queue?",
            required=[["4.85"]],
            forbidden=["5.48"],
            evidence=["4.85 megabytes"],
            gold=dict(
                pair=7,
                quote="Tamarack ingest queue is capped at 4.85 megabytes per partition",
                text="Tamarack ingest queue is capped at 4.85 megabytes per partition",
                value="4.85",
            ),
        ),
        case(
            "dp-late-oqua",
            "identifier",
            "vi",
            {
                3: (
                    "Trạm Ổ Quạ có 4 máy phát dự phòng.",
                    "Đã rõ.",
                ),
                4: (
                    "Mã kích hoạt cũ OQR-8124-V của trạm Ổ Quạ đã hết hạn từ ngày 30 tháng 6.",
                    "Đã ghi.",
                ),
                5: (
                    "Trạm Ổ Quạ cách trung tâm điều phối 38 km.",
                    "Theo bản đồ tuyến, xe kỹ thuật mất khoảng 52 phút để tới trạm Ổ Quạ.",
                ),
                6: (
                    "Trạm Ổ Quạ có 2 bồn nhiên liệu dự trữ, mỗi bồn chứa 900 lít.",
                    "Đã ghi nhận.",
                ),
                7: (
                    "Mã kích hoạt mới của trạm Ổ Quạ là OQR-8142-V.",
                    "Đã ghi.",
                ),
            },
            [7],
            "Mã kích hoạt mới của trạm Ổ Quạ là gì?",
            required=[["OQR-8142-V"]],
            forbidden=["OQR-8124-V"],
            evidence=["OQR-8142-V"],
            gold=dict(
                pair=7,
                quote="Mã kích hoạt mới của trạm Ổ Quạ là OQR-8142-V",
                text="Mã kích hoạt mới của trạm Ổ Quạ là OQR-8142-V",
                value="oqr-8142-v",
            ),
        ),
        case(
            "dp-fix-wexcombe",
            "correction",
            "en",
            {
                2: (
                    "The Wexcombe restore drill runs every 2 months on host wx-db-07.",
                    "Understood.",
                ),
                3: (
                    "The Wexcombe archive job keeps 26 weekly snapshots.",
                    "Noted.",
                ),
                4: (
                    "The Wexcombe archive bucket currently holds 1.8 TB.",
                    "The bucket report from this morning lists 1.8 TB across 412 objects.",
                ),
                5: (
                    "Wexcombe also keeps 12 monthly snapshots.",
                    "Got it.",
                ),
                6: ("Make that 33 weekly snapshots instead.", "Updated."),
            },
            [3, 6],
            "How many weekly snapshots does the Wexcombe archive job keep now?",
            required=[["33 weekly", "33 snapshots"]],
            forbidden=["26 weekly", "26 snapshots"],
            evidence=["33 weekly snapshots"],
            gold=dict(
                pair=6,
                quote="Make that 33 weekly snapshots instead",
                text="Make that 33 weekly snapshots instead",
                value="33",
                replaces=3,
            ),
        ),
        case(
            "dp-neg-ngoive",
            "negation",
            "vi",
            {
                2: (
                    "Cụm Ngòi Ve có 6 máy ứng dụng, từ nv-app-31 đến nv-app-36.",
                    "Đã rõ.",
                ),
                3: (
                    "Cổng thanh toán Ngòi Ve xử lý trung bình 85 giao dịch mỗi giây.",
                    "Số liệu giám sát cho thấy đỉnh tải của cổng thanh toán là 140 giao dịch mỗi giây lúc 19:10.",
                ),
                4: (
                    "Ghi chú vận hành tuần này cho hệ thống Ngòi Ve, mọi người đọc kỹ trước ca trực. "
                    "Ngòi Ve chạy job đồng bộ liên tục cả ngày, mỗi lần xử lý khoảng 4.725 bản ghi, "
                    "và máy chủ nv-app-31 đang gánh phần lớn lưu lượng của cổng thanh toán; "
                    "vì vậy, không được chạy job đồng bộ Ngòi Ve trên nv-app-31 trong khoảng 17:45 đến 20:15; "
                    "ngoài khoảng đó, job đồng bộ có thể chạy bình thường trên mọi máy trong cụm; "
                    "nhật ký của job được giữ trong một tháng trên ổ lưu trữ chung, "
                    "còn khi cần chạy gấp trong khoảng đó thì dùng máy nv-app-36 thay thế.",
                    "Đã rõ.",
                ),
                6: (
                    "Báo cáo tuần trước của Ngòi Ve ghi nhận 2 sự cố mạng vào ngày 17.",
                    "Đã ghi nhận.",
                ),
            },
            [4],
            "Có được chạy job đồng bộ Ngòi Ve trên nv-app-31 lúc 19:05 không? Bắt đầu bằng Có hoặc Không, rồi nêu khoảng thời gian bị cấm.",
            required=[
                [
                    "không,",
                    "không.",
                    "không:",
                    "không được",
                    "không thể",
                    "không –",
                    "không -",
                    "không (",
                ],
                ["20:15", "20h15"],
            ],
            forbidden=["có,", "có."],
            evidence=["không được chạy job đồng bộ Ngòi Ve", "20:15"],
            gold=dict(
                pair=4,
                kind="constraint",
                quote="không được chạy job đồng bộ Ngòi Ve trên nv-app-31 trong khoảng 17:45 đến 20:15",
                text="Không được chạy job đồng bộ Ngòi Ve trên nv-app-31 trong khoảng 17:45 đến 20:15",
                value="20:15",
            ),
        ),
    ]
