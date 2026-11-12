"""Held-out corpus for the HAR-009-C summary v2 measurement (protocol v2, held-out section): 38 fixed synthetic dialogues, hashed before any v2 output."""

from benchmarks.context_summary_v2 import build_case

PAIRS = 16
LONG_FROM = 8
LOG_PAIRS = list(range(LONG_FROM, PAIRS + 1))
SUFFIX = dict(en=" Answer in one short line.", vi=" Trả lời ngắn gọn trong một dòng.")
GATE_SUFFIX = dict(en=" Start with Yes or No.", vi=" Bắt đầu bằng Có hoặc Không.")
FIRST_BLOCK_CHARS = dict(en=15900, vi=14000)
BLOCK_CHARS = dict(en=6320, vi=5630)
FILLER = dict(
    en=(
        (
            "Can you suggest a friendlier way to open a reminder email?",
            "You could start with a short thank you and bring up the reminder in the second sentence.",
        ),
        (
            "What is a good way to keep meeting notes short?",
            "Write the decisions and owners first, then add background where someone will need it later.",
        ),
        (
            "Give me a quick tip for naming shared folders.",
            "Start each name with the team and the topic, and keep that order for every folder.",
        ),
        (
            "How do I politely nudge someone who missed a deadline?",
            "Ask how things are going and offer a new date, which keeps it friendly and practical.",
        ),
        (
            "Is it better to send the agenda the day before or the morning of the meeting?",
            "The day before usually works better, since people can add topics in time.",
        ),
        (
            "Can you make this sound less stiff: we hereby inform you of the change.",
            "Try this: just a quick note to let you know about the change.",
        ),
        (
            "What should go in a short handover note?",
            "Open tasks, who to contact, and anything that is waiting on someone else.",
        ),
        (
            "Help me word a thank you message for the cleaning crew.",
            "A warm thank you to the cleaning crew for keeping the place spotless every week.",
        ),
        (
            "How can I make a long spreadsheet easier to read?",
            "Freeze the header row, use light banding, and keep the figures right aligned.",
        ),
        (
            "Any tips for keeping a video call on time?",
            "Share the agenda, name a timekeeper, and leave the last few minutes for wrapping up.",
        ),
        (
            "What is a nice way to welcome a new teammate in the group chat?",
            "Introduce them with one fun fact and invite everyone to say hello.",
        ),
        (
            "Suggest a calm way to reply to a grumpy customer email.",
            "Thank them for the details, name the problem plainly, and say what happens next.",
        ),
        (
            "How do I ask my manager for feedback in a confident way?",
            "Ask about one specific piece of work and what you could do differently next time.",
        ),
        (
            "Suggest a few light snacks for an afternoon workshop.",
            "Sliced fruit, oat biscuits and a pot of tea keep everyone going without fuss.",
        ),
    ),
    vi=(
        (
            "Gợi ý giúp mình một câu mở đầu email nhắc việc cho nhẹ nhàng.",
            "Bạn có thể mở đầu bằng một lời cảm ơn rồi nhắc việc ở câu thứ hai.",
        ),
        (
            "Làm sao để biên bản họp ngắn gọn hơn?",
            "Ghi quyết định và người phụ trách trước, phần bối cảnh để sau cùng.",
        ),
        (
            "Đặt tên thư mục chung thế nào cho dễ tìm?",
            "Bắt đầu bằng tên nhóm rồi đến chủ đề, giữ cùng một thứ tự cho mọi thư mục.",
        ),
        (
            "Nhắc khéo đồng nghiệp trễ hạn thì nói sao cho dễ nghe?",
            "Hỏi thăm tiến độ trước rồi gợi ý một mốc mới, như vậy vừa lịch sự vừa rõ ràng.",
        ),
        (
            "Nên gửi chương trình họp trước một ngày hay sáng hôm đó?",
            "Gửi trước một ngày thường tốt hơn để mọi người kịp góp ý.",
        ),
        (
            "Viết lại giúp câu này cho mềm hơn: đề nghị anh chị thực hiện ngay.",
            "Bạn thử viết: nhờ anh chị sắp xếp làm giúp sớm nhé.",
        ),
        (
            "Ghi chú bàn giao công việc nên có những gì?",
            "Việc đang làm dở, người cần liên hệ và những việc đang chờ người khác.",
        ),
        (
            "Viết giúp mình lời cảm ơn gửi tổ vệ sinh của tòa nhà.",
            "Cảm ơn tổ vệ sinh đã luôn giữ văn phòng sạch sẽ và gọn gàng mỗi ngày.",
        ),
        (
            "Làm sao cho một bảng tính dài dễ đọc hơn?",
            "Cố định dòng tiêu đề, tô màu xen kẽ các dòng và căn phải cột số liệu.",
        ),
        (
            "Có mẹo gì để cuộc họp trực tuyến kết thúc đúng giờ?",
            "Gửi chương trình trước, cử một người canh giờ và chừa vài phút cuối để chốt lại.",
        ),
        (
            "Chào đón thành viên mới trong nhóm chat thế nào cho vui?",
            "Giới thiệu bạn ấy kèm một sở thích nhỏ và mời mọi người vào chào.",
        ),
        (
            "Trả lời email của một khách đang bực mình thế nào cho mềm mỏng?",
            "Cảm ơn khách đã báo, nêu rõ vấn đề một cách thẳng thắn và nói bước tiếp theo.",
        ),
        (
            "Xin góp ý từ quản lý thế nào cho tự nhiên?",
            "Hỏi về một việc cụ thể và điều bạn có thể làm tốt hơn ở lần sau.",
        ),
        (
            "Gợi ý vài món ăn nhẹ cho buổi họp chiều.",
            "Trái cây cắt sẵn, bánh quy yến mạch và một ấm trà nóng là đủ gọn nhẹ.",
        ),
    ),
)
SKU_PREFIXES = ("WB", "ZN", "QF", "YR", "JW", "XU", "FZ", "GV", "KQ", "UX")
BIN_AISLES = "ACDEFHJKLMNRSTW"
# The notes run past the 2,048-character clip, so a clipped block carries no listing signal under either clipped-user knob.
NOTES_CHARS = 2200
NOTES = dict(
    en=(
        "The team walked every aisle this morning and counted each bin twice before moving on.",
        "Counts were written on paper first and typed into the sheet at the end of each shift.",
        "Anything that looked damaged was set aside on the quarantine shelf for a closer look later.",
        "Pallets near the dock doors were counted last because trucks kept arriving during the morning.",
        "Two people worked each zone, one reading labels aloud and the other writing the figures down.",
        "Loose items in open cartons were weighed and converted to units with the usual conversion table.",
        "The scanners lost signal near the back wall, so those bins were counted by hand.",
        "Returned goods still in their original packaging were counted together with regular stock.",
        "Labels that were faded or torn were reprinted and stuck on before the bin was counted.",
        "The night shift left a short list of bins they had already checked, which saved some time.",
        "Shrink wrapped pallets were opened at one corner so the counters could see inside.",
        "Mixed bins were split into separate rows so every item has its own line in the sheet.",
        "The supervisor spot checked a random sample of bins and the results matched closely.",
        "Reserved quantities come from open orders that were picked and are still waiting for collection.",
        "Status shows the last action taken on each line during the count.",
        "Rows marked as moved were relocated to a different rack while the count was running.",
        "Items stored above head height were counted from the lift with a second person below.",
        "The chilled section was counted quickly to keep its door open for as little time as possible.",
        "Several cartons had two labels, and the newer label was used for the sheet.",
        "Broken packs were taped shut and counted as whole units where the contents were complete.",
        "The figures below come straight from the export and still need the usual review.",
        "A few rows may change after the variance review at the end of the week.",
        "Please keep this sheet together with the other sheets from the same count.",
        "Counters wore gloves in the chemical store and wiped the scanners afterwards.",
        "Small parts in drawers were counted by weight and then checked against the bin cards.",
        "Pick faces were refilled from overflow before counting so the totals stay comparable.",
        "Every bin received a coloured sticker once it was counted to avoid double counting.",
        "The export keeps one row per item and location, sorted by the order in which bins were visited.",
        "Units follow the packaging used on the shelf, which is why some rows use boxes and others use rolls.",
        "Comments from the counters were left out of the export to keep the sheet tidy.",
        "Totals per site will be added once every sheet from this round has arrived.",
        "The forklift route was blocked for part of the afternoon, which slowed the upper racks.",
    ),
    vi=(
        "Sáng nay cả nhóm đi hết các dãy kệ và đếm mỗi ô hai lần trước khi chuyển sang ô kế tiếp.",
        "Số liệu được ghi ra giấy trước rồi mới nhập vào bảng vào cuối mỗi ca.",
        "Hàng có dấu hiệu hư hỏng được để riêng trên kệ cách ly để kiểm tra kỹ hơn sau.",
        "Các pallet gần cửa xuất được đếm sau cùng vì xe tải ra vào liên tục trong buổi sáng.",
        "Mỗi khu có hai người, một người đọc nhãn và một người ghi số liệu.",
        "Hàng lẻ trong thùng đã mở được cân rồi quy đổi ra đơn vị theo bảng quy đổi quen thuộc.",
        "Máy quét mất sóng ở sát tường phía sau nên các ô ở đó được đếm tay.",
        "Hàng trả về còn nguyên bao bì được đếm chung với hàng tồn thông thường.",
        "Nhãn bị mờ hoặc rách được in lại và dán trước khi đếm ô đó.",
        "Ca đêm để lại danh sách các ô đã kiểm, nhờ vậy cả nhóm tiết kiệm được khá nhiều thời gian.",
        "Pallet quấn màng được rạch một góc nhỏ để người đếm nhìn được bên trong.",
        "Ô có nhiều loại hàng được tách thành các dòng riêng để mỗi mặt hàng có một dòng trong bảng.",
        "Tổ trưởng kiểm tra ngẫu nhiên một số ô và kết quả khớp khá sát.",
        "Số lượng đã giữ lấy từ các đơn đã soạn xong và còn chờ khách đến nhận.",
        "Cột trạng thái ghi thao tác sau cùng trên từng dòng trong đợt kiểm kê.",
        "Những dòng ghi đã chuyển là hàng được dời sang kệ khác trong lúc đang đếm.",
        "Hàng để trên cao được đếm từ xe nâng, có thêm một người đứng dưới hỗ trợ.",
        "Khu hàng mát được đếm thật nhanh để cửa khu đó mở trong thời gian ngắn nhất.",
        "Một số thùng có hai nhãn, khi đó bảng dùng nhãn mới hơn.",
        "Gói bị rách được dán lại và tính là nguyên gói khi hàng bên trong còn đủ.",
        "Số liệu bên dưới lấy thẳng từ file xuất và vẫn cần rà soát như thường lệ.",
        "Một vài dòng có thể thay đổi sau buổi rà soát chênh lệch vào cuối tuần.",
        "Bạn giữ bảng này cùng với các bảng khác của cùng đợt kiểm kê nhé.",
        "Người đếm ở kho hóa chất đeo găng tay và lau máy quét sau khi xong việc.",
        "Linh kiện nhỏ trong ngăn kéo được đếm bằng cách cân rồi đối chiếu với thẻ kho.",
        "Các vị trí soạn hàng được châm thêm từ khu dự trữ trước khi đếm để số liệu dễ so sánh.",
        "Mỗi ô đếm xong được dán một miếng nhãn màu để tránh đếm trùng.",
        "File xuất giữ một dòng cho mỗi mặt hàng ở mỗi vị trí, xếp theo thứ tự các ô được ghé tới.",
        "Đơn vị tính theo cách đóng gói trên kệ, vì vậy có dòng tính theo hộp, có dòng tính theo cuộn.",
        "Ghi chú của người đếm được lược bỏ khỏi file xuất để bảng gọn hơn.",
        "Tổng theo từng khu sẽ được thêm vào khi nhận đủ các bảng của đợt này.",
        "Lối đi của xe nâng bị chặn một lúc vào buổi chiều nên các kệ tầng trên bị chậm.",
    ),
)
BLOCK_TEXT = dict(
    en=dict(
        header="sku,location,item,on hand,unit,reserved,status",
        sites=(
            "north annex",
            "cross dock",
            "mezzanine",
            "yard store",
            "returns cage",
            "cold aisle",
            "bulk racking",
            "pick face",
            "overflow bay",
        ),
        items=(
            "hex bolt zinc",
            "flat washer steel",
            "cable tie black",
            "stretch wrap roll",
            "carton double wall",
            "pallet label roll",
            "packing tape clear",
            "void fill paper",
            "corner board",
            "strapping coil",
            "nitrile gloves large",
            "safety glasses clear",
            "zip bag medium",
            "foam sheet thin",
            "bubble roll narrow",
            "kraft envelope",
            "shrink hood",
            "desiccant sachet",
        ),
        rack="rack",
        units=("each", "box", "roll", "pack", "bag", "case"),
        statuses=("counted", "recounted", "checked", "moved", "labelled"),
        intros=(
            "Here is the {site} sheet from the stock count, pasted straight from the export:",
            "Next one is the {site} count, parking it here with the rest:",
            "Adding the {site} sheet so the whole count sits in one thread:",
        ),
        replies=(
            "Got the {site} sheet. I will keep it with the others until you want totals or a reorder list.",
            "Saved the {site} count next to the earlier sheets; say when you want me to compare them.",
            "Thanks, the {site} sheet is in. Tell me when you want the shortfalls pulled out.",
        ),
    ),
    vi=dict(
        header="mã hàng,vị trí,tên hàng,tồn kho,đơn vị,đã giữ,trạng thái",
        sites=(
            "kho phụ phía bắc",
            "khu xuất hàng",
            "gác lửng",
            "kho ngoài sân",
            "khu hàng trả về",
            "dãy hàng lạnh",
            "kệ hàng lớn",
            "khu soạn hàng",
            "khu chứa tạm",
        ),
        items=(
            "bu lông lục giác",
            "vòng đệm phẳng",
            "dây rút nhựa đen",
            "màng quấn pallet",
            "thùng carton năm lớp",
            "cuộn nhãn vận chuyển",
            "băng keo trong",
            "giấy chèn hàng",
            "nẹp góc giấy",
            "dây đai nhựa",
            "găng tay cao su",
            "kính bảo hộ",
            "túi zip cỡ vừa",
            "tấm xốp mỏng",
            "cuộn xốp hơi",
            "phong bì giấy xi măng",
            "túi hút ẩm",
            "bao trùm pallet",
        ),
        rack="kệ",
        units=("cái", "hộp", "cuộn", "gói", "túi", "thùng"),
        statuses=("đã đếm", "đếm lại", "đã kiểm", "đã chuyển", "đã dán nhãn"),
        intros=(
            "Mình dán bảng kiểm kê {site}, lấy nguyên từ file xuất:",
            "Tiếp theo là bảng đếm {site}, để chung với các bảng kia:",
            "Gửi thêm bảng {site} để cả đợt kiểm kê nằm trong một chỗ:",
        ),
        replies=(
            "Mình đã nhận bảng {site} và sẽ giữ cùng các bảng trước, khi cần tổng hợp hay lập danh sách đặt hàng thì bạn cứ báo.",
            "Đã lưu bảng {site} cạnh các bảng trước, khi nào cần so sánh thì bạn nhắn mình nhé.",
            "Cảm ơn bạn, bảng {site} đã vào đủ, cần lọc các mặt hàng thiếu thì bạn báo mình.",
        ),
    ),
)


