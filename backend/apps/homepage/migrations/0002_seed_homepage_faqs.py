from django.db import migrations


FAQS = [
    ("What is TURFBARI?", "TURFBARI is a turf management platform that helps turf owners manage online bookings, time slots, pricing, customer information, payment verification, and daily operations from one dashboard."),
    ("How can I register my turf?", "Choose a suitable subscription plan, complete the registration form, and submit your bKash payment details. After an administrator verifies the payment, the account can be activated."),
    ("How do customers book my turf?", "After your account is active and online booking is configured, you receive a dedicated public booking page. Share its link or QR code so customers can view slots and submit booking requests."),
    ("Do customers need to create an account?", "No. Customers can visit a turf's public booking page and submit a booking request without creating a TURFBARI account."),
    ("How does bKash payment verification work?", "Customers send the required advance to the bKash number configured by the turf owner and submit their sender number, amount, and transaction ID. The owner or an authorized manager reviews the payment before confirming the booking."),
    ("How much does SMS cost?", "SMS is charged per billable segment. The current rate and an estimate are shown in TURFBARI before a message is sent; long or Bengali messages may use multiple segments."),
    ("Do I need to recharge my SMS wallet?", "Yes. TURFBARI uses a prepaid SMS wallet. Recharge the wallet before using paid SMS services; messages are blocked if there is not enough balance."),
    ("What happens if my SMS wallet has insufficient balance?", "The SMS is not sent and TURFBARI explains that the wallet needs a recharge. Booking operations continue normally."),
    ("Will TURFBARI teach me how to use the platform?", "After account activation, you can coordinate onboarding guidance with TURFBARI support staff, including help with bookings, slots, pricing, payment review, QR codes, and SMS."),
    ("Is customer support available 24/7?", "Support channels are listed in the Contact Us section. Availability and response times can vary."),
    ("Can I change my subscription plan?", "You can submit a renewal or plan-change request. The request requires payment submission and administrator approval. Plans do not renew or switch automatically."),
    ("How can I contact TURFBARI?", "Use the current phone number, support email, and Facebook page shown in the Contact Us section."),
]


def seed_faqs(apps, schema_editor):
    FAQ = apps.get_model("homepage", "HomepageFAQ")
    if FAQ.objects.exists():
        return
    FAQ.objects.bulk_create([
        FAQ(question_en=question, answer_en=answer, display_order=index, is_published=True)
        for index, (question, answer) in enumerate(FAQS, start=1)
    ])


class Migration(migrations.Migration):
    dependencies = [("homepage", "0001_initial")]
    operations = [migrations.RunPython(seed_faqs, migrations.RunPython.noop)]
