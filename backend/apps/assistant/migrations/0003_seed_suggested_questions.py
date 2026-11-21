from django.db import migrations


def seed_questions(apps, schema_editor):
    Question = apps.get_model("assistant", "SuggestedQuestion")
    questions = ["What is TURFBARI?","How do I register my turf?","How do customers book a slot?","How does SMS Wallet pricing work?","How can I try the demo?"]
    bengali = [[2463, 2494, 2480, 2509, 2475, 2476, 2494, 2465, 2492, 2495, 32, 2453, 2496, 63], [2453, 2496, 2477, 2494, 2476, 2503, 32, 2438, 2478, 2494, 2480, 32, 2463, 2494, 2480, 2509, 2475, 32, 2472, 2495, 2476, 2472, 2509, 2471, 2472, 32, 2453, 2480, 2476, 63], [2455, 2509, 2480, 2494, 2489, 2453, 2480, 2494, 32, 2453, 2496, 2477, 2494, 2476, 2503, 32, 2488, 2509, 2482, 2463, 32, 2476, 2497, 2453, 32, 2453, 2480, 2476, 2503, 2472, 63], [83, 77, 83, 32, 87, 97, 108, 108, 101, 116, 32, 2447, 2476, 2434, 32, 83, 77, 83, 45, 2447, 2480, 32, 2454, 2480, 2458, 32, 2453, 2496, 2477, 2494, 2476, 2503, 32, 2453, 2494, 2460, 32, 2453, 2480, 2503, 63], [2465, 2503, 2478, 2507, 32, 2453, 2496, 2477, 2494, 2476, 2503, 32, 2476, 2509, 2479, 2476, 2489, 2494, 2480, 32, 2453, 2480, 2476, 63]]
    for index, (english, points) in enumerate(zip(questions, bengali, strict=True)):
        localized = "".join(chr(point) for point in points)
        Question.objects.get_or_create(
            question_en=english,
            defaults={"question_bn": localized, "display_order": index + 1, "is_active": True},
        )


class Migration(migrations.Migration):
    dependencies = [("assistant", "0002_assistantusageday_assistantsettings_retention_days")]
    operations = [migrations.RunPython(seed_questions, migrations.RunPython.noop)]