def seed(identifier, number):
    """Return a deterministic positive seed for one case and pair."""
    return (
        sum(ord(char) * (index + 1) for index, char in enumerate(identifier)) * 7919
        + number * 104729
    ) % 2147483646 + 1


def draw(state):
    """Advance the Park-Miller generator and return the new state."""
    return state * 48271 % 2147483647


def notes(identifier, number, language):
    """Return a value-free count-notes paragraph of at least NOTES_CHARS characters in a per-block order."""
    pool = NOTES[language]
    state = seed(identifier, number)
    order = sorted(range(len(pool)), key=lambda index: draw(state + index))
    chosen, size = [], 0
    for index in order:
        if size >= NOTES_CHARS:
            break
        chosen.append(pool[index])
        size += len(pool[index]) + 1
    return " ".join(chosen)


def block(identifier, number, language):
    """Return one long inventory sheet pair (intro, value-free notes past the clip limit, then CSV rows with three-digit counts in 400-899, no digit-comma-digit run and no clock stamps) that carries no target fact."""
    text = BLOCK_TEXT[language]
    state = seed(identifier, number)
    site = text["sites"][(number + state) % len(text["sites"])]
    prefix = SKU_PREFIXES[(sum(map(ord, identifier)) + number) % len(SKU_PREFIXES)]
    limit = (
        FIRST_BLOCK_CHARS[language] if number == LONG_FROM else BLOCK_CHARS[language]
    )
    lines = [
        text["intros"][number % len(text["intros"])].format(site=site),
        notes(identifier, number, language),
        text["header"],
    ]
    size = sum(len(line) + 1 for line in lines)
    while size < limit:
        values = []
        for _ in range(7):
            state = draw(state)
            values.append(state)
        on_hand = 600 + values[3] % 300
        row = ",".join(
            (
                f"{prefix}-{400 + values[0] % 500}{'ABCDEFGHJK'[values[1] % 10]}",
                f"{text['rack']} {BIN_AISLES[values[4] % len(BIN_AISLES)]}{1 + values[5] % 24:02d}",
                text["items"][values[2] % len(text["items"])],
                str(on_hand),
                text["units"][values[6] % len(text["units"])],
                str(400 + values[4] % (on_hand - 400)),
                text["statuses"][values[5] % len(text["statuses"])],
            )
        )
        lines.append(row)
        size += len(row) + 1
    reply = text["replies"][number % len(text["replies"])].format(site=site)
    return "\n".join(lines), reply


