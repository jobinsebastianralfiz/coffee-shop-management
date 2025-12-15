web: python manage.py migrate && python manage.py collectstatic --noinput && python manage.py setup_demo && gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
