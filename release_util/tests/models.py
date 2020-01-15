from django.db import models


class Author(models.Model):
    class Meta:
        app_label = 'release_util'
        unique_together = ('name', 'slug')

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)
    birthplace = models.CharField(max_length=255)
    slug = models.SlugField(null=True)
    rating = models.IntegerField(default=0)


class Book(models.Model):
    class Meta:
        app_label = 'release_util'

    id = models.AutoField(primary_key=True)
    author = models.ForeignKey(Author, on_delete=models.SET_NULL, null=True)
    isbn = models.CharField(max_length=255)


class Bookstore(models.Model):
    class Meta:
        app_label = 'release_util'

    id = models.AutoField(primary_key=True)
    address = models.CharField(max_length=255)


class Foo(models.Model):
    class Meta:
        app_label = 'test_app'

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=255)


class HistoricalFoo(models.Model):
    class Meta:
        app_label = 'test_app'

    id = models.IntegerField()
    name = models.CharField(max_length=255)
    history_id = models.AutoField(primary_key=True, serialize=False)
    # Sqlite returns None for DateTimeField causing test failure, so use CharsField instead.
    history_date = models.CharField(max_length=10)
    history_type = models.CharField(max_length=1)
    history_change_reason = models.CharField(max_length=100, null=True)
    history_user_id = models.IntegerField(null=True)