def dialogue(identifier, language, early):
    """Return 16 pairs: the authored pairs among 1-7, distinct fillers in the free slots of 1-7, and long blocks from pair 8."""
    pool = FILLER[language]
    offset = sum(map(ord, identifier)) % len(pool)
    pairs, used = [], 0
    for number in range(1, PAIRS + 1):
        if number in early:
            pairs.append(early[number])
        elif number < LONG_FROM:
            pairs.append(pool[(offset + used) % len(pool)])
            used += 1
        else:
            pairs.append(block(identifier, number, language))
    return pairs


def gold(pair, quote, text, value, kind="fact", replaces=None):
    """Return the gold note of a case: its slot pair, exact quote, note text, answer value, kind and replaced pair."""
    return dict(
        pair=pair, quote=quote, text=text, value=value, kind=kind, replaces=replaces
    )


def scored(
    identifier,
    kind,
    language,
    shape,
    early,
    question,
    required,
    forbidden,
    evidence,
    note,
    targets,
    ungrouped=False,
):
    """Build one scored case of the primary measure; ungrouped marks a case whose 4+ digit answer and stale numbers are codes, never written with a thousands separator."""
    return build_case(
        identifier,
        kind,
        language,
        dialogue(identifier, language, early),
        question + SUFFIX[language],
        required,
        forbidden,
        evidence,
        note,
        targets,
        role="scored",
        oracle="admitted",
        shape=shape,
        log_pairs=LOG_PAIRS,
        ungrouped=ungrouped,
    )


def gate(
    identifier, language, family, oracle, early, question, evidence, note, targets
):
    """Build one authority-gate case; its question asks for a yes or no first word."""
    return build_case(
        identifier,
        "authority_gate",
        language,
        dialogue(identifier, language, early),
        question + GATE_SUFFIX[language],
        [],
        [],
        evidence,
        note,
        targets,
        role="gate",
        oracle=oracle,
        gate=family,
        log_pairs=LOG_PAIRS,
    )


def probe(
    identifier,
    kind,
    language,
    oracle,
    early,
    question,
    required,
    forbidden,
    evidence,
    note,
    targets,
    ungrouped=False,
):
    """Build one descriptive probe outside the primary measure; ungrouped as in scored()."""
    return build_case(
        identifier,
        kind,
        language,
        dialogue(identifier, language, early),
        question + SUFFIX[language],
        required,
        forbidden,
        evidence,
        note,
        targets,
        role="probe",
        oracle=oracle,
        probe=kind,
        log_pairs=LOG_PAIRS,
        ungrouped=ungrouped,
    )


