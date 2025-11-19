import stripe
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.cache import cache
from django.db import transaction
from .models import Item, Order
import logging

logger = logging.getLogger(__name__)


def get_stripe_keys(currency):
    if currency == 'eur':
        return {
            'publishable_key': settings.STRIPE_PUBLISHABLE_KEY_EUR,
            'secret_key': settings.STRIPE_SECRET_KEY_EUR,
        }
    return {
        'publishable_key': settings.STRIPE_PUBLISHABLE_KEY_USD,
        'secret_key': settings.STRIPE_SECRET_KEY_USD,
    }


@require_http_methods(["GET"])
def item_view(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    stripe_keys = get_stripe_keys(item.currency)
    
    context = {
        'item': item,
        'stripe_publishable_key': stripe_keys['publishable_key'],
    }
    return render(request, 'payments/item.html', context)


@require_http_methods(["GET"])
def buy_item(request, item_id):
    item = get_object_or_404(Item, id=item_id)
    stripe_keys = get_stripe_keys(item.currency)
    stripe.api_key = stripe_keys['secret_key']
    
    logger.info(f"Создание checkout session для товара {item_id} ({item.name})")
    
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': item.currency,
                    'product_data': {
                        'name': item.name,
                        'description': item.description,
                    },
                    'unit_amount': int(item.price * 100),
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.build_absolute_uri('/success/') + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.build_absolute_uri(f'/item/{item_id}/'),
            metadata={
                'item_id': item_id,
            }
        )
        
        logger.info(f"Checkout session создан: {checkout_session.id} для товара {item_id}")
        return JsonResponse({'id': checkout_session.id})
    
    except stripe.error.CardError as e:
        logger.error(f"Card error для товара {item_id}: {e}")
        return JsonResponse({'error': 'Ошибка карты. Попробуйте другую карту.'}, status=400)
    
    except stripe.error.RateLimitError as e:
        logger.error(f"Rate limit для товара {item_id}: {e}")
        return JsonResponse({'error': 'Слишком много запросов. Попробуйте позже.'}, status=429)
    
    except stripe.error.InvalidRequestError as e:
        logger.error(f"Invalid request для товара {item_id}: {e}")
        return JsonResponse({'error': 'Ошибка конфигурации платежа. Свяжитесь с поддержкой.'}, status=400)
    
    except stripe.error.AuthenticationError as e:
        logger.critical(f"Stripe authentication failed для товара {item_id}: {e}")
        return JsonResponse({'error': 'Ошибка системы. Свяжитесь с поддержкой.'}, status=500)
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error для товара {item_id}: {e}")
        return JsonResponse({'error': 'Ошибка платежной системы. Попробуйте позже.'}, status=500)
    
    except Exception as e:
        logger.exception(f"Unexpected error в buy_item для товара {item_id}: {e}")
        return JsonResponse({'error': 'Произошла ошибка. Попробуйте позже.'}, status=500)


@require_http_methods(["GET"])
def order_view(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related('discount', 'tax'),
        id=order_id
    )
    order_items = order.orderitem_set.select_related('item').all()
    
    if order_items:
        currency = order_items[0].item.currency
        if order.currency != currency:
            order.currency = currency
            order.save(update_fields=['currency'])
    
    stripe_keys = get_stripe_keys(order.currency)
    
    context = {
        'order': order,
        'order_items': order_items,
        'stripe_publishable_key': stripe_keys['publishable_key'],
    }
    return render(request, 'payments/order.html', context)


