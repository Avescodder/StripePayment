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
        verbose_name='Валюта',
        db_index=True 
    )
    image_url = models.URLField(blank=True, null=True, verbose_name='URL изображения')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Товар'
        verbose_name_plural = 'Товары'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'currency']),
        ]

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
        verbose_name='Stripe Coupon ID',
        unique=True  
    )
    active = models.BooleanField(default=True, verbose_name='Активна', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Скидка'
        verbose_name_plural = 'Скидки'
        indexes = [
            models.Index(fields=['active', '-created_at']),
        ]

    def __str__(self):
        if self.discount_type == 'percentage':
            return f"{self.name} - {self.value}%"
        return f"{self.name} - {self.value}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        if self.discount_type == 'percentage' and self.value > 100:
            raise ValidationError('Процент скидки не может быть больше 100%')
        
        if self.discount_type == 'percentage' and self.value < 0:
            raise ValidationError('Процент скидки не может быть отрицательным')
        
        if self.discount_type == 'fixed' and self.value < 0:
            raise ValidationError('Фиксированная скидка не может быть отрицательной')


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
        verbose_name='Stripe Tax Rate ID',
        unique=True
    )
    inclusive = models.BooleanField(default=False, verbose_name='Включён в цену')
    active = models.BooleanField(default=True, verbose_name='Активен', db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Налог'
        verbose_name_plural = 'Налоги'
        indexes = [
            models.Index(fields=['active', '-created_at']),
        ]

    def __str__(self):
        return f"{self.name} - {self.percentage}%"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        if self.percentage < 0:
            raise ValidationError('Процент налога не может быть отрицательным')
        
        if self.percentage > 100:
            raise ValidationError('Процент налога не может быть больше 100%')


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
        verbose_name='Статус',
        db_index=True  
    )
    stripe_session_id = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name='Stripe Session ID',
        unique=True,  
        db_index=True  
    )
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Общая сумма',
        db_index=True 
    )
    currency = models.CharField(
        max_length=3,
        default='usd',
        verbose_name='Валюта',
        db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-created_at', 'status']),
            models.Index(fields=['status', '-total_amount']),
            models.Index(fields=['stripe_session_id']),
        ]

    def __str__(self):
        return f"Заказ #{self.id} - {self.total_amount} {self.currency.upper()}"

    def calculate_total(self):
        total = sum(
            order_item.item.price * order_item.quantity 
            for order_item in self.orderitem_set.select_related('item').all()
        )
        
        if self.discount and self.discount.active:
            if self.discount.discount_type == 'percentage':
                discount_amount = total * (self.discount.value / 100)
                total = total - discount_amount
            else:  
                total = max(total - self.discount.value, Decimal('0'))

        if self.tax and self.tax.active and not self.tax.inclusive:
            tax_amount = total * (self.tax.percentage / 100)
            total = total + tax_amount
        
        return total.quantize(Decimal('0.01'))  

    def save(self, *args, **kwargs):
        if self.pk:
            self.total_amount = self.calculate_total()
        super().save(*args, **kwargs)
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        if self.discount and not self.discount.active:
            raise ValidationError('Нельзя использовать неактивную скидку')
        
        if self.tax and not self.tax.active:
            raise ValidationError('Нельзя использовать неактивный налог')


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
        indexes = [
            models.Index(fields=['order', 'item']),
        ]

    def __str__(self):
        return f"{self.item.name} x{self.quantity}"
    
    def get_subtotal(self):
        return (self.item.price * self.quantity).quantize(Decimal('0.01'))
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.order_id:
            self.order.save()  