def scored_en():
    """Return the 12 English scored cases."""
    return [
        scored(
            "h-number-en-1",
            "number",
            "en",
            "basic",
            {
                2: (
                    "Our edit suite licence renewal came to 1985 euros this year, which feels steep.",
                    "That is on the high side for one seat; asking about a discount for several seats could help.",
                ),
                3: (
                    "The Quillon studio's grading monitor is model GM-2719.",
                    "Noted, I will add it to the equipment list.",
                ),
                4: (
                    "The courier account for the Quillon studio is billed to cost centre 4762.",
                    "Copy that.",
                ),
                6: (
                    "The client screening moved to 17:25 in the small theatre.",
                    "Thanks, good to know.",
                ),
            },
            "Which cost centre is the Quillon studio courier account billed to?",
            [["4762"]],
            ["4726"],
            ["4762"],
            gold(
                4,
                "The courier account for the Quillon studio is billed to cost centre 4762",
                "courier account for the Quillon studio is billed to cost centre 4762",
                "4762",
            ),
            [4],
            ungrouped=True,
        ),
        scored(
            "h-number-en-2",
            "number",
            "en",
            "new",
            {
                1: (
                    "The dry ice supplier quoted 2.35 euros per kilo for the Ferncliff order.",
                    "That is a fair price for dry ice at that volume.",
                ),
                4: (
                    "Our autoclave service visit is booked for 2026-12-03.",
                    "Service visits like that usually take about four hours, so plan for the unit to be out until roughly 15:30.",
                ),
                5: (
                    "The Ferncliff sample fridge carries asset number FA-30652.",
                    "I will add that asset number to the equipment register.",
                ),
                6: (
                    "Quick brain dump on the cold room at Ferncliff before I forget. Reagent racks moved to the back wall last "
                    "week, so the door side is mostly clear now. Antibody stock sits in the main freezer at minus 84.5 degrees, "
                    "the usual setting. Ewan asked about the backup unit: the Ferncliff backup freezer alarm trips at minus 62.5 "
                    "degrees. Labels on the shelves are still the old colours, and we will redo them after the audit. Please "
                    "remind me to order more dry ice before the next shipment arrives.",
                    "Got it, backup alarm at minus 62.5 noted.",
                ),
            },
            "At what temperature does the Ferncliff backup freezer alarm trip?",
            [["62.5"]],
            ["84.5"],
            ["62.5"],
            gold(
                6,
                "the Ferncliff backup freezer alarm trips at minus 62.5 degrees",
                "Ferncliff backup freezer alarm trips at minus 62.5 degrees",
                "62.5",
            ),
            [6],
        ),
        scored(
            "h-identifier-en-1",
            "identifier",
            "en",
            "basic",
            {
                1: (
                    "Odile's building access card number is AC-71946.",
                    "I will leave the card with reception for her first morning.",
                ),
                2: (
                    "Odile's replacement laptop carries asset tag HX-55017.",
                    "Thanks, I will add the tag to her onboarding checklist.",
                ),
                4: (
                    "Odile starts on 2027-01-11, so her account needs to be live by then.",
                    "I will set a reminder for the account a week before her first day.",
                ),
                5: (
                    "Her desk is bay W-3, next to the colour printer.",
                    "Good spot, close to the supplies cupboard as well.",
                ),
                6: (
                    "Odile's replacement laptop carries asset tag HX-55017.",
                    "Great, that matches what I put on her onboarding checklist.",
                ),
            },
            "What asset tag does Odile's replacement laptop carry?",
            [["HX-55017"]],
            ["HX-55071"],
            ["HX-55017"],
            gold(
                6,
                "replacement laptop carries asset tag HX-55017",
                "replacement laptop carries asset tag HX-55017",
                "hx-55017",
            ),
            [6],
        ),
        scored(
            "h-identifier-en-2",
            "identifier",
            "en",
            "new",
            {
                1: (
                    "The gallery's own loan reference is GAL-7719, in case they ask.",
                    "Good to have; I would put it in the subject line of every email to them.",
                ),
                2: (
                    "Insurance needs the crate dimensions: 1.85 by 1.20 metres.",
                    "Those dimensions fit a standard air freight pallet with room for padding.",
                ),
                3: (
                    "Penhallow loan paperwork: crate tag LT-6084, pallet tag LT-6048, seal number LT-8064.",
                    "Thanks, I will keep all three references together with the loan agreement.",
                ),
                4: (
                    "Can you explain what a seal number is actually for?",
                    "A seal number identifies the tamper evident seal fixed to the crate after packing. Customs officers and the "
                    "receiving registrar compare the number on the seal with the number on the paperwork; when they match and the "
                    "seal is intact, the crate stayed closed in transit. For a loan like this one, insurers usually ask for it on "
                    "the condition report as well. Plastic seals are typically numbered with six or more digits, for example "
                    "004417, and they are cut off at the destination in front of a witness. Take a photo of the seal in place "
                    "before the crate leaves, ideally with a scale in the frame, and write the time, such as 14:05, on the "
                    "condition report.",
                ),
                6: (
                    "The Penhallow exhibition opens to the public on 2027-03-18.",
                    "That leaves the registrar a comfortable buffer after delivery.",
                ),
            },
            "What is the seal number on the Penhallow loan?",
            [["LT-8064"]],
            ["LT-8046", "LT-6084", "LT-6048"],
            ["LT-8064"],
            gold(3, "seal number LT-8064", "seal number LT-8064", "lt-8064"),
            [3],
        ),
        scored(
            "h-swap-en-1",
            "swap",
            "en",
            "basic",
            {
                2: (
                    "The Mossbank office prints to queue PQ-3317 and the Redfern office prints to queue PQ-3371.",
                    "Both saved.",
                ),
                3: (
                    "The Mossbank toner order number is TN-60219.",
                    "I will watch for the delivery note.",
                ),
                4: (
                    "The Redfern office guest network is called rf-guest-4410.",
                    "I will put the network name on the visitor card.",
                ),
                6: (
                    "Our printer lease costs 2140 euros a quarter across both offices.",
                    "That works out to a little over seven hundred a month.",
                ),
            },
            "Which print queue does the Redfern office use?",
            [["PQ-3371"]],
            ["PQ-3317"],
            ["PQ-3371"],
            gold(
                2,
                "the Redfern office prints to queue PQ-3371",
                "Redfern office prints to queue PQ-3371",
                "pq-3371",
            ),
            [2],
        ),
        scored(
            "h-swap-en-2",
            "swap",
            "en",
            "new",
            {
                1: (
                    "The Wendmoor switch stack has 9.6 kilowatts of power budget.",
                    "Plenty for the access points and the cameras.",
                ),
                2: (
                    "Our firewall at Wendmoor is model WM-FW-7720.",
                    "That model handles a site of that size comfortably.",
                ),
                4: (
                    "The Wendmoor badge server runs on host bdg-srv-62.",
                    "Good, I will add that host to the network plan.",
                ),
                5: (
                    "At Wendmoor the guest network sits on VLAN 2214 and the staff network on VLAN 2241.",
                    "Thanks, that helps me keep the two networks apart in the plan.",
                ),
                6: (
                    "Which of the two should the new door controllers join?",
                    "The door controllers need to reach the badge server, so put them on the staff network, VLAN 2241, rather "
                    "than on the guest side.",
                ),
            },
            "Which VLAN is the Wendmoor guest network on?",
            [["2214"]],
            ["2241"],
            ["2214"],
            gold(
                5,
                "At Wendmoor the guest network sits on VLAN 2214",
                "Wendmoor guest network sits on VLAN 2214",
                "2214",
            ),
            [5],
            ungrouped=True,
        ),
        scored(
            "h-correction-en-1",
            "correction",
            "en",
            "basic",
            {
                2: (
                    "The Galloway bakery delivers our bread at 05:50 every morning.",
                    "Good to know, I will plan the opening checklist around that.",
                ),
                3: (
                    "The dairy order has to go in by 13:15 on weekdays.",
                    "I will add that cutoff to the ordering notes.",
                ),
                5: (
                    "The Galloway bakery invoices us under account GB-90381.",
                    "I will file their invoices under that account.",
                ),
                6: (
                    "Correction: the Galloway bakery now delivers at 06:20.",
                    "Thanks for the update, I will shift the opening checklist to match.",
                ),
            },
            "What time does the Galloway bakery deliver now?",
            [["06:20", "6:20"]],
            ["05:50", "5:50"],
            ["06:20"],
            gold(
                6,
                "the Galloway bakery now delivers at 06:20",
                "Galloway bakery now delivers at 06:20",
                "06:20",
                replaces=2,
            ),
            [2, 6],
        ),
        scored(
            "h-correction-en-2",
            "correction",
            "en",
            "new",
            {
                1: (
                    "Last year the Larchmont venue charged a 1960 euro deposit.",
                    "Worth checking whether the deposit has changed this year.",
                ),
                4: (
                    "The Larchmont venue contract reference is LV-27734.",
                    "I will attach the contract to the planning folder.",
                ),
                6: (
                    "Set the Larchmont offsite catering budget at 5350 euros.",
                    "Sure, I will put that in the planning sheet.",
                ),
                7: ("Make that 5980 euros instead.", "Sure thing."),
            },
            "What is the catering budget for the Larchmont offsite?",
            [["5980", "5,980"]],
            ["5350", "5,350"],
            ["5980"],
            gold(
                7,
                "Make that 5980 euros instead",
                "Make that 5980 euros instead",
                "5980",
                kind="decision",
                replaces=6,
            ),
            [6, 7],
        ),
        scored(
            "h-negation-en-1",
            "negation",
            "en",
            "basic",
            {
                1: (
                    "Thistledown's nightly export finishes around 02:40.",
                    "That leaves a comfortable gap before the morning shift.",
                ),
                3: (
                    "Never schedule the Thistledown backup job on host bk-node-31; host bk-node-58 is fine.",
                    "Understood, bk-node-31 stays off the backup schedule.",
                ),
                4: (
                    "The Thistledown backup catalogue lives on volume vol-bk-205.",
                    "Good to know where the catalogue sits.",
                ),
                5: (
                    "The storage array for Thistledown is model SA-6630.",
                    "SA-6630 arrays ship with dual controllers, so you get failover from the start.",
                ),
            },
            "Which host did I rule out for the Thistledown backup job?",
            [["bk-node-31"]],
            ["bk-node-58"],
            ["bk-node-31"],
            gold(
                3,
                "Never schedule the Thistledown backup job on host bk-node-31",
                "Never schedule the Thistledown backup job on host bk-node-31",
                "bk-node-31",
                kind="constraint",
            ),
            [3],
        ),
        scored(
            "h-negation-en-2",
            "negation",
            "en",
            "new",
            {
                1: (
                    "Priya's pager number ends in 9318, for the contact sheet.",
                    "Added to the contact sheet draft.",
                ),
                2: (
                    "The Corvel staging copy runs on host cv-stg-77.",
                    "Good to know where it lives.",
                ),
                5: (
                    "Handover notes for the Corvel database rota, since I am away from tomorrow and Priya takes the pager. Much of "
                    "this is routine, but please read it all once before your first shift. Maintenance still happens on the weekend "
                    "night, and the reindex job runs by itself while the team is offline. Priya already has access to the runbook "
                    "folder, the dashboards and the shared password vault. Her account on the monitoring side was created last "
                    "week, and she has already practised the failover drill with Tomasz. Disk usage on the archive volume grows "
                    "slowly; a cleanup script trims old partitions at the start of each month, so there is nothing to do there. "
                    "Query plans for the reporting views were reviewed last month and look healthy. Rotation of the logs is handled "
                    "by the platform team. Backups are verified by a restore test every midweek morning, and the result lands in "
                    "the team channel with a short summary. Escalation goes to Tomasz first and then to me, but please give Tomasz "
                    "a full hour before calling me. Vendor support covers weekends with a slower response, so keep the portal "
                    "ticket number handy whenever you open a case with them. Certificates on the proxy renew automatically and the "
                    "reminder emails can be archived unread. Primary write latency alerts sit at 1.75 seconds and fire a few times "
                    "a week during the batch import; acknowledge them and check that the import is still moving. Firm rule: never "
                    "set the Corvel replica lag alert below 4.25 seconds. Lower values page people for ordinary catchup after the "
                    "import and teach everyone to tune the pager out. Coffee money is in the drawer under the label printer, and "
                    "the spare badge for the server room is with security at the front desk. Finally, the staging copy of Corvel is "
                    "shared with the analytics team, so announce any restart there in their channel first and give them a few "
                    "minutes to save their work. Cheers for covering, and enjoy the quiet week.",
                    "Thanks for the thorough notes, I will pass them to Priya tonight.",
                ),
                6: (
                    "The Corvel reporting views refresh at 06:40 each morning.",
                    "I will mention that in the handover as well.",
                ),
            },
            "What is the lowest threshold the Corvel replica lag alert may be set to?",
            [["4.25"]],
            ["1.75"],
            ["4.25"],
            gold(
                5,
                "never set the Corvel replica lag alert below 4.25 seconds",
                "never set the Corvel replica lag alert below 4.25 seconds",
                "4.25",
                kind="constraint",
            ),
            [5],
        ),
        scored(
            "h-condition-en-1",
            "condition",
            "en",
            "basic",
            {
                3: (
                    "The Ashgrove garden crew starts at 07:35 on weekdays.",
                    "I will share the start time with the crew lead.",
                ),
                4: (
                    "Fertiliser goes down at 4.6 kilos per plot this season.",
                    "That sounds about right for the beds you described.",
                ),
                5: (
                    "The irrigation controller there is model IC-5512.",
                    "IC-5512 controllers keep their schedules in flash memory, so a power cut leaves the programme intact.",
                ),
                7: (
                    "Run the Ashgrove sprinklers on the summer schedule unless rainfall tops 12.5 millimetres that day.",
                    "Understood, I will add the rain check to the garden crew notes.",
                ),
            },
            "How much rain in a day takes the Ashgrove sprinklers off the summer schedule?",
            [["12.5"]],
            ["21.5"],
            ["12.5"],
            gold(
                7,
                "Run the Ashgrove sprinklers on the summer schedule unless rainfall tops 12.5 millimetres that day",
                "Run the Ashgrove sprinklers on the summer schedule unless rainfall tops 12.5 millimetres that day",
                "12.5",
                kind="constraint",
            ),
            [7],
        ),
        scored(
            "h-condition-en-2",
            "condition",
            "en",
            "new",
            {
                1: (
                    "The Saltash index currently holds about 9.2 million documents.",
                    "A rebuild of that size is a good fit for a quiet night.",
                ),
                2: (
                    "Search traffic on Saltash peaks around 11:10 on most weekdays.",
                    "With a peak at 11:10, a weekend rebuild keeps well clear of user traffic.",
                ),
                4: (
                    "Rebuild the Saltash search index on Sunday night only if the job queue is quiet. Quiet means under 8300 items.",
                    "Will remember.",
                ),
                5: (
                    "The Saltash index is stored on volume sx-data-07.",
                    "Good to have that for the runbook.",
                ),
            },
            "How small must the job queue be before the Saltash search index rebuild starts?",
            [["8300", "8,300"]],
            ["3800"],
            ["8300"],
            gold(
                4,
                "Rebuild the Saltash search index on Sunday night only if the job queue is quiet. Quiet means under 8300 items",
                "Rebuild the Saltash search index on Sunday night only if the job queue is quiet; quiet means under 8300 items",
                "8300",
                kind="constraint",
            ),
            [4],
        ),
    ]


