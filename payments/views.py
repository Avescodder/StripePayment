import stripe
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .models import Item, Order, OrderItem
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
        )
        
        return JsonResponse({'id': checkout_session.id})
    
    except Exception as e:
        logger.error(f"Ошибка создания Stripe Session: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def order_view(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order_items = order.orderitem_set.select_related('item').all()
    
    if order_items:
        order.currency = order_items[0].item.currency
        order.save()
    
    stripe_keys = get_stripe_keys(order.currency)
    
    context = {
        'order': order,
        'order_items': order_items,
        'stripe_publishable_key': stripe_keys['publishable_key'],
    }
    return render(request, 'payments/order.html', context)


@require_http_methods(["GET"])
def buy_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order_items = order.orderitem_set.select_related('item').all()
    
    if not order_items:
        return JsonResponse({'error': 'Заказ пуст'}, status=400)
    
    currency = order_items[0].item.currency
    stripe_keys = get_stripe_keys(currency)
    stripe.api_key = stripe_keys['secret_key']
    
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
        }
        
        if order.discount and order.discount.active:
            if order.discount.stripe_coupon_id:
                session_params['discounts'] = [{
                    'coupon': order.discount.stripe_coupon_id
                }]
            else:
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
                order.discount.save()
                session_params['discounts'] = [{'coupon': coupon.id}]
        
        checkout_session = stripe.checkout.Session.create(**session_params)
        
        order.stripe_session_id = checkout_session.id
        order.save()
        
        return JsonResponse({'id': checkout_session.id})
    
    except Exception as e:
        logger.error(f"Ошибка создания Stripe Session для заказа: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)


@require_http_methods(["GET"])
def success_view(request):
    session_id = request.GET.get('session_id')
    return render(request, 'payments/success.html', {'session_id': session_id})


@csrf_exempt
@require_http_methods(["POST"])
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError:
        return JsonResponse({'error': 'Invalid signature'}, status=400)
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
    
        try:
            order = Order.objects.get(stripe_session_id=session['id'])
            order.status = 'paid'
            order.save()
            logger.info(f"Заказ {order.id} оплачен")
        except Order.DoesNotExist:
            logger.warning(f"Заказ с session_id {session['id']} не найден")
    
    return JsonResponse({'status': 'success'})


def home_view(request):
    items = Item.objects.all()
    orders = Order.objects.all()[:10] 
    
    context = {
        'items': items,
        'orders': orders,
    }
    return render(request, 'payments/home.html', context)