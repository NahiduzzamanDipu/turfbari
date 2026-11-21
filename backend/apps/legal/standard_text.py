# ruff: noqa: E501
"""TurfBari's standard wording for every legal module (English + Bengali).

Used to create the first drafts and by the admin "Rewrite with standard text" button. It describes how
TurfBari actually works (bKash advance verified by the business, prepaid SMS wallet, plans that never
renew by themselves …). It is a starting point written without legal advice: an admin must review it,
ideally with a lawyer, before publishing. Numbers that admins can change in settings are not repeated
here; only fixed platform rules are (৳500 minimum advance, 10-minute slot hold, 3-day grace period).

No model imports: migrations use this module.
"""

import html

# A document is a list of blocks: ("h", text) heading, ("p", text) paragraph, ("ul", [items]) list.
Block = tuple[str, object]


def render(blocks: list[Block]) -> str:
    out = []
    for kind, value in blocks:
        if kind == "h":
            out.append(f"<h2>{html.escape(value)}</h2>")
        elif kind == "p":
            out.append(f"<p>{html.escape(value)}</p>")
        elif kind == "ul":
            out.append("<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in value) + "</ul>")
    return "".join(out)


INTRO_EN = "This document is part of the TurfBari terms. If anything here conflicts with the General Terms & Conditions, the General Terms & Conditions apply."
INTRO_BN = (
    "এই ডকুমেন্টটি TurfBari-র শর্তাবলীর অংশ। এখানে কোনো কিছু সাধারণ শর্তাবলীর সাথে সাংঘর্ষিক হলে সাধারণ শর্তাবলী প্রযোজ্য হবে।"
)

CONTACT_EN = "Questions or complaints: contact TurfBari through the support details shown on the TurfBari website or in your workspace. We aim to reply within 3 working days."
CONTACT_BN = "প্রশ্ন বা অভিযোগ: TurfBari ওয়েবসাইট বা আপনার ওয়ার্কস্পেসে দেওয়া সাপোর্ট যোগাযোগের মাধ্যমে জানান। আমরা ৩ কর্মদিবসের মধ্যে উত্তর দেওয়ার চেষ্টা করি।"

DOCS: dict[str, dict[str, object]] = {}

# ---------------------------------------------------------------------------- 1. General terms
DOCS["terms"] = {
    "title_en": "Terms & Conditions",
    "title_bn": "শর্তাবলী",
    "en": [
        ("h", "1. About TurfBari"),
        (
            "p",
            'TurfBari is an online platform that lets sports facilities in Bangladesh ("businesses", such as football turfs) publish a booking page, manage their slots and receive booking requests from players ("customers"). TurfBari provides the software. The business that owns the facility provides the playing time and is responsible for the facility.',
        ),
        ("h", "2. Accepting these terms"),
        (
            "p",
            "By registering a business, signing in, or sending a booking request you confirm that you have read and agree to these terms and to the other policies shown with them. If you do not agree, do not use TurfBari. When a version changes we show the new version and, where needed, ask you to accept it again.",
        ),
        ("h", "3. Who can use TurfBari"),
        (
            "ul",
            [
                "You must give true, current information (name, mobile number, email).",
                "Business accounts are opened only after TurfBari reviews the application.",
                "You are responsible for everything done through your account and for keeping your password private.",
                "Customers under 18 should book with the permission of a parent or guardian.",
            ],
        ),
        ("h", "4. Bookings and payments"),
        (
            "p",
            "A booking request is not confirmed until the business checks the bKash advance you sent and approves it. The advance is paid directly to the business's bKash number; TurfBari does not receive or hold booking money. Details are in the Booking & Reservation Policy and the Payment, Refund & Cancellation Policy.",
        ),
        ("h", "5. Businesses' responsibilities"),
        (
            "ul",
            [
                "Keep prices, opening hours, slots and facility information accurate.",
                "Verify each payment honestly and promptly, and confirm or reject requests.",
                "Provide the booked facility in a safe condition at the booked time.",
                "Handle refunds owed to customers under your published policy and these terms.",
            ],
        ),
        ("h", "6. TurfBari's role and limits"),
        (
            "p",
            "TurfBari is not a party to the agreement between a customer and a business and is not responsible for the condition of a facility, injuries, lost property, or disputes about play. We work to keep the service available and accurate but cannot guarantee it will always be uninterrupted or error-free. To the extent the law allows, TurfBari's liability for any claim is limited to the fees the claimant paid to TurfBari in the previous three months.",
        ),
        ("h", "7. Suspension and closure"),
        (
            "p",
            "TurfBari may suspend or close an account that breaks these terms, gives false information, misuses payments or SMS, or puts others at risk. Where reasonable we will tell you why first.",
        ),
        ("h", "8. Changes"),
        (
            "p",
            "We may update these terms. Each version shows its version number and effective date, and earlier versions stay available on the legal pages.",
        ),
        ("h", "9. Governing law"),
        (
            "p",
            "These terms are governed by the laws of Bangladesh. Disputes are first handled through TurfBari support; if not resolved, they fall under the courts of Dhaka.",
        ),
        ("h", "10. Contact"),
        ("p", CONTACT_EN),
    ],
    "bn": [
        ("h", "১. TurfBari সম্পর্কে"),
        (
            "p",
            'TurfBari একটি অনলাইন প্ল্যাটফর্ম, যার মাধ্যমে বাংলাদেশের খেলার সুবিধা প্রদানকারী প্রতিষ্ঠান ("ব্যবসা", যেমন ফুটবল টার্ফ) বুকিং পেজ চালু, স্লট পরিচালনা এবং খেলোয়াড়দের ("গ্রাহক") কাছ থেকে বুকিং অনুরোধ গ্রহণ করতে পারে। TurfBari সফটওয়্যার সরবরাহ করে; খেলার সময় ও মাঠের দায়িত্ব সংশ্লিষ্ট ব্যবসার।',
        ),
        ("h", "২. শর্তাবলী গ্রহণ"),
        (
            "p",
            "ব্যবসা নিবন্ধন, সাইন ইন বা বুকিং অনুরোধ পাঠানোর মাধ্যমে আপনি নিশ্চিত করছেন যে আপনি এই শর্তাবলী ও সাথে দেখানো অন্যান্য নীতিমালা পড়েছেন এবং সম্মত হয়েছেন। সম্মত না হলে TurfBari ব্যবহার করবেন না। নতুন সংস্করণ এলে আমরা তা দেখাব এবং প্রয়োজনে আবার সম্মতি চাইব।",
        ),
        ("h", "৩. কারা ব্যবহার করতে পারবেন"),
        (
            "ul",
            [
                "সঠিক ও হালনাগাদ তথ্য (নাম, মোবাইল নম্বর, ইমেইল) দিতে হবে।",
                "TurfBari আবেদন যাচাই করার পরই ব্যবসার অ্যাকাউন্ট খোলা হয়।",
                "আপনার অ্যাকাউন্টে করা সব কাজের দায় আপনার; পাসওয়ার্ড গোপন রাখুন।",
                "১৮ বছরের কম বয়সী গ্রাহক অভিভাবকের অনুমতি নিয়ে বুকিং করবেন।",
            ],
        ),
        ("h", "৪. বুকিং ও পেমেন্ট"),
        (
            "p",
            "ব্যবসা আপনার পাঠানো বিকাশ অগ্রিম যাচাই করে অনুমোদন না দেওয়া পর্যন্ত বুকিং নিশ্চিত হয় না। অগ্রিম সরাসরি ব্যবসার বিকাশ নম্বরে যায়; TurfBari বুকিংয়ের টাকা গ্রহণ বা জমা রাখে না। বিস্তারিত বুকিং ও রিজার্ভেশন নীতি এবং পেমেন্ট, রিফান্ড ও বাতিলকরণ নীতিতে দেওয়া আছে।",
        ),
        ("h", "৫. ব্যবসার দায়িত্ব"),
        (
            "ul",
            [
                "মূল্য, খোলার সময়, স্লট ও মাঠের তথ্য সঠিক রাখা।",
                "প্রতিটি পেমেন্ট সততার সাথে দ্রুত যাচাই করে অনুরোধ নিশ্চিত বা বাতিল করা।",
                "বুক করা সময়ে নিরাপদ অবস্থায় মাঠ প্রদান করা।",
                "প্রকাশিত নীতি ও এই শর্তাবলী অনুযায়ী গ্রাহকের প্রাপ্য রিফান্ড দেওয়া।",
            ],
        ),
        ("h", "৬. TurfBari-র ভূমিকা ও সীমাবদ্ধতা"),
        (
            "p",
            "গ্রাহক ও ব্যবসার মধ্যকার চুক্তিতে TurfBari পক্ষ নয় এবং মাঠের অবস্থা, আঘাত, হারানো জিনিস বা খেলা নিয়ে বিরোধের জন্য দায়ী নয়। আমরা সেবা সচল ও নির্ভুল রাখার চেষ্টা করি, তবে সবসময় নিরবচ্ছিন্ন বা ত্রুটিমুক্ত থাকার নিশ্চয়তা দিতে পারি না। আইন যতটুকু অনুমতি দেয়, যেকোনো দাবিতে TurfBari-র দায় দাবিকারী গত তিন মাসে TurfBari-কে যে ফি দিয়েছেন তার মধ্যে সীমাবদ্ধ।",
        ),
        ("h", "৭. স্থগিত ও বন্ধ করা"),
        (
            "p",
            "শর্ত ভঙ্গ, মিথ্যা তথ্য, পেমেন্ট বা এসএমএসের অপব্যবহার, অথবা অন্যদের ঝুঁকিতে ফেললে TurfBari অ্যাকাউন্ট স্থগিত বা বন্ধ করতে পারে। যুক্তিসঙ্গত হলে আগে কারণ জানানো হবে।",
        ),
        ("h", "৮. পরিবর্তন"),
        (
            "p",
            "আমরা এই শর্তাবলী হালনাগাদ করতে পারি। প্রতিটি সংস্করণে সংস্করণ নম্বর ও কার্যকর তারিখ থাকে এবং আগের সংস্করণগুলো আইনি পেজে দেখা যায়।",
        ),
        ("h", "৯. প্রযোজ্য আইন"),
        (
            "p",
            "এই শর্তাবলী বাংলাদেশের আইন অনুযায়ী পরিচালিত। বিরোধ প্রথমে TurfBari সাপোর্টের মাধ্যমে সমাধানের চেষ্টা করা হবে; সমাধান না হলে ঢাকার আদালতের এখতিয়ারে যাবে।",
        ),
        ("h", "১০. যোগাযোগ"),
        ("p", CONTACT_BN),
    ],
}

# ---------------------------------------------------------------------------- 2. Privacy
DOCS["privacy"] = {
    "title_en": "Privacy Policy",
    "title_bn": "গোপনীয়তা নীতি",
    "en": [
        ("h", "1. What we collect"),
        (
            "ul",
            [
                "Customers: name, mobile number, optional email and team name, the slots you request, and the bKash sender number, amount and Transaction ID you enter for the advance.",
                "Business owners and managers: name, email, mobile number, business details and address, sign-in records, and payment details for plans and SMS recharges.",
                "Technical data: device and browser information, a random visitor id kept in your browser for unfinished bookings, and a one-way (hashed) form of your IP address used for abuse prevention and acceptance records.",
            ],
        ),
        ("h", "2. Why we use it"),
        (
            "ul",
            [
                "To make and manage bookings and let the business verify your payment.",
                "To send booking and account SMS and emails (confirmations, reminders, password resets).",
                "To prevent fraud and abuse, such as fake bookings or repeated requests.",
                "To keep records required for accounting, disputes and the legal agreements you accepted.",
                "To improve TurfBari. We do not sell personal data.",
            ],
        ),
        ("h", "3. Who can see it"),
        (
            "ul",
            [
                "The business you book with sees your booking details and contact number so it can serve you.",
                "TurfBari administrators, only as needed to run and support the service.",
                "Service providers that run parts of TurfBari for us (hosting, database, file storage, SMS delivery, email), bound to use the data only for that purpose.",
                "Authorities, when the law requires it.",
            ],
        ),
        ("h", "4. How long we keep it"),
        (
            "p",
            "Booking, payment and acceptance records are kept as long as needed for accounting, disputes and legal obligations. Unfinished booking drafts in your browser can be cleared at any time. Business accounts and their data are kept while the account is active and for a reasonable period afterwards.",
        ),
        ("h", "5. Security"),
        (
            "p",
            "We use encrypted connections, hashed passwords, optional two-step sign-in, access controls between businesses, and encrypted storage of sensitive provider keys. No system is completely secure; tell us immediately if you think your account has been misused.",
        ),
        ("h", "6. Your choices"),
        (
            "p",
            "You may ask to see or correct your personal data, or to delete it where we are not required to keep it. Businesses can correct customer records in their workspace. Contact TurfBari support for any request.",
        ),
        ("h", "7. Cookies"),
        (
            "p",
            "We use only the cookies and browser storage needed to sign you in, protect forms and remember your unfinished booking. We do not use advertising cookies.",
        ),
        ("h", "8. Contact"),
        ("p", CONTACT_EN),
    ],
    "bn": [
        ("h", "১. আমরা কী তথ্য সংগ্রহ করি"),
        (
            "ul",
            [
                "গ্রাহক: নাম, মোবাইল নম্বর, ঐচ্ছিক ইমেইল ও টিমের নাম, অনুরোধ করা স্লট, এবং অগ্রিমের জন্য দেওয়া বিকাশ প্রেরক নম্বর, টাকার পরিমাণ ও ট্রানজেকশন আইডি।",
                "ব্যবসার মালিক ও ম্যানেজার: নাম, ইমেইল, মোবাইল নম্বর, ব্যবসার তথ্য ও ঠিকানা, সাইন-ইন রেকর্ড, এবং প্ল্যান ও এসএমএস রিচার্জের পেমেন্ট তথ্য।",
                "প্রযুক্তিগত তথ্য: ডিভাইস ও ব্রাউজারের তথ্য, অসম্পূর্ণ বুকিংয়ের জন্য ব্রাউজারে রাখা একটি র‍্যান্ডম ভিজিটর আইডি, এবং অপব্যবহার রোধ ও সম্মতির রেকর্ডের জন্য আপনার আইপি ঠিকানার একমুখী (হ্যাশ করা) রূপ।",
            ],
        ),
        ("h", "২. কেন ব্যবহার করি"),
        (
            "ul",
            [
                "বুকিং তৈরি ও পরিচালনা এবং ব্যবসাকে আপনার পেমেন্ট যাচাই করতে দেওয়া।",
                "বুকিং ও অ্যাকাউন্ট সংক্রান্ত এসএমএস ও ইমেইল পাঠানো (নিশ্চিতকরণ, রিমাইন্ডার, পাসওয়ার্ড রিসেট)।",
                "ভুয়া বুকিং বা বারবার অনুরোধের মতো প্রতারণা ও অপব্যবহার রোধ।",
                "হিসাব, বিরোধ নিষ্পত্তি ও আপনার দেওয়া সম্মতির রেকর্ড সংরক্ষণ।",
                "TurfBari উন্নত করা। আমরা ব্যক্তিগত তথ্য বিক্রি করি না।",
            ],
        ),
        ("h", "৩. কারা দেখতে পারে"),
        (
            "ul",
            [
                "যে ব্যবসায় বুকিং করছেন, সেবা দেওয়ার জন্য তারা আপনার বুকিংয়ের তথ্য ও যোগাযোগ নম্বর দেখে।",
                "TurfBari অ্যাডমিন, শুধু সেবা চালানো ও সহায়তার প্রয়োজনে।",
                "যেসব সেবাদাতা আমাদের হয়ে TurfBari-র অংশ চালায় (হোস্টিং, ডেটাবেস, ফাইল স্টোরেজ, এসএমএস, ইমেইল) — শুধু সেই কাজের জন্য তথ্য ব্যবহারের শর্তে।",
                "আইনের প্রয়োজনে কর্তৃপক্ষ।",
            ],
        ),
        ("h", "৪. কতদিন রাখি"),
        (
            "p",
            "বুকিং, পেমেন্ট ও সম্মতির রেকর্ড হিসাব, বিরোধ ও আইনি বাধ্যবাধকতার জন্য যতদিন প্রয়োজন ততদিন রাখা হয়। ব্রাউজারে থাকা অসম্পূর্ণ বুকিং যেকোনো সময় মুছে ফেলা যায়। ব্যবসার অ্যাকাউন্ট সক্রিয় থাকা পর্যন্ত এবং পরে যুক্তিসঙ্গত সময় তথ্য রাখা হয়।",
        ),
        ("h", "৫. নিরাপত্তা"),
        (
            "p",
            "আমরা এনক্রিপ্টেড সংযোগ, হ্যাশ করা পাসওয়ার্ড, ঐচ্ছিক দুই-ধাপের সাইন-ইন, ব্যবসাগুলোর মধ্যে অ্যাক্সেস নিয়ন্ত্রণ এবং সংবেদনশীল কী-র এনক্রিপ্টেড সংরক্ষণ ব্যবহার করি। কোনো সিস্টেমই সম্পূর্ণ নিরাপদ নয়; অ্যাকাউন্টের অপব্যবহার সন্দেহ হলে সঙ্গে সঙ্গে জানান।",
        ),
        ("h", "৬. আপনার অধিকার"),
        (
            "p",
            "আপনি আপনার ব্যক্তিগত তথ্য দেখতে, সংশোধন করতে, অথবা যেখানে রাখা বাধ্যতামূলক নয় সেখানে মুছে ফেলতে অনুরোধ করতে পারেন। ব্যবসা তাদের ওয়ার্কস্পেসে গ্রাহকের তথ্য সংশোধন করতে পারে। যেকোনো অনুরোধে TurfBari সাপোর্টে যোগাযোগ করুন।",
        ),
        ("h", "৭. কুকি"),
        (
            "p",
            "শুধু সাইন-ইন, ফর্ম সুরক্ষা এবং অসম্পূর্ণ বুকিং মনে রাখার জন্য প্রয়োজনীয় কুকি ও ব্রাউজার স্টোরেজ ব্যবহার করা হয়। বিজ্ঞাপনের কুকি ব্যবহার করা হয় না।",
        ),
        ("h", "৮. যোগাযোগ"),
        ("p", CONTACT_BN),
    ],
}

# ---------------------------------------------------------------------------- 3. Platform rules
DOCS["rules"] = {
    "title_en": "Platform Rules & Regulations",
    "title_bn": "প্ল্যাটফর্মের নিয়মাবলী",
    "en": [
        ("p", INTRO_EN),
        ("h", "Listing rules for businesses"),
        (
            "ul",
            [
                "List only facilities you own or are authorised to manage, with real photos and correct address.",
                "Show the real price for every slot. Extra charges must be shown before booking.",
                "Every online booking needs an advance of at least ৳500 (or the full price if lower), paid to the business's own bKash number.",
                "Keep your booking page, opening hours and blocked times up to date; do not accept two bookings for the same field and time.",
                "Verify each advance against your bKash account before approving it; reject requests with wrong or missing payment and say why.",
                "Publish your own cancellation policy. It may add to, but must not contradict, TurfBari's policies.",
            ],
        ),
        ("h", "Conduct"),
        (
            "ul",
            [
                "Treat customers, staff and TurfBari support respectfully.",
                "Use customer contact details only for their bookings and the messages they would expect.",
                "Follow local laws, including trade licences, safety and noise rules that apply to your facility.",
            ],
        ),
        ("h", "Enforcement"),
        (
            "p",
            "Breaking these rules can lead to a warning, hiding the booking page, suspension, or closing the account, depending on how serious and repeated the problem is.",
        ),
    ],
    "bn": [
        ("p", INTRO_BN),
        ("h", "ব্যবসার তালিকাভুক্তির নিয়ম"),
        (
            "ul",
            [
                "শুধু নিজের বা পরিচালনার অনুমতি আছে এমন মাঠ তালিকাভুক্ত করুন, আসল ছবি ও সঠিক ঠিকানাসহ।",
                "প্রতিটি স্লটের প্রকৃত মূল্য দেখান। অতিরিক্ত কোনো চার্জ বুকিংয়ের আগেই দেখাতে হবে।",
                "প্রতিটি অনলাইন বুকিংয়ে কমপক্ষে ৳৫০০ অগ্রিম (মূল্য কম হলে পুরো মূল্য) ব্যবসার নিজস্ব বিকাশ নম্বরে দিতে হয়।",
                "বুকিং পেজ, খোলার সময় ও বন্ধ সময় হালনাগাদ রাখুন; একই মাঠ ও সময়ে দুটি বুকিং গ্রহণ করবেন না।",
                "অনুমোদনের আগে প্রতিটি অগ্রিম আপনার বিকাশ অ্যাকাউন্টে মিলিয়ে নিন; ভুল বা অনুপস্থিত পেমেন্টের অনুরোধ কারণসহ বাতিল করুন।",
                "নিজস্ব বাতিলকরণ নীতি প্রকাশ করুন। এটি TurfBari-র নীতিতে সংযোজন করতে পারে, কিন্তু বিরোধী হতে পারবে না।",
            ],
        ),
        ("h", "আচরণ"),
        (
            "ul",
            [
                "গ্রাহক, কর্মী ও TurfBari সাপোর্টের সাথে সম্মানজনক আচরণ করুন।",
                "গ্রাহকের যোগাযোগ তথ্য শুধু তাদের বুকিং ও প্রত্যাশিত বার্তার জন্য ব্যবহার করুন।",
                "ট্রেড লাইসেন্স, নিরাপত্তা ও শব্দ সংক্রান্ত নিয়মসহ প্রযোজ্য স্থানীয় আইন মেনে চলুন।",
            ],
        ),
        ("h", "নিয়ম প্রয়োগ"),
        ("p", "নিয়ম ভঙ্গের গুরুত্ব ও পুনরাবৃত্তি অনুযায়ী সতর্কতা, বুকিং পেজ লুকানো, স্থগিত বা অ্যাকাউন্ট বন্ধ করা হতে পারে।"),
    ],
}

# ---------------------------------------------------------------------------- 4. Account usage
DOCS["account_usage"] = {
    "title_en": "Account Usage Policy",
    "title_bn": "অ্যাকাউন্ট ব্যবহারের নীতি",
    "en": [
        ("p", INTRO_EN),
        ("h", "Your account"),
        (
            "ul",
            [
                "Each person uses their own login. Owners add managers from the Team page instead of sharing the owner password.",
                "The first password you receive is temporary: change it at first sign-in. Use a strong password and turn on two-step sign-in where available.",
                "Owners decide what each manager can do (for example approving payments or viewing SMS) and remain responsible for their managers' actions.",
                "Remove managers who no longer work for you.",
            ],
        ),
        ("h", "Security"),
        (
            "ul",
            [
                "Do not try to access another business's data, test the system's security, or automate access without TurfBari's written permission.",
                "Tell TurfBari immediately if you notice unusual activity; we may sign out sessions or reset passwords to protect the account.",
            ],
        ),
        ("h", "Plan and access"),
        (
            "p",
            "Workspace features depend on an active plan. When a plan ends you keep read access during the grace period; taking new bookings needs a paid plan.",
        ),
    ],
    "bn": [
        ("p", INTRO_BN),
        ("h", "আপনার অ্যাকাউন্ট"),
        (
            "ul",
            [
                "প্রত্যেকে নিজের লগইন ব্যবহার করবেন। মালিকের পাসওয়ার্ড শেয়ার না করে Team পেজ থেকে ম্যানেজার যোগ করুন।",
                "প্রথম পাওয়া পাসওয়ার্ড অস্থায়ী: প্রথম সাইন-ইনে বদলে নিন। শক্তিশালী পাসওয়ার্ড ব্যবহার করুন এবং সম্ভব হলে দুই-ধাপের সাইন-ইন চালু করুন।",
                "প্রতিটি ম্যানেজার কী করতে পারবেন (যেমন পেমেন্ট অনুমোদন বা এসএমএস দেখা) তা মালিক ঠিক করেন এবং ম্যানেজারদের কাজের দায় মালিকের।",
                "যারা আর আপনার সাথে কাজ করেন না, তাদের সরিয়ে দিন।",
            ],
        ),
        ("h", "নিরাপত্তা"),
        (
            "ul",
            [
                "অন্য ব্যবসার তথ্যে প্রবেশ, সিস্টেমের নিরাপত্তা পরীক্ষা বা TurfBari-র লিখিত অনুমতি ছাড়া স্বয়ংক্রিয় অ্যাক্সেসের চেষ্টা করবেন না।",
                "অস্বাভাবিক কিছু দেখলে সঙ্গে সঙ্গে TurfBari-কে জানান; অ্যাকাউন্ট রক্ষায় আমরা সেশন বন্ধ বা পাসওয়ার্ড রিসেট করতে পারি।",
            ],
        ),
        ("h", "প্ল্যান ও অ্যাক্সেস"),
        (
            "p",
            "ওয়ার্কস্পেসের সুবিধা সক্রিয় প্ল্যানের উপর নির্ভর করে। প্ল্যান শেষ হলে গ্রেস পিরিয়ডে তথ্য দেখা যায়; নতুন বুকিং নিতে পেইড প্ল্যান লাগবে।",
        ),
    ],
}

# ---------------------------------------------------------------------------- 5. Prohibited activities
DOCS["prohibited"] = {
    "title_en": "Prohibited Activities & User Responsibilities",
    "title_bn": "নিষিদ্ধ কার্যকলাপ ও ব্যবহারকারীর দায়িত্ব",
    "en": [
        ("p", INTRO_EN),
        ("h", "You must not"),
        (
            "ul",
            [
                "Send fake booking requests, use someone else's name or number, or hold slots you do not intend to book.",
                "Enter a bKash Transaction ID you did not pay, or reuse another person's payment.",
                "Harass, threaten or abuse customers, staff or businesses.",
                "Send spam, misleading or offensive SMS, or messages to people who did not agree to receive them.",
                "Upload illegal, misleading or other people's copyrighted content.",
                "Try to break, overload, copy or reverse engineer TurfBari, or bypass its limits.",
                "Use TurfBari for gambling, betting or any unlawful purpose.",
            ],
        ),
        ("h", "Your responsibilities"),
        (
            "ul",
            [
                "Give correct information and keep it up to date.",
                "Follow the facility's rules and staff instructions when you play.",
                "Report problems or suspected fraud to the business or TurfBari support.",
            ],
        ),
        ("h", "Consequences"),
        (
            "p",
            "TurfBari may cancel affected requests, limit bookings from a mobile number, suspend accounts, and share information with authorities where the law requires.",
        ),
    ],
    "bn": [
        ("p", INTRO_BN),
        ("h", "যা করা যাবে না"),
        (
            "ul",
            [
                "ভুয়া বুকিং অনুরোধ পাঠানো, অন্যের নাম বা নম্বর ব্যবহার, বা বুক করার ইচ্ছা ছাড়া স্লট আটকে রাখা।",
                "পরিশোধ না করা বিকাশ ট্রানজেকশন আইডি দেওয়া বা অন্যের পেমেন্ট আবার ব্যবহার করা।",
                "গ্রাহক, কর্মী বা ব্যবসাকে হয়রানি, হুমকি বা অপমান করা।",
                "স্প্যাম, বিভ্রান্তিকর বা আপত্তিকর এসএমএস, বা সম্মতি দেয়নি এমন কাউকে বার্তা পাঠানো।",
                "অবৈধ, বিভ্রান্তিকর বা অন্যের কপিরাইটযুক্ত কনটেন্ট আপলোড করা।",
                "TurfBari ভাঙা, অতিরিক্ত চাপ দেওয়া, কপি বা রিভার্স ইঞ্জিনিয়ার করা, বা এর সীমা এড়ানোর চেষ্টা।",
                "জুয়া, বাজি বা যেকোনো বেআইনি উদ্দেশ্যে TurfBari ব্যবহার।",
            ],
        ),
        ("h", "আপনার দায়িত্ব"),
        (
            "ul",
            [
                "সঠিক তথ্য দেওয়া ও হালনাগাদ রাখা।",
                "খেলার সময় মাঠের নিয়ম ও কর্মীদের নির্দেশনা মেনে চলা।",
                "সমস্যা বা প্রতারণার সন্দেহ হলে ব্যবসা বা TurfBari সাপোর্টকে জানানো।",
            ],
        ),
        ("h", "পরিণতি"),
        (
            "p",
            "TurfBari সংশ্লিষ্ট অনুরোধ বাতিল, কোনো মোবাইল নম্বরের বুকিং সীমিত, অ্যাকাউন্ট স্থগিত এবং আইনের প্রয়োজনে কর্তৃপক্ষকে তথ্য দিতে পারে।",
        ),
    ],
}

# ---------------------------------------------------------------------------- 6. Booking & reservation
DOCS["booking"] = {
    "title_en": "Booking & Reservation Policy",
    "title_bn": "বুকিং ও রিজার্ভেশন নীতি",
    "en": [
        ("p", INTRO_EN),
        ("h", "How a booking works"),
        (
            "ul",
            [
                "When you pick a slot it is held for you for 10 minutes while you complete the request.",
                "Send the advance shown (at least ৳500, or the full price if lower) by bKash Send Money to the business's number, then enter the sender number, amount and Transaction ID.",
                "Your request then waits for the business to check the payment. You receive an SMS when it is confirmed or rejected, and you can check its status with your booking reference.",
                "A booking is confirmed only after the business approves it. Until then the slot is reserved for you but not guaranteed.",
            ],
        ),
        ("h", "Limits"),
        (
            "ul",
            [
                "Each mobile number can book a limited number of slots per day, shown on the booking page.",
                "Only a few unconfirmed requests are allowed per number per day, to stop slots being blocked.",
                "If you leave a held slot unused, you may need to wait a short time before holding it again.",
            ],
        ),
        ("h", "On the day"),
        (
            "ul",
            [
                "Arrive on time and show your booking reference if asked. Your time ends at the booked end time even if you start late.",
                "Pay the remaining balance to the business as they ask (usually at the venue).",
            ],
        ),
        ("h", "Changes"),
        (
            "p",
            "To change or cancel, contact the business directly. Refunds follow the Payment, Refund & Cancellation Policy and the business's own cancellation policy.",
        ),
    ],
    "bn": [
        ("p", INTRO_BN),
        ("h", "বুকিং যেভাবে হয়"),
        (
            "ul",
            [
                "স্লট বেছে নিলে অনুরোধ সম্পূর্ণ করার জন্য তা ১০ মিনিট আপনার জন্য আটকে রাখা হয়।",
                "দেখানো অগ্রিম (কমপক্ষে ৳৫০০, মূল্য কম হলে পুরো মূল্য) বিকাশ সেন্ড মানির মাধ্যমে ব্যবসার নম্বরে পাঠান, তারপর প্রেরক নম্বর, টাকার পরিমাণ ও ট্রানজেকশন আইডি দিন।",
                "এরপর ব্যবসা পেমেন্ট যাচাই না করা পর্যন্ত অনুরোধ অপেক্ষায় থাকে। নিশ্চিত বা বাতিল হলে এসএমএস পাবেন; বুকিং রেফারেন্স দিয়ে অবস্থাও দেখতে পারবেন।",
                "ব্যবসা অনুমোদন দিলেই বুকিং নিশ্চিত হয়। তার আগে স্লটটি আপনার জন্য সংরক্ষিত, তবে নিশ্চিত নয়।",
            ],
        ),
        ("h", "সীমা"),
        (
            "ul",
            [
                "প্রতিটি মোবাইল নম্বরে দিনে নির্দিষ্ট সংখ্যক স্লট বুক করা যায়, যা বুকিং পেজে দেখানো হয়।",
                "স্লট আটকে রাখা রোধে প্রতিটি নম্বরে দিনে অল্প কয়েকটি অনিশ্চিত অনুরোধ করা যায়।",
                "আটকে রাখা স্লট ব্যবহার না করলে আবার আটকাতে কিছুক্ষণ অপেক্ষা করতে হতে পারে।",
            ],
        ),
        ("h", "খেলার দিন"),
        (
            "ul",
            [
                "সময়মতো আসুন এবং চাইলে বুকিং রেফারেন্স দেখান। দেরিতে শুরু করলেও বুক করা শেষ সময়েই আপনার সময় শেষ হবে।",
                "বাকি টাকা ব্যবসার নির্দেশনা অনুযায়ী (সাধারণত মাঠে) পরিশোধ করুন।",
            ],
        ),
        ("h", "পরিবর্তন"),
        (
            "p",
            "পরিবর্তন বা বাতিলের জন্য সরাসরি ব্যবসার সাথে যোগাযোগ করুন। রিফান্ড পেমেন্ট, রিফান্ড ও বাতিলকরণ নীতি এবং ব্যবসার নিজস্ব বাতিলকরণ নীতি অনুযায়ী হবে।",
        ),
    ],
}

# ---------------------------------------------------------------------------- 7. Payment / refund / cancellation
DOCS["refund"] = {
    "title_en": "Payment, Refund & Cancellation Policy",
    "title_bn": "পেমেন্ট, রিফান্ড ও বাতিলকরণ নীতি",
    "en": [
        ("p", INTRO_EN),
        ("h", "Booking payments (customers)"),
        (
            "ul",
            [
                "Booking advances are paid directly to the business's bKash number. TurfBari never receives this money, so refunds of booking payments are made by the business.",
                "If the business rejects your request (for example the slot is no longer available), it must return the advance you sent to the number you paid from.",
                "If the business cancels a confirmed booking, you are entitled to a full refund of what you paid, or a new time if you agree.",
                "If you cancel, the business's published cancellation policy decides what is refunded. If the business has none, the advance is refundable when you cancel at least 24 hours before the start time.",
                "No refund is due if you do not come, or come late, for a confirmed booking.",
                "bKash charges are not refundable unless the business made the mistake.",
                "Wrong payments (wrong number or amount) must be reported to the business and to bKash quickly; TurfBari will help with the records it has.",
            ],
        ),
        ("h", "Payments to TurfBari (businesses)"),
        (
            "ul",
            [
                "Plan fees are paid in advance and are not refunded for unused days, except where TurfBari made an error or ends the service without cause.",
                "SMS wallet credit is prepaid and not refundable as cash. SMS that the SMS provider clearly refuses are refunded to the wallet automatically; uncertain ones can be checked and refunded by TurfBari.",
                "The bKash charge added to a recharge or plan payment covers the transfer cost and is not refunded.",
                "A payment that cannot be matched (wrong Transaction ID or amount) will be rejected; send the correct details or contact support.",
            ],
        ),
        ("h", "Disputes"),
        (
            "p",
            "Contact the business first. If it is not resolved within 7 days, contact TurfBari support with your booking reference; we can review the records and may restrict a business that does not follow this policy.",
        ),
    ],
    "bn": [
        ("p", INTRO_BN),
        ("h", "বুকিং পেমেন্ট (গ্রাহক)"),
        (
            "ul",
            [
                "বুকিংয়ের অগ্রিম সরাসরি ব্যবসার বিকাশ নম্বরে যায়। TurfBari এই টাকা গ্রহণ করে না, তাই বুকিং পেমেন্টের রিফান্ড ব্যবসাই দেবে।",
                "ব্যবসা অনুরোধ বাতিল করলে (যেমন স্লট আর খালি নেই) আপনি যে নম্বর থেকে পাঠিয়েছেন সেখানে অগ্রিম ফেরত দিতে হবে।",
                "ব্যবসা নিশ্চিত বুকিং বাতিল করলে আপনি পরিশোধিত পুরো টাকা ফেরত পাবেন, অথবা সম্মত হলে নতুন সময়।",
                "আপনি বাতিল করলে ব্যবসার প্রকাশিত বাতিলকরণ নীতি অনুযায়ী রিফান্ড হবে। ব্যবসার কোনো নীতি না থাকলে শুরুর অন্তত ২৪ ঘণ্টা আগে বাতিল করলে অগ্রিম ফেরতযোগ্য।",
                "নিশ্চিত বুকিংয়ে না এলে বা দেরিতে এলে কোনো রিফান্ড প্রাপ্য নয়।",
                "ব্যবসার ভুল না হলে বিকাশ চার্জ ফেরতযোগ্য নয়।",
                "ভুল পেমেন্ট (ভুল নম্বর বা পরিমাণ) দ্রুত ব্যবসা ও বিকাশকে জানাতে হবে; TurfBari তার কাছে থাকা রেকর্ড দিয়ে সহায়তা করবে।",
            ],
        ),
        ("h", "TurfBari-কে পেমেন্ট (ব্যবসা)"),
        (
            "ul",
            [
                "প্ল্যান ফি অগ্রিম পরিশোধ করতে হয়; অব্যবহৃত দিনের জন্য ফেরত দেওয়া হয় না, তবে TurfBari-র ভুল বা কারণ ছাড়া সেবা বন্ধ করলে ভিন্ন কথা।",
                "এসএমএস ওয়ালেট ক্রেডিট প্রিপেইড এবং নগদে ফেরতযোগ্য নয়। এসএমএস প্রোভাইডার স্পষ্টভাবে প্রত্যাখ্যান করলে টাকা স্বয়ংক্রিয়ভাবে ওয়ালেটে ফেরত যায়; অনিশ্চিতগুলো TurfBari যাচাই করে ফেরত দিতে পারে।",
                "রিচার্জ বা প্ল্যান পেমেন্টে যোগ হওয়া বিকাশ চার্জ লেনদেন খরচ, যা ফেরতযোগ্য নয়।",
                "মেলানো যায় না এমন পেমেন্ট (ভুল ট্রানজেকশন আইডি বা পরিমাণ) বাতিল হবে; সঠিক তথ্য দিন বা সাপোর্টে যোগাযোগ করুন।",
            ],
        ),
        ("h", "বিরোধ"),
        (
            "p",
            "প্রথমে ব্যবসার সাথে যোগাযোগ করুন। ৭ দিনের মধ্যে সমাধান না হলে বুকিং রেফারেন্সসহ TurfBari সাপোর্টে জানান; আমরা রেকর্ড পর্যালোচনা করতে পারি এবং নীতি না মানা ব্যবসার কার্যক্রম সীমিত করতে পারি।",
        ),
    ],
}

# ---------------------------------------------------------------------------- 8. Subscription & billing
DOCS["subscription"] = {
    "title_en": "Subscription & Billing Policy",
    "title_bn": "সাবস্ক্রিপশন ও বিলিং নীতি",
    "en": [
        ("p", INTRO_EN),
        ("h", "Plans"),
        (
            "ul",
            [
                "Businesses use TurfBari on a monthly, half-yearly or yearly plan at the prices shown on the Subscription page when you order.",
                "Plans never renew automatically. You choose a plan and pay for each period yourself.",
                "Choosing a plan creates an invoice. Pay it by the methods shown (for example bKash) and submit the payment details; a plan starts or extends only after TurfBari approves the payment.",
                "A promo code, if valid, reduces the invoice before payment; it has no cash value.",
            ],
        ),
        ("h", "When a plan ends"),
        (
            "ul",
            [
                "You get a 3-day grace period after the paid-until date. During it you can keep working; renew before it ends.",
                "After the grace period your booking page is hidden and new bookings are paused until you pay. Your data is kept.",
            ],
        ),
        ("h", "Price changes"),
        ("p", "Prices can change for future periods. Periods you already paid for keep their price."),
        ("h", "Refunds"),
        ("p", "See the Payment, Refund & Cancellation Policy."),
    ],
    "bn": [
        ("p", INTRO_BN),
        ("h", "প্ল্যান"),
        (
            "ul",
            [
                "ব্যবসাগুলো মাসিক, ষাণ্মাসিক বা বার্ষিক প্ল্যানে TurfBari ব্যবহার করে, অর্ডারের সময় সাবস্ক্রিপশন পেজে দেখানো মূল্যে।",
                "প্ল্যান কখনো স্বয়ংক্রিয়ভাবে নবায়ন হয় না। প্রতিটি মেয়াদ আপনি নিজে বেছে নিয়ে পরিশোধ করবেন।",
                "প্ল্যান বেছে নিলে একটি ইনভয়েস তৈরি হয়। দেখানো মাধ্যমে (যেমন বিকাশ) পরিশোধ করে পেমেন্টের তথ্য জমা দিন; TurfBari অনুমোদন দিলে তবেই প্ল্যান শুরু বা বাড়বে।",
                "বৈধ প্রোমো কোড পেমেন্টের আগে ইনভয়েস কমায়; এর কোনো নগদ মূল্য নেই।",
            ],
        ),
        ("h", "প্ল্যান শেষ হলে"),
        (
            "ul",
            [
                "পরিশোধিত মেয়াদের পর ৩ দিনের গ্রেস পিরিয়ড থাকে। এ সময় কাজ চালিয়ে যেতে পারবেন; শেষ হওয়ার আগে নবায়ন করুন।",
                "গ্রেস পিরিয়ডের পর পরিশোধ না করা পর্যন্ত বুকিং পেজ লুকানো থাকে এবং নতুন বুকিং বন্ধ থাকে। আপনার তথ্য সংরক্ষিত থাকে।",
            ],
        ),
        ("h", "মূল্য পরিবর্তন"),
        ("p", "ভবিষ্যৎ মেয়াদের মূল্য পরিবর্তন হতে পারে। ইতিমধ্যে পরিশোধিত মেয়াদের মূল্য একই থাকবে।"),
        ("h", "রিফান্ড"),
        ("p", "পেমেন্ট, রিফান্ড ও বাতিলকরণ নীতি দেখুন।"),
    ],
}

# ---------------------------------------------------------------------------- 9. SMS wallet
DOCS["sms"] = {
    "title_en": "SMS Wallet & Communication Policy",
    "title_bn": "এসএমএস ওয়ালেট ও যোগাযোগ নীতি",
    "en": [
        ("p", INTRO_EN),
        ("h", "Prepaid wallet"),
        (
            "ul",
            [
                "Every business has a prepaid SMS wallet. Booking SMS, single SMS and campaigns are charged from it at the price per SMS part shown in your workspace.",
                "Bengali (Unicode) messages use more parts than English ones; the cost estimate is shown before you send.",
                "If the wallet does not have enough balance, messages are blocked (not sent) until you recharge, and you can retry them.",
                "Recharge by bKash Send Money: the total includes a bKash charge shown before you pay. Credit is added after TurfBari verifies the payment.",
                "Every charge, refund and recharge is recorded in the wallet ledger and cannot be edited.",
            ],
        ),
        ("h", "What you may send"),
        (
            "ul",
            [
                "Send messages only to your own customers, about their bookings or your facility.",
                "Promotional messages must be honest, identify your business, and stop for anyone who asks.",
                "Do not send threats, misleading offers, political or adult content, or messages that break Bangladesh telecom rules.",
            ],
        ),
        ("h", "Controls"),
        (
            "p",
            "TurfBari may turn off SMS types or the SMS service for an account, set limits, or hold campaigns to prevent abuse or follow telecom rules. Delivery depends on mobile operators; TurfBari cannot guarantee that every accepted message reaches the phone.",
        ),
    ],
    "bn": [
        ("p", INTRO_BN),
        ("h", "প্রিপেইড ওয়ালেট"),
        (
            "ul",
            [
                "প্রতিটি ব্যবসার একটি প্রিপেইড এসএমএস ওয়ালেট আছে। বুকিং এসএমএস, একক এসএমএস ও ক্যাম্পেইনের খরচ ওয়ার্কস্পেসে দেখানো প্রতি পার্টের মূল্যে এখান থেকে কাটা হয়।",
                "বাংলা (ইউনিকোড) বার্তায় ইংরেজির চেয়ে বেশি পার্ট লাগে; পাঠানোর আগে খরচের হিসাব দেখানো হয়।",
                "ওয়ালেটে যথেষ্ট ব্যালেন্স না থাকলে রিচার্জ না করা পর্যন্ত বার্তা ব্লক থাকে (পাঠানো হয় না), পরে আবার পাঠানো যায়।",
                "বিকাশ সেন্ড মানির মাধ্যমে রিচার্জ করুন: মোট টাকায় পরিশোধের আগে দেখানো বিকাশ চার্জ যুক্ত থাকে। TurfBari পেমেন্ট যাচাই করলে ক্রেডিট যোগ হয়।",
                "প্রতিটি খরচ, ফেরত ও রিচার্জ ওয়ালেট লেজারে লেখা থাকে এবং পরিবর্তন করা যায় না।",
            ],
        ),
        ("h", "যা পাঠাতে পারবেন"),
        (
            "ul",
            [
                "শুধু নিজের গ্রাহকদের তাদের বুকিং বা আপনার মাঠ সম্পর্কে বার্তা পাঠান।",
                "প্রচারমূলক বার্তা সৎ হতে হবে, আপনার ব্যবসার নাম থাকতে হবে, এবং কেউ না চাইলে পাঠানো বন্ধ করতে হবে।",
                "হুমকি, বিভ্রান্তিকর অফার, রাজনৈতিক বা প্রাপ্তবয়স্ক কনটেন্ট, বা বাংলাদেশের টেলিযোগাযোগ নিয়ম ভঙ্গকারী বার্তা পাঠাবেন না।",
            ],
        ),
        ("h", "নিয়ন্ত্রণ"),
        (
            "p",
            "অপব্যবহার রোধ বা টেলিযোগাযোগ নিয়ম মানতে TurfBari কোনো অ্যাকাউন্টের এসএমএস ধরন বা সেবা বন্ধ, সীমা নির্ধারণ বা ক্যাম্পেইন স্থগিত করতে পারে। বার্তা পৌঁছানো মোবাইল অপারেটরের উপর নির্ভর করে; গৃহীত প্রতিটি বার্তা ফোনে পৌঁছানোর নিশ্চয়তা TurfBari দিতে পারে না।",
        ),
    ],
}

# ---------------------------------------------------------------------------- sector (football turfs)
DOCS["sector_terms"] = {
    "title_en": "Football Turf & Sports Facilities — Terms",
    "title_bn": "ফুটবল টার্ফ ও স্পোর্টস ফ্যাসিলিটি — শর্তাবলী",
    "en": [
        (
            "p",
            "These terms apply in addition to TurfBari's platform terms when you book or run a football turf or similar sports facility. They never replace the platform terms.",
        ),
        ("h", "Playing at your own risk"),
        (
            "p",
            "Football and other sports involve physical contact and a risk of injury. Players take part at their own risk and should be fit to play. The business should keep first-aid available and the playing surface, nets and lights in safe condition.",
        ),
        ("h", "Facility and weather"),
        (
            "ul",
            [
                "Slot length, number of players per field and included equipment are as shown on the booking page.",
                "For outdoor or rooftop turfs, the business decides whether play is safe in heavy rain, storms or power cuts. If the business stops play for these reasons, it should offer a new time or a refund for the unused time.",
            ],
        ),
        ("h", "Damage and property"),
        (
            "p",
            "The booking group is responsible for damage it causes beyond normal use. Neither the business nor TurfBari is responsible for valuables left unattended unless the business offers secure storage.",
        ),
    ],
    "bn": [
        (
            "p",
            "ফুটবল টার্ফ বা একই ধরনের খেলার মাঠ বুক বা পরিচালনা করলে TurfBari-র প্ল্যাটফর্ম শর্তাবলীর পাশাপাশি এই শর্তগুলো প্রযোজ্য। এগুলো কখনো প্ল্যাটফর্ম শর্তাবলীর পরিবর্তে নয়।",
        ),
        ("h", "নিজ দায়িত্বে খেলা"),
        (
            "p",
            "ফুটবল ও অন্যান্য খেলায় শারীরিক সংস্পর্শ ও আঘাতের ঝুঁকি থাকে। খেলোয়াড়রা নিজ দায়িত্বে অংশ নেন এবং খেলার উপযোগী শারীরিক অবস্থায় থাকবেন। ব্যবসা প্রাথমিক চিকিৎসার ব্যবস্থা রাখবে এবং মাঠ, নেট ও আলো নিরাপদ অবস্থায় রাখবে।",
        ),
        ("h", "মাঠ ও আবহাওয়া"),
        (
            "ul",
            [
                "স্লটের দৈর্ঘ্য, প্রতি মাঠে খেলোয়াড় সংখ্যা ও অন্তর্ভুক্ত সরঞ্জাম বুকিং পেজে যেমন দেখানো আছে তেমন।",
                "খোলা বা ছাদের টার্ফে প্রবল বৃষ্টি, ঝড় বা বিদ্যুৎ বিভ্রাটে খেলা নিরাপদ কিনা তা ব্যবসা ঠিক করবে। এসব কারণে খেলা বন্ধ করলে ব্যবসা নতুন সময় বা অব্যবহৃত সময়ের রিফান্ড দেবে।",
            ],
        ),
        ("h", "ক্ষতি ও জিনিসপত্র"),
        (
            "p",
            "স্বাভাবিক ব্যবহারের বাইরে কোনো ক্ষতি করলে বুকিং গ্রুপ দায়ী থাকবে। ব্যবসা নিরাপদ সংরক্ষণের ব্যবস্থা না দিলে অযত্নে রাখা মূল্যবান জিনিসের জন্য ব্যবসা বা TurfBari দায়ী নয়।",
        ),
    ],
}

DOCS["sector_rules"] = {
    "title_en": "Football Turf Rules",
    "title_bn": "ফুটবল টার্ফের নিয়মাবলী",
    "en": [
        (
            "p",
            "Rules for players at football turfs booked through TurfBari. Each turf may add its own rules, shown at the venue or on its booking page.",
        ),
        (
            "ul",
            [
                "Arrive at least 10 minutes early. Play starts and ends at the booked times.",
                "Wear turf shoes or flat rubber studs. Metal studs and bare feet are not allowed.",
                "No smoking, alcohol, drugs, gum or glass bottles on the field.",
                "Keep to the number of players allowed for the field you booked.",
                "Children under 12 must be supervised by an adult.",
                "Respect other groups: leave the field promptly when your time ends and keep noise reasonable.",
                "Report any injury or damage to the turf staff straight away.",
                "Follow staff instructions about safety, weather and lights.",
            ],
        ),
    ],
    "bn": [
        (
            "p",
            "TurfBari-র মাধ্যমে বুক করা ফুটবল টার্ফে খেলোয়াড়দের জন্য নিয়ম। প্রতিটি টার্ফ নিজস্ব নিয়ম যোগ করতে পারে, যা মাঠে বা বুকিং পেজে দেখানো থাকে।",
        ),
        (
            "ul",
            [
                "অন্তত ১০ মিনিট আগে আসুন। বুক করা সময়ে খেলা শুরু ও শেষ হবে।",
                "টার্ফ শু বা সমতল রাবার স্টাড পরুন। ধাতব স্টাড বা খালি পায়ে খেলা যাবে না।",
                "মাঠে ধূমপান, মদ, মাদক, চুইংগাম বা কাচের বোতল নিষিদ্ধ।",
                "বুক করা মাঠের জন্য অনুমোদিত খেলোয়াড় সংখ্যা মেনে চলুন।",
                "১২ বছরের কম বয়সী শিশুদের সাথে একজন প্রাপ্তবয়স্ক থাকতে হবে।",
                "অন্য গ্রুপকে সম্মান করুন: সময় শেষে দ্রুত মাঠ ছেড়ে দিন এবং শব্দ নিয়ন্ত্রণে রাখুন।",
                "কোনো আঘাত বা ক্ষতি হলে সঙ্গে সঙ্গে টার্ফের কর্মীদের জানান।",
                "নিরাপত্তা, আবহাওয়া ও আলো সংক্রান্ত কর্মীদের নির্দেশনা মেনে চলুন।",
            ],
        ),
    ],
}


def standard_text(
    category: str, sector_name_en: str | None = None, sector_name_bn: str | None = None
) -> dict | None:
    """Title + HTML bodies for a module, or None if TurfBari has no standard text for it.
    Sector documents of a sector other than football get a neutral title with the sector name."""
    if category == "terms":
        from apps.legal.terms_content import terms_text

        return terms_text()
    doc = DOCS.get(category)
    if doc is None:
        return None
    title_en, title_bn = doc["title_en"], doc["title_bn"]
    if (
        category in ("sector_terms", "sector_rules")
        and sector_name_en
        and "football" not in sector_name_en.lower()
    ):
        return None  # the football wording would be wrong for another sport
    return {
        "title_en": title_en,
        "title_bn": title_bn,
        "body_en": render(doc["en"]),
        "body_bn": render(doc["bn"]),
    }