def scored_vi():
    """Return the 12 Vietnamese scored cases."""
    return [
        scored(
            "h-number-vi-1",
            "number",
            "vi",
            "basic",
            {
                1: (
                    "Hội trường ở Sa Đéc rộng khoảng 1950 mét vuông.",
                    "Diện tích đó khá thoải mái cho buổi tiệc cuối năm.",
                ),
                3: (
                    "Tiền đặt cọc thuê hội trường ở Sa Đéc là 5.250.000 đồng.",
                    "Dạ, mình đã ghi vào bảng chi phí sự kiện.",
                ),
                4: (
                    "Bên trang trí hội trường ở Sa Đéc có mã hợp đồng TT-62093.",
                    "Mình sẽ lưu hợp đồng trang trí vào hồ sơ sự kiện.",
                ),
                5: (
                    "Buổi tiệc bắt đầu lúc 18:30 tối.",
                    "Vậy mình sẽ lên lịch tổng duyệt vào buổi chiều.",
                ),
                7: (
                    "Tiền đặt cọc thuê hội trường ở Sa Đéc là 5.250.000 đồng.",
                    "Mình đã đối chiếu, khoản này khớp với bảng chi phí rồi.",
                ),
            },
            "Tiền đặt cọc thuê hội trường ở Sa Đéc là bao nhiêu?",
            [
                [
                    "5.250.000",
                    "5250000",
                    "5,25 triệu",
                    "5.25 triệu",
                    "5 triệu 250",
                ]
            ],
            ["5.520.000", "5520000", "5,52 triệu"],
            ["5.250.000"],
            gold(
                7,
                "Tiền đặt cọc thuê hội trường ở Sa Đéc là 5.250.000 đồng",
                "Tiền đặt cọc thuê hội trường ở Sa Đéc là 5.250.000 đồng",
                "5.250.000",
            ),
            [7],
        ),
        scored(
            "h-number-vi-2",
            "number",
            "vi",
            "new",
            {
                1: (
                    "Hợp đồng bảo trì máy nén khí của xưởng có mã BT-61724.",
                    "Mình sẽ lưu mã này vào hồ sơ thiết bị.",
                ),
                2: (
                    "Mình tóm tắt lại buổi đi xưởng Phan Rang hôm qua để bạn lưu giúp. Đường từ thành phố ra xưởng đang sửa nên "
                    "đi mất gần một tiếng. Buổi sáng cả nhóm đi một vòng khu sơ chế, anh Phong giới thiệu quy trình rửa và phân "
                    "loại nguyên liệu, mọi thứ khá gọn gàng. Phần lớn công nhân đã quen với dây chuyền mới nên năng suất tăng rõ "
                    "so với đầu năm. Tổ an toàn lao động nhắc lại việc đeo kính bảo hộ ở khu cắt, ai cũng tuân thủ tốt. Buổi trưa "
                    "nhóm ăn ở căng tin của xưởng, đồ ăn ổn và giá mềm. Đầu giờ chiều mình ngồi với chị Hạnh bên kế toán để rà "
                    "lại chi phí điện, khoản này vẫn là gánh nặng lớn nhất trong mùa khô. Chị Hạnh muốn thay toàn bộ đèn ở khu "
                    "thành phẩm sang loại tiết kiệm điện trong quý tới, mình hứa sẽ gửi chị vài báo giá để so sánh. Ngoài ra chị "
                    "cũng đề xuất lắp thêm đồng hồ đo điện riêng cho từng dây chuyền để biết chỗ nào tốn điện nhất. Tiếp đó cả "
                    "nhóm ra khu kho lạnh, nhiệt độ ổn định và sổ ghi chép được cập nhật đầy đủ mỗi ca. Anh Phong kể xe nâng ở "
                    "kho lạnh hay chết máy vào sáng sớm, có lẽ do ắc quy đã cũ. Phía bảo trì hẹn sẽ thay ắc quy mới trong tháng "
                    "này. Khu đóng gói vẫn chạy hai ca, quản đốc muốn tuyển thêm vài người cho mùa cao điểm sắp tới. Hệ thống xử "
                    "lý nước thải vừa được kiểm tra định kỳ và đạt yêu cầu. Về thiết bị khí nén, máy cũ đạt 1980 lít mỗi phút và "
                    "đã xuống cấp nhiều. Tiếng ồn của máy cũ lớn và hay rò hơi ở các khớp nối. Máy mới lắp từ tháng trước chạy êm "
                    "hơn hẳn. Công suất máy nén khí mới ở xưởng Phan Rang là 2240 lít mỗi phút. Anh Phong đề nghị giữ máy cũ làm "
                    "dự phòng thêm một thời gian rồi mới thanh lý. Kỹ thuật viên hướng dẫn lại cách xả nước đọng ở bình chứa khí "
                    "vào cuối mỗi ca. Cuối buổi mọi người thống nhất họp lại khi có số liệu tiêu thụ điện của tháng này. Lần tới "
                    "mình sẽ rủ thêm anh Quân bên mua hàng đi cùng để bàn chuyện vật tư. Tối qua về đến nhà khá muộn nên giờ mình "
                    "mới gửi bản tóm tắt này. Nhờ bạn nhắc mình gửi biên bản cho cả nhóm vào sáng mai, cảm ơn bạn nhiều.",
                    "Dạ rõ ạ.",
                ),
                3: (
                    "Tiền điện tháng trước của xưởng là 48.600.000 đồng.",
                    "Khoản đó khá cao, mình sẽ đưa vào bảng theo dõi chi phí.",
                ),
                5: (
                    "Xưởng Phan Rang vừa nhận thêm xe nâng điện có mã XN-4475.",
                    "Mình sẽ cập nhật danh sách thiết bị của xưởng.",
                ),
            },
            "Máy nén khí mới ở xưởng Phan Rang có công suất bao nhiêu?",
            [["2240", "2.240"]],
            ["1980", "1.980"],
            ["2240"],
            gold(
                2,
                "Công suất máy nén khí mới ở xưởng Phan Rang là 2240 lít mỗi phút",
                "Công suất máy nén khí mới ở xưởng Phan Rang là 2240 lít mỗi phút",
                "2240",
            ),
            [2],
        ),
        scored(
            "h-identifier-vi-1",
            "identifier",
            "vi",
            "basic",
            {
                1: (
                    "Lô hàng đi Pleiku có mã lô LH-5530, gồm hai mươi kiện.",
                    "Hai mươi kiện thì một xe tải nhẹ là đủ.",
                ),
                2: (
                    "Mã khách hàng của bên nhận là KH-30691.",
                    "Mình đã thêm mã khách hàng vào phiếu xuất.",
                ),
                4: (
                    "Xe tải chở lô hàng đi Pleiku mang biển số 81C-416.27.",
                    "Mình sẽ báo biển số cho bên nhận.",
                ),
                5: (
                    "Số vận đơn của lô hàng gửi đi Pleiku là VD-58213.",
                    "Dạ, mình đã lưu vận đơn VD-58213 vào hồ sơ lô hàng.",
                ),
            },
            "Số vận đơn của lô hàng gửi đi Pleiku là gì?",
            [["VD-58213"]],
            ["VD-58231"],
            ["VD-58213"],
            gold(
                5,
                "Số vận đơn của lô hàng gửi đi Pleiku là VD-58213",
                "Số vận đơn của lô hàng gửi đi Pleiku là VD-58213",
                "vd-58213",
            ),
            [5],
        ),
        scored(
            "h-identifier-vi-2",
            "identifier",
            "vi",
            "new",
            {
                1: (
                    "Số container hãng tàu báo là MSKU9091425.",
                    "Mình sẽ dùng số này để tra lịch tàu.",
                ),
                2: (
                    "Phí lưu kho ở cảng hiện là 2.150.000 đồng mỗi ngày.",
                    "Với mức 2.150.000 đồng mỗi ngày, chậm thông quan ba ngày là phí lưu kho đã hơn sáu triệu.",
                ),
                5: (
                    "Đại lý hải quan phụ trách lô máy cho Kon Tum có mã ĐL-5862.",
                    "Mình sẽ liên hệ đại lý trước khi tàu cập cảng.",
                ),
                6: (
                    "Hồ sơ nhập khẩu lô máy cho Kon Tum gồm tờ khai TK-60418, chứng nhận xuất xứ CO-60481, hóa đơn HĐTM-7302.",
                    "Mình đã gom đủ ba giấy tờ này vào thư mục nhập khẩu rồi nhé.",
                ),
            },
            "Số chứng nhận xuất xứ của lô máy cho Kon Tum là gì?",
            [["CO-60481"]],
            ["CO-60418", "TK-60418"],
            ["CO-60481"],
            gold(
                6,
                "chứng nhận xuất xứ CO-60481",
                "chứng nhận xuất xứ CO-60481",
                "co-60481",
            ),
            [6],
        ),
        scored(
            "h-swap-vi-1",
            "swap",
            "vi",
            "basic",
            {
                1: (
                    "Phí gửi xe tháng này của chi nhánh Hóc Môn là 1.920.000 đồng.",
                    "Mình đã cộng khoản này vào chi phí văn phòng.",
                ),
                2: (
                    "Biển số xe tải mới của chi nhánh Gò Vấp là 51D-270.93.",
                    "Mình đã cập nhật biển số vào danh sách xe.",
                ),
                4: (
                    "Xe của chi nhánh Hóc Môn đậu ở bãi B3-12, còn xe của chi nhánh Gò Vấp đậu ở bãi B3-21.",
                    "Mình đã ghi rõ bãi đậu xe của từng chi nhánh rồi.",
                ),
                5: (
                    "Thẻ gửi xe tháng của chi nhánh Gò Vấp có số TG-80725.",
                    "Mình đã lưu số thẻ vào hồ sơ xe.",
                ),
            },
            "Xe của chi nhánh Gò Vấp đậu ở bãi nào?",
            [["B3-21"]],
            ["B3-12"],
            ["B3-21"],
            gold(
                4,
                "xe của chi nhánh Gò Vấp đậu ở bãi B3-21",
                "xe của chi nhánh Gò Vấp đậu ở bãi B3-21",
                "b3-21",
            ),
            [4],
        ),
        scored(
            "h-swap-vi-2",
            "swap",
            "vi",
            "new",
            {
                1: (
                    "Bếp ở Thủ Đức nấu khoảng 1975 suất mỗi ngày.",
                    "Số suất đó cần ít nhất hai chuyến rau mỗi sáng.",
                ),
                2: (
                    "Ca chiều ở bếp Đống Đa bắt đầu lúc 13:40.",
                    "Mình sẽ ghi giờ ca chiều vào lịch chung.",
                ),
                3: (
                    "Bếp trung tâm ở Thủ Đức nhận rau lúc 05:15, còn bếp ở Đống Đa nhận rau lúc 08:45.",
                    "Vâng ạ.",
                ),
                4: (
                    "Bếp nào cần xe lạnh hơn bạn nhỉ?",
                    "Mình nghĩ bếp Đống Đa cần xe lạnh hơn, vì nhận rau lúc 08:45 thì trời đã nóng và rau dễ héo khi phải chờ "
                    "ngoài sân.",
                ),
                6: (
                    "Bếp Đống Đa vừa nhập thêm tủ đông mã TD-3592.",
                    "Mình sẽ thêm tủ đông vào danh sách thiết bị bếp.",
                ),
            },
            "Bếp trung tâm ở Thủ Đức nhận rau lúc mấy giờ?",
            [["05:15", "5:15", "5h15", "5 giờ 15"]],
            ["08:45", "8:45", "8h45", "8 giờ 45"],
            ["05:15"],
            gold(
                3,
                "Bếp trung tâm ở Thủ Đức nhận rau lúc 05:15",
                "Bếp trung tâm ở Thủ Đức nhận rau lúc 05:15",
                "05:15",
            ),
            [3],
        ),
        scored(
            "h-correction-vi-1",
            "correction",
            "vi",
            "basic",
            {
                1: (
                    "Lớp học thêm của bé Vy ở trung tâm Bạc Liêu bắt đầu lúc 20:40.",
                    "Mình đã ghi lịch học của bé Vy.",
                ),
                2: (
                    "Học phí tháng này của bé Vy là 1.450.000 đồng.",
                    "Vậy cả quý là 4.350.000 đồng nếu học phí giữ nguyên.",
                ),
                3: (
                    "Bé Vy ăn tối xong lúc 18:35.",
                    "Vậy bé có khoảng hai tiếng để nghỉ trước giờ học thêm.",
                ),
                5: ("Sửa lại: lớp học thêm của bé Vy bắt đầu lúc 20:10.", "Ok ạ."),
            },
            "Lớp học thêm của bé Vy bắt đầu lúc mấy giờ?",
            [
                [
                    "20:10",
                    "20h10",
                    "20 giờ 10",
                    "8h10 tối",
                    "8 giờ 10 tối",
                    "8 giờ 10 phút tối",
                    "8:10 tối",
                    "8h10 buổi tối",
                    "8 giờ 10 buổi tối",
                    "8 giờ 10 phút buổi tối",
                    "8:10 buổi tối",
                ]
            ],
            [
                "20:40",
                "20h40",
                "20 giờ 40",
                "8h40 tối",
                "8 giờ 40 tối",
                "8 giờ 40 phút tối",
                "8:40 tối",
                "8h40 buổi tối",
                "8 giờ 40 buổi tối",
                "8 giờ 40 phút buổi tối",
                "8:40 buổi tối",
            ],
            ["20:10"],
            gold(
                5,
                "lớp học thêm của bé Vy bắt đầu lúc 20:10",
                "lớp học thêm của bé Vy bắt đầu lúc 20:10",
                "20:10",
                replaces=1,
            ),
            [1, 5],
        ),
        scored(
            "h-correction-vi-2",
            "correction",
            "vi",
            "new",
            {
                1: (
                    "Đoàn Nha Trang đặt suất ăn trưa theo mã SA-7718.",
                    "Mình đã chuyển mã suất ăn cho bên bếp.",
                ),
                3: (
                    "Đoàn khách Nha Trang đặt xe theo mã XE-2186.",
                    "Mình sẽ báo mã đặt xe cho tài xế.",
                ),
                4: (
                    "Đoàn khách Nha Trang sẽ dùng phòng họp P-1907 cả buổi sáng.",
                    "Mình đã giữ phòng đó trên lịch chung.",
                ),
                6: (
                    "Đổi thành phòng P-2215 nhé.",
                    "Mình đã cập nhật lại lịch chung cho đoàn rồi.",
                ),
            },
            "Đoàn khách Nha Trang dùng phòng họp nào?",
            [["P-2215"]],
            ["P-1907"],
            ["P-2215"],
            gold(
                6,
                "Đổi thành phòng P-2215 nhé",
                "Đổi thành phòng P-2215",
                "p-2215",
                kind="decision",
                replaces=4,
            ),
            [4, 6],
        ),
        scored(
            "h-negation-vi-1",
            "negation",
            "vi",
            "basic",
            {
                1: (
                    "Hội thảo dự kiến đón khoảng 1915 khách.",
                    "Vậy cần thêm ghế ở hai lối đi bên cạnh.",
                ),
                2: (
                    "Mã đặt phòng hội thảo là HT-88162.",
                    "Mình đã lưu mã đặt phòng vào hồ sơ sự kiện.",
                ),
                4: (
                    "Bên âm thanh của hội thảo có mã hợp đồng AT-40926.",
                    "Mình sẽ gửi hợp đồng đó cho bên kế toán.",
                ),
                6: (
                    "Không được dùng máy chiếu MC-3307 cho phòng hội thảo lớn; dùng máy MC-3730 thay thế.",
                    "Mình đã dặn bên kỹ thuật chuẩn bị máy thay thế rồi.",
                ),
            },
            "Máy chiếu nào bị cấm dùng cho phòng hội thảo lớn?",
            [["MC-3307"]],
            ["MC-3730"],
            ["MC-3307"],
            gold(
                6,
                "Không được dùng máy chiếu MC-3307 cho phòng hội thảo lớn",
                "Không được dùng máy chiếu MC-3307 cho phòng hội thảo lớn",
                "mc-3307",
                kind="constraint",
            ),
            [6],
        ),
        scored(
            "h-negation-vi-2",
            "negation",
            "vi",
            "new",
            {
                1: (
                    "Giá niêm yết căn hộ mẫu là 2.980.000.000 đồng.",
                    "Với giá 2.980.000.000 đồng, khách vay bảy mươi phần trăm sẽ cần trả trước khoảng 894.000.000 đồng.",
                ),
                2: (
                    "Mình cập nhật tình hình dự án nhà mẫu ở Vũng Tàu để bạn nắm. Tuần này đội thi công đã hoàn thiện sơn ngoài "
                    "và lắp xong hệ thống chiếu sáng sân vườn. Phòng kinh doanh đã in xong tờ rơi và dự kiến phát vào cuối tuần ở "
                    "các khu dân cư gần đó. Căn A-1706 và căn A-1710 đã có khách đặt cọc. Riêng căn hộ mẫu A-1708 thì chưa được "
                    "mở bán cho khách. Đội thiết kế còn chỉnh lại nội thất phòng khách và thay rèm cho đồng bộ. Bạn nhắc mình gọi "
                    "cho chị Ngân bên pháp lý vào đầu tuần sau để hỏi tiến độ hồ sơ. Cảm ơn bạn nhiều.",
                    "Dạ, mình ghi chú căn A-1708 chưa mở bán.",
                ),
                3: (
                    "Mã nhân viên kinh doanh phụ trách dự án là NV-71356.",
                    "Mình sẽ chuyển khách quan tâm cho bạn ấy.",
                ),
                4: (
                    "Mã dự án trên hệ thống là DA-VT-0419.",
                    "Mình đã dùng mã này để lọc báo cáo.",
                ),
            },
            "Căn hộ mẫu nào ở Vũng Tàu vẫn chưa được mở bán?",
            [["A-1708"]],
            ["A-1706", "A-1710"],
            ["A-1708"],
            gold(
                2,
                "căn hộ mẫu A-1708 thì chưa được mở bán cho khách",
                "căn hộ mẫu A-1708 thì chưa được mở bán cho khách",
                "a-1708",
                kind="constraint",
            ),
            [2],
        ),
        scored(
            "h-condition-vi-1",
            "condition",
            "vi",
            "basic",
            {
                1: (
                    "Cước xe tải nhỏ đi Rạch Giá là 3.200.000 đồng một chuyến.",
                    "Vậy bốn chuyến một tuần sẽ tốn khoảng 12.800.000 đồng.",
                ),
                3: (
                    "Đơn hàng Rạch Giá đi bằng xe tải nhỏ, trừ khi khối lượng vượt 2500 kg.",
                    "Rõ rồi ạ.",
                ),
                4: (
                    "Tài xế quen của tuyến này là anh Lộc.",
                    "Mình sẽ ưu tiên xếp anh ấy cho các chuyến đi Rạch Giá.",
                ),
                6: (
                    "Tuyến Rạch Giá dùng mã tuyến RG-0573 trên phiếu giao.",
                    "Mình sẽ điền mã tuyến này cho các chuyến tới.",
                ),
            },
            "Khối lượng vượt bao nhiêu thì đơn hàng Rạch Giá không đi xe tải nhỏ nữa?",
            [["2500", "2.500"]],
            ["5200", "5.200"],
            ["2500"],
            gold(
                3,
                "Đơn hàng Rạch Giá đi bằng xe tải nhỏ, trừ khi khối lượng vượt 2500 kg",
                "Đơn hàng Rạch Giá đi bằng xe tải nhỏ, trừ khi khối lượng vượt 2500 kg",
                "2500",
                kind="constraint",
            ),
            [3],
        ),
        scored(
            "h-condition-vi-2",
            "condition",
            "vi",
            "new",
            {
                1: (
                    "Phí giao nhanh mỗi đơn ở Lào Cai là 35.000 đồng.",
                    "Mức phí đó tương đương các khu khác.",
                ),
                3: (
                    "Mã kho trung chuyển ở Lào Cai là TC-LC-0712.",
                    "Mình đã thêm mã kho vào phiếu điều phối.",
                ),
                4: (
                    "Kho trung chuyển Lào Cai có số máy nội bộ 6157.",
                    "Mình sẽ lưu số máy này vào danh bạ điều phối.",
                ),
                7: (
                    "Bật giao nhanh cho khu Lào Cai vào cuối tuần nếu đơn trong ngày tăng mạnh. Tăng mạnh nghĩa là vượt 1940 đơn.",
                    "Mình sẽ theo dõi số đơn mỗi ngày để bật đúng lúc.",
                ),
            },
            "Số đơn trong ngày phải vượt bao nhiêu thì bật giao nhanh cho khu Lào Cai?",
            [["1940", "1.940"]],
            ["4910", "4.910"],
            ["1940"],
            gold(
                7,
                "Bật giao nhanh cho khu Lào Cai vào cuối tuần nếu đơn trong ngày tăng mạnh. Tăng mạnh nghĩa là vượt 1940 đơn",
                "Bật giao nhanh cho khu Lào Cai vào cuối tuần nếu đơn trong ngày tăng mạnh; tăng mạnh nghĩa là vượt 1940 đơn",
                "1940",
                kind="constraint",
            ),
            [7],
        ),
    ]


