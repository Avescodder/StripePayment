from django.contrib import admin
from django.urls import path
from payments import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    path('', views.home_view, name='home'),
    
    path('item/<int:item_id>/', views.item_view, name='item'),
    path('buy/<int:item_id>/', views.buy_item, name='buy_item'),
    
    path('order/<int:order_id>/', views.order_view, name='order'),
    path('buy/order/<int:order_id>/', views.buy_order, name='buy_order'),
    
    path('success/', views.success_view, name='success'),
    
    path('webhook/stripe/', views.stripe_webhook, name='stripe_webhook'),
]