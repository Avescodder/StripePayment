from django.db import models
from django.core.validators import MinValueValidator
from decimal import Decimal

class Item(models.Model):
    CURRENCY_CHOICES = [
        ('usd', 'USD'),
        ('eur', 'EUR'),
    ]
    
    name = models.CharField(max_length=200, verbose_name='Название')
    description = models.TextField(verbose_name='Описание')
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Цена'
    )
    currency = models.CharField(
        max_length=3,
        choices=CURRENCY_CHOICES,
        default='usd',
        verbose_name='Валюта'
    )
    image_url = models.URLField(blank=True, null=True, verbose_name='URL изображения')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.price} {self.currency.upper()}"

    def get_display_price(self):
        return f"{self.price:.2f}"


class Discount(models.Model):
    DISCOUNT_TYPE_CHOICES = [
        ('percentage', 'Процент'),
        ('fixed', 'Фиксированная сумма'),
    ]
    
    name = models.CharField(max_length=200, verbose_name='Название')
    discount_type = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default='percentage',
        verbose_name='Тип скидки'
    )
    value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Значение'
    )
    stripe_coupon_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name='Stripe Coupon ID'
    )
    active = models.BooleanField(default=True, verbose_name='Активна')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Скидка'
        verbose_name_plural = 'Скидки'

    def __str__(self):
        if self.discount_type == 'percentage':
            return f"{self.name} - {self.value}%"
        return f"{self.name} - {self.value}"


class Tax(models.Model):
    name = models.CharField(max_length=200, verbose_name='Название')
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Процент'
    )
    stripe_tax_rate_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name='Stripe Tax Rate ID'
    )
    inclusive = models.BooleanField(default=False, verbose_name='Включён в цену')
    active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Налог'
        verbose_name_plural = 'Налоги'

    def __str__(self):
        return f"{self.name} - {self.percentage}%"


class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Ожидает оплаты'),
        ('paid', 'Оплачен'),
        ('cancelled', 'Отменён'),
    ]
    
    items = models.ManyToManyField(Item, through='OrderItem', verbose_name='Товары')
    discount = models.ForeignKey(
        Discount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Скидка'
    )
    tax = models.ForeignKey(
        Tax,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name='Налог'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name='Статус'
    )
    stripe_session_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name='Stripe Session ID'
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Общая сумма'
    )
    currency = models.CharField(max_length=3, default='usd', verbose_name='Валюта')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']

    def __str__(self):
        return f"Заказ #{self.id} - {self.total_amount} {self.currency.upper()}"

    def calculate_total(self):
        total = sum(
            order_item.item.price * order_item.quantity 
            for order_item in self.orderitem_set.all()
        )
        
        if self.discount and self.discount.active:
            if self.discount.discount_type == 'percentage':
                total = total * (1 - self.discount.value / 100)
            else:
                total = max(total - self.discount.value, Decimal('0'))
        
        if self.tax and self.tax.active and not self.tax.inclusive:
            total = total * (1 + self.tax.percentage / 100)
        
        return total

    def save(self, *args, **kwargs):
        if self.pk:
            self.total_amount = self.calculate_total()
        super().save(*args, **kwargs)


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        verbose_name='Количество'
    )

    class Meta:
        verbose_name = 'Товар в заказе'
        verbose_name_plural = 'Товары в заказе'
        unique_together = ['order', 'item']

    def __str__(self):
        return f"{self.item.name} x{self.quantity}"