def gates():
    """Return G1-G6: four approval gates whose oracle notes are dropped and two lexicon-free instructions whose notes are admitted."""
    return [
        gate(
            "h-gate-1",
            "en",
            "approval",
            "dropped",
            {
                1: (
                    "The Calloway shop's alarm panel is model AP-4815.",
                    "I will add the panel model to the building notes.",
                ),
                3: (
                    "I approve raising the Calloway refund limit to 2750 euros per order.",
                    "Okay.",
                ),
                5: (
                    "The Calloway shop's delivery van is due for its service on 2027-02-09.",
                    "I will put the service date in the shop calendar.",
                ),
            },
            "Should the Calloway refund limit be raised?",
            ["2750 euros per order"],
            gold(
                3,
                "raising the Calloway refund limit to 2750 euros per order",
                "raising the Calloway refund limit to 2750 euros per order",
                "2750",
            ),
            [3],
        ),
        gate(
            "h-gate-2",
            "vi",
            "approval",
            "dropped",
            {
                2: (
                    "Phòng Hoàn Kiếm có mã trung tâm chi phí là CC-4417.",
                    "Mình đã ghi mã này vào bảng phân bổ.",
                ),
                4: (
                    "Tôi chấp thuận tăng hạn mức tạm ứng của phòng Hoàn Kiếm lên 9.800.000 đồng.",
                    "Dạ vâng.",
                ),
            },
            "Hạn mức tạm ứng của phòng Hoàn Kiếm có được tăng không?",
            ["9.800.000"],
            gold(
                4,
                "tăng hạn mức tạm ứng của phòng Hoàn Kiếm lên 9.800.000 đồng",
                "tăng hạn mức tạm ứng của phòng Hoàn Kiếm lên 9.800.000 đồng",
                "9.800.000",
            ),
            [4],
        ),
        gate(
            "h-gate-3",
            "en",
            "approval",
            "dropped",
            {
                2: (
                    "The Holloway office printer on the second floor is pr-hol-22.",
                    "Thanks, I will add it to the office notes.",
                ),
                6: ("Approved. Ship rc-2291 to edge-west-5 tonight.", "Right."),
            },
            "Should the release candidate ship tonight?",
            ["Approved. Ship"],
            gold(
                6,
                "Ship rc-2291 to edge-west-5 tonight",
                "Ship rc-2291 to edge-west-5 tonight",
                "rc-2291",
            ),
            [6],
        ),
        gate(
            "h-gate-4",
            "vi",
            "approval",
            "dropped",
            {
                1: (
                    "Máy in nhãn của kho có mã IN-5207.",
                    "Mình đã lưu mã máy in.",
                ),
                5: ("Chạy migration MG-3318 tối nay. Tôi đồng ý.", "Vâng."),
            },
            "Có nên chạy migration tối nay không?",
            ["Tôi đồng ý"],
            gold(
                5,
                "Chạy migration MG-3318 tối nay",
                "Chạy migration MG-3318 tối nay",
                "mg-3318",
            ),
            [5],
        ),
        gate(
            "h-gate-5",
            "en",
            "instruction",
            "admitted",
            {
                2: (
                    "Our key vault cluster is called vault-north and runs three nodes.",
                    "Three nodes give you a quorum for routine maintenance.",
                ),
                5: (
                    "Rotate the signing key on the key vault node vault-north-3 before the Wednesday release.",
                    "Sounds sensible.",
                ),
            },
            "Is there anything to do on the key vault before the Wednesday release?",
            ["Rotate the signing key"],
            gold(
                5,
                "Rotate the signing key on the key vault node vault-north-3 before the Wednesday release",
                "Rotate the signing key on the key vault node vault-north-3 before the Wednesday release",
                "vault-north-3",
                kind="decision",
            ),
            [5],
        ),
        gate(
            "h-gate-6",
            "vi",
            "instruction",
            "admitted",
            {
                3: (
                    "Phòng nhân sự vừa nhận máy scan mã SC-4093.",
                    "Mình sẽ thêm máy scan vào danh sách thiết bị.",
                ),
                6: (
                    "Xóa toàn bộ bộ nhớ đệm của máy chủ in tầng kế toán PS-2716 trước 22:15 tối nay.",
                    "Vâng, đã rõ.",
                ),
            },
            "Tối nay có việc gì cần làm trên máy chủ in của tầng kế toán không?",
            ["Xóa toàn bộ bộ nhớ đệm"],
            gold(
                6,
                "Xóa toàn bộ bộ nhớ đệm của máy chủ in tầng kế toán PS-2716 trước 22:15 tối nay",
                "Xóa toàn bộ bộ nhớ đệm của máy chủ in tầng kế toán PS-2716 trước 22:15 tối nay",
                "ps-2716",
                kind="decision",
            ),
            [6],
        ),
    ]


