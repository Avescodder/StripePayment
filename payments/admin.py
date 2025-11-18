from django.contrib import admin
from .models import Item, Order, OrderItem, Discount, Tax


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'price', 'currency', 'created_at']
    list_filter = ['currency', 'created_at']
    search_fields = ['name', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'description', 'image_url')
        }),
        ('Цена', {
            'fields': ('price', 'currency')
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = ['item', 'quantity']
    autocomplete_fields = ['item']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'total_amount', 'currency', 'discount', 'tax', 'created_at']
    list_filter = ['status', 'currency', 'created_at']
    search_fields = ['id', 'stripe_session_id']
    readonly_fields = ['total_amount', 'stripe_session_id', 'created_at', 'updated_at']
    inlines = [OrderItemInline]
    
    fieldsets = (
        ('Статус', {
            'fields': ('status',)
        }),
        ('Скидки и налоги', {
            'fields': ('discount', 'tax')
        }),
        ('Финансы', {
            'fields': ('total_amount', 'currency')
        }),
        ('Stripe', {
            'fields': ('stripe_session_id',),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.total_amount = obj.calculate_total()
        obj.save()


@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ['name', 'discount_type', 'value', 'active', 'stripe_coupon_id']
    list_filter = ['discount_type', 'active', 'created_at']
    search_fields = ['name', 'stripe_coupon_id']
    readonly_fields = ['stripe_coupon_id', 'created_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'discount_type', 'value', 'active')
        }),
        ('Stripe', {
            'fields': ('stripe_coupon_id',),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


@admin.register(Tax)
class TaxAdmin(admin.ModelAdmin):
    list_display = ['name', 'percentage', 'inclusive', 'active', 'stripe_tax_rate_id']
    list_filter = ['inclusive', 'active', 'created_at']
    search_fields = ['name', 'stripe_tax_rate_id']
    readonly_fields = ['stripe_tax_rate_id', 'created_at']
    
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'percentage', 'inclusive', 'active')
        }),
        ('Stripe', {
            'fields': ('stripe_tax_rate_id',),
            'classes': ('collapse',)
        }),
        ('Метаданные', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )