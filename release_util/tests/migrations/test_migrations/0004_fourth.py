from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("release_util", "0003_third"),
    ]

    operations = [
        migrations.AlterField(
            model_name="author",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="book",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
        migrations.AlterField(
            model_name="bookstore",
            name="id",
            field=models.AutoField(primary_key=True, serialize=False),
        ),
    ]