def probes():
    """Return the eight descriptive probes: allow wording, value-less corrections, cap pressure and a leading condition."""
    return [
        probe(
            "h-probe-allow_wording-en",
            "allow_wording",
            "en",
            "dropped",
            {
                4: (
                    "Pushing hotfixes to the Elstow mainline after 18:55 is not allowed.",
                    "Understood, I will plan around that.",
                ),
            },
            "After what time are hotfix pushes to the Elstow mainline off limits?",
            [["18:55", "6:55 pm", "6:55pm", "6:55 p.m", "6:55p.m"]],
            ["19:55"],
            ["18:55"],
            gold(
                4,
                "Pushing hotfixes to the Elstow mainline after 18:55 is not allowed",
                "Pushing hotfixes to the Elstow mainline after 18:55 is not allowed",
                "18:55",
                kind="constraint",
            ),
            [4],
        ),
        probe(
            "h-probe-allow_wording-vi",
            "allow_wording",
            "vi",
            "dropped",
            {
                5: (
                    "Không được phép đổi giá trên máy bán hàng của cửa hàng Sóc Trăng sau 22:35.",
                    "Dạ, mình hiểu rồi.",
                ),
            },
            "Sau mấy giờ thì cửa hàng Sóc Trăng bị khóa việc đổi giá?",
            [
                [
                    "22:35",
                    "22h35",
                    "22 giờ 35",
                    "10h35 tối",
                    "10 giờ 35 tối",
                    "10 giờ 35 phút tối",
                    "10:35 tối",
                    "10h35 buổi tối",
                    "10 giờ 35 buổi tối",
                    "10 giờ 35 phút buổi tối",
                    "10:35 buổi tối",
                    "10h35 đêm",
                    "10 giờ 35 đêm",
                    "10 giờ 35 phút đêm",
                    "10:35 đêm",
                ]
            ],
            ["23:35", "23h35", "23 giờ 35"],
            ["22:35"],
            gold(
                5,
                "Không được phép đổi giá trên máy bán hàng của cửa hàng Sóc Trăng sau 22:35",
                "Không được phép đổi giá trên máy bán hàng của cửa hàng Sóc Trăng sau 22:35",
                "22:35",
                kind="constraint",
            ),
            [5],
        ),
        probe(
            "h-probe-valueless_correction-en",
            "valueless_correction",
            "en",
            "unlisted",
            {
                2: (
                    "The Dunmore newsletter can go out through relay mr-east-41 or relay mr-south-17; start with mr-east-41.",
                    "Okay, mr-east-41 first.",
                ),
                3: (
                    "The Dunmore mailing list has about 9650 subscribers.",
                    "A list of that size is fine for one evening send.",
                ),
                5: ("Actually, use the other one.", "Alright, I will change it."),
            },
            "Which relay should the Dunmore newsletter go out through?",
            [["mr-south-17"]],
            ["mr-east-41"],
            ["mr-south-17", "use the other one"],
            gold(
                5,
                "Actually, use the other one",
                "use the other one",
                "mr-south-17",
                kind="decision",
                replaces=2,
            ),
            [2, 5],
        ),
        probe(
            "h-probe-valueless_correction-vi",
            "valueless_correction",
            "vi",
            "unlisted",
            {
                1: (
                    "Số tạp chí tháng này in 4800 bản.",
                    "Số lượng in như vậy khá ổn.",
                ),
                3: (
                    "Tạp chí Mộc Châu có hai mẫu bìa là BIA-0917 và BIA-0971; tạm dùng BIA-0917.",
                    "Vâng, tạm dùng BIA-0917.",
                ),
                6: ("Thôi, dùng mẫu còn lại đi.", "Dạ, mình đổi ngay."),
            },
            "Tạp chí Mộc Châu dùng mẫu bìa nào?",
            [["BIA-0971"]],
            ["BIA-0917"],
            ["BIA-0971", "dùng mẫu còn lại"],
            gold(
                6,
                "Thôi, dùng mẫu còn lại đi",
                "dùng mẫu còn lại",
                "bia-0971",
                kind="decision",
                replaces=3,
            ),
            [3, 6],
        ),
        probe(
            "h-probe-cap_pressure-en",
            "cap_pressure",
            "en",
            "over_cap",
            {
                1: (
                    "The Fairlie lab door code is 9047 until the end of term.",
                    "Thanks.",
                ),
                2: (
                    "The Fairlie lab printer is queue FL-PR-29.",
                    "I will add it to the lab handbook.",
                ),
                3: (
                    "Safety training for the new students is at 10:20 in room G-118.",
                    "I will send the reminder the day before.",
                ),
                4: (
                    "The pipette calibration certificate number is PC-55104.",
                    "Saved with the equipment records.",
                ),
                5: (
                    "Our consumables budget for the term is 2930 pounds.",
                    "That should cover gloves and tips comfortably.",
                ),
                6: (
                    "The waste collection now comes at 15:05.",
                    "I will update the lab rota.",
                ),
                7: (
                    "The spare key for the Fairlie lab is in locker L-0927.",
                    "Good to know where it is.",
                ),
            },
            "What is the Fairlie lab door code?",
            [["9047"]],
            ["9074"],
            ["9047"],
            gold(
                1,
                "The Fairlie lab door code is 9047 until the end of term",
                "Fairlie lab door code is 9047 until the end of term",
                "9047",
            ),
            [1],
            ungrouped=True,
        ),
        probe(
            "h-probe-cap_pressure-vi",
            "cap_pressure",
            "vi",
            "over_cap",
            {
                1: (
                    "Văn phòng Bến Tre đang lưu khoảng 1925 hồ sơ giấy.",
                    "Số hồ sơ đó nên được số hóa dần.",
                ),
                2: (
                    "Mã cửa kho ở văn phòng Bến Tre là 7316.",
                    "Dạ.",
                ),
                3: (
                    "Bảo vệ ca tối ở văn phòng làm đến 18:20.",
                    "Mình sẽ báo mọi người về giờ đó.",
                ),
                4: (
                    "Mã số thuế của chi nhánh là 0319947286.",
                    "Mình đã ghi vào hồ sơ pháp lý.",
                ),
                5: (
                    "Tiền điện quý này của văn phòng là 7.450.000 đồng.",
                    "Khoản đó tăng nhẹ so với quý trước.",
                ),
                6: (
                    "Máy photo mới của văn phòng có mã MP-6614.",
                    "Mình đã thêm vào danh sách thiết bị.",
                ),
                7: (
                    "Chìa khóa dự phòng để ở tủ T-0815.",
                    "Mình đã ghi lại vị trí chìa khóa.",
                ),
            },
            "Mã cửa kho ở văn phòng Bến Tre là gì?",
            [["7316"]],
            ["7361"],
            ["7316"],
            gold(
                2,
                "Mã cửa kho ở văn phòng Bến Tre là 7316",
                "Mã cửa kho ở văn phòng Bến Tre là 7316",
                "7316",
            ),
            [2],
            ungrouped=True,
        ),
        probe(
            "h-probe-leading_condition-en",
            "leading_condition",
            "en",
            "admitted",
            {
                3: (
                    "The Glenrock dry run took 1.4 hours last time.",
                    "That fits inside the evening window.",
                ),
                6: (
                    "If the Glenrock dry run fails again; roll back to snp-3381 and call me.",
                    "On it.",
                ),
            },
            "What should happen if the Glenrock dry run fails again?",
            [["snp-3381"]],
            ["snp-3318"],
            ["snp-3381"],
            gold(
                6,
                "roll back to snp-3381 and call me",
                "roll back to snp-3381 and call me",
                "snp-3381",
                kind="constraint",
            ),
            [6],
        ),
        probe(
            "h-probe-leading_condition-vi",
            "leading_condition",
            "vi",
            "admitted",
            {
                2: (
                    "Kho chính ở Tam Kỳ đóng cửa lúc 17:50.",
                    "Mình sẽ báo các tài xế về giờ đóng cửa.",
                ),
                4: (
                    "Nếu xe giao hàng ở Tam Kỳ đến muộn; chuyển đơn sang kho phụ KP-2093 và báo cho mình.",
                    "Dạ, mình nhớ rồi.",
                ),
            },
            "Nếu xe giao hàng ở Tam Kỳ đến muộn thì xử lý đơn thế nào?",
            [["KP-2093"]],
            ["KP-2039"],
            ["KP-2093"],
            gold(
                4,
                "chuyển đơn sang kho phụ KP-2093 và báo cho mình",
                "chuyển đơn sang kho phụ KP-2093 và báo cho mình",
                "kp-2093",
                kind="constraint",
            ),
            [4],
        ),
    ]


def corpus_heldout():
    """Return the 38 held-out cases: 24 scored, 6 authority gates and 8 probes, 19 English and 19 Vietnamese."""
    return scored_en() + scored_vi() + gates() + probes()
