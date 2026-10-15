"""Guest pay-at-table links and the Razorpay webhook."""

from django.urls import path

from apps.payments import views

app_name = "payments"

urlpatterns = [
    path("pay/<uuid:order_uuid>/", views.pay_page, name="pay"),
    path("pay/<uuid:order_uuid>/qr.png", views.pay_qr, name="pay_qr"),
    path("pay/<uuid:order_uuid>/receipt/", views.pay_receipt, name="pay_receipt"),
    path("pay/<uuid:order_uuid>/start/", views.pay_start, name="pay_start"),
    path("pay/<uuid:order_uuid>/verify/", views.pay_verify, name="pay_verify"),
    path("pay/<uuid:order_uuid>/status/", views.pay_status, name="pay_status"),
    path("pay/s/<uuid:sale_uuid>/", views.pay_sale_page, name="pay_sale"),
    path("pay/s/<uuid:sale_uuid>/qr.svg", views.pay_sale_qr, name="pay_sale_qr"),
    path("pay/s/<uuid:sale_uuid>/start/", views.pay_sale_start, name="pay_sale_start"),
    path("pay/s/<uuid:sale_uuid>/verify/", views.pay_sale_verify, name="pay_sale_verify"),
    path("pay/s/<uuid:sale_uuid>/status/", views.pay_sale_status, name="pay_sale_status"),
    path("payments/razorpay/webhook/", views.razorpay_webhook, name="razorpay_webhook"),
]
