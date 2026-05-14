# Bible Reading v2 bilingual/email-optional repair patch

Copy these files over the same paths in `c:\dev\bible_reading_v2`.

Important cleanup after copying:

```cmd
rmdir /s /q reading\TEMPLATETAGS
```

Django only discovers lowercase `reading\templatetags`, not uppercase `TEMPLATETAGS`.

Then run:

```cmd
python manage.py check
python manage.py test accounts.tests -v 2
python manage.py test reading.tests.ImportReadingPlanCommandTests -v 2
python manage.py test reading.tests.BibleReadingFlowTests.test_home_dashboard_shows_start_reading_button -v 2
python manage.py runserver
```

Manual check:

- Signup should not require email.
- Language switch should toggle 中文 / English.
- Today page should show passage buttons in current language.
- Scripture reader should default to current language tab.
- Reflection form should appear at the last reading passage.
