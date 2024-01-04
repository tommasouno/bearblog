# Generated by Django 3.1.14 on 2024-01-04 08:37

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0096_blog_auth_token'),
    ]

    operations = [
        migrations.CreateModel(
            name='RssSubscriber',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('access_date', models.DateTimeField(auto_now_add=True)),
                ('hash_id', models.CharField(max_length=200)),
                ('blog', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='blogs.blog')),
            ],
        ),
    ]