@require_http_methods(["GET"])
@transaction.atomic
def buy_order(request, order_id):
    order = get_object_or_404(
        Order.objects.select_related('discount', 'tax').select_for_update(),
        id=order_id
    )
    order_items = order.orderitem_set.select_related('item').all()
    
    if not order_items:
        logger.warning(f"Попытка оплаты пустого заказа {order_id}")
        return JsonResponse({'error': 'Заказ пуст'}, status=400)
    
    currencies = set(item.item.currency for item in order_items)
    if len(currencies) > 1:
        logger.error(f"Заказ {order_id} содержит товары в разных валютах: {currencies}")
        return JsonResponse({
            'error': 'В заказе товары с разными валютами. Разделите заказ на несколько.'
        }, status=400)
    
    currency = currencies.pop()
    stripe_keys = get_stripe_keys(currency)
    stripe.api_key = stripe_keys['secret_key']
    
    logger.info(f"Создание checkout session для заказа {order_id}")
    
    try:
        line_items = []
        for order_item in order_items:
            line_items.append({
                'price_data': {
                    'currency': currency,
                    'product_data': {
                        'name': order_item.item.name,
                        'description': order_item.item.description,
                    },
                    'unit_amount': int(order_item.item.price * 100),
                },
                'quantity': order_item.quantity,
            })
        
        session_params = {
            'payment_method_types': ['card'],
            'line_items': line_items,
            'mode': 'payment',
            'success_url': request.build_absolute_uri('/success/') + '?session_id={CHECKOUT_SESSION_ID}',
            'cancel_url': request.build_absolute_uri(f'/order/{order_id}/'),
            'metadata': {
                'order_id': order_id,
            }
        }
        
        if order.discount and order.discount.active:
            if not order.discount.stripe_coupon_id:
                logger.info(f"Создание Stripe купона для скидки {order.discount.id}")
                try:
                    if order.discount.discount_type == 'percentage':
                        coupon = stripe.Coupon.create(
                            percent_off=float(order.discount.value),
                            duration='once',
                            name=order.discount.name,
                        )
                    else:
                        coupon = stripe.Coupon.create(
                            amount_off=int(order.discount.value * 100),
                            currency=currency,
                            duration='once',
                            name=order.discount.name,
                        )
                    order.discount.stripe_coupon_id = coupon.id
                    order.discount.save(update_fields=['stripe_coupon_id'])
                    logger.info(f"Stripe купон создан: {coupon.id}")
                except stripe.error.StripeError as e:
                    logger.error(f"Ошибка создания купона: {e}")
            
            if order.discount.stripe_coupon_id:
                session_params['discounts'] = [{
                    'coupon': order.discount.stripe_coupon_id
                }]

        
        checkout_session = stripe.checkout.Session.create(**session_params)
        
        order.stripe_session_id = checkout_session.id
        order.save(update_fields=['stripe_session_id'])
        
        logger.info(f"Checkout session создан: {checkout_session.id} для заказа {order_id}")
        return JsonResponse({'id': checkout_session.id})
    
    except stripe.error.CardError as e:
        logger.error(f"Card error для заказа {order_id}: {e}")
        return JsonResponse({'error': 'Ошибка карты. Попробуйте другую карту.'}, status=400)
    
    except stripe.error.RateLimitError as e:
        logger.error(f"Rate limit для заказа {order_id}: {e}")
        return JsonResponse({'error': 'Слишком много запросов. Попробуйте позже.'}, status=429)
    
    except stripe.error.InvalidRequestError as e:
        logger.error(f"Invalid request для заказа {order_id}: {e}")
        return JsonResponse({'error': 'Ошибка конфигурации платежа. Свяжитесь с поддержкой.'}, status=400)
    
    except stripe.error.AuthenticationError as e:
        logger.critical(f"Stripe authentication failed для заказа {order_id}: {e}")
        return JsonResponse({'error': 'Ошибка системы. Свяжитесь с поддержкой.'}, status=500)
    
    except stripe.error.StripeError as e:
        logger.error(f"Stripe error для заказа {order_id}: {e}")
        return JsonResponse({'error': 'Ошибка платежной системы. Попробуйте позже.'}, status=500)
    
    except Exception as e:
        logger.exception(f"Unexpected error в buy_order для заказа {order_id}: {e}")
        return JsonResponse({'error': 'Произошла ошибка. Попробуйте позже.'}, status=500)


@require_http_methods(["GET"])
def success_view(request):
    session_id = request.GET.get('session_id')
    logger.info(f"Пользователь перенаправлен на success page, session_id: {session_id}")
    return render(request, 'payments/success.html', {'session_id': session_id})


@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
    if not client_ip:
        client_ip = request.META.get('REMOTE_ADDR', 'unknown')
    
    logger.info(f"Webhook получен от IP: {client_ip}")
    
    if not sig_header:
        logger.warning(f"Webhook без signature от IP: {client_ip}")
        return JsonResponse({'error': 'No signature header'}, status=400)
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        logger.info(f"Webhook event: {event['type']}, id: {event['id']}")
    
    except ValueError as e:
        logger.error(f"Invalid webhook payload: {e}")
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid webhook signature: {e}")
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        session_id = session.get('id')
        
        logger.info(f"Обработка checkout.session.completed для session: {session_id}")
        
        try:
            with transaction.atomic():
                order = Order.objects.select_for_update().get(stripe_session_id=session_id)
                
                if order.status == 'paid':
                    logger.info(f"Заказ {order.id} уже оплачен, пропускаем")
                    return JsonResponse({'status': 'already_paid'})
                
                order.status = 'paid'
                order.save(update_fields=['status', 'updated_at'])
                
                logger.info(f"Заказ {order.id} успешно помечен как оплаченный")
        
        except Order.DoesNotExist:
            logger.warning(f"Заказ с session_id {session_id} не найден в БД")
        
        except Exception as e:
            logger.exception(f"Ошибка обработки webhook для session {session_id}: {e}")
            return JsonResponse({'error': 'Processing error'}, status=500)
    
    elif event['type'] == 'payment_intent.succeeded':
        logger.info(f"Payment intent succeeded: {event['data']['object']['id']}")
    
    elif event['type'] == 'payment_intent.payment_failed':
        logger.warning(f"Payment intent failed: {event['data']['object']['id']}")
    
    return JsonResponse({'status': 'success'})


def home_view(request):
    items = Item.objects.all()
    orders = Order.objects.select_related('discount', 'tax').prefetch_related(
        'orderitem_set__item'
    ).all()[:10]
    
    context = {
        'items': items,
        'orders': orders,
    }
    return render(request, 'payments/home.html', context)


@require_http_methods(["GET"])
def health_check(request):
    try:
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        
        cache_key = 'stripe_health_check'
        stripe_ok = cache.get(cache_key)
        
        if stripe_ok is None:
            try:
                stripe.api_key = settings.STRIPE_SECRET_KEY_USD
                stripe.Account.retrieve()
                stripe_ok = True
                cache.set(cache_key, True, timeout=60)  
            except Exception as e:
                logger.error(f"Stripe health check failed: {e}")
                stripe_ok = False
        
        if not stripe_ok:
            return JsonResponse({
                'status': 'degraded',
                'database': 'ok',
                'stripe': 'error'
            }, status=503)
        
        return JsonResponse({
            'status': 'healthy',
            'database': 'ok',
            'stripe': 'ok'
        })
    
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JsonResponse({
            'status': 'unhealthy',
            'error': str(e) if settings.DEBUG else 'Service unavailable'
        }, status=